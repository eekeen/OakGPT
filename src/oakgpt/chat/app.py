"""Chat configuration, managed llama-server processes and application wiring.

Two model profiles exist: ``text`` (Qwen3, required) and ``vision`` (Qwen3-VL, optional).
Managed servers are exclusive: at most one runs at a time, so the GPU only ever holds one
model. A reply is routed to the vision profile when its conversation contains an image,
and the pool swaps servers when the routed profile is not the one loaded.

The optional document library (Chat C3) runs its embedding model in a separate
llama-server next to the pool, on the CPU by default so the GPU rule above still holds.
"""

import json
import re
import socket
import subprocess
import threading
import time
import webbrowser
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any
from urllib.error import URLError

from oakgpt.chat.documents import (
    METHODS,
    QUERY_TASK,
    SUFFIXES,
    DocumentIndex,
    Embedder,
    Hit,
    build_index,
)
from oakgpt.chat.engine import (
    PRESETS,
    ChatEngine,
    ChatSettings,
    LlamaChatClient,
    VisionChatEngine,
    settings_from,
)
from oakgpt.chat.server import ChatApp, make_server
from oakgpt.chat.store import ConversationStore
from oakgpt.chat.template import Message
from oakgpt.provenance import sha256

# Qwen3-VL wraps each image in <|vision_start|>/<|vision_end|>: a 640x480 image measured
# 302 prompt tokens for 300 image patches (reports/chat/c1_1).
VISION_DELIMITER_TOKENS = 2


@dataclass(frozen=True)
class ManagedServer:
    binary: Path
    model: Path
    context: int = 8192
    gpu_layers: int = 99
    threads: int = 8
    log_dir: Path = Path("runs/chat/server")
    mmproj: Path | None = None
    image_max_tokens: int | None = None
    lora: Path | None = None  # GGUF LoRA adapter applied by llama-server (Chat C2).
    # (fast, reasoning) adapter scales sent with every request (Chat C2.1). The adapter is
    # then loaded unapplied, and llama-server's RAM prompt cache is disabled because it
    # matches cached prompts by tokens only, not by the LoRA scale they were computed with.
    lora_scales: tuple[float, float] | None = None
    embedding: bool = False  # Serve an embedding model (Chat C3) instead of generation.

    def __post_init__(self) -> None:
        if self.lora_scales is not None:
            if self.lora is None:
                raise ValueError("lora_scales needs a lora adapter")
            if not all(0 <= scale <= 2 for scale in self.lora_scales):
                raise ValueError("lora_scales must be in [0, 2]")

    def command(self, port: int) -> list[str]:
        command = [
            str(self.binary),
            "-m",
            str(self.model),
            "-c",
            str(self.context),
            "-ngl",
            str(self.gpu_layers),
            "-t",
            str(self.threads),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--parallel",
            "1",
        ]
        if self.mmproj is not None:
            command += ["--mmproj", str(self.mmproj)]
        if self.image_max_tokens is not None:
            command += ["--image-max-tokens", str(self.image_max_tokens)]
        if self.lora is not None:
            command += ["--lora", str(self.lora)]
        if self.lora_scales is not None:
            command += ["--lora-init-without-apply", "--cache-ram", "0"]
        if self.embedding:
            # Qwen3-Embedding uses last-token pooling; one chunk must fit one micro-batch.
            command += ["--embedding", "--pooling", "last", "-b", "2048", "-ub", "2048"]
        return command

    def files(self) -> list[Path]:
        optional = [path for path in (self.mmproj, self.lora) if path is not None]
        return [self.model, *optional]


@dataclass(frozen=True)
class VisionProfile:
    url: str
    image_max_tokens: int = 1024
    identity: dict[str, Any] = field(default_factory=dict)
    managed: ManagedServer | None = None


@dataclass(frozen=True)
class EmbeddingProfile:
    url: str
    identity: dict[str, Any] = field(default_factory=dict)
    managed: ManagedServer | None = None


@dataclass(frozen=True)
class DocumentsConfig:
    folder: Path
    index: Path
    method: str = "hybrid"
    top_k: int = 6
    max_words: int = 200
    embedding: EmbeddingProfile | None = None

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ValueError(f"documents.method must be one of {METHODS}")
        if self.method != "bm25" and self.embedding is None:
            raise ValueError(f"documents.method {self.method!r} needs an embedding block")
        if not 1 <= self.top_k <= 20 or not 20 <= self.max_words <= 2000:
            raise ValueError("documents.top_k must be in [1, 20] and max_words in [20, 2000]")


@dataclass(frozen=True)
class ChatConfig:
    url: str
    storage: Path
    web_port: int = 8765
    system_prompt: str = ""
    defaults: ChatSettings = field(default_factory=ChatSettings)
    default_preset: str = "chat"  # Mode the UI starts in until the user picks one.
    identity: dict[str, Any] = field(default_factory=dict)
    cache_prompt: bool = True
    managed: ManagedServer | None = None
    vision: VisionProfile | None = None
    documents: DocumentsConfig | None = None

    @classmethod
    def load(cls, path: Path) -> "ChatConfig":
        values: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        base = path.parent

        def resolve(value: str) -> Path:
            return (base / value).resolve()

        def managed(raw: dict[str, Any] | None, **extra: Any) -> ManagedServer | None:
            if not raw:
                return None
            server = dict(raw)
            mmproj = server.pop("mmproj", None)
            lora = server.pop("lora", None)
            scales = server.pop("lora_scales", None)
            if scales is not None and set(scales) != {"chat", "reasoning"}:
                raise ValueError("lora_scales needs exactly the keys chat and reasoning")
            return ManagedServer(
                binary=resolve(server.pop("binary")),
                model=resolve(server.pop("model")),
                log_dir=resolve(server.pop("log_dir", "../../runs/chat/server")),
                mmproj=None if mmproj is None else resolve(mmproj),
                lora=None if lora is None else resolve(lora),
                lora_scales=None
                if scales is None
                else (float(scales["chat"]), float(scales["reasoning"])),
                **server,
                **extra,
            )

        vision = None
        if values.get("vision"):
            raw = values["vision"]
            image_max_tokens = int(raw.get("image_max_tokens", 1024))
            vision = VisionProfile(
                url=raw["llama_url"],
                image_max_tokens=image_max_tokens,
                identity=raw.get("identity", {}),
                managed=managed(raw.get("managed_server"), image_max_tokens=image_max_tokens),
            )
        documents = None
        if values.get("documents"):
            raw = dict(values["documents"])
            embedding = None
            if raw.get("embedding"):
                spec = raw["embedding"]
                embedding = EmbeddingProfile(
                    url=spec["llama_url"],
                    identity=spec.get("identity", {}),
                    managed=managed(spec.get("managed_server"), embedding=True),
                )
            documents = DocumentsConfig(
                folder=resolve(raw["folder"]),
                index=resolve(raw["index"]),
                method=raw.get("method", "hybrid"),
                top_k=int(raw.get("top_k", 6)),
                max_words=int(raw.get("max_words", 200)),
                embedding=embedding,
            )
        default_preset = values.get("defaults", {}).get("preset", "chat")
        if default_preset not in ("chat", "reasoning"):  # The two modes the UI offers.
            raise ValueError(f"defaults.preset must be chat or reasoning, not {default_preset!r}")
        return cls(
            url=values["llama_url"],
            storage=resolve(values["storage"]),
            web_port=values.get("web_port", 8765),
            system_prompt=values.get("system_prompt", ""),
            defaults=settings_from(values.get("defaults", {})),
            default_preset=default_preset,
            identity=values.get("identity", {}),
            cache_prompt=values.get("cache_prompt", True),
            managed=managed(values.get("managed_server")),
            vision=vision,
            documents=documents,
        )


def _port(url: str) -> int:
    return int(url.rsplit(":", 1)[1].rstrip("/"))


class ManagedProcess:
    """One llama-server child process with its logs and a verified model path."""

    def __init__(self, spec: ManagedServer, client: LlamaChatClient) -> None:
        self.spec = spec
        self.client = client
        self.process: subprocess.Popen[bytes] | None = None
        self._logs: list[IO[str]] = []

    def start(self, timeout: float = 180) -> dict[str, Any]:
        port = _port(self.client.url)
        with socket.socket() as probe:  # Refuse to adopt a server we did not start.
            probe.bind(("127.0.0.1", port))
        directory = self.spec.log_dir / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        directory.mkdir(parents=True, exist_ok=False)
        command = self.spec.command(port)
        (directory / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
        stdout = (directory / "stdout.txt").open("w", encoding="utf-8")
        stderr = (directory / "stderr.txt").open("w", encoding="utf-8")
        self._logs = [stdout, stderr]
        started = time.perf_counter()
        self.process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + timeout
            while True:
                if self.process.poll() is not None:
                    raise RuntimeError(f"llama-server exited; see {directory / 'stderr.txt'}")
                try:
                    props = self.client.json("/props")
                    if self.client.json("/health").get("status") == "ok":
                        if Path(props["model_path"]).resolve() != self.spec.model.resolve():
                            raise RuntimeError("Server model path differs from configured model")
                        break
                except (URLError, ConnectionError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("llama-server readiness timed out")
                time.sleep(0.25)
        except BaseException:
            self.stop()
            raise
        return {
            "log_dir": str(directory),
            "command": command,
            "load_s": round(time.perf_counter() - started, 3),
        }

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
        for log in self._logs:
            log.close()
        self._logs = []


@contextmanager
def managed_llama(spec: ManagedServer, client: LlamaChatClient) -> Iterator[dict[str, Any]]:
    process = ManagedProcess(spec, client)
    launch = process.start()
    try:
        yield launch
    finally:
        process.stop()


@dataclass
class Profile:
    engine: ChatEngine
    identity: dict[str, Any]
    managed: ManagedServer | None


class ModelPool:
    """Keeps at most one managed llama-server running and swaps on demand."""

    def __init__(self, profiles: dict[str, Profile]) -> None:
        self.profiles = profiles
        self.active: str | None = None
        self.loading: str | None = None
        self.launches: dict[str, dict[str, Any]] = {}
        self._process: ManagedProcess | None = None
        self._lock = threading.Lock()

    def activate(self, name: str) -> float | None:
        """Make ``name`` the serving profile; return the load time if a server started."""
        with self._lock:
            if self.active == name:
                return None
            profile = self.profiles[name]
            if profile.managed is None:
                self.active = name  # An external server is assumed to be running.
                return None
            self.loading = name
            try:
                if self._process is not None:
                    self._process.stop()
                    self._process = None
                    self.active = None
                process = ManagedProcess(profile.managed, profile.engine.client)
                launch = process.start()
                self._process = process
                self.launches[name] = launch
                self.active = name
                return float(launch["load_s"])
            finally:
                self.loading = None

    def close(self) -> None:
        with self._lock:
            if self._process is not None:
                self._process.stop()
                self._process = None
            self.active = None

    def respond(
        self, messages: list[Message], settings: ChatSettings
    ) -> Generator[dict[str, Any], None, None]:
        name = "vision" if any(message.images for message in messages) else "text"
        if name not in self.profiles:
            raise ValueError("This conversation has images, but no vision model is configured")
        load_s = self.activate(name)
        events = self.profiles[name].engine.respond(messages, settings)
        try:
            first = next(events)
            first["model_load_s"] = load_s
            yield first
            yield from events
        finally:
            events.close()


def cached_sha256(path: Path, cache_file: Path) -> str:
    """SHA-256 of ``path``, reused while its size and modification time are unchanged."""
    try:
        cache: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    stat = path.stat()
    key = str(path.resolve())
    entry = cache.get(key)
    if entry and entry["size"] == stat.st_size and entry["mtime_ns"] == stat.st_mtime_ns:
        return str(entry["sha256"])
    digest = sha256(path)
    cache[key] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest}
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return digest


def _identity(base: dict[str, Any], managed: ManagedServer | None, cache: Path) -> dict[str, Any]:
    identity = dict(base)
    if managed is not None:
        identity["gguf_filename"] = managed.model.name
        identity["gguf_sha256"] = cached_sha256(managed.model, cache)
        if managed.mmproj is not None:
            identity["mmproj_filename"] = managed.mmproj.name
            identity["mmproj_sha256"] = cached_sha256(managed.mmproj, cache)
        if managed.lora is not None:
            identity["lora_filename"] = managed.lora.name
            identity["lora_sha256"] = cached_sha256(managed.lora, cache)
        if managed.lora_scales is not None:
            identity["lora_scales"] = {
                "chat": managed.lora_scales[0],
                "reasoning": managed.lora_scales[1],
            }
    return identity


def build_pool(config: ChatConfig) -> ModelPool:
    cache = config.storage.parent / "hash-cache.json"
    print("Checking model file hashes for provenance ...", flush=True)
    text = LlamaChatClient(config.url, cache_prompt=config.cache_prompt)
    scales = None if config.managed is None else config.managed.lora_scales
    profiles = {
        "text": Profile(
            ChatEngine(text, lora_scales=scales),
            _identity(config.identity, config.managed, cache),
            config.managed,
        )
    }
    if config.vision is not None:
        vision = config.vision
        client = LlamaChatClient(vision.url, cache_prompt=config.cache_prompt)
        engine = VisionChatEngine(client, vision.image_max_tokens + VISION_DELIMITER_TOKENS)
        profiles["vision"] = Profile(
            engine, _identity(vision.identity, vision.managed, cache), vision.managed
        )
    return ModelPool(profiles)


_UPLOAD_NAME = re.compile(r"^[\w][\w .()-]{0,99}$")
MAX_UPLOAD_CHARS = 1_000_000


class DocumentLibrary:
    """The user's document folder, its search index and the embedding server.

    The index is rebuilt in a background thread (at start and on request) and swapped in
    atomically, so replies keep using the previous index while a rebuild runs. Embeddings
    of unchanged chunks are reused from the saved index when the model identity matches.
    """

    def __init__(self, config: DocumentsConfig, hash_cache: Path) -> None:
        self.config = config
        self.hash_cache = hash_cache
        self.index: DocumentIndex | None = None
        self.embedder: Embedder | None = None
        self.state = "not started"
        self.error: str | None = None
        self.last_build_s: float | None = None
        self.launch: dict[str, Any] | None = None
        self._process: ManagedProcess | None = None
        self._build = threading.Lock()

    def start(self) -> None:
        profile = self.config.embedding
        if profile is None or self.config.method == "bm25":
            return
        client = LlamaChatClient(profile.url, timeout=600)
        identity = _identity(profile.identity, profile.managed, self.hash_cache)
        identity["query_task"] = QUERY_TASK
        if profile.managed is not None:
            self._process = ManagedProcess(profile.managed, client)
            self.launch = self._process.start()
        self.embedder = Embedder(client, identity)

    def close(self) -> None:
        if self._process is not None:
            self._process.stop()
            self._process = None

    def reindex(self) -> dict[str, Any]:
        with self._build:
            self.state, self.error = "indexing", None
            started = time.perf_counter()
            try:
                previous = None
                if self.config.index.is_file():
                    try:
                        previous = DocumentIndex.load(self.config.index)
                    except (ValueError, KeyError, TypeError):
                        previous = None  # An unreadable cache is simply rebuilt.
                index = build_index(
                    self.config.folder, self.config.max_words, self.embedder, previous
                )
                index.save(self.config.index)
            except Exception as error:
                self.state, self.error = "error", str(error)
                raise
            self.index = index
            self.last_build_s = round(time.perf_counter() - started, 3)
            self.state = "ready"
            return index.summary()

    def reindex_async(self) -> bool:
        if self._build.locked():
            return False

        def run() -> None:
            try:
                self.reindex()
            except Exception:
                pass  # Recorded in self.error and shown by status().

        threading.Thread(target=run, name="document-index", daemon=True).start()
        return True

    def search(self, query: str) -> list[Hit]:
        index = self.index
        if index is None:
            raise ValueError(f"The document index is not ready ({self.state})")
        return index.search(query, self.config.top_k, self.config.method, self.embedder)

    def add(self, name: str, text: str) -> str:
        """Save an uploaded text document into the folder; never overwrites a file."""
        if not _UPLOAD_NAME.fullmatch(name) or Path(name).suffix.lower() not in SUFFIXES:
            raise ValueError("Use a plain file name ending in .md, .markdown or .txt")
        if not text.strip() or len(text) > MAX_UPLOAD_CHARS:
            raise ValueError("A document must have 1 to 1,000,000 characters")
        self.config.folder.mkdir(parents=True, exist_ok=True)
        try:
            with (self.config.folder / name).open("x", encoding="utf-8", newline="\n") as out:
                out.write(text)
        except FileExistsError:
            raise ValueError(f"{name} already exists in the documents folder") from None
        return name

    def status(self) -> dict[str, Any]:
        index = self.index
        return {
            "state": self.state,
            "error": self.error,
            "folder": str(self.config.folder),
            "method": self.config.method,
            "top_k": self.config.top_k,
            "last_build_s": self.last_build_s,
            "documents": [] if index is None else index.files,
            **({} if index is None else index.summary()),
        }


def run_chat(config: ChatConfig, open_browser: bool = True) -> None:
    pool = build_pool(config)
    library = None
    try:
        print("Loading the text model ...", flush=True)
        pool.activate("text")
        if config.documents is not None:
            library = DocumentLibrary(config.documents, config.storage.parent / "hash-cache.json")
            print("Starting document search ...", flush=True)
            library.start()
            library.reindex_async()

        def status() -> dict[str, Any]:
            common = {
                "vision_available": "vision" in pool.profiles,
                "models": {
                    name: {"model": profile.identity.get("model"), "loaded": name == pool.active}
                    for name, profile in pool.profiles.items()
                },
                "cache_prompt": config.cache_prompt,
                "presets": {name: asdict(preset) for name, preset in PRESETS.items()},
                "default_preset": config.default_preset,
                "system_prompt": config.system_prompt,
            }
            active = pool.active
            if pool.loading is not None or active is None:
                return {"ready": False, "loading": pool.loading, **common}
            profile = pool.profiles[active]
            client = profile.engine.client
            props = client.json("/props")
            return {
                "ready": client.json("/health").get("status") == "ok",
                "active_model": active,
                "model_path": Path(props.get("model_path", "")).name,
                "context_length": props["default_generation_settings"]["n_ctx"],
                "build": props.get("build_info"),
                "identity": {**profile.identity, "managed_server": pool.launches.get(active)},
                **common,
            }

        app = ChatApp(
            ConversationStore(config.storage),
            pool.respond,
            status,
            config.defaults,
            config.system_prompt,
            vision="vision" in pool.profiles,
            documents=library,
        )
        server = make_server(app, config.web_port)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        print(f"OakGPT chat is running at {url}  (Ctrl+C to stop)", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        if library is not None:
            library.close()
        pool.close()
