#!/usr/bin/env bash
# Root is needed only to detach the private test mount, never the shared /mnt/d.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=84 ROS_LOCALHOST_ONLY=1
project="$(cd "$(dirname "$0")/.." && pwd)"
output="${1:?Supply a NEW output parent directory}"
mkdir "$output"
cases=(control lost_lidar stale_lidar delayed_lidar future_lidar lost_tf future_tf
  action_abort executor_crash watchdog_crash heartbeat_interruption late_goal
  mission_expiration replay corrupt_json duplicate_key unsafe_omission
  oversized_payload delayed_delivery spool_loss drvfs_detach)
for runtime in legacy hardened; do
  install=/home/eekeen/projects/oak-ros-phase31-final
  extra=()
  if [[ "$runtime" == hardened ]]; then
    install=/home/eekeen/projects/oak-ros-phase31
    extra=(--require-safe)
  fi
  python3 "$project/scripts/robotics_fault_matrix.py" \
    --output "$output/fault-$runtime-v4" --runtime "$runtime" \
    --package-path "$install/oak_mission/lib/python3.12/site-packages" \
    --validator /home/eekeen/projects/oak-build/oak-validate \
    --policy "$project/configs/robotics/policy_v1.json" \
    --cases "${cases[@]}" "${extra[@]}"
done
