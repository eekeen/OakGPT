"""Analyze same-kernel BOOTTIME traces without mixing DDS or simulation clocks."""

from collections import Counter, defaultdict
from typing import Any


def expiration_bracket_valid(
    earlier_wall_ns: int,
    earlier_mono_ns: int,
    later_wall_ns: int,
    later_mono_ns: int,
    expires_wall_ns: int,
) -> bool:
    """Bound an observed wall-clock crossing, rejecting coarse or jumping clocks."""
    elapsed_mono = later_mono_ns - earlier_mono_ns
    elapsed_wall = later_wall_ns - earlier_wall_ns
    return (
        earlier_wall_ns < expires_wall_ns <= later_wall_ns
        and 0 <= elapsed_mono <= 20_000_000
        and abs(elapsed_wall - elapsed_mono) <= 2_000_000
    )


def distribution(values: list[int]) -> dict[str, int | None]:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "median_ns": ordered[len(ordered) // 2] if ordered else None,
        "p95_ns": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else None,
        "p99_ns": ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))] if ordered else None,
        "max_ns": max(ordered) if ordered else None,
    }


def analyze_timing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(r["stage"]) for r in rows)
    previous: dict[tuple[int, int, str], int] = {}
    started: dict[tuple[int, int, str], tuple[int, int]] = {}
    gaps: dict[str, list[int]] = defaultdict(list)
    durations: dict[str, list[int]] = defaultdict(list)
    cpu: dict[str, list[int]] = defaultdict(list)
    commands: dict[int, dict[str, int]] = defaultdict(dict)
    for row in sorted(rows, key=lambda r: r["boot_ns"]):
        stage, stamp = str(row["stage"]), int(row["boot_ns"])
        key = (int(row["pid"]), int(row.get("tid", row["pid"])), stage)
        if key in previous:
            gaps[stage].append(stamp - previous[key])
        previous[key] = stamp
        if stage.endswith("_begin"):
            started[(*key[:2], stage[:-6])] = (stamp, int(row["thread_cpu_ns"]))
        elif stage.endswith("_end"):
            beginning = started.pop((*key[:2], stage[:-4]), None)
            if beginning:
                durations[stage[:-4]].append(stamp - beginning[0])
                cpu[stage[:-4]].append(int(row["thread_cpu_ns"]) - beginning[1])
        sequence = row.get("sequence")
        if "frame_id" in row:
            sequence = int(row["frame_id"].rsplit("/", 1)[1])
        if sequence is not None and stage in {
            "guard_publish_begin",
            "guard_publish_end",
            "dds_take",
            "gz_publish_begin",
            "gz_publish_end",
            "native_decoded",
        }:
            commands[int(sequence)].setdefault(stage, stamp)
    edges = {}
    nonzero = {
        int(r["sequence"])
        for r in rows
        if r["stage"] == "guard_publish_begin"
        and "sequence" in r
        and (abs(float(r.get("vx", 0))) > 0 or abs(float(r.get("wz", 0))) > 0)
    }
    native = sorted((r for r in rows if r["stage"] == "native_decoded"), key=lambda r: r["boot_ns"])
    native_gaps = [b["boot_ns"] - a["boot_ns"] for a, b in zip(native, native[1:], strict=False)]
    moving_gaps = [
        b["boot_ns"] - a["boot_ns"]
        for a, b in zip(native, native[1:], strict=False)
        if a.get("sequence") in nonzero
    ]
    states = [r["state"] for r in rows if r["stage"] == "expiry_state"]
    nonzero_latency = [
        r["native_decoded"] - r["guard_publish_begin"]
        for sequence, r in commands.items()
        if sequence in nonzero
        and "native_decoded" in r
        and "guard_publish_begin" in r
        and r["native_decoded"] >= r["guard_publish_begin"]
    ]
    for before, after in [
        ("guard_publish_begin", "dds_take"),
        ("dds_take", "gz_publish_begin"),
        ("gz_publish_begin", "native_decoded"),
        ("guard_publish_begin", "native_decoded"),
    ]:
        edges[before + "->" + after] = distribution(
            [
                r[after] - r[before]
                for r in commands.values()
                if before in r and after in r and r[after] >= r[before]
            ]
        )
    return {
        "stage_counts": dict(counts),
        "command_stream": {
            "native_interarrival": distribution(native_gaps),
            "native_gaps_over_200ms": sum(g > 200_000_000 for g in native_gaps),
            "gaps_following_nonzero_command": distribution(moving_gaps),
            "gaps_over_200ms_following_nonzero": sum(g > 200_000_000 for g in moving_gaps),
            "nonzero_guard_begin_to_native": distribution(nonzero_latency),
            "native_latch_observed": any(state.get("latched", False) for state in states),
            "native_state_reasons": dict(Counter(str(state.get("reason")) for state in states)),
            "limits": "Nonzero commanded velocity is not proof of actual motion. "
            "Gap counts are serial intervals, not independent trials; "
            "a missing state trace cannot establish absence of expiry.",
        },
        "interarrival": {k: distribution(v) for k, v in gaps.items()},
        "call_wall_duration": {k: distribution(v) for k, v in durations.items()},
        "call_thread_cpu_duration": {k: distribution(v) for k, v in cpu.items()},
        "matched_command_edges": edges,
        "clock": "All computed deltas use Linux CLOCK_BOOTTIME, same kernel only",
        "limits": [
            "Publish begin/end measure API duration, not a DDS wire transmission timestamp.",
            "DDS source/received timestamps are retained as realtime fields "
            "and never subtracted from BOOTTIME.",
            "DDS take to Gazebo publish includes conversion and callback processing; "
            "transport begins at the publication API.",
            "One guard epoch per session is required; analyze sessions separately.",
            "Wall duration minus thread CPU includes blocking and descheduling; "
            "it does not uniquely identify either cause.",
        ],
    }
