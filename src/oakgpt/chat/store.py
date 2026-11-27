"""Conversation persistence: one JSON document per conversation, replaced atomically.

Conversations are private user data. The default location is under the ignored ``runs/``
directory so they are never committed.
"""

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FORMAT = "oakgpt-chat-v1"  # User messages may carry an optional "images" list.
_ID = re.compile(r"^[0-9a-f]{32}$")
_IMAGE_ID = re.compile(r"^[0-9a-f]{64}$")
TITLE_LENGTH = 60
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Formats decoded by llama.cpp (stb_image) that the UI produces; identified by content.
IMAGE_TYPES = {b"\x89PNG\r\n\x1a\n": ("image/png", "png"), b"\xff\xd8\xff": ("image/jpeg", "jpg")}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def title_from(text: str) -> str:
    words = " ".join(text.split())
    return words if len(words) <= TITLE_LENGTH else words[: TITLE_LENGTH - 1].rstrip() + "…"


def image_type(data: bytes) -> tuple[str, str]:
    """Return (media type, extension) from the file signature; reject anything else."""
    for signature, kind in IMAGE_TYPES.items():
        if data.startswith(signature):
            return kind
    raise ValueError("Images must be PNG or JPEG")


def _atomic_write(directory: Path, target: Path, data: bytes) -> None:
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class ImageStore:
    """Image files per conversation: ``<root>/<conversation id>/<sha256>.<ext>``.

    Images are named by content hash, so the same image attached twice is stored once,
    and deleting a conversation removes its directory.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _directory(self, conversation_id: str) -> Path:
        if not _ID.fullmatch(conversation_id):
            raise KeyError(conversation_id)
        return self.root / conversation_id

    def save(self, conversation_id: str, data: bytes) -> dict[str, str]:
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"Each image must be 1 byte to {MAX_IMAGE_BYTES // 2**20} MiB")
        media_type, extension = image_type(data)
        image_id = hashlib.sha256(data).hexdigest()
        directory = self._directory(conversation_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{image_id}.{extension}"
        if not target.is_file():
            _atomic_write(directory, target, data)
        return {"id": image_id, "type": media_type}

    def load(self, conversation_id: str, image_id: str) -> tuple[bytes, str]:
        if not _IMAGE_ID.fullmatch(image_id):
            raise KeyError(image_id)
        directory = self._directory(conversation_id)
        for media_type, extension in IMAGE_TYPES.values():
            path = directory / f"{image_id}.{extension}"
            if path.is_file():
                return path.read_bytes(), media_type
        raise KeyError(image_id)

    def delete_conversation(self, conversation_id: str) -> None:
        directory = self._directory(conversation_id)
        if directory.is_dir():
            for path in directory.iterdir():
                path.unlink()
            directory.rmdir()


class ConversationStore:
    def __init__(self, root: Path, images: Path | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.images = ImageStore(images if images is not None else root / "images")
        self._lock = threading.Lock()

    def _path(self, conversation_id: str) -> Path:
        # A strict ID pattern prevents path traversal through the HTTP API.
        if not _ID.fullmatch(conversation_id):
            raise KeyError(conversation_id)
        return self.root / f"{conversation_id}.json"

    def _write(self, conversation: dict[str, Any]) -> None:
        data = json.dumps(conversation, ensure_ascii=False, indent=1).encode("utf-8")
        _atomic_write(self.root, self._path(conversation["id"]), data)

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
                conversation["title"] = title_from(message["content"]) or "Image"
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
            self.images.delete_conversation(conversation_id)

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
                    "images": any(m.get("images") for m in conversation["messages"]),
                }
            )
        return sorted(summaries, key=lambda item: item["updated"], reverse=True)
