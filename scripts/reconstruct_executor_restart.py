"""Read-only reconstruction; missing heartbeat/authorization records stay unavailable."""

import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def reconstruct(archive):
    with tarfile.open(archive) as bundle:
        files = {m.name: m for m in bundle.getmembers() if m.isfile()}

        def read(suffix):
            matches = [m for name, m in files.items() if name.endswith(suffix)]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one {suffix}, got {len(matches)}")
            return bundle.extractfile(matches[0]).read().decode()

        result = json.loads(read("/executor_restart/result.json"))
        trace = [json.loads(line) for line in read("/trajectory.jsonl").splitlines()]
        timing = []
        for name, member in files.items():
            if "/timing/" in name and name.endswith(".jsonl") and "resources" not in name:
                timing.extend(json.loads(line) for line in bundle.extractfile(member))
    injection = result["injection"]["before_monotonic_ns"]
    after = result["injection"]["after_monotonic_ns"]
    events = []

    def add(label, record, key, source, limitation=None):
        events.append(
            {
                "event": label,
                "relative_monotonic_s": (record[key] - injection) / 1e9,
                "source": source,
                "record": record,
                "limitation": limitation,
            }
        )

    def first(rows, predicate, key):
        found = [r for r in rows if r[key] >= injection and predicate(r)]
        return min(found, key=lambda r: r[key]) if found else None

    add(
        "crash signal requested",
        result["injection"],
        "before_monotonic_ns",
        "result.json",
        "Signal syscall bracket, not instrumented executor exit.",
    )
    events.append(
        {
            "event": "crash signal syscall returned",
            "relative_monotonic_s": (after - injection) / 1e9,
            "source": "result.json",
            "limitation": "Does not prove exact process exit time.",
        }
    )
    for label, stage, predicate in [
        ("guard zero publication begins", "guard_publish_begin", lambda r: r["vx"] == r["wz"] == 0),
        ("guard detection tick ends", "guard_tick_end", lambda r: r["reason"] != "forwarding"),
        ("native receives zero target", "native_decoded", lambda r: r.get("vx") == 0),
    ]:
        row = first(
            timing,
            lambda r, stage=stage, predicate=predicate: r["stage"] == stage and predicate(r),
            "mono_ns",
        )
        if row:
            add(
                label,
                row,
                "mono_ns",
                "timing",
                "Native decode is not independent wheel/physics application proof."
                if stage == "native_decoded"
                else None,
            )
    for kind in ["guard_events", "watchdog_events", "command"]:
        row = first(
            trace,
            lambda r, kind=kind: (
                r["kind"] == kind and (kind != "command" or r["vx"] == r["wz"] == 0)
            ),
            "monotonic_ns",
        )
        if row:
            add(
                "observer " + kind,
                row,
                "monotonic_ns",
                "trajectory.jsonl",
                "Observer receipt time, not publisher/actuator execution time.",
            )
    if result["restart_receipt"]:
        add(
            "replacement process spawned",
            result["restart_receipt"],
            "monotonic_ns",
            "RESTARTED_EXECUTOR.json",
            "Spawn receipt is not readiness or recovery authorization.",
        )
    # Original independent scoring is retained, not rescaled using wall/simulation clocks.
    scored = json.loads(Path("reports/phase33/final-motion-v1.json").read_text())
    scored = next(r for r in scored["trials"] if r["case"] == "executor_restart")
    return {
        "archive_sha256": hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
        "clock_domain": "Same WSL kernel MONOTONIC; no BOOTTIME/wall subtraction",
        "timeline": sorted(events, key=lambda r: r["relative_monotonic_s"]),
        "native_stopping": scored["native_stopping"],
        "observer_stopping": result["response"],
        "restart_probe_result": result["restart_probe_result"],
        "unavailable": [
            "heartbeat publication/receipt sequence and source age",
            "exact executor exit instant",
            "verified restart authorization",
            "successful fresh authorized mission after restart",
        ],
        "interpretation": "500 ms heartbeat freshness consumes the stopping budget before braking; "
        "receipt-only heartbeats do not bound delivery age. Restart remains "
        "latched on the unfinished mission and no recovery was demonstrated.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = reconstruct("reports/phase33/final-faults-v1/raw/executor_restart.tar.gz")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
