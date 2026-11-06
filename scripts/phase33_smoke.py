"""Small quiet-host startup/dispatch qualification, never a large efficacy matrix."""

import argparse
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from navigation_study import run_trial

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-baseline", type=Path, required=True)
    parser.add_argument("--backend", choices=["fast_default", "fast_udp", "cyclone"], required=True)
    parser.add_argument("--install", required=True)
    parser.add_argument("--qualification-only", action="store_true")
    args = parser.parse_args()
    baseline = json.loads(args.host_baseline.read_text(encoding="utf-8-sig"))
    if not baseline["quiet_baseline"]:
        raise RuntimeError("Quiet-host gate unmet")
    args.output.mkdir(parents=True)
    source = args.output / "source"
    source.mkdir()
    for name in [
        "phase33_smoke.py",
        "navigation_study.py",
        "receiver_clock_mailbox.py",
        "probe_ros_startup.py",
        "probe_ros_startup.sh",
        "robotics_session.py",
    ]:
        shutil.copyfile(Path("scripts") / name, source / (name + ".txt"))
    instructions = [] if args.qualification_only else ["Go to station"]
    write_new_json(
        args.output / "protocol.json",
        {
            "backend": args.backend,
            "world": "empty-210",
            "instructions": instructions,
            "host_baseline": baseline,
            "baseline_sha256": sha256(args.host_baseline),
            "install": args.install,
            "deadline_s": 30,
            "lease_ms": 200,
            "scope": "Development startup/dispatch smoke only; no efficacy inference",
        },
    )
    cyclone = args.backend == "cyclone"
    config = SimpleNamespace(
        output=args.output,
        install=args.install,
        launch="expiry.launch.py",
        overlay=Path("configs/robotics/phase32_corrected.json"),
        progress_trace=True,
        timing=True,
        timing_stacks=False,
        clock_mailbox=True,
        startup_probe=True,
        trace_logging="on",
        publication_mode="SYNCHRONOUS",
        rmw="rmw_cyclonedds_cpp" if cyclone else "rmw_fastrtps_cpp",
        cyclone_config=Path("configs/robotics/phase33_cyclonedds.xml") if cyclone else None,
        expiry_plugin_dir=args.install + "-expiry",
        fastdds_profile=None
        if cyclone
        else Path(
            "configs/robotics/phase33_fastdds_udp.xml"
            if args.backend == "fast_udp"
            else "configs/robotics/phase32_fastdds_services.xml"
        ),
        instructions=instructions,
    )
    result = run_trial(config, Path("runs/phase32/development-worlds-v1/empty-210"))
    passed = result["environment_failure"] is None and all(
        mission["result"]["status"] == "completed" for mission in result["missions"]
    )
    write_new_json(
        args.output / "qualification.json",
        {
            "passed": passed,
            "dispatched": len(result["missions"]),
            "environment_failure": result["environment_failure"],
        },
    )
    print(json.dumps({"passed": passed, "environment_failure": result["environment_failure"]}))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
