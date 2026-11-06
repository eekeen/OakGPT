#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
exec python3 /mnt/d/Projects/OakGPT/scripts/isolate_dds_timing.py "$@"
