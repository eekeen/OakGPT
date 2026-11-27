"""Incremental separation of a streamed Qwen3 reply into reasoning and answer text.

Stream deltas can split ``<think>`` or ``</think>`` across chunks, so undecided text is
buffered until it can no longer be the prefix of a tag.
"""

from typing import Literal

Channel = Literal["reasoning", "answer"]
OPEN = "<think>"
CLOSE = "</think>"


class ReasoningSplitter:
    def __init__(self, expect_reasoning: bool) -> None:
        # Without thinking, the prompt already contains an empty think block.
        self._state = "start" if expect_reasoning else "answer"
        self._buffer = ""
        self._strip_newlines = False
        self._reasoning_start = False

    def feed(self, delta: str) -> list[tuple[Channel, str]]:
        self._buffer += delta
        output: list[tuple[Channel, str]] = []
        while self._buffer:
            if self._state == "start":
                stripped = self._buffer.lstrip()
                if stripped.startswith(OPEN):
                    self._buffer = stripped[len(OPEN) :]
                    self._state = "reasoning"
                    self._reasoning_start = True
                elif OPEN.startswith(stripped):
                    break  # Still possibly the opening tag.
                else:
                    self._state = "answer"
            elif self._state == "reasoning":
                if self._reasoning_start:
                    # The newline after "<think>" may arrive in a later chunk.
                    self._buffer = self._buffer.lstrip("\n")
                    if not self._buffer:
                        break
                    self._reasoning_start = False
                index = self._buffer.find(CLOSE)
                if index >= 0:
                    text = self._buffer[:index].rstrip("\n")
                    if text:
                        output.append(("reasoning", text))
                    self._buffer = self._buffer[index + len(CLOSE) :]
                    self._state = "answer"
                    self._strip_newlines = True
                    continue
                keep = _partial_suffix(self._buffer, CLOSE)
                # Trailing newlines may belong to the closing "\n</think>" separator.
                text = self._buffer[: len(self._buffer) - keep].rstrip("\n")
                if text:
                    output.append(("reasoning", text))
                self._buffer = self._buffer[len(text) :]
                break
            else:
                if self._strip_newlines:
                    self._buffer = self._buffer.lstrip("\n")
                    if not self._buffer:
                        break
                    self._strip_newlines = False
                output.append(("answer", self._buffer))
                self._buffer = ""
        return output

    def finish(self) -> list[tuple[Channel, str]]:
        """Flush buffered text, e.g. when generation stops inside the reasoning block."""
        text, self._buffer = self._buffer, ""
        if not text or (self._strip_newlines and not text.strip("\n")):
            return []
        channel: Channel = "reasoning" if self._state == "reasoning" else "answer"
        return [(channel, text)]


def _partial_suffix(text: str, tag: str) -> int:
    """Length of the longest suffix of ``text`` that is a proper prefix of ``tag``."""
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:size]):
            return size
    return 0
