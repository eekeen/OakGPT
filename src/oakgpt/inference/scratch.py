import codecs
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import torch

from oakgpt.config import ModelConfig
from oakgpt.inference.base import GenerationConfig, TokenEvent
from oakgpt.model import TransformerLM
from oakgpt.provenance import sha256
from oakgpt.tokenization import Tokenizer
from oakgpt.training.checkpoint import load_checkpoint


class ScratchBackend:
    """Single-sequence autoregressive inference; recomputes context, without a KV cache."""

    def __init__(self, checkpoint: Path, device: str = "cpu", cpu_threads: int = 2) -> None:
        torch.set_num_threads(cpu_threads)
        self.device = torch.device(device)
        state = load_checkpoint(checkpoint)
        self.model = TransformerLM(ModelConfig(**state["model_config"])).to(self.device)
        self.model.load_state_dict(state["model"])
        self.model.eval()
        self.tokenizer = Tokenizer.from_dict(state["tokenizer"])
        self.checkpoint_hash = sha256(checkpoint)

    def metadata(self) -> dict[str, Any]:
        return {
            "backend": "scratch",
            "checkpoint_sha256": self.checkpoint_hash,
            "device": str(self.device),
            "model_config": vars(self.model.config),
            "tokenizer": self.tokenizer.kind,
            "kv_cache": False,
            "cpu_threads": torch.get_num_threads(),
            "cuda_device_name": torch.cuda.get_device_name(self.device)
            if self.device.type == "cuda"
            else None,
            "parameters": sum(p.numel() for p in self.model.parameters()),
        }

    def stream(self, prompt: str, config: GenerationConfig) -> Iterator[TokenEvent]:
        ids = self.tokenizer.encode(prompt, bos=True)
        # Reject rather than silently truncate: benchmark workloads must stay defined.
        if len(ids) + config.max_new_tokens > self.model.config.context_length:
            raise ValueError("Prompt plus generation budget exceeds the scratch context length")
        generator = torch.Generator(device=self.device).manual_seed(config.seed)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        for _ in range(config.max_new_tokens):
            # Exit inference_mode before yielding, to avoid changing the caller's autograd state.
            with torch.inference_mode():
                inputs = torch.tensor([ids], device=self.device, dtype=torch.long)
                logits = self.model(inputs)[0, -1].float()
                logits[self.tokenizer.bos_id] = float("-inf")
                if config.temperature == 0:
                    next_id = int(logits.argmax())
                else:
                    logits = logits / config.temperature
                    if config.top_k:
                        threshold = torch.topk(logits, min(config.top_k, logits.numel())).values[-1]
                        logits[logits < threshold] = float("-inf")
                    next_id = int(torch.multinomial(logits.softmax(-1), 1, generator=generator))
            ids.append(next_id)
            if self.tokenizer.kind == "byte" and next_id >= 3:
                delta = decoder.decode(bytes([next_id - 3]))
            else:
                delta = self.tokenizer.decode([next_id])
            yield TokenEvent(delta, 1)
            if next_id == self.tokenizer.eos_id:
                break
        tail = decoder.decode(b"", final=True)
        if tail:
            yield TokenEvent(tail, 0)
