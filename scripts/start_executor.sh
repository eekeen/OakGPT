#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "${OAK_ROS_INSTALL:-$HOME/projects/oak-ros-install}/setup.bash"
set -u
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ROS_DOMAIN_ID=73
export ROS_LOCALHOST_ONLY=1
exec ros2 run oak_mission mission_executor \
  --spool "${OAK_SPOOL:-$PROJECT_ROOT/runs/phase3/spool}" \
  --validator "${OAK_VALIDATOR:-$HOME/projects/oak-build/oak-validate}" \
  --policy "$PROJECT_ROOT/configs/robotics/policy_v1.json" \
  --ros-args -p use_sim_time:=true
