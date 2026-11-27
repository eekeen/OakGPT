"""Score actual motion and confirmed payload delivery, never ROS cancellation alone."""

import argparse
import json
import math
from pathlib import Path

from analyze_phase32 import fault_cohort

from oakgpt.provenance import sha256
from oakgpt.robotics.ground_truth import angle_difference, stopping_response
from oakgpt.robotics.planner import write_new_json


def payload_delivery(rows, injection, before, cutoff):
    frame = injection["frame_id"]
    sequence = int(frame.rsplit("/", 1)[1])
    scoped = [r for r in rows if before <= r["mono_ns"] <= cutoff]
    bridge_take = [r for r in scoped if r["stage"] == "dds_take" and r.get("frame_id") == frame]
    gz_publish = [
        r
        for r in scoped
        if r["stage"] == "gz_publish_begin"
        and r.get("frame_id") == frame
        and r.get("issued_ns") == injection["issued_boottime_ns"]
    ]
    native = [
        r
        for r in scoped
        if r["stage"] == "native_decoded"
        and r.get("sequence") == sequence
        and r.get("issued_ns") == injection["issued_boottime_ns"]
        and abs(r.get("vx", 0) - injection["vx"]) < 1e-8
    ]
    original_seen = any(
        r["stage"] == "native_decoded"
        and r["mono_ns"] < before
        and r.get("sequence") == sequence
        and r.get("issued_ns") == injection["issued_boottime_ns"]
        for r in rows
    )
    reasons = {
        r["state"]["reason"]
        for r in scoped
        if r["stage"] == "expiry_state" and r["state"]["latched"]
    }
    expected = (
        "invalid_command_age" if injection["kind"] == "stale_command" else "identity_or_replay"
    )
    replay_identity_confirmed = (
        injection["kind"] != "replayed_command" or original_seen or len(native) >= 2
    )
    return bool(bridge_take and gz_publish and native and replay_identity_confirmed), {
        "bridge_take_matching_records": len(bridge_take),
        "gazebo_publish_matching_records": len(gz_publish),
        "native_decode_matching_records": len(native),
        "original_native_header_seen_before_injection": original_seen,
        "replay_identity_confirmed": replay_identity_confirmed,
        "expected_rejection_observed": expected in reasons,
        "nonzero_payload": abs(injection["vx"]) > 0.01,
        "frame_id": frame,
        "issued_boottime_ns": injection["issued_boottime_ns"],
    }


def post_confirmation_motion(truth, anchor, response):
    if not response or not response["settled"]:
        return None
    confirmed = anchor["sim_ns"] + round(response["confirmed_after_sim_s"] * 1e9)
    observed = [r for r in truth if r["sim_ns"] >= confirmed]
    speeds, turns, gaps = [], [], []
    for a, b in zip(observed, observed[1:], strict=False):
        dt = (b["sim_ns"] - a["sim_ns"]) / 1e9
        if dt > 0:
            gaps.append(dt)
            speeds.append(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / dt)
            turns.append(abs(angle_difference(b["yaw"], a["yaw"])) / dt)
    return {
        "sample_intervals": len(gaps),
        "max_gap_sim_s": max(gaps) if gaps else None,
        "max_speed_m_s": max(speeds) if speeds else None,
        "max_yaw_rate_rad_s": max(turns) if turns else None,
        "remained_within_settled_thresholds": bool(gaps)
        and max(gaps) <= 0.15
        and max(speeds) <= 0.01
        and max(turns) <= 0.03,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (args.root / "COMPLETE").exists():
        raise ValueError("Final fault scoring requires every preregistered case")
    plan = json.loads((args.root / "plan.json").read_text())
    trials = []
    for case in plan["cases"]:
        directory = args.root / "cases" / case / case
        result = json.loads((directory / "result.json").read_text())
        # This independently recomputes the frozen observer-based stopping metric.
        required = [
            "injection",
            "response",
            "anchor",
            "observation_end_monotonic_ns",
            "mission_result",
            "last_action_status",
        ]
        legacy = (
            fault_cohort(directory.parent)["trials"][0]
            if all(k in result for k in required)
            else {
                "case": case,
                "eligible": False,
                "environment_failure": result.get("environment_failure"),
                "unavailable": "Incomplete observation; no stopping pass inferred",
            }
        )
        rows = []
        hashes = {}
        for path in sorted((directory / "timing").glob("*.jsonl")):
            hashes[path.name] = sha256(path)
            if path.name != "resources.jsonl":
                rows.extend(json.loads(line) for line in path.read_text().splitlines())
        injection = result.get("injection", {})
        before = injection.get("before_monotonic_ns")
        cutoff = result.get("observation_end_monotonic_ns")
        truth = sorted(
            [
                {**r, "kind": "truth", "monotonic_ns": r["mono_ns"]}
                for r in rows
                if r["stage"] == "ground_truth_native"
                and cutoff is not None
                and r["mono_ns"] <= cutoff
            ],
            key=lambda r: r["mono_ns"],
        )
        earlier = [r for r in truth if before is not None and r["mono_ns"] <= before]
        native_precondition, response, later_motion = None, None, None
        if len(earlier) >= 2:
            a, b = earlier[-2:]
            dt = (b["sim_ns"] - a["sim_ns"]) / 1e9
            speed = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / dt if dt > 0 else None
            age = (before - b["mono_ns"]) / 1e9
            native_precondition = {
                "speed_m_s": speed,
                "truth_age_s": age,
                "sample_gap_sim_s": dt,
                "eligible": speed is not None
                and speed > 0.05
                and 0 < dt <= 0.15
                and 0 <= age <= 0.15,
            }
            response = stopping_response(truth, b)
            later_motion = post_confirmation_motion(truth, b, response)
            if response["settled"]:
                onset_sim = b["sim_ns"] + round(response["stop_latency_sim_s"] * 1e9)
                onset = next((r for r in truth if r["sim_ns"] == onset_sim), None)
                response["onset_monotonic_s_from_injection"] = (
                    (onset["mono_ns"] - before) / 1e9 if onset else None
                )
        payload = case in {"stale_command", "replayed_command"}
        delivered, details = None, None
        if payload and before is not None and cutoff is not None:
            delivered, details = payload_delivery(rows, injection, before, cutoff)
        eligible = bool(
            legacy["eligible"] and native_precondition and native_precondition["eligible"]
        )
        within = bool(response and response["settled"] and response["stop_latency_sim_s"] <= 0.5)
        delivery_pass = not payload or bool(
            delivered and details["expected_rejection_observed"] and details["nonzero_payload"]
        )
        trials.append(
            {
                "case": case,
                "result_sha256": sha256(directory / "result.json"),
                "trace_sha256": hashes,
                "observer_analysis": legacy,
                "native_motion_precondition": native_precondition,
                "native_stopping": response,
                "payload_delivery_verified": delivered,
                "payload_evidence": details,
                "post_confirmation_motion": later_motion,
                "eligible": eligible,
                "within_0_5_sim_s": within,
                "passed": eligible
                and within
                and bool(legacy.get("within_0_5_sim_s"))
                and delivery_pass
                and not result.get("environment_failure"),
                "environment_failure": result.get("environment_failure"),
                "executor_restart_receipt": result.get("restart_receipt"),
                "executor_restart_probe": result.get("restart_probe_result"),
            }
        )
    write_new_json(
        args.output,
        {
            "plan_sha256": sha256(args.root / "plan.json"),
            "trials": trials,
            "planned": len(plan["cases"]),
            "eligible": sum(t["eligible"] for t in trials),
            "passed": sum(t["passed"] for t in trials),
            "all_ten_passed": len(trials) == 10 and all(t["passed"] for t in trials),
            "limits": [
                "Native PostUpdate and Gazebo pose observer share simulator physics; "
                "neither is a physical robot stopping measurement.",
                "Both observer and native motion metrics must meet the unchanged target. "
                "Missing observations are not passes.",
                "Settling is simulated onset sustained for 0.3 s; wall/monotonic latency "
                "is reported separately, including simulator stalls.",
                "Only records preceding the explicit observation cutoff are scored; "
                "cleanup-induced stopping is excluded.",
                "Delivery uses same-kernel MONOTONIC matches; BOOTTIME issued headers are "
                "compared for equality, never subtracted from MONOTONIC.",
            ],
        },
    )


if __name__ == "__main__":
    main()
