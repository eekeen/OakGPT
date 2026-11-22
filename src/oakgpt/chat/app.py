"""Chat configuration, optional managed llama-server process and application wiring."""

import json
import socket
import subprocess
import time
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError

from oakgpt.chat.engine import PRESETS, ChatEngine, ChatSettings, LlamaChatClient, settings_from
from oakgpt.chat.server import ChatApp, make_server
from oakgpt.chat.store import ConversationStore
from oakgpt.provenance import sha256


@dataclass(frozen=True)
class ManagedServer:
    binary: Path
    model: Path
    context: int = 8192
    gpu_layers: int = 99
    threads: int = 8
    log_dir: Path = Path("runs/chat/server")

    def command(self, port: int) -> list[str]:
        return [
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


@dataclass(frozen=True)
class ChatConfig:
    url: str
    storage: Path
    web_port: int = 8765
    system_prompt: str = ""
    defaults: ChatSettings = field(default_factory=ChatSettings)
    identity: dict[str, Any] = field(default_factory=dict)
    cache_prompt: bool = True
    managed: ManagedServer | None = None

    @classmethod
    def load(cls, path: Path) -> "ChatConfig":
        values: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        base = path.parent

        def resolve(value: str) -> Path:
            return (base / value).resolve()

        managed = None
        if values.get("managed_server"):
            server = dict(values["managed_server"])
            managed = ManagedServer(
                binary=resolve(server.pop("binary")),
                model=resolve(server.pop("model")),
                log_dir=resolve(server.pop("log_dir", "../../runs/chat/server")),
                **server,
            )
        return cls(
            url=values["llama_url"],
            storage=resolve(values["storage"]),
            web_port=values.get("web_port", 8765),
            system_prompt=values.get("system_prompt", ""),
            defaults=settings_from(values.get("defaults", {})),
            identity=values.get("identity", {}),
            cache_prompt=values.get("cache_prompt", True),
            managed=managed,
        )


def _port(url: str) -> int:
    return int(url.rsplit(":", 1)[1].rstrip("/"))


@contextmanager
def managed_llama(spec: ManagedServer, client: LlamaChatClient) -> Iterator[dict[str, Any]]:
    port = _port(client.url)
    with socket.socket() as probe:  # Refuse to adopt a server we did not start.
        probe.bind(("127.0.0.1", port))
    directory = spec.log_dir / datetime.now().strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=False)
    command = spec.command(port)
    (directory / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    with (
        (directory / "stdout.txt").open("w", encoding="utf-8") as stdout,
        (directory / "stderr.txt").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 180
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"llama-server exited; see {directory / 'stderr.txt'}")
                try:
                    props = client.json("/props")
                    if client.json("/health").get("status") == "ok":
                        if Path(props["model_path"]).resolve() != spec.model.resolve():
                            raise RuntimeError("Server model path differs from configured model")
                        break
                except (URLError, ConnectionError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("llama-server readiness timed out")
                time.sleep(0.5)
            yield {"log_dir": str(directory), "command": command}
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run_chat(config: ChatConfig, open_browser: bool = True) -> None:
    client = LlamaChatClient(config.url, cache_prompt=config.cache_prompt)
    identity = dict(config.identity)
    if config.managed is not None:
        print("Hashing model file for provenance ...", flush=True)
        identity["gguf_sha256"] = sha256(config.managed.model)
        identity["gguf_filename"] = config.managed.model.name
    with _maybe_managed(config, client) as launch:
        if launch:
            identity["managed_server"] = launch

        def status() -> dict[str, Any]:
            props = client.json("/props")
            return {
                "ready": client.json("/health").get("status") == "ok",
                "model_path": Path(props.get("model_path", "")).name,
                "context_length": props["default_generation_settings"]["n_ctx"],
                "build": props.get("build_info"),
                "identity": identity,
                "cache_prompt": config.cache_prompt,
                "presets": {name: asdict(preset) for name, preset in PRESETS.items()},
                "system_prompt": config.system_prompt,
            }

        app = ChatApp(
            ConversationStore(config.storage),
            ChatEngine(client).respond,
            status,
            config.defaults,
            config.system_prompt,
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


@contextmanager
def _maybe_managed(config: ChatConfig, client: LlamaChatClient) -> Iterator[dict[str, Any]]:
    if config.managed is None:
        yield {}
    else:
        with managed_llama(config.managed, client) as launch:
            yield launch
