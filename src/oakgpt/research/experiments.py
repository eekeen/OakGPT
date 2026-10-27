import itertools
import json
import statistics
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from oakgpt.config import ModelConfig, TrainConfig
from oakgpt.inference.scratch import ScratchBackend
from oakgpt.provenance import environment, sha256
from oakgpt.training.data import load_windows
from oakgpt.training.trainer import evaluate, train


def run_suite(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    base = TrainConfig.load(path.parent / spec["base_config"])
    root = (path.parent / spec["output_dir"]).resolve()
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)
    runs = []
    grid = spec["grid"]
    for depth, width, position, seed in itertools.product(
        grid["n_layers"], grid["d_model"], grid["positional_encoding"], grid["seed"]
    ):
        name = f"L{depth}-D{width}-{position}-S{seed}"
        model = ModelConfig(
            **(
                asdict(base.model)
                | {"n_layers": depth, "d_model": width, "positional_encoding": position}
            )
        )
        config = replace(base, model=model, seed=seed, output_dir=str(root / name))
        (root / f"{name}.json").write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
        last = train(config)
        backend = ScratchBackend(last.with_name("best.pt"), config.device)
        validation = load_windows(
            Path(config.validation_path),
            backend.tokenizer,
            model.context_length,
            config.data_format,
        )
        full_validation = evaluate(backend.model, validation, config.batch_size, backend.device)
        del backend
        session = json.loads((last.parent / f"session-1-{config.steps}.json").read_text())
        metrics = [
            json.loads(line) for line in (last.parent / "metrics.jsonl").read_text().splitlines()
        ]
        record = {
            "name": name,
            "depth": depth,
            "width": width,
            "position": position,
            "seed": seed,
            "config": config.to_dict(),
            "full_validation": full_validation,
            "checkpoint_sha256": sha256(last.with_name("best.pt")),
            "session": session,
            "convergence": metrics,
        }
        runs.append(record)
        (root / f"{name}-result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    groups = aggregate_runs(runs)
    selected = min(groups, key=lambda g: g["validation_nll_mean"])
    # Touch the held-out language-model test only after selecting by mean full validation NLL.
    test_path = (path.parent / spec["test_path"]).resolve()
    test_results = []
    for run in runs:
        if (run["depth"], run["width"], run["position"]) == (
            selected["depth"],
            selected["width"],
            selected["position"],
        ):
            backend = ScratchBackend(root / run["name"] / "best.pt", base.device)
            data = load_windows(
                test_path, backend.tokenizer, base.model.context_length, base.data_format
            )
            test_results.append(
                {
                    "seed": run["seed"],
                    **evaluate(backend.model, data, base.batch_size, backend.device),
                }
            )
    result = {
        "schema_version": 1,
        "spec": spec,
        "spec_sha256": sha256(path),
        "environment": environment(),
        "runs": runs,
        "groups": groups,
        "selected_by_validation": selected,
        "test_sha256": sha256(test_path),
        "selected_test_results": test_results,
    }
    (root / "suite.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    return result


def aggregate_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int, str], list[dict[str, Any]]] = {}
    for run in runs:
        groups.setdefault((run["depth"], run["width"], run["position"]), []).append(run)
    output = []
    for (depth, width, position), records in sorted(groups.items()):
        if len({r["seed"] for r in records}) != len(records):
            raise ValueError("Duplicate seed in architecture group")
        losses = [float(r["full_validation"]["nll"]) for r in records]
        output.append(
            {
                "depth": depth,
                "width": width,
                "position": position,
                "seeds": [r["seed"] for r in records],
                "validation_nll_mean": statistics.mean(losses),
                "validation_nll_sd": statistics.stdev(losses) if len(losses) > 1 else None,
                "compute_seconds_mean": statistics.mean(
                    r["session"]["compute_seconds"] for r in records
                ),
                "peak_allocated_bytes_max": max(
                    (r["session"]["cuda_peak_allocated_bytes"] or 0) for r in records
                )
                or None,
            }
        )
    return output
