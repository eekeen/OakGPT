# Executor fault-marker ordering follow-up

Baseline: `58f275a`; branch `remediation/phase33-executor-restart`.
The initial implementation, failed host admission and its archive remain unchanged.

Final review found that a marker write error could occur before setting the
in-memory executor latch. The setter now latches memory first. An exception
while writing `SAFETY_FAULT` still propagates, but neither an attempted assignment
of `False` nor readiness certificates can clear that in-memory fault.
The new regression injects an `OSError` and verifies that rearming remains blocked.
It is a synthetic failure test, not a power-loss/filesystem durability experiment.

Fresh source/build/install prefix:
`/home/eekeen/projects/oak-phase33-executor-remediation-v6`.
All mission Python files match working source and snapshot byte for byte.
Hashes for all four native libraries are recorded in `verification.json`.

Actual checks:

- Python: **130 passed, 2 hardware skips**; strict mypy **38 modules**; Ruff lint/format pass.
- Fresh installed ROS/package tests: **29 passed**, no errors/failures/skips.
- Separate installed expiry/message tests: **2 passed**.
- Wheel/sdist built; **17 required sources** verified.
- The C++ authorization, expiry code and policy/configuration did not change.
  Release, ASan/UBSan, oracle and actual mailbox results are retained in the
  [initial remediation archive](../executor-remediation-v2/raw/manifest.json);
  that C++ suite was not unnecessarily repeated for this Python-only change.
- All six hosted CI jobs passed for baseline `58f275a` at
  [run 42390689758](https://github.com/eekeen/OakGPT/actions/runs/42390689758).
  Follow-up commit CI is checked separately after push.

`raw/manifest.json` preserves exact follow-up logs and source copies. Its synthetic
ROS helper inherited an obsolete relative C++ receipt path from the earlier template;
the authoritative `verification.json` points explicitly to the original component
logs. No earlier log was rewritten to conceal that procedural issue.

**No Gazebo development or independent validation was dispatched.** The existing
host gate still fails (24.75–25.55% CPU, 2.18–2.55 selected external cores); no new
quiet-host indication has arrived. No threshold, lease or navigation deadline changed.
There is no measured stopping or safe restart-success claim and no frozen corrected
candidate. **Phase 4 remains NO-GO. PR #6 remains unchanged.**

Next action is a newly qualified quiet-host development window, followed by actual
motion/arrival verification and normal-navigation false-stop measurements. Successful
development must precede a new freeze and independent, previously unconsumed worlds.
