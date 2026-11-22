"""Qwen3 ChatML rendering as typed segments.

The rendering mirrors the ``tokenizer.chat_template`` embedded in the Qwen3 GGUF for the
subset OakGPT uses: one optional leading system message, alternating user/assistant
turns, no tools. Earlier assistant turns are rendered without their reasoning block,
exactly as the upstream template does.

Each segment carries a ``control`` flag. Control segments contain the template's own
delimiters and are tokenized with special-token parsing; message content is tokenized
as plain text, so a user typing ``<|im_end|>`` cannot forge a role boundary.
"""

from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]
ROLES: tuple[str, ...] = ("system", "user", "assistant")


@dataclass(frozen=True)
class Message:
    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"Unknown chat role: {self.role!r}")
        if not isinstance(self.content, str):
            raise TypeError("Message content must be a string")


@dataclass(frozen=True)
class Segment:
    text: str
    control: bool


def strip_reasoning(content: str) -> str:
    """Drop a ``<think>...</think>`` prefix, using the same split rule as the GGUF template."""
    if "</think>" in content:
        return content.split("</think>")[-1].lstrip("\n")
    return content


def validate_conversation(messages: list[Message]) -> None:
    if not messages:
        raise ValueError("A conversation needs at least one user message")
    body = messages[1:] if messages[0].role == "system" else messages
    if any(message.role == "system" for message in body):
        raise ValueError("Only the first message may be a system message")
    if not body or body[-1].role != "user":
        raise ValueError("The last message must be a user message")
    for index, message in enumerate(body):
        expected = "user" if index % 2 == 0 else "assistant"
        if message.role != expected:
            raise ValueError("User and assistant messages must alternate, starting with user")


def render_qwen3(messages: list[Message], *, thinking: bool) -> list[Segment]:
    """Render a conversation ending in a user turn, followed by the generation prompt."""
    validate_conversation(messages)
    segments: list[Segment] = []
    for message in messages:
        content = message.content
        if message.role == "assistant":
            content = strip_reasoning(content)
        segments.append(Segment(f"<|im_start|>{message.role}\n", True))
        if content:
            segments.append(Segment(content, False))
        segments.append(Segment("<|im_end|>\n", True))
    segments.append(Segment("<|im_start|>assistant\n", True))
    if not thinking:
        # Equivalent to the template's ``enable_thinking=false`` branch.
        segments.append(Segment("<think>\n\n</think>\n\n", True))
    return segments


def render_text(segments: list[Segment]) -> str:
    return "".join(segment.text for segment in segments)
