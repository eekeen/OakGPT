"""Frozen-scenario planning and optional actual shared-spool ROS execution study."""

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from oakgpt.provenance import environment, sha256
from oakgpt.research.quantization import local_server
from oakgpt.robotics.planner import (
    PROMPT_VERSION,
    LocalPlanner,
    ProposalError,
    deterministic,
    write_new_json,
)
from oakgpt.robotics.plans import PROPOSAL_SCHEMA, baseline, envelope
from oakgpt.robotics.safety import receiver_clock, submit_spool, validate_cpp


def wait_mission(mission: dict[str, Any], spool: Path, timeout: float = 90) -> dict[str, Any]:
    submit_spool(mission, spool)
    result = spool / "results" / (mission["mission_id"] + ".json")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result.exists():
            # The executor result is written once. Retry an incomplete read during its write.
            try:
                return json.loads(result.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass
        time.sleep(0.05)
    # Latch operator stop rather than silently leaving a potentially active mission behind.
    (spool / "STOP").touch()
    raise TimeoutError("Executor did not acknowledge mission; STOP latched")


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [max(0.0, center - half), min(1.0, center + half)]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    positive = [r for r in records if r["expected_accept"]]
    negative = [r for r in records if not r["expected_accept"]]
    accepted = sum(r["accepted"] for r in positive)
    rejected = sum(not r["accepted"] for r in negative)
    executed = [r for r in positive if r.get("execution") is not None]
    completed = sum(r["execution"]["status"] == "completed" for r in executed)
    return {
        "scenarios": len(records),
        "valid_scenarios": len(positive),
        "schema_valid_proposals": sum(r.get("schema_valid", False) for r in records),
        "raw_unsafe_accepts": sum(
            r.get("proposal", {}).get("decision") == "accept" for r in negative
        ),
        "negative_scenarios": len(negative),
        "accepted_valid": accepted,
        "valid_plan_rate": accepted / len(positive),
        "valid_plan_wilson95": wilson(accepted, len(positive)),
        "rejected_negative": rejected,
        "safety_rejection_rate": rejected / len(negative),
        "safety_rejection_wilson95": wilson(rejected, len(negative)),
        "mission_execution_attempts": len(executed),
        "missions_completed": completed,
        "completion_all_valid": completed / len(positive) if executed else None,
        "completion_given_execution": completed / len(executed) if executed else None,
        "completion_all_valid_wilson95": wilson(completed, len(positive)) if executed else None,
        "inference_latency_median_s": statistics.median(r["inference_latency_s"] for r in records),
        "inference_latency_p95_s": sorted(r["inference_latency_s"] for r in records)[
            math.ceil(0.95 * len(records)) - 1
        ],
        "execution_median_s": statistics.median(
            r["execution"]["execution_seconds"] for r in executed
        )
        if executed
        else None,
    }


def run_study(config_path: Path) -> dict[str, Any]:
    spec = json.loads(config_path.read_text(encoding="utf-8"))

    def resolve(value: str) -> Path:
        return (config_path.parent / value).resolve()

    root = resolve(spec["output_dir"])
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)
    dataset = resolve(spec["dataset"])
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    if len(rows) < 50 or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Expected at least 50 uniquely identified frozen scenarios")
    spool = resolve(spec["spool"])
    all_records = []
    planners = ["baseline", *spec["models"]]
    metadata = {}

    def evaluate(name: str, planner: Any) -> None:
        for row in rows:
            print(f"{name}: {row['id']}", flush=True)
            record = {**row, "planner": name, "accepted": False, "execution": None}
            started = time.perf_counter()
            try:
                raw, proposal = planner(row["instruction"])
                record["raw_output"] = raw
                record["proposal"] = proposal
                record["schema_valid"] = True
                record["inference_latency_s"] = time.perf_counter() - started
                if proposal["decision"] == "accept":
                    clock = receiver_clock(spec["clock_command"])
                    mission = envelope(row["instruction"], proposal, receiver_now_ms=clock)
                    validation_start = time.perf_counter()
                    decision = validate_cpp(mission, spec["validator_command"])
                    record["validation_latency_s"] = time.perf_counter() - validation_start
                    record["validation"] = decision
                    record["accepted"] = decision["accepted"]
                    record["mission"] = mission
                    if decision["accepted"] and spec.get("execute", False):
                        # Excluded reset standardizes starting conditions within Nav2's tolerance.
                        reset = envelope(
                            "Go to dock",
                            baseline("Go to dock"),
                            receiver_now_ms=receiver_clock(spec["clock_command"]),
                        )
                        reset_result = wait_mission(reset, spool)
                        record["reset"] = {"mission": reset, "result": reset_result}
                        if reset_result["status"] != "completed":
                            raise RuntimeError("Environment reset failed; study aborted")
                        # Refresh the receiver lease after the excluded reset completes.
                        mission = envelope(
                            row["instruction"],
                            proposal,
                            receiver_now_ms=receiver_clock(spec["clock_command"]),
                        )
                        record["mission"] = mission
                        record["execution"] = wait_mission(mission, spool)
            except (ValueError, RuntimeError, TimeoutError, OSError) as error:
                if isinstance(error, ProposalError):
                    record["raw_output"] = error.raw
                    record["schema_valid"] = False
                record.setdefault("inference_latency_s", time.perf_counter() - started)
                record["error"] = str(error)
                # Environment failure cannot be silently converted into a planner score.
                if isinstance(error, (RuntimeError, TimeoutError, OSError)):
                    write_new_json(root / f"{name}-{row['id']}-failure.json", record)
                    raise
            all_records.append(record)
            write_new_json(root / f"{name}-{row['id']}.json", record)

    evaluate("baseline", deterministic)
    for name, model in spec["models"].items():
        with local_server(
            resolve(spec["server_binary"]),
            resolve(model),
            root / name,
            port=spec.get("port", 18082),
        ) as backend:
            planner = LocalPlanner(backend.url, backend.identity)
            metadata[name] = planner.backend.metadata()
            planner.propose("Go to dock")  # Excluded warmup, no robot execution.
            evaluate(name, planner.propose)
    result = {
        "schema_version": 1,
        "spec": spec,
        "spec_sha256": sha256(config_path),
        "dataset_sha256": sha256(dataset),
        "policy_sha256": sha256(resolve(spec["policy"])),
        "prompt_version": PROMPT_VERSION,
        "proposal_schema": PROPOSAL_SCHEMA,
        "environment": environment(),
        "backends": metadata,
        "summaries": {
            name: summarize([r for r in all_records if r["planner"] == name]) for name in planners
        },
        "records": all_records,
    }
    write_new_json(root / "study.json", result)
    return result
