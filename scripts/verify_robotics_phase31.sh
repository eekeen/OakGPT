#!/usr/bin/env bash
# Independent build directories keep measured binaries and installed runtimes unchanged.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
project="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:?Supply a NEW verification output directory}"
mkdir -p "$(dirname "$output")"
mkdir "$output"
cd "$project"
release="$HOME/projects/oak-phase31-verify-release"
asan="$HOME/projects/oak-phase31-verify-asan"
cmake -S cpp -B "$release" -DCMAKE_BUILD_TYPE=Release > "$output/cmake-release.log" 2>&1
cmake --build "$release" --parallel 2 > "$output/build-release.log" 2>&1
ctest --test-dir "$release" --output-on-failure -V > "$output/ctest-release.log" 2>&1
python3 scripts/check_robotics_cpp.py --validator "$release/oak-validate" \
  --policy configs/robotics/policy_v1.json > "$output/cpp-oracle.log" 2>&1
cmake -S cpp -B "$asan" -DCMAKE_BUILD_TYPE=Debug -DOAK_SANITIZERS=ON \
  > "$output/cmake-sanitizer.log" 2>&1
cmake --build "$asan" --parallel 2 > "$output/build-sanitizer.log" 2>&1
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  ctest --test-dir "$asan" --output-on-failure -V > "$output/ctest-sanitizer.log" 2>&1
colcon --log-base "$output/colcon-build-log" build --base-paths "$project/robotics/ros2_ws/src" \
  --build-base "$HOME/projects/oak-ros-phase31-verify-build" \
  --install-base "$HOME/projects/oak-ros-phase31-verify" > "$output/ros-build.log" 2>&1
source "$HOME/projects/oak-ros-phase31-verify/setup.bash"
export ROS_DOMAIN_ID=85 ROS_LOCALHOST_ONLY=1
colcon --log-base "$output/colcon-test-log" test --packages-select oak_mission \
  --build-base "$HOME/projects/oak-ros-phase31-verify-build" \
  --install-base "$HOME/projects/oak-ros-phase31-verify" \
  --test-result-base "$output/ros-test-results" > "$output/ros-test.log" 2>&1
colcon --log-base "$output/colcon-results-log" test-result \
  --test-result-base "$output/ros-test-results" --verbose \
  > "$output/ros-test-summary.log" 2>&1
git diff --exit-code 6b93133 -- cpp reports/results reports/phase2 reports/phase3 \
  output/pdf/phase2-research-report.pdf output/pdf/phase3-research-report.pdf \
  > "$output/historical-evidence.log"
python3 -c 'import json,platform,datetime; print(json.dumps({"passed":True,"platform":platform.platform(),"completed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}))' \
  > "$output/robotics.json"
