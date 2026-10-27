# Working on OakGPT

- Keep scratch training (`training/`) separate from inference (`inference/`).
- Primary inference is local. Never upload prompts, datasets, or weights to a cloud API.
- Run `python -m pytest`, `ruff check .`, `ruff format --check .`, and `mypy` before committing.
- Tests must work on CPU without model downloads. Mark physical GPU/GGUF tests `hardware`.
- Never invent performance numbers. Preserve raw benchmark records, configuration, hashes,
  environment, and measurement limitations. CPU smoke results are not GPU results.
- Keep evaluation examples out of training data. Changing a dataset requires a version change.
- Checkpoint loading is restricted to tensor/primitive data via `weights_only=True`.
- Do not commit models, checkpoints, secrets, or large external datasets.
- Future robotics output is untrusted data: never execute model text as commands.
- Prefer small explicit implementations and standard-library dependencies.
