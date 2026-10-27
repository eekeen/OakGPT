"""Own one fresh simulation/executor/bag session and stop its exact descendant processes."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import oak_mission
import rclpy
from lifecycle_msgs.srv import GetState
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool
from tf2_msgs.msg import TFMessage


def descendant_identities(roots):
    rows = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
            rows[int(path.parent.name)] = (int(fields[1]), fields[19])
        except (OSError, ValueError, IndexError):
            continue
    owned = set(roots)
    while True:
        expanded = owned | {pid for pid, (parent, _) in rows.items() if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    return {pid: rows[pid][1] for pid in owned if pid in rows}


def signal_owned(owned, kind):
    for pid, start in owned.items():
        try:
            current = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
            if current == start:
                os.kill(pid, kind)
        except (OSError, IndexError):
            continue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--bag", type=Path, required=True)
    parser.add_argument("--world-directory", type=Path)
    parser.add_argument("--allow-executor-exit", action="store_true")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    if (args.directory / "READY.json").exists():
        raise FileExistsError("Session already started")
    processes, logs, roles = [], [], {}
    rclpy.init(args=[])
    node = Node("oak_session_readiness")
    state = {"scan": False, "watchdog": False}
    if args.world_directory:
        state["truth"] = False
        state["routing"] = False
        node.create_subscription(
            TFMessage,
            "/oak/ground_truth",
            lambda m: state.update(
                truth=any(t.child_frame_id == "oak_robot" for t in m.transforms)
            ),
            10,
        )
    node.create_subscription(
        LaserScan, "/scan", lambda _: state.update(scan=True), qos_profile_sensor_data
    )
    node.create_subscription(
        Bool,
        "/oak/watchdog_ready",
        lambda m: state.update(watchdog=m.data),
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
    )
    clients = [
        node.create_client(GetState, f"/{name}/get_state")
        for name in ["bt_navigator", "controller_server", "amcl"]
    ]

    def start(name, command):
        log = (args.directory / f"{name}.log").open("x")
        logs.append(log)
        process = subprocess.Popen(command, stdout=log, stderr=log)
        processes.append(process)
        roles[process.pid] = name
        return process

    try:
        launch = ["ros2", "launch", "oak_mission", "simulation.launch.py"]
        if args.world_directory:
            world = args.world_directory
            launch = [
                "ros2",
                "launch",
                "oak_mission",
                "reliability.launch.py",
                "world:=" + str(world / "world.sdf"),
                "map:=" + str(world / "map.yaml"),
                "params:=" + str(world / "nav2.yaml"),
            ]
            start(
                "observer",
                [
                    "ros2",
                    "run",
                    "oak_mission",
                    "mission_observer",
                    "--output",
                    str(args.directory / "trajectory.jsonl"),
                    "--ros-args",
                    "-p",
                    "use_sim_time:=true",
                ],
            )
        start("simulation", launch)
        start(
            "executor",
            [
                "ros2",
                "run",
                "oak_mission",
                "mission_executor",
                "--spool",
                str(args.directory / "spool"),
                "--validator",
                str(Path.home() / "projects/oak-build/oak-validate"),
                "--policy",
                str(args.project / "configs/robotics/policy_v1.json"),
                "--ros-args",
                "-p",
                "use_sim_time:=true",
            ],
        )
        deadline = time.monotonic() + 90
        ready = False
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("A session process exited during startup")
            rclpy.spin_once(node, timeout_sec=0.1)
            if args.world_directory:
                publishers = node.get_publishers_info_by_topic("/cmd_vel")
                upstream = node.get_publishers_info_by_topic("/oak/nav_cmd_vel")
                state["routing"] = (
                    len(publishers) == 1
                    and publishers[0].node_name == "oak_velocity_guard"
                    and len(upstream) == 1
                    and upstream[0].node_name == "collision_monitor"
                )
            if not all(state.values()) or not all(c.service_is_ready() for c in clients):
                continue
            futures = [c.call_async(GetState.Request()) for c in clients]
            end = time.monotonic() + 3
            while not all(f.done() for f in futures) and time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.05)
            if all(f.done() and f.result().current_state.id == 3 for f in futures):
                ready = True
                break
        if not ready:
            raise TimeoutError("Lifecycle/scan/watchdog readiness deadline")
        start(
            "rosbag",
            [
                "ros2",
                "bag",
                "record",
                "-s",
                "mcap",
                "-o",
                str(args.bag),
                "/clock",
                "/tf",
                "/tf_static",
                "/scan",
                "/odom",
                "/cmd_vel",
                "/amcl_pose",
                "/oak/mission_events",
                "/oak/watchdog_events",
                "/oak/heartbeat",
                "/oak/watchdog_lease",
                "/oak/ground_truth",
                "/oak/guard_events",
                "/oak/nav_cmd_vel",
                "/navigate_to_pose/_action/status",
            ],
        )
        time.sleep(2)  # Excluded recorder discovery, not a measurement.
        ready_path = args.directory / "READY.json"
        ready_path.write_text(
            json.dumps(
                {
                    "ready_at_ns": time.time_ns(),
                    "pids": [p.pid for p in processes],
                    "ros_domain": os.getenv("ROS_DOMAIN_ID"),
                    "gazebo_partition": os.getenv("GZ_PARTITION"),
                    "command_route_checked": bool(args.world_directory),
                    "command_publisher_nodes": [
                        p.node_name for p in node.get_publishers_info_by_topic("/cmd_vel")
                    ],
                    "guard_input_publisher_nodes": [
                        p.node_name for p in node.get_publishers_info_by_topic("/oak/nav_cmd_vel")
                    ],
                    "installed_ros_source_sha256": {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in Path(oak_mission.__file__).parent.glob("*.py")
                    },
                }
            )
        )
        while not (args.directory / "STOP_SESSION").exists():
            if any(
                p.poll() is not None
                and not (args.allow_executor_exit and roles[p.pid] == "executor")
                for p in processes
            ):
                raise RuntimeError("A session process exited unexpectedly")
            time.sleep(0.2)
    finally:
        owned = descendant_identities([p.pid for p in processes])
        signal_owned(owned, signal.SIGINT)
        time.sleep(5)
        signal_owned(owned, signal.SIGTERM)
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                signal_owned(owned, signal.SIGKILL)
                p.wait(timeout=5)
        for log in logs:
            log.close()
        (args.directory / "STOPPED.json").write_text(
            json.dumps({"owned_processes": owned, "stopped_at_ns": time.time_ns()})
        )
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
