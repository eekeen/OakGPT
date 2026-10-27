import torch
from torch import Tensor
from torch.utils.data import Dataset


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
