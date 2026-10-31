#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
repo=/mnt/d/Projects/OakGPT
prefix="${1:?Supply a fresh, absolute install prefix; completed builds are immutable}"
if [[ "$prefix" != /home/eekeen/projects/oak-phase33-* || -e "$prefix" || -e "${prefix}-build" || -e "${prefix}-source" ]]; then
  echo 'Refusing an existing or out-of-workspace build prefix' >&2
  exit 1
fi
python3 "$repo/scripts/snapshot_phase33_build.py" "$repo" "$prefix"
source_tree="${prefix}-source"
colcon --log-base "${prefix}-log" build --base-paths "$source_tree/robotics/ros2_ws/src" \
  --packages-select oak_mission oak_nav_trace --build-base "${prefix}-build" --install-base "$prefix" \
  --merge-install --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON
cmake -S "$source_tree/robotics/command_expiry" -B "${prefix}-expiry" \
  -DOAK_BUILD_GAZEBO_PLUGIN=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "${prefix}-expiry" --parallel 2
