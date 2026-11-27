# Follow-up: uncertain goal acceptance and latched cancellation

After commit `561c28a`, review identified that a timed-out goal acceptance could become
an orphan if the executor subsequently sent an inactive heartbeat. The revised executor
latches `faulted=true` on uncertain acceptance; the watchdog remains latched and keeps
cancelling even after `active=false`. Cancellation failures use the same fault propagation.

`late-goal-check-v2/result.json` records an actual ROS transport fault test using an
explicit fake namespaced action server, real simulator clock/scan input and real executor/
watchdog processes. The action server deliberately delays acceptance seven seconds,
exceeding the executor's five-second timeout. The executor failed closed; the late
accepted goal was canceled, and the watchdog observed one goal canceling. The fixture
never publishes robot velocities and is not part of the 180-case quality cohort.

The first fixture (`late-goal-check`) observed the server cancellation but stopped
observation before the asynchronous watchdog acknowledgement arrived, failing its
assertion. The test now waits for both events. That failed observation record is retained.
`followup-live-checks/summary.json` records nine successful actual Gazebo executor regression
checks with the fault flag enabled. These repeats are regression checks, not additional
independent quality examples. The previous nominal study and original raw manifest remain
unchanged. `source_versions.json` identifies the tested source hashes; `manifest.json`
inventories files archived before this explanatory README.

Inside Ubuntu, after sourcing Jazzy and the package install, with simulation running:

```bash
export ROS_DOMAIN_ID=73 ROS_LOCALHOST_ONLY=1
python3 scripts/check_robotics_late_goal.py --output runs/new-late-goal-check \
  --validator "$HOME/projects/oak-build/oak-validate" \
  --policy "$PWD/configs/robotics/policy_v1.json"
```

The test owns and stops its namespaced child processes. Run only in the isolated project
ROS domain. It requires an installed package, /clock and /scan, but no model server.
