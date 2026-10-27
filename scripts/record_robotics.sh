#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=73
export ROS_LOCALHOST_ONLY=1
exec ros2 bag record -s mcap -o "${1:?provide a new bag output directory}" \
  /clock /tf /tf_static /odom /scan /cmd_vel /amcl_pose \
  /oak/mission_events /oak/watchdog_events /oak/heartbeat /oak/watchdog_lease
