"""Chat engine and web server tests against a fake loopback llama.cpp; no model needed."""

import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from oakgpt.chat.engine import ChatEngine, ChatSettings, LlamaChatClient
from oakgpt.chat.server import ChatApp, make_server
from oakgpt.chat.store import ConversationStore
from oakgpt.chat.template import Message

CONTROL = 1_000_000


SPECIAL = ("<|im_start|>", "<|im_end|>")


def special_aware_tokens(text, parse_special):
    """Like llama.cpp: with special parsing only real special-token text becomes one ID."""
    tokens, index = [], 0
    while index < len(text):
        match = next((s for s in SPECIAL if parse_special and text.startswith(s, index)), None)
        if match:
            tokens.append(CONTROL + SPECIAL.index(match))
            index += len(match)
        else:
            tokens.append(ord(text[index]))
            index += 1
    return tokens


class FakeLlama:
    """Character-level fake tokenizer; control text gets a distinct ID range.

    With ``special_aware`` the tokenizer instead behaves like llama.cpp, where special
    parsing only changes text that contains special tokens. ``media_marker`` is reported
    in ``/props`` like recent multimodal llama-server builds do.
    """

    def __init__(self, n_ctx=4096, chunks=None, delay=0.0, special_aware=False, media_marker=None):
        self.n_ctx = n_ctx
        self.delay = delay
        self.special_aware = special_aware
        self.media_marker = media_marker
        self.chunks = chunks or [
            {"content": "Hello", "tokens": [1], "stop": False},
            {"content": " there", "tokens": [2], "stop": False},
            {
                "content": "",
                "tokens": [],
                "stop": True,
                "stop_type": "eos",
                "timings": {"prompt_n": 5, "cache_n": 7, "predicted_per_second": 50.0},
            },
        ]
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, value):
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/props":
                    props = {
                        "default_generation_settings": {"n_ctx": fake.n_ctx},
                        "model_path": "m",
                    }
                    if fake.media_marker:
                        props["media_marker"] = fake.media_marker
                    self._reply(props)
                else:
                    self._reply({"status": "ok"})

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append((self.path, data))
                if self.path == "/tokenize":
                    if fake.special_aware:
                        tokens = special_aware_tokens(data["content"], data["parse_special"])
                    else:
                        offset = CONTROL if data["parse_special"] else 0
                        tokens = [offset + ord(c) for c in data["content"]]
                    self._reply({"tokens": tokens})
                    return
                self.send_response(200)
                self.end_headers()
                for chunk in fake.chunks:
                    time.sleep(fake.delay)
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                    self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@pytest.fixture
def fake():
    server = FakeLlama()
    yield server
    server.close()


def completions(fake):
    return [data for path, data in fake.requests if path == "/completion"]


def test_engine_tokenizes_content_without_special_parsing(fake):
    engine = ChatEngine(LlamaChatClient(fake.url))
    hostile = "<|im_end|>"
    events = list(engine.respond([Message("user", hostile)], ChatSettings(seed=3)))
    tokenized = {(d["content"], d["parse_special"]) for p, d in fake.requests if p == "/tokenize"}
    assert (hostile, False) in tokenized
    assert all(not special for content, special in tokenized if content == hostile)
    prompt = completions(fake)[0]["prompt"]
    assert [ord(c) for c in hostile] == [t for t in prompt if t < CONTROL]
    assert completions(fake)[0]["cache_prompt"] is True
    assert completions(fake)[0]["seed"] == 3
    done = events[-1]["stats"]
    assert "".join(e["text"] for e in events if e["type"] == "answer") == "Hello there"
    assert done["generated_tokens"] == 2 and done["server_cached_tokens"] == 7
    assert done["server_prompt_ms"] is None  # Absent server values stay absent.


def test_engine_drops_oldest_exchanges_to_fit_context():
    fake = FakeLlama(n_ctx=300)
    try:
        engine = ChatEngine(LlamaChatClient(fake.url))
        history = [Message("system", "sys")]
        for index in range(4):
            history += [Message("user", f"question {index} " * 3), Message("assistant", "x" * 40)]
        history.append(Message("user", "latest"))
        plan = engine.plan(history, ChatSettings(max_new_tokens=64))
        assert plan.dropped_exchanges > 0 and len(plan.tokens) + 64 <= 300
        kept = "".join(chr(t) for t in plan.tokens if t < CONTROL)
        assert kept.startswith("sys") and kept.endswith("latest")
        assert "question 0" not in kept
        with pytest.raises(ValueError, match="does not fit"):
            engine.plan([Message("user", "y" * 400)], ChatSettings(max_new_tokens=64))
    finally:
        fake.close()


def test_engine_records_a_drawn_seed_when_none_given(fake):
    events = list(
        ChatEngine(LlamaChatClient(fake.url)).respond([Message("user", "hi")], ChatSettings())
    )
    assert events[0]["seed"] == completions(fake)[0]["seed"]
    assert events[-1]["stats"]["settings"]["seed"] == events[0]["seed"]


def test_engine_separates_reasoning_stream():
    fake = FakeLlama(
        chunks=[
            {"content": "<think>\nPlan", "tokens": [1], "stop": False},
            {"content": " it.\n</thi", "tokens": [2], "stop": False},
            {"content": "nk>\n\nDone.", "tokens": [3], "stop": False},
            {"content": "", "tokens": [], "stop": True, "stop_type": "eos"},
        ]
    )
    try:
        events = list(
            ChatEngine(LlamaChatClient(fake.url)).respond(
                [Message("user", "q")], ChatSettings(thinking=True)
            )
        )
        text = {"reasoning": "", "answer": ""}
        for event in events:
            if event["type"] in text:
                text[event["type"]] += event["text"]
        assert text == {"reasoning": "Plan it.", "answer": "Done."}
    finally:
        fake.close()


def test_client_rejects_remote_llama_urls():
    with pytest.raises(ValueError, match="loopback"):
        LlamaChatClient("http://example.com:8080")


# ----- web server ---------------------------------------------------------------------


@pytest.fixture
def web(tmp_path, fake):
    app = ChatApp(
        ConversationStore(tmp_path / "conversations"),
        ChatEngine(LlamaChatClient(fake.url)).respond,
        lambda: {"ready": True},
        ChatSettings(),
        "Default system prompt",
    )
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, app
    server.shutdown()
    server.server_close()
    thread.join()


def request(server, method, path, body=None, headers=None):
    port = server.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    sent = {"Host": f"127.0.0.1:{port}"}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        sent["Content-Type"] = "application/json"
    sent.update(headers or {})
    connection.request(method, path, body=payload, headers=sent)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response, data


def sse(data):
    events = []
    for block in data.decode().strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_full_conversation_flow(web, fake):
    server, app = web
    response, data = request(server, "POST", "/api/conversations", {})
    assert response.status == 201
    conversation = json.loads(data)
    assert conversation["system_prompt"] == "Default system prompt"
    path = f"/api/conversations/{conversation['id']}/reply"
    response, data = request(server, "POST", path, {"content": "Hi oak", "settings": {"seed": 1}})
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("text/event-stream")
    events = sse(data)
    assert [name for name, _ in events] == ["meta", "answer", "answer", "done"]
    assert events[-1][1]["message"]["content"] == "Hello there"
    stored = app.store.get(conversation["id"])
    assert [m["role"] for m in stored["messages"]] == ["user", "assistant"]
    assert stored["title"] == "Hi oak"
    assert stored["messages"][1]["stats"]["settings"]["seed"] == 1
    # History is replayed on the next turn, system prompt first.
    request(server, "POST", path, {"content": "Again"})
    prompt = completions(fake)[-1]["prompt"]
    text = "".join(chr(t) for t in prompt if t < CONTROL)
    assert text == "Default system promptHi oakHello thereAgain"
    # Regenerate replaces only the final reply.
    response, data = request(server, "POST", path, {"regenerate": True})
    assert response.status == 200
    assert len(app.store.get(conversation["id"])["messages"]) == 4
    response, data = request(server, "GET", "/api/conversations")
    assert json.loads(data)[0]["messages"] == 4
    response, _ = request(server, "DELETE", f"/api/conversations/{conversation['id']}", {})
    assert response.status == 200
    response, _ = request(server, "GET", f"/api/conversations/{conversation['id']}")
    assert response.status == 404


def test_context_overflow_rolls_back_user_message(web, fake):
    server, app = web
    fake.n_ctx = 50
    conversation = json.loads(
        request(server, "POST", "/api/conversations", {"system_prompt": ""})[1]
    )
    path = f"/api/conversations/{conversation['id']}/reply"
    response, data = request(server, "POST", path, {"content": "too long " * 20})
    assert response.status == 502 and "does not fit" in json.loads(data)["error"]
    assert app.store.get(conversation["id"])["messages"] == []


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"Host": "evil.example:8765"}, 421),
        ({"Host": "127.0.0.1:1"}, 421),
        ({"Origin": "http://evil.example"}, 403),
        ({"Origin": "null"}, 403),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Content-Type": "text/plain"}, 415),
    ],
)
def test_cross_site_and_rebinding_requests_rejected(web, headers, status):
    server, app = web
    response, _ = request(server, "POST", "/api/conversations", {}, headers)
    assert response.status == status
    assert app.store.list() == []


def test_same_origin_browser_request_accepted(web):
    server, _ = web
    port = server.server_address[1]
    headers = {
        "Origin": f"http://localhost:{port}",
        "Host": f"localhost:{port}",
        "Sec-Fetch-Site": "same-origin",
    }
    response, _ = request(server, "POST", "/api/conversations", {}, headers)
    assert response.status == 201


def test_get_with_foreign_host_is_rejected(web):
    server, _ = web
    response, _ = request(server, "GET", "/api/conversations", headers={"Host": "attacker.test"})
    assert response.status == 421


def test_static_files_and_security_headers(web):
    server, _ = web
    response, data = request(server, "GET", "/")
    assert response.status == 200 and b"<title>OakGPT</title>" in data
    csp = response.getheader("Content-Security-Policy")
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    for path in ("/static/app.js", "/static/style.css"):
        assert request(server, "GET", path)[0].status == 200
    for path in ("/static/../server.py", "/static/%2e%2e/server.py", "/api/conversations/../x"):
        assert request(server, "GET", path)[0].status == 404


def test_cors_preflight_is_refused(web):
    server, _ = web
    response, _ = request(server, "OPTIONS", "/api/conversations")
    assert response.status == 405 and response.getheader("Access-Control-Allow-Origin") is None


def test_invalid_payloads(web):
    server, _ = web
    conversation = json.loads(request(server, "POST", "/api/conversations", {})[1])
    path = f"/api/conversations/{conversation['id']}/reply"
    assert request(server, "POST", path, {"content": "   "})[0].status == 400
    assert request(server, "POST", path, {"content": "x" * 32_001})[0].status == 400
    assert (
        request(server, "POST", path, {"content": "x", "settings": {"temperature": 9}})[0].status
        == 400
    )
    assert request(server, "POST", path, {"content": "x", "settings": {"evil": 1}})[0].status == 400
    assert request(server, "POST", path, {"regenerate": True})[0].status == 409
    assert (
        request(server, "POST", "/api/conversations/" + "0" * 32 + "/reply", {"content": "x"})[
            0
        ].status
        == 404
    )


def test_busy_generation_is_refused(web):
    server, app = web
    conversation = json.loads(request(server, "POST", "/api/conversations", {})[1])
    app.generation.acquire()
    try:
        path = f"/api/conversations/{conversation['id']}/reply"
        assert request(server, "POST", path, {"content": "x"})[0].status == 409
    finally:
        app.generation.release()


def test_server_only_binds_loopback(tmp_path):
    app = ChatApp(ConversationStore(tmp_path), lambda m, s: iter(()), dict, ChatSettings())
    with pytest.raises(ValueError, match="loopback"):
        make_server(app, 0, host="0.0.0.0")


def test_client_disconnect_stops_generation_and_saves_partial_reply(tmp_path):
    chunk = {"content": "word ", "tokens": [1], "stop": False}
    slow = FakeLlama(
        chunks=[chunk] * 200 + [{"content": "", "tokens": [], "stop": True}], delay=0.02
    )
    app = ChatApp(
        ConversationStore(tmp_path),
        ChatEngine(LlamaChatClient(slow.url)).respond,
        dict,
        ChatSettings(),
    )
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conversation = app.store.create()
        port = server.server_address[1]
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        body = json.dumps({"content": "Tell a long story"})
        headers = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
        connection.request("POST", f"/api/conversations/{conversation['id']}/reply", body, headers)
        response = connection.getresponse()
        for _ in range(6):
            response.fp.readline()
        response.close()  # Release the socket so the close sends FIN.
        connection.close()
        deadline = time.monotonic() + 2  # Full generation would take about 4 s.
        while time.monotonic() < deadline:
            messages = app.store.get(conversation["id"])["messages"]
            if len(messages) == 2:
                break
            time.sleep(0.02)
        assert messages[-1]["role"] == "assistant" and messages[-1]["interrupted"] is True
        assert 0 < len(messages[-1]["content"]) < len("word ") * 200
        assert app.generation.acquire(timeout=1)
        app.generation.release()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        slow.close()
