import json
from bisect import bisect_right
from pathlib import Path

import torch
from torch import Tensor
from torch.utils.data import Dataset

from oakgpt.tokenization import Tokenizer


class TokenWindows(Dataset[tuple[Tensor, Tensor]]):
    """Non-overlapping targets, with one shared boundary input token between windows."""

    def __init__(self, tokens: list[int], context_length: int) -> None:
        self.tokens = torch.tensor(tokens, dtype=torch.long)
        self.context_length = context_length
        if context_length < 1 or len(tokens) <= context_length:
            raise ValueError("Corpus must contain at least context_length + 1 tokens")

    def __len__(self) -> int:
        return (len(self.tokens) - 1) // self.context_length

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        if not 0 <= index < len(self):
            raise IndexError(index)
        start = index * self.context_length
        window = self.tokens[start : start + self.context_length + 1]
        return window[:-1], window[1:]


class DocumentWindows(Dataset[tuple[Tensor, Tensor]]):
    """Full windows within documents; never cross a document boundary."""

    def __init__(self, documents: list[str], tokenizer: Tokenizer, context_length: int) -> None:
        self.context_length = context_length
        self.documents = []
        self.ends = []
        count = 0
        for text in documents:
            tokens = torch.tensor(tokenizer.encode(text, bos=True, eos=True), dtype=torch.long)
            windows = (len(tokens) - 1) // context_length
            if windows:
                self.documents.append(tokens)
                count += windows
                self.ends.append(count)
        if not count:
            raise ValueError("No complete document windows")

    def __len__(self) -> int:
        return self.ends[-1]

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor]:
        if not 0 <= index < len(self):
            raise IndexError(index)
        document = bisect_right(self.ends, index)
        local = index - (self.ends[document - 1] if document else 0)
        start = local * self.context_length
        window = self.documents[document][start : start + self.context_length + 1]
        return window[:-1], window[1:]


def read_documents(path: Path, data_format: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if data_format == "text":
        return [text]
    return [json.loads(line)["text"] for line in text.splitlines() if line.strip()]


def load_windows(
    path: Path, tokenizer: Tokenizer, context_length: int, data_format: str
) -> TokenWindows | DocumentWindows:
    documents = read_documents(path, data_format)
    if data_format == "text":
        return TokenWindows(tokenizer.encode(documents[0], bos=True, eos=True), context_length)
    return DocumentWindows(documents, tokenizer, context_length)
