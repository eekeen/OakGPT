"""ROS fault fixture: late Nav2 goal acceptance must not disarm the watchdog.

Requires the real simulation's /clock and /scan, but uses an explicitly fake namespaced
action server (no velocities). Its 7 s acceptance delay exceeds the executor's 5 s bound.
This is a protocol fault test, never scored as a Gazebo navigation result.
"""

import argparse
import json
import os
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

import rclpy
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    spool = args.output / "spool"
    (spool / "pending").mkdir(parents=True)
    rclpy.init(args=[])
    node = Node("late_goal_fixture", namespace="oak_faulttest")
    events = []
    state = []

    def accept(request):
        state.append({"event": "goal_requested", "time": time.time()})
        time.sleep(7)
        state.append({"event": "late_goal_accepted", "time": time.time()})
        return GoalResponse.ACCEPT

    def execute(handle):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if handle.is_cancel_requested:
                handle.canceled()
                state.append({"event": "late_goal_canceled", "time": time.time()})
                return NavigateToPose.Result()
            time.sleep(0.05)
        handle.abort()
        return NavigateToPose.Result()

    server = ActionServer(
        node,
        NavigateToPose,
        "navigate_to_pose",
        execute,
        goal_callback=accept,
        cancel_callback=lambda _: CancelResponse.ACCEPT,
        callback_group=ReentrantCallbackGroup(),
    )
    node.create_subscription(
        String, "oak/watchdog_events", lambda message: events.append(json.loads(message.data)), 10
    )
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    worker = threading.Thread(target=executor.spin, daemon=True)
    worker.start()
    processes = []
    logs = []
    result = None
    try:
        commands = [
            [
                "ros2",
                "run",
                "oak_mission",
                "mission_watchdog",
                "--ros-args",
                "-r",
                "__ns:=/oak_faulttest",
            ],
            [
                "ros2",
                "run",
                "oak_mission",
                "mission_executor",
                "--spool",
                str(spool),
                "--validator",
                str(args.validator),
                "--policy",
                str(args.policy),
                "--ros-args",
                "-p",
                "use_sim_time:=true",
                "-r",
                "__ns:=/oak_faulttest",
                "-r",
                "scan:=/scan",
            ],
        ]
        for i, command in enumerate(commands):
            log = (args.output / f"node-{i}.log").open("w")
            logs.append(log)
            processes.append(
                subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
            )
        # Discovery/startup, not measured as fault-response latency.
        time.sleep(4)
        now = time.time_ns() // 1000000
        mission_id = "m-" + uuid.uuid4().hex[:16]
        mission = {
            "schema_version": 1,
            "mission_id": mission_id,
            "policy_id": "oak-room-v1",
            "issued_at_ms": now,
            "expires_at_ms": now + 60000,
            "instruction": "Go to station",
            "steps": [{"action": "navigate", "destination": "station", "duration_s": 0}],
        }
        temporary = spool / "pending" / (mission_id + ".tmp")
        temporary.write_text(json.dumps(mission))
        temporary.rename(temporary.with_suffix(".json"))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            path = spool / "results" / (mission_id + ".json")
            if path.exists():
                result = json.loads(path.read_text())
            if (
                result
                and any(e["event"] == "late_goal_canceled" for e in state)
                and any(e["event"] == "watchdog_stop" and e["canceling"] > 0 for e in events)
            ):
                break
            time.sleep(0.1)
        record = {
            "fixture": "delayed acceptance, fake action server, real ROS transport",
            "acceptance_delay_s": 7,
            "result": result,
            "server_events": state,
            "watchdog_events": events,
        }
        (args.output / "result.json").write_text(json.dumps(record, indent=2))
        assert (
            result
            and result["status"] == "failed"
            and result["reason"] == "ROS action/service timeout"
        ), result
        assert any(e["event"] == "late_goal_canceled" for e in state), state
        assert any(e["event"] == "watchdog_stop" and e["canceling"] > 0 for e in events), events
        print(
            "Late accepted goal independently canceled after executor timeout; "
            "no motor publisher in fixture"
        )
    finally:
        for process in processes:
            os.killpg(process.pid, signal.SIGINT)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for log in logs:
            log.close()
        executor.shutdown(timeout_sec=2)
        worker.join(timeout=2)
        server.destroy()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
