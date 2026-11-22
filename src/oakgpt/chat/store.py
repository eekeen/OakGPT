"""Conversation persistence: one JSON document per conversation, replaced atomically.

Conversations are private user data. The default location is under the ignored ``runs/``
directory so they are never committed.
"""

import json
import os
import re
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FORMAT = "oakgpt-chat-v1"
_ID = re.compile(r"^[0-9a-f]{32}$")
TITLE_LENGTH = 60


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def title_from(text: str) -> str:
    words = " ".join(text.split())
    return words if len(words) <= TITLE_LENGTH else words[: TITLE_LENGTH - 1].rstrip() + "…"


class ConversationStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, conversation_id: str) -> Path:
        # A strict ID pattern prevents path traversal through the HTTP API.
        if not _ID.fullmatch(conversation_id):
            raise KeyError(conversation_id)
        return self.root / f"{conversation_id}.json"

    def _write(self, conversation: dict[str, Any]) -> None:
        path = self._path(conversation["id"])
        handle, temporary = tempfile.mkstemp(dir=self.root, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(conversation, stream, ensure_ascii=False, indent=1)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def create(self, system_prompt: str = "") -> dict[str, Any]:
        stamp = now()
        conversation: dict[str, Any] = {
            "format": FORMAT,
            "id": uuid.uuid4().hex,
            "title": "New chat",
            "created": stamp,
            "updated": stamp,
            "system_prompt": system_prompt,
            "messages": [],
        }
        with self._lock:
            self._write(conversation)
        return conversation

    def get(self, conversation_id: str) -> dict[str, Any]:
        path = self._path(conversation_id)
        if not path.is_file():
            raise KeyError(conversation_id)
        conversation: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if conversation.get("format") != FORMAT:
            raise ValueError(f"Unsupported conversation format in {path.name}")
        return conversation

    def save(self, conversation: dict[str, Any]) -> None:
        conversation["updated"] = now()
        with self._lock:
            self._write(conversation)

    def append(self, conversation_id: str, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            conversation = self.get(conversation_id)
            if message["role"] == "user" and not conversation["messages"]:
                conversation["title"] = title_from(message["content"])
            conversation["messages"].append(message)
            conversation["updated"] = now()
            self._write(conversation)
        return conversation

    def drop_trailing_assistant(self, conversation_id: str) -> dict[str, Any]:
        with self._lock:
            conversation = self.get(conversation_id)
            messages = conversation["messages"]
            if messages and messages[-1]["role"] == "assistant":
                messages.pop()
                conversation["updated"] = now()
                self._write(conversation)
        return conversation

    def delete(self, conversation_id: str) -> None:
        path = self._path(conversation_id)
        with self._lock:
            if not path.is_file():
                raise KeyError(conversation_id)
            path.unlink()

    def list(self) -> list[dict[str, Any]]:
        summaries = []
        for path in self.root.glob("*.json"):
            if not _ID.fullmatch(path.stem):
                continue
            try:
                conversation = self.get(path.stem)
            except (ValueError, json.JSONDecodeError):
                continue  # Unreadable files are left untouched for manual inspection.
            summaries.append(
                {
                    "id": conversation["id"],
                    "title": conversation["title"],
                    "updated": conversation["updated"],
                    "messages": len(conversation["messages"]),
                }
            )
        return sorted(summaries, key=lambda item: item["updated"], reverse=True)
