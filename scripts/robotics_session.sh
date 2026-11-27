#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "${OAK_ROS_INSTALL:-$HOME/projects/oak-ros-phase31-final}/setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-73}"
export ROS_LOCALHOST_ONLY=1
export GZ_PARTITION="${GZ_PARTITION:-oakgpt-phase31}"
export LIBGL_ALWAYS_SOFTWARE=1
if [[ -n "${OAK_FASTDDS_PROFILE:-}" && "${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}" == rmw_fastrtps_cpp ]]; then
  export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
  export RMW_FASTRTPS_USE_QOS_FROM_XML=0
  export FASTRTPS_DEFAULT_PROFILES_FILE="$OAK_FASTDDS_PROFILE"
fi
exec python3 "$(dirname "$0")/robotics_session.py" "$@"
