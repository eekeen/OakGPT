#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "${OAK_ROS_INSTALL:-$HOME/projects/oak-ros-phase31-final}/setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-73}"
export ROS_LOCALHOST_ONLY=1
export GZ_PARTITION="${GZ_PARTITION:-oakgpt-phase31}"
export LIBGL_ALWAYS_SOFTWARE=1
exec python3 "$(dirname "$0")/robotics_session.py" "$@"
