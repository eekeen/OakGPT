# Next development phases

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
