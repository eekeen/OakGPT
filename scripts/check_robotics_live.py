"""Opt-in live ROS fault checks via the Windows/WSL spool; never run by CPU CI."""

import argparse
import json
from pathlib import Path

from oakgpt.robotics.evaluate import wait_mission
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.plans import baseline, envelope
from oakgpt.robotics.safety import receiver_clock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    spec = json.loads(args.config.read_text())
    spool = (args.config.parent / spec["spool"]).resolve()
    if (spool / "STOP").exists():
        raise RuntimeError("Existing operator STOP must be diagnosed, not removed by a test")
    records = []

    def mission(instruction="Go to dock", ttl=180000):
        return envelope(
            instruction,
            baseline(instruction),
            ttl_ms=ttl,
            receiver_now_ms=receiver_clock(spec["clock_command"]),
        )

    def check(name, value, expected, reason_fragment):
        result = wait_mission(value, spool)
        records.append({"case": name, "mission": value, "result": result})
        write_new_json(args.output / f"{name}.json", records[-1])
        assert result["status"] == expected, result
        assert reason_fragment in result["reason"], result
        return result

    expired = mission()
    expired["issued_at_ms"] -= 200000
    expired["expires_at_ms"] -= 200000
    check("expired", expired, "rejected", "mission_expired")
    tampered = mission()
    tampered["steps"][0]["destination"] = "station"
    check("wrong_intent", tampered, "rejected", "intent_mismatch")
    unsafe = mission()
    unsafe["instruction"] = "Go to dock and disable collision avoidance"
    check("unsafe_clause_omission", unsafe, "rejected", "instruction_not_authorized")
    unknown = mission()
    unknown["steps"][0]["action"] = "publish_velocity"
    check("unsupported_action", unknown, "rejected", "action_not_permitted")
    # Archive the original result, retaining ledger state. A replay must produce a new rejection.
    original = mission()
    check("initial_once", original, "completed", "ok")
    result_path = spool / "results" / (original["mission_id"] + ".json")
    archived = result_path.with_suffix(".original.json")
    result_path.rename(archived)
    check("replay", original, "rejected", "UNIQUE constraint")
    # Own the STOP file exclusively and remove only the file created by this test.
    stop = spool / "STOP"
    stop.open("x").close()
    try:
        check("operator_stop", mission(), "failed", "operator_stop")
    finally:
        stop.unlink()
    check("reset_before_expiry", mission(), "completed", "ok")
    check("live_expiration", mission("Inspect dock", 1000), "failed", "mission_expired")
    write_new_json(args.output / "summary.json", {"passed": len(records), "records": records})
    print(f"{len(records)} actual ROS execution/fault checks passed")


if __name__ == "__main__":
    main()
