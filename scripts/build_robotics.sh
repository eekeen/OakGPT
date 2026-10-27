#!/usr/bin/env bash
set -eo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
cmake -S "$PROJECT_ROOT/cpp" -B "$HOME/projects/oak-build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$HOME/projects/oak-build" --parallel 4
ctest --test-dir "$HOME/projects/oak-build" --output-on-failure
python3 "$PROJECT_ROOT/scripts/check_robotics_cpp.py" \
  --validator "$HOME/projects/oak-build/oak-validate" \
  --policy "$PROJECT_ROOT/configs/robotics/policy_v1.json"
cd "$HOME/projects"
colcon --log-base oak-ros-log build --base-paths "$PROJECT_ROOT/robotics/ros2_ws/src" \
  --build-base oak-ros-build --install-base oak-ros-install
