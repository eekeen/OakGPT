# Roadmap

## Priorities after Phase 3.1

1. **Navigation reliability before broader autonomy.** Preserve the nine-world results,
   including four pre-injection navigation failures. Record planned paths, costmaps,
   controller state and near-goal behavior on a separate development world set. Tune
   progress/controller settings there, then preregister a new held-out study. Keep
   mission expiration and the independent C++ contract fixed.
2. **Remove remaining software stop failure points.** Evaluate guard-process loss,
   compound faults and host suspension. Add independently enforced actuator-side command
   expiry and process supervision before a physical robot is considered. A canceled ROS
   action or a zero message does not prove motion stopped.
3. **Broader language with independent review.** Obtain additional annotators and an
   untouched instruction test set. Compare exact interpretation, abstention, unsafe
   proposals and controlled authorization separately. Implement an audited operator
   review flow only if needed; confirmation must never bypass C++ validation.
4. **Fine-tuning as a measured hypothesis.** Use disjoint training data, excluding both
   frozen instruction fixtures. Evaluate adapter training and inference within 6 GB;
   compare against the deterministic recognizer and unchanged base models. Do not trade
   increased unsafe proposals for a higher positive interpretation score.
5. **Demonstration and publication.** Provide a deterministic offline demonstration with
   replayable success and failure traces, pinned environments, raw manifests and clear
   simulator-only limits. Publish negative results and missing outcomes alongside gains.

The sections below retain the original extension plan for context. Phase 2 GPU studies
and Phase 3/3.1 C++/ROS2/Gazebo components are now implemented; LoRA remains future work.

Phase 1 implements scratch training and local inference. Phase 2 adds physical GPU
verification, licensed data and controlled experiments. Phase 3 now implements bounded
planning, C++ validation and actual ROS2 Jazzy/Nav2/Gazebo execution. LoRA remains deferred.
Historical phase reports retain their original evidence.

## Prior recommendation (before Phase 3.1)

This recommendation motivated the now-completed Phase 3.1 study; the priorities above
supersede it.

Prioritize simulator ground-truth trajectory and stopping-distance checks, randomized
cluttered worlds, independent simulator seeds, action-server outages, sensor/TF loss,
watchdog failure, process restarts and long-duration replay tests. Automate optional ROS
integration on a suitable Ubuntu runner while keeping CPU CI independent of ROS/models.

Freeze a second independently authored instruction set before prompt refinement. Evaluate
language coverage and abstention with paired comparisons and randomized timing order.
The v1 grammar already has a perfect deterministic baseline; observed unsafe raw Qwen
accepts do not justify expanding actuator authority. Keep current references immutable.

Physical deployment requires a hardware e-stop, independent velocity deadman, measured
stopping distance, authenticated ROS communication, operator arming and a new explicit
threat analysis. The current executor remains simulation-only. Later LoRA research may
test structured planning and abstention using original trainable weights and independent
held-out requests, after measuring adapter feasibility on 6 GB VRAM.

## Original planning notes (historical)

The sequence below records the initial roadmap. Current phase boundaries follow the
implemented user requests and verification documents above.

## Phase 2: credible data and LoRA

Start with a licensed, versioned text corpus and document-level deduplicated splits.
Establish several scratch baselines and a frozen held-out evaluation set, then quantify
Qwen quantization and offload tradeoffs. Implement or integrate LoRA in a separate
`finetuning/` module with immutable base-model identifiers, adapter metadata, tokenizer
and prompt-template versions. Training adapters requires original trainable weights;
GGUF inference weights are not the scratch training checkpoint format. Begin with short
sequences and small microbatches; measure 6 GB feasibility before choosing QLoRA packages.
Keep optional fine-tuning dependencies out of CPU core installation. Do not claim LoRA
support until adapter training, loading and evaluation are tested.

## Phase 3: command validation in C++

Define a versioned JSON action schema with allowlisted action names, SI units, bounded
linear/angular velocity, timestamps and expiration, frame identifiers and finite numbers.
Write a standalone C++ validator with rejection tests, fuzz cases, and CMake/CTest CI.
The Python inference adapter proposes data; only a validated typed action can pass to
the controller. No shell commands, generated code execution or direct model-to-motor path.
Add rate limits, watchdog stop, stale-command rejection and explicit operator arming.
Implement these when the action schema and robot limits are selected, avoiding speculative
stub APIs in the working language-model core.

## Phase 4: ROS2 Jazzy and Gazebo

Use a separate Ubuntu 24.04/ROS2 Jazzy environment, independently of native Windows
development. Choose the compatible Gazebo distribution using current official ROS docs
at implementation time. Package a ROS inference bridge and validator/controller as
separate nodes. Start in simulation with bounded commands and reproducible world files.
Record model/schema versions, simulator seeds, rosbag data, success criteria and failure
cases. Latency budgets, QoS and safe fallback must be designed from measured behavior.
Keep ROS and simulation dependencies outside the base Python package and CPU CI.
