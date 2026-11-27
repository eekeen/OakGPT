#!/usr/bin/env bash
# Run AFTER experiments: compiling during trials would confound CPU contention.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
repo=/mnt/d/Projects/OakGPT
output="${1:?New absolute verification output}"
prefix="${2:?Installed runtime to test}"
build="${3:?New native verification build prefix}"
[[ "$build" == /home/eekeen/projects/oak-phase33-* && ! -e "$build" ]]
mkdir "$output"
mkdir "$build"
cd "$repo"
for mode in release sanitizer; do
  flags=()
  type=Release
  if [[ "$mode" == sanitizer ]]; then flags=(-DOAK_SANITIZERS=ON); type=Debug; fi
  for component in validator expiry; do
    source=cpp
    if [[ "$component" == expiry ]]; then source=robotics/command_expiry; fi
    target="$build/$component-$mode"
    cmake -S "$source" -B "$target" -DCMAKE_BUILD_TYPE="$type" "${flags[@]}" > "$output/$component-$mode-configure.log" 2>&1
    cmake --build "$target" --parallel 2 > "$output/$component-$mode-build.log" 2>&1
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir "$target" --output-on-failure -V > "$output/$component-$mode-ctest.log" 2>&1
  done
done
python3 scripts/check_robotics_cpp.py --validator "$build/validator-release/oak-validate" --policy configs/robotics/policy_v1.json > "$output/frozen-cpp-oracle.log"
PYTHONPATH="$repo/src" python3 scripts/check_clock_mailbox.py --validator "$build/validator-release/oak-validate" --policy "$repo/configs/robotics/policy_v1.json" > "$output/clock-mailbox.json"
source "$prefix/setup.bash"
export ROS_DOMAIN_ID=85 ROS_LOCALHOST_ONLY=1
colcon --log-base "$output/colcon-log" test --merge-install --base-paths "${prefix}-source/robotics/ros2_ws/src" --packages-select oak_mission oak_nav_trace --build-base "${prefix}-build" --install-base "$prefix" --test-result-base "$output/ros-results" > "$output/ros-test.log" 2>&1
colcon --log-base "$output/colcon-result-log" test-result --test-result-base "$output/ros-results" --verbose > "$output/ros-summary.log" 2>&1
ctest --test-dir "${prefix}-expiry" --output-on-failure -V > "$output/installed-expiry.log" 2>&1
bash scripts/verify_timing_overhead.sh "$output/overhead" "$prefix" > "$output/overhead.log" 2>&1
git diff --exit-code e806d56380e812848f1b7a4aadabcacee0d6457d -- cpp robotics/command_expiry/include reports/phase2 reports/phase3 reports/phase31 reports/phase32 > "$output/history-unchanged.log"
python3 -c 'import json,platform; print(json.dumps({"passed":True,"platform":platform.platform()}))' > "$output/COMPLETE.json"
