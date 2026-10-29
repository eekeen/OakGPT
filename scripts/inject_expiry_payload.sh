#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source "${1:?ROS install}/setup.bash"
shift
export ROS_DOMAIN_ID=73 ROS_LOCALHOST_ONLY=1
exec python3 "$(dirname "$0")/inject_expiry_payload.py" "$@"
