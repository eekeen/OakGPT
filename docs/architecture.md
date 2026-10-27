# Architecture

```text
JSON configuration -> CLI
  train -> Tokenizer -> TokenWindows -> TransformerLM -> AdamW/AMP
                                    -> validation -> best/last checkpoint
  generate / benchmark -> InferenceBackend protocol
                          |-- ScratchBackend -> TransformerLM + checkpoint
                          `-- LlamaCppBackend -> loopback HTTP -> llama.cpp C++ -> GGUF
  benchmark -> raw response/timing records + quality scorer + VRAM sampler -> JSON
```

`src/oakgpt/model.py` contains no training loop. Attention explicitly forms Q/K/V,
scales QKᵀ by sqrt(head dimension), masks future positions, applies fp32 softmax, combines
values and projects back to model width. Pre-norm LayerNorm and residual connections
surround attention and a GELU MLP. Dropout applies during training. Position embeddings
are learned by default, with deterministic sinusoidal encoding as a configurable ablation.
The output projection shares input embedding weights. Loss is mean next-token
cross-entropy. No bidirectional Transformer library or pretrained architecture is reused.

Training uses full-length windows and drops the incomplete trailing window. Adjacent
windows share one input/target boundary token; each target is scored once. Random batches
sample windows with replacement using an independent saved generator. This fixed-step
definition avoids ambiguous epoch/resume behavior. Validation visits all complete windows
in deterministic order and weights losses by target count; it is not used for gradients.
The corpus is loaded into RAM, appropriate for Phase 1 fixtures and small datasets; larger
corpora will need a memory-mapped token dataset. No claim of distributed or large-scale
training support is made.

The checkpoint contains model/tokenizer config, tensor state, optimizer/scaler state,
step, best validation loss, corpus hashes and Python/Torch/CUDA/sampler RNG state.
Writes replace atomically in the same directory. Resume allows changing the total step
budget, validation frequency and output directory; model/data/optimizer/device settings
must match. CPU tests require bit-exact continuation. Exact cross-device or cross-version
reproduction is not guaranteed. Load trusted checkpoints only, with `weights_only=True`.

Inference yields `TokenEvent(text, token_count)`. This supports partial Unicode text and
native token counts independent of display text. Scratch inference is intentionally simple:
single sequence, no KV cache, no quantization, and a hard context budget. Its decode cost
grows with sequence length. llama.cpp owns optimized kernels, quantization and KV caching;
benchmark differences reflect whole systems as well as model differences.

Future adapters can implement the protocol without modifying the trainer. Robotics
integration belongs downstream of inference, behind a typed schema and deterministic
validator; generated strings are never executable authority.
