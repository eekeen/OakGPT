"""Document mode in the web server and the document library; no model needed."""

import json
import threading

import pytest

from oakgpt.chat.app import ChatConfig, DocumentLibrary, DocumentsConfig, ManagedServer
from oakgpt.chat.documents import NOT_FOUND
from oakgpt.chat.engine import ChatEngine, ChatSettings, LlamaChatClient
from oakgpt.chat.server import ChatApp, make_server
from oakgpt.chat.store import ConversationStore
from tests.test_chat_server import CONTROL, FakeLlama, request, sse


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "ports.md").write_text(
        "# Ports\n\nThe vision server listens on port 18081.", encoding="utf-8"
    )
    (folder / "other.md").write_text("# Other\n\nUnrelated text about oak trees.", encoding="utf-8")
    config = DocumentsConfig(folder, tmp_path / "index.json", method="bm25", top_k=2)
    library = DocumentLibrary(config, tmp_path / "hash-cache.json")
    library.start()
    library.reindex()
    return library


@pytest.fixture
def served(tmp_path, library):
    fake = FakeLlama(n_ctx=8192)
    app = ChatApp(
        ConversationStore(tmp_path / "conversations"),
        ChatEngine(LlamaChatClient(fake.url)).respond,
        lambda: {"ready": True},
        ChatSettings(),
        "",
        documents=library,
    )
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, app, fake
    server.shutdown()
    server.server_close()
    thread.join()
    fake.close()


def prompt_text(fake):
    prompt = [data for path, data in fake.requests if path == "/completion"][-1]["prompt"]
    return "".join(chr(t) for t in prompt if t < CONTROL)


def test_library_indexes_and_searches(library):
    status = library.status()
    assert status["state"] == "ready" and status["documents"][0]["path"] == "other.md"
    assert status["chunks"] == 2 and library.index is not None
    assert [h.chunk.path for h in library.search("vision port")] == ["ports.md"]


def test_library_upload_rules(library):
    assert library.add("notes.md", "# Notes\n\nNew.") == "notes.md"
    library.reindex()
    assert [d["path"] for d in library.status()["documents"]] == [
        "notes.md",
        "other.md",
        "ports.md",
    ]
    for name in ("../evil.md", "a/b.md", "x.exe", ".hidden.md", "notes.md"):
        with pytest.raises(ValueError):
            library.add(name, "text")
    with pytest.raises(ValueError):
        library.add("empty.md", "   ")


def test_reply_with_documents_grounds_the_prompt_and_stores_sources(served):
    server, app, fake = served
    conversation = app.store.create()
    path = f"/api/conversations/{conversation['id']}/reply"
    response, data = request(
        server, "POST", path, {"content": "Which port has vision?", "documents": True}
    )
    assert response.status == 200
    events = sse(data)
    meta = events[0][1]
    assert meta["sources"][0]["path"] == "ports.md" and meta["sources"][0]["n"] == 1
    sent = prompt_text(fake)
    assert '<source id="1" location="ports.md > Ports">' in sent and NOT_FOUND in sent
    assert sent.count("Question: Which port has vision?") == 1
    stored = app.store.get(conversation["id"])["messages"]
    assert stored[0]["content"] == "Which port has vision?"  # The user's words, unchanged.
    assert stored[1]["meta"]["sources"][0]["path"] == "ports.md"
    response, data = request(server, "POST", path, {"content": "And now?"})
    assert response.status == 200 and "<source" not in prompt_text(fake)


def test_documents_api(served, library):
    server, _, _ = served
    response, data = request(server, "GET", "/api/documents")
    status = json.loads(data)
    assert response.status == 200 and status["available"] and status["chunks"] == 2
    response, data = request(server, "POST", "/api/documents", {"name": "new.txt", "text": "x"})
    assert response.status == 201 and json.loads(data)["saved"] == "new.txt"
    library._build.acquire()  # Wait for the background rebuild the upload started.
    library._build.release()
    response, data = request(server, "POST", "/api/documents", {"name": "../x.md", "text": "x"})
    assert response.status == 400
    response, data = request(server, "POST", "/api/documents/reindex", {})
    assert response.status == 202


def test_documents_refused_without_library_or_with_images(tmp_path, served):
    fake = FakeLlama()
    app = ChatApp(
        ConversationStore(tmp_path / "plain"),
        ChatEngine(LlamaChatClient(fake.url)).respond,
        lambda: {"ready": True},
        ChatSettings(),
    )
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conversation = app.store.create()
        path = f"/api/conversations/{conversation['id']}/reply"
        response, _ = request(server, "POST", path, {"content": "q", "documents": True})
        assert response.status == 400
        response, data = request(server, "GET", "/api/documents")
        assert json.loads(data) == {"available": False}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        fake.close()


def test_search_failure_rolls_back_the_user_message(served, library):
    server, app, _ = served
    library.index = None
    library.state = "indexing"
    conversation = app.store.create()
    path = f"/api/conversations/{conversation['id']}/reply"
    response, data = request(server, "POST", path, {"content": "q", "documents": True})
    assert response.status == 502 and b"not ready" in data
    assert app.store.get(conversation["id"])["messages"] == []


def test_documents_config_and_embedding_server_flags(tmp_path):
    config = {
        "llama_url": "http://127.0.0.1:18080",
        "storage": "conversations",
        "documents": {
            "folder": "docs",
            "index": "index.json",
            "method": "hybrid",
            "top_k": 4,
            "embedding": {
                "llama_url": "http://127.0.0.1:18082",
                "managed_server": {"binary": "llama-server", "model": "e.gguf", "gpu_layers": 0},
                "identity": {"model": "Qwen/Qwen3-Embedding-0.6B"},
            },
        },
    }
    path = tmp_path / "chat.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    documents = ChatConfig.load(path).documents
    assert documents is not None and documents.top_k == 4 and documents.folder == tmp_path / "docs"
    managed = documents.embedding.managed
    command = managed.command(18082)
    assert command[command.index("--pooling") + 1] == "last" and "--embedding" in command
    assert command[command.index("-ngl") + 1] == "0"
    assert "--embedding" not in ManagedServer(tmp_path / "b", tmp_path / "m").command(1)
    with pytest.raises(ValueError, match="needs an embedding"):
        DocumentsConfig(tmp_path, tmp_path / "i.json", method="dense")
    with pytest.raises(ValueError):
        DocumentsConfig(tmp_path, tmp_path / "i.json", method="bm25", top_k=0)
