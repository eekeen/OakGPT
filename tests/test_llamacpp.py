import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from oakgpt.inference.base import GenerationConfig
from oakgpt.inference.llamacpp import LlamaCppBackend


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://192.168.1.2:8080",
        "http://localhost@evil.com",
        "http://localhost/path",
    ],
)
def test_remote_endpoints_rejected(url):
    with pytest.raises(ValueError, match="loopback"):
        LlamaCppBackend(url)


@pytest.mark.integration
def test_real_http_sse_protocol_without_model():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"status": "ok", "default_generation_settings": {"n_ctx": 2048}}
                ).encode()
            )

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(data)
            self.send_response(200)
            self.end_headers()
            if self.path == "/tokenize":
                self.wfile.write(b'{"tokens":[1,2,3]}')
            else:
                for chunk in [
                    {"content": "oak", "tokens": [7], "stop": False},
                    {"content": "", "tokens": [], "stop": True},
                ]:
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                    self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        backend = LlamaCppBackend(f"http://127.0.0.1:{server.server_port}")
        assert backend.metadata()["health"]["status"] == "ok"
        events = list(backend.stream("hi", GenerationConfig(max_new_tokens=4)))
        assert events[0].text == "oak" and events[0].token_count == 1
        assert requests[-1]["cache_prompt"] is False
        assert "</think>" in requests[-1]["prompt"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
