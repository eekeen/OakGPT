#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
repo=/mnt/d/Projects/OakGPT
prefix=/home/eekeen/projects/oak-phase33-instrumented
colcon --log-base "${prefix}-log" build --base-paths "$repo/robotics/ros2_ws/src" \
  --packages-select oak_mission oak_nav_trace --build-base "${prefix}-build" --install-base "$prefix" \
  --merge-install --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON
cmake -S "$repo/robotics/command_expiry" -B "${prefix}-expiry" \
  -DOAK_BUILD_GAZEBO_PLUGIN=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "${prefix}-expiry" --parallel 2
