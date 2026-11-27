"""Standard-library web server for the local chat UI.

Threat model: a single local user. The server binds to loopback only. Because any website
open in the same browser can still send requests to ``127.0.0.1``, every request must carry
an expected ``Host`` header (DNS-rebinding defence), state-changing requests must be JSON
(no CORS preflight is ever answered, so cross-site pages cannot send them) and a present
``Origin`` must be our own. Responses forbid framing and external resources.
"""

import base64
import binascii
import json
import threading
from collections.abc import Callable, Generator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any, Protocol
from urllib.parse import urlsplit

from oakgpt.chat.documents import Hit, ground, public_sources
from oakgpt.chat.engine import ChatSettings, settings_from
from oakgpt.chat.store import ConversationStore, ImageStore, now
from oakgpt.chat.template import Message

MAX_BODY_BYTES = 256 * 1024
MAX_UPLOAD_BODY_BYTES = 8 * 1024 * 1024  # A JSON-encoded text document (see DocumentLibrary).
MAX_REPLY_BODY_BYTES = 48 * 1024 * 1024  # Room for MAX_IMAGES base64-encoded images.
MAX_IMAGES = 4
MAX_MESSAGE_CHARS = 32_000
MAX_SYSTEM_CHARS = 8_000
# Explicit overrides a vision reply keeps from the request; the rest comes from its preset.
VISION_OVERRIDES = ("temperature", "max_new_tokens", "seed")
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8"),
    "/static/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

Responder = Callable[[list[Message], ChatSettings], Generator[dict[str, Any], None, None]]


class Library(Protocol):
    """The document library seen by the web server (``app.DocumentLibrary``)."""

    def search(self, query: str) -> list[Hit]: ...
    def status(self) -> dict[str, Any]: ...
    def add(self, name: str, text: str) -> str: ...
    def reindex_async(self) -> bool: ...


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


class ChatApp:
    """Request-independent state shared by handler threads."""

    def __init__(
        self,
        store: ConversationStore,
        respond: Responder,
        status: Callable[[], dict[str, Any]],
        defaults: ChatSettings,
        system_prompt: str = "",
        vision: bool = False,
        documents: Library | None = None,
    ) -> None:
        self.store = store
        self.respond = respond
        self.status = status
        self.defaults = defaults
        self.system_prompt = system_prompt
        self.vision = vision  # Whether a vision model is configured.
        self.documents = documents
        # llama.cpp runs one slot; overlapping generations would queue invisibly.
        self.generation = threading.Lock()


def uses_vision(conversation: dict[str, Any]) -> bool:
    return any(item.get("images") for item in conversation["messages"])


def conversation_messages(conversation: dict[str, Any], images: ImageStore) -> list[Message]:
    messages = []
    if conversation["system_prompt"].strip():
        messages.append(Message("system", conversation["system_prompt"]))
    for item in conversation["messages"]:
        data = tuple(
            images.load(conversation["id"], image["id"])[0] for image in item.get("images", [])
        )
        messages.append(Message(item["role"], item["content"], data))
    return messages


def decode_images(value: Any) -> list[bytes]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_IMAGES:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"images must be a list of at most {MAX_IMAGES}")
    decoded = []
    for item in value:
        if not isinstance(item, str):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Each image must be a base64 string")
        try:
            decoded.append(base64.b64decode(item, validate=True))
        except binascii.Error:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid base64 image data") from None
    return decoded


class Handler(BaseHTTPRequestHandler):
    server_version = "OakGPT-chat"
    sys_version = ""
    app: ChatApp
    allowed_hosts: frozenset[str]

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Request lines can contain conversation IDs; keep the console quiet.

    # ----- transport helpers -------------------------------------------------------------

    def _headers(self, status: HTTPStatus, content_type: str, length: int | None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self._headers(status, content_type, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: HTTPStatus, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False).encode()
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"error": message})

    def _check_request(self, state_changing: bool) -> None:
        host = self.headers.get("Host", "")
        if host not in self.allowed_hosts:
            raise ApiError(HTTPStatus.MISDIRECTED_REQUEST, "Unexpected Host header")
        origin = self.headers.get("Origin")
        if origin is not None:
            parsed = urlsplit(origin)
            if parsed.scheme != "http" or parsed.netloc not in self.allowed_hosts:
                raise ApiError(HTTPStatus.FORBIDDEN, "Cross-origin request refused")
        if state_changing:
            if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                raise ApiError(HTTPStatus.FORBIDDEN, "Cross-site request refused")
            content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
            if content_type != "application/json":
                raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Expected application/json")

    def _body(self, limit: int = MAX_BODY_BYTES) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid Content-Length") from None
        if length < 0 or length > limit:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Body must be JSON") from None
        if not isinstance(value, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Body must be a JSON object")
        return value

    def _dispatch(self, state_changing: bool, route: Callable[[list[str]], None]) -> None:
        try:
            self._check_request(state_changing)
            parts = [part for part in urlsplit(self.path).path.split("/") if part]
            route(parts)
        except ApiError as error:
            self._error(error.status, str(error))
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "Not found")

    # ----- routes ------------------------------------------------------------------------

    def do_GET(self) -> None:
        self._dispatch(False, self._get)

    def do_HEAD(self) -> None:
        self._dispatch(False, self._get)

    def do_POST(self) -> None:
        self._dispatch(True, self._post)

    def do_DELETE(self) -> None:
        self._dispatch(True, self._delete)

    def do_OPTIONS(self) -> None:
        # Deliberately no CORS: a refused preflight blocks cross-site JSON/DELETE requests.
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "CORS is not supported")

    def _get(self, parts: list[str]) -> None:
        path = urlsplit(self.path).path
        if path in STATIC:
            name, content_type = STATIC[path]
            body = files("oakgpt.chat").joinpath("static", name).read_bytes()
            self._send(HTTPStatus.OK, body, content_type)
        elif parts == ["api", "status"]:
            try:
                status = self.app.status()
            except OSError as error:
                status = {"ready": False, "error": f"Model server unavailable: {error}"}
            self._json(HTTPStatus.OK, status)
        elif parts == ["api", "conversations"]:
            self._json(HTTPStatus.OK, self.app.store.list())
        elif parts == ["api", "documents"]:
            library = self.app.documents
            self._json(
                HTTPStatus.OK,
                {"available": False}
                if library is None
                else {"available": True, **library.status()},
            )
        elif len(parts) == 3 and parts[:2] == ["api", "conversations"]:
            self._json(HTTPStatus.OK, self.app.store.get(parts[2]))
        elif len(parts) == 5 and parts[:2] == ["api", "conversations"] and parts[3] == "images":
            data, media_type = self.app.store.images.load(parts[2], parts[4])
            self._send(HTTPStatus.OK, data, media_type)
        else:
            raise KeyError(path)

    def _delete(self, parts: list[str]) -> None:
        if len(parts) == 3 and parts[:2] == ["api", "conversations"]:
            self.app.store.delete(parts[2])
            self._json(HTTPStatus.OK, {"deleted": parts[2]})
        else:
            raise KeyError(self.path)

    def _post(self, parts: list[str]) -> None:
        is_reply = len(parts) == 4 and parts[:2] == ["api", "conversations"] and parts[3] == "reply"
        limit = MAX_REPLY_BODY_BYTES if is_reply else MAX_BODY_BYTES
        if parts == ["api", "documents"]:
            limit = MAX_UPLOAD_BODY_BYTES
        body = self._body(limit)
        if parts[:2] == ["api", "documents"]:
            self._documents(parts[2:], body)
        elif parts == ["api", "conversations"]:
            system_prompt = body.get("system_prompt", self.app.system_prompt)
            if not isinstance(system_prompt, str) or len(system_prompt) > MAX_SYSTEM_CHARS:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid system prompt")
            self._json(HTTPStatus.CREATED, self.app.store.create(system_prompt))
        elif is_reply:
            self._reply(parts[2], body)
        else:
            raise KeyError(self.path)

    def _documents(self, rest: list[str], body: dict[str, Any]) -> None:
        library = self.app.documents
        if library is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Document search is not configured")
        if rest == ["reindex"]:
            started = library.reindex_async()
            self._json(HTTPStatus.ACCEPTED, {"started": started, **library.status()})
        elif not rest:
            name, text = body.get("name"), body.get("text")
            if not isinstance(name, str) or not isinstance(text, str):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Send a name and the document text")
            try:
                saved = library.add(name, text)
            except ValueError as error:
                raise ApiError(HTTPStatus.BAD_REQUEST, str(error)) from None
            library.reindex_async()
            self._json(HTTPStatus.CREATED, {"saved": saved, **library.status()})
        else:
            raise KeyError(self.path)

    # ----- generation --------------------------------------------------------------------

    def _reply(self, conversation_id: str, body: dict[str, Any]) -> None:
        content = body.get("content", "")
        regenerate = body.get("regenerate", False) is True
        documents = body.get("documents", False) is True
        if documents and self.app.documents is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Document search is not configured")
        images = [] if regenerate else decode_images(body.get("images"))
        if images and not self.app.vision:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Image input is not configured")
        if not regenerate and (
            not isinstance(content, str)
            or not (content.strip() or images)
            or len(content) > MAX_MESSAGE_CHARS
        ):
            raise ApiError(
                HTTPStatus.BAD_REQUEST, "Send an image or a message of 1-32000 characters"
            )
        raw_settings = body.get("settings", {})
        if not isinstance(raw_settings, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "settings must be an object")
        try:
            settings = settings_from(raw_settings, self.app.defaults)
            vision_settings = settings_from(
                {key: raw_settings[key] for key in VISION_OVERRIDES if key in raw_settings}
                | {"preset": "vision"}
            )
        except (TypeError, ValueError) as error:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(error)) from None
        if not self.app.generation.acquire(blocking=False):
            raise ApiError(HTTPStatus.CONFLICT, "A reply is already being generated")
        try:
            store = self.app.store
            conversation = store.get(conversation_id)
            if regenerate:
                conversation = store.drop_trailing_assistant(conversation_id)
                if not conversation["messages"] or conversation["messages"][-1]["role"] != "user":
                    raise ApiError(HTTPStatus.CONFLICT, "Nothing to regenerate")
            else:
                if conversation["messages"] and conversation["messages"][-1]["role"] == "user":
                    raise ApiError(HTTPStatus.CONFLICT, "Previous message has no reply")
                user: dict[str, Any] = {"role": "user", "content": content, "created": now()}
                if images:
                    try:
                        user["images"] = [store.images.save(conversation_id, i) for i in images]
                    except ValueError as error:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(error)) from None
                conversation = store.append(conversation_id, user)
            # A conversation with any image is answered by the vision model from then on.
            vision = uses_vision(conversation)
            if documents and vision:
                if not regenerate:
                    conversation["messages"].pop()
                    store.save(conversation)
                raise ApiError(
                    HTTPStatus.BAD_REQUEST,
                    "Document answers are not available in conversations with images",
                )
            chosen = vision_settings if vision else settings
            self._stream_reply(conversation, chosen, not regenerate, documents)
        finally:
            self.app.generation.release()

    def _event(self, name: str, value: dict[str, Any]) -> None:
        # After the client closes, the next write fails (tested); generation then stops.
        payload = json.dumps(value, ensure_ascii=False)
        self.wfile.write(f"event: {name}\ndata: {payload}\n\n".encode())
        self.wfile.flush()

    def _stream_reply(
        self,
        conversation: dict[str, Any],
        settings: ChatSettings,
        rollback_user: bool,
        documents: bool = False,
    ) -> None:
        store = self.app.store
        answer: list[str] = []
        reasoning: list[str] = []
        meta: dict[str, Any] = {}
        stats: dict[str, Any] | None = None
        messages = conversation_messages(conversation, store.images)
        sources: list[dict[str, Any]] | None = None
        try:
            if documents and self.app.documents is not None:
                # The search uses the user's own words; the model sees them with sources.
                hits = self.app.documents.search(messages[-1].content)
                messages = ground(messages, hits)
                sources = public_sources(hits)
            events = self.app.respond(messages, settings)
            first = next(events)  # Context planning errors surface before the stream opens.
            if sources is not None:
                first["sources"] = sources
        except (ValueError, RuntimeError, OSError) as error:
            if rollback_user:
                conversation["messages"].pop()
                store.save(conversation)
            raise ApiError(HTTPStatus.BAD_GATEWAY, str(error)) from None
        self._headers(HTTPStatus.OK, "text/event-stream; charset=utf-8", None)
        interrupted = False
        try:
            meta = first
            self._event("meta", first)
            for event in events:
                if event["type"] == "answer":
                    answer.append(event["text"])
                elif event["type"] == "reasoning":
                    reasoning.append(event["text"])
                elif event["type"] == "done":
                    stats = event["stats"]
                    continue
                self._event(event["type"], {"text": event["text"]})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            interrupted = True  # The user pressed stop or closed the tab.
        except (RuntimeError, OSError, ValueError) as error:
            interrupted = True
            try:
                self._event("error", {"error": str(error)})
            except OSError:
                pass
        finally:
            events.close()  # Closes the upstream stream, which stops llama.cpp decoding.
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(answer),
            "created": now(),
            "meta": {key: value for key, value in meta.items() if key != "type"},
        }
        if reasoning:
            message["reasoning"] = "".join(reasoning)
        if stats is not None:
            message["stats"] = stats
        if interrupted:
            message["interrupted"] = True
        saved = store.append(conversation["id"], message)
        if not interrupted:
            try:
                self._event("done", {"message": message, "title": saved["title"]})
            except OSError:
                pass


def make_server(app: ChatApp, port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "::1"):
        raise ValueError("The chat server only binds to a loopback address")
    server = ThreadingHTTPServer((host, port), Handler)
    actual = server.server_address[1]
    names = ("127.0.0.1", "localhost") if host == "127.0.0.1" else ("[::1]", "localhost")
    handler = type(
        "BoundHandler",
        (Handler,),
        {"app": app, "allowed_hosts": frozenset(f"{name}:{actual}" for name in names)},
    )
    server.RequestHandlerClass = handler
    server.daemon_threads = True
    return server
