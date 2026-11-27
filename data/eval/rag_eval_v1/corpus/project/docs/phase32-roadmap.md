# Research priorities after Phase 3.2

1. **Close failed or unavailable acceptance criteria.** Replicate formal faults
   with valid motion preconditions, independently confirmed payload delivery and
   retained failed runs. Investigate transient lifecycle/watchdog readiness and
   vendor shutdown errors before unattended demonstrations. Do not trade away
   expiration or authorization checks to improve navigation completion.
2. **Replicate navigation externally.** Freeze a second cohort with new layout
   families, more independent start-seed clusters and repeated sessions. Include
   dynamic obstacles only after the static study is stable. Separate startup,
   planning, controller, localization and action-protocol failure denominators.
3. **Improve independent observation.** Add actual Gazebo contact sensing and
   record acceleration/velocity ground truth directly. Continue retaining pose
   traces and sampling gaps. Circle/box clearance is insufficient evidence for
   collision-free operation or between-sample stopping bounds.
4. **Test the lowest command consumer.** Evaluate host suspend/resume, WSL VM
   suspension and compound guard/bridge/watchdog failures in a controlled local
   environment. A native simulator plugin cannot establish physical coast-down
   behavior. Any later robot must have independently clocked actuator-side expiry
   and an operator-controlled stop, followed by separate physical validation.
5. **Prepare a reproducible offline demonstration.** Pin installed versions,
   verify model/binary hashes, audit owned-process cleanup, and display rejected
   missions and unavailable telemetry explicitly. Keep large bags local and
   publish byte-verifiable compact evidence. Preserve the independent C++ gate.
6. **Revisit language-model value before fine-tuning.** Use the approved Phase 3.1
   linguistic results and failure taxonomy to define a research question that
   distinguishes interpretation from executable authorization. Preregister a
   separate held-out linguistic set and independent review. LoRA remains future
   work until navigation and observation limitations are resolved.

A publication should present negative results, extensive development selection,
small-sample uncertainty, shared-runtime confounding, sampling limitations and
simulator-only scope as core findings. A portfolio demonstration should make
those limits easy to inspect rather than claiming certified or physical safety.
