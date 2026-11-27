#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "$1/setup.bash"
shift
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-73}"
export ROS_LOCALHOST_ONLY=1
if [[ -n "${OAK_FASTDDS_PROFILE:-}" && "${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}" == rmw_fastrtps_cpp ]]; then
  export RMW_FASTRTPS_USE_QOS_FROM_XML=0
  export FASTRTPS_DEFAULT_PROFILES_FILE="$OAK_FASTDDS_PROFILE"
fi
exec python3 /mnt/d/Projects/OakGPT/scripts/probe_ros_startup.py "$@"
