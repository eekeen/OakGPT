"""Explicit pre-norm decoder Transformer with tied embeddings and causal attention."""

import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from oakgpt.config import ModelConfig


class CausalSelfAttention(nn.Module):
    mask: Tensor

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.n_heads = config.n_heads
        self.head_dim = config.d_model // config.n_heads
        self.qkv = nn.Linear(config.d_model, 3 * config.d_model, bias=False)
        self.projection = nn.Linear(config.d_model, config.d_model, bias=False)
        self.dropout = nn.Dropout(config.dropout)
        self.register_buffer(
            "mask",
            torch.ones(config.context_length, config.context_length, dtype=torch.bool).tril(),
            persistent=False,
        )

    def forward(self, x: Tensor) -> Tensor:
        batch, length, width = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        q, k, v = [
            t.view(batch, length, self.n_heads, self.head_dim).transpose(1, 2) for t in (q, k, v)
        ]
        scores = (q @ k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        scores = scores.masked_fill(~self.mask[:length, :length], float("-inf"))
        # Softmax in fp32 avoids reduced-precision instability.
        weights = self.dropout(F.softmax(scores.float(), dim=-1).to(x.dtype))
        output = (weights @ v).transpose(1, 2).contiguous().view(batch, length, width)
        return self.dropout(self.projection(output))  # type: ignore[no-any-return]


class DecoderBlock(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.attention_norm = nn.LayerNorm(config.d_model)
        self.attention = CausalSelfAttention(config)
        self.ff_norm = nn.LayerNorm(config.d_model)
        self.feed_forward = nn.Sequential(
            nn.Linear(config.d_model, config.ff_multiplier * config.d_model),
            nn.GELU(),
            nn.Linear(config.ff_multiplier * config.d_model, config.d_model),
            nn.Dropout(config.dropout),
        )

    def forward(self, x: Tensor) -> Tensor:
        x = x + self.attention(self.attention_norm(x))
        return x + self.feed_forward(self.ff_norm(x))  # type: ignore[no-any-return]


class TransformerLM(nn.Module):
    sinusoidal: Tensor

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.d_model)
        self.position_embedding = nn.Embedding(config.context_length, config.d_model)
        positions = torch.arange(config.context_length).unsqueeze(1)
        frequencies = torch.exp(
            torch.arange(0, config.d_model, 2) * (-math.log(10000.0) / config.d_model)
        )
        encoding = torch.zeros(config.context_length, config.d_model)
        encoding[:, 0::2] = torch.sin(positions * frequencies)
        encoding[:, 1::2] = torch.cos(positions * frequencies[: config.d_model // 2])
        self.register_buffer("sinusoidal", encoding, persistent=False)
        if config.positional_encoding == "sinusoidal":
            self.position_embedding.requires_grad_(False)
        self.dropout = nn.Dropout(config.dropout)
        self.blocks = nn.Sequential(*(DecoderBlock(config) for _ in range(config.n_layers)))
        self.final_norm = nn.LayerNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)
        self.apply(self._initialize)
        self.lm_head.weight = self.token_embedding.weight

    @staticmethod
    def _initialize(module: nn.Module) -> None:
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(self, tokens: Tensor) -> Tensor:
        if tokens.ndim != 2 or not 1 <= tokens.shape[1] <= self.config.context_length:
            raise ValueError("Expected [batch, length] with length inside context window")
        length = tokens.shape[1]
        if self.config.positional_encoding == "learned":
            position = self.position_embedding(torch.arange(length, device=tokens.device))
        else:
            position = self.sinusoidal[:length]
        x = self.dropout(self.token_embedding(tokens) + position)
        return self.lm_head(self.final_norm(self.blocks(x)))  # type: ignore[no-any-return]

    def loss(self, inputs: Tensor, targets: Tensor) -> Tensor:
        logits = self(inputs)
        return F.cross_entropy(logits.reshape(-1, self.config.vocab_size), targets.reshape(-1))
