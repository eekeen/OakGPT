"""Run inside the isolated ROS domain after other studies; deliberately suspends executor.

Pass the exact mission_executor child PID and a new output path. The process command
and spool are verified before SIGSTOP. The test always resumes it. A successful test
latches watchdog/executor and requires an operator restart before more missions.
"""

import argparse
import json
import os
import signal
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-pid", type=int, required=True)
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    command = Path(f"/proc/{args.executor_pid}/cmdline").read_bytes().decode().split("\0")
    if not any(s.endswith("/mission_executor") for s in command) or str(args.spool) not in command:
        raise RuntimeError("PID is not the exact expected spool executor")
    if args.output.exists() or (args.spool / "STOP").exists():
        raise RuntimeError("Existing evidence or operator stop")
    rclpy.init()
    node = Node("oak_watchdog_fault_test")
    events = []
    node.create_subscription(
        String, "oak/watchdog_events", lambda m: events.append(json.loads(m.data)), 10
    )
    # A task away from dock ensures an action is still live when heartbeat is suspended.
    import uuid

    now = time.time_ns() // 1000000
    mission_id = "m-" + uuid.uuid4().hex[:16]
    mission = {
        "schema_version": 1,
        "mission_id": mission_id,
        "policy_id": "oak-room-v1",
        "issued_at_ms": now,
        "expires_at_ms": now + 60000,
        "instruction": "Go to storage then inspect station",
        "steps": [
            {"action": "navigate", "destination": "storage", "duration_s": 0},
            {"action": "navigate", "destination": "station", "duration_s": 0},
            {"action": "inspect", "destination": "station", "duration_s": 2},
        ],
    }
    moving = []
    node.create_subscription(
        String, "oak/mission_events", lambda m: moving.append(json.loads(m.data)), 10
    )
    # Allow DDS discovery before sending the mission.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    temporary = args.spool / "pending" / (mission_id + ".tmp")
    temporary.write_text(json.dumps(mission))
    temporary.rename(temporary.with_suffix(".json"))
    suspended = False
    started = time.monotonic()
    try:
        deadline = started + 10
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if any(
                e["mission_id"] == mission_id and e["event"] == "navigation_feedback"
                for e in moving
            ):
                os.kill(args.executor_pid, signal.SIGSTOP)
                suspended = True
                break
        if not suspended:
            raise RuntimeError("No live navigation feedback to suspend")
        stopped_at = time.monotonic()
        deadline = stopped_at + 6
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            if any(e["event"] == "watchdog_stop" and e["canceling"] > 0 for e in events):
                break
        observed = time.monotonic() - stopped_at
        assert any(e["event"] == "watchdog_stop" and e["canceling"] > 0 for e in events), events
    finally:
        if suspended:
            os.kill(args.executor_pid, signal.SIGCONT)
        node.destroy_node()
        rclpy.shutdown()
    result_path = args.spool / "results" / (mission_id + ".json")
    deadline = time.monotonic() + 12
    while not result_path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    result = json.loads(result_path.read_text())
    record = {
        "mission": mission,
        "events": events,
        "execution": result,
        "cancel_ack_observed_after_suspend_s": observed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(record, stream, indent=2)
    assert result["status"] == "failed", result
    print("Actual heartbeat-loss cancellation acknowledged; restart latched nodes before reuse")


if __name__ == "__main__":
    main()
