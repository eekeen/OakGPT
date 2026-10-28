#!/usr/bin/env bash
# Protocol regression only: synthetic sensors/action server, no simulated motors.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=84 ROS_LOCALHOST_ONLY=1
project="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:?Supply a NEW output directory}"
cases=(control lost_lidar stale_lidar delayed_lidar future_lidar lost_tf future_tf
  action_abort executor_crash watchdog_crash heartbeat_interruption late_goal
  mission_expiration replay corrupt_json duplicate_key unsafe_omission
  oversized_payload delayed_delivery spool_loss drvfs_detach)
python3 "$project/scripts/robotics_fault_matrix.py" \
  --output "$output" --runtime hardened \
  --package-path /home/eekeen/projects/oak-ros-phase32-v5/oak_mission/lib/python3.12/site-packages \
  --validator /home/eekeen/projects/oak-build/oak-validate \
  --policy "$project/configs/robotics/policy_v1.json" \
  --cases "${cases[@]}" --require-safe
cp "$0" "$output/executed_protocol.sh"
