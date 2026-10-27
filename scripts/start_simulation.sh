#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "${OAK_ROS_INSTALL:-$HOME/projects/oak-ros-install}/setup.bash"
set -u
export ROS_DOMAIN_ID=73
export ROS_LOCALHOST_ONLY=1
export GZ_PARTITION=oakgpt-phase3
export LIBGL_ALWAYS_SOFTWARE=1
exec ros2 launch oak_mission simulation.launch.py
