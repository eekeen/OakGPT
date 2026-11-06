#!/usr/bin/env bash
# Resume only the failed test invocation, preserving the initial merged-layout error.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
output="${1:?New output directory}"
prefix="${2:?Existing measured runtime}"
mkdir "$output"
source "$prefix/setup.bash"
export ROS_DOMAIN_ID=85 ROS_LOCALHOST_ONLY=1
colcon --log-base "$output/colcon-log" test --merge-install --base-paths "${prefix}-source/robotics/ros2_ws/src" --packages-select oak_mission oak_nav_trace --build-base "${prefix}-build" --install-base "$prefix" --test-result-base "$output/ros-results" > "$output/ros-test.log" 2>&1
colcon --log-base "$output/colcon-result-log" test-result --test-result-base "$output/ros-results" --verbose > "$output/ros-summary.log" 2>&1
ctest --test-dir "${prefix}-expiry" --output-on-failure -V > "$output/installed-expiry.log" 2>&1
bash /mnt/d/Projects/OakGPT/scripts/verify_timing_overhead.sh "$output/overhead" "$prefix" > "$output/overhead.log" 2>&1
git -C /mnt/d/Projects/OakGPT diff --exit-code e806d56380e812848f1b7a4aadabcacee0d6457d -- cpp robotics/command_expiry/include reports/phase2 reports/phase3 reports/phase31 reports/phase32 > "$output/history-unchanged.log"
echo passed > "$output/COMPLETE.txt"
