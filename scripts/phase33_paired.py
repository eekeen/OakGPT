"""Execute a frozen, paired 24-world replication; completed trials are never retried."""

import argparse
import json
import random
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from navigation_study import run_trial
from paired_navigation_study import check_freeze

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worlds", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    freeze = check_freeze(args.freeze)
    generation = json.loads((args.worlds / "generation.json").read_text())
    if generation["freeze_sha256"] != sha256(args.freeze) or generation["split"] != "held_out":
        raise ValueError("Generation does not match freeze")
    worlds = sorted(p.parent for p in args.worlds.glob("*/world.json"))
    if len(worlds) != 24 or len(generation["start_seeds"]) != 8:
        raise ValueError("Expected 24 worlds in eight independent start-seed clusters")
    rng = random.Random(generation["master_seed"] ^ 0x33BADC)
    rng.shuffle(worlds)
    first = [True] * 12 + [False] * 12
    rng.shuffle(first)
    schedule = []
    for world, candidate_first in zip(worlds, first, strict=True):
        variants = (
            ["candidate", "phase32_sync"] if candidate_first else ["phase32_sync", "candidate"]
        )
        schedule.extend({"world": world.name, "variant": variant} for variant in variants)
    assets = {
        p.relative_to(args.worlds).as_posix(): sha256(p)
        for p in args.worlds.rglob("*")
        if p.is_file()
    }
    spec = {"schedule": schedule, "assets_sha256": assets, "freeze_sha256": sha256(args.freeze)}
    args.output.mkdir(parents=True, exist_ok=args.resume)
    if args.resume:
        if json.loads((args.output / "schedule.json").read_text()) != spec:
            raise ValueError("Resume schedule/assets differ")
    else:
        write_new_json(args.output / "schedule.json", spec)
    for variant in ["candidate", "phase32_sync"]:
        (args.output / variant).mkdir(exist_ok=args.resume)
    results = []
    for entry in schedule:
        check_freeze(args.freeze)
        for name, digest in assets.items():
            if sha256(args.worlds / name) != digest:
                raise ValueError("Held-out asset changed: " + name)
        directory = args.output / entry["variant"] / entry["world"]
        if directory.exists():
            if not args.resume or not (directory / "result.json").exists():
                raise RuntimeError(
                    "Inspect preserved incomplete case before resuming: " + str(directory)
                )
            result = json.loads((directory / "result.json").read_text())
            results.append({**entry, "result": result})
            continue
        preflight = args.output / "host-preflight"
        preflight.mkdir(exist_ok=True)
        baseline = preflight / f"{entry['variant']}-{entry['world']}-{time.time_ns()}.json"
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-File",
                "scripts/measure_phase33_host.ps1",
                "-Output",
                str(baseline),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if not json.loads(baseline.read_text(encoding="utf-8-sig"))["quiet_baseline"]:
            raise RuntimeError(
                "Host gate failed before dispatch; no replacement trial: " + str(baseline)
            )
        candidate = entry["variant"] == "candidate"
        profile = (
            freeze["fastdds_profile"]
            if candidate
            else "configs/robotics/phase32_fastdds_services.xml"
        )
        cyclone_config = freeze["cyclone_config"] if candidate else None
        config = SimpleNamespace(
            output=args.output / entry["variant"],
            install=freeze["install"],
            launch="expiry.launch.py",
            overlay=Path(freeze["corrected_overlay"]),
            progress_trace=True,
            timing=True,
            timing_stacks=False,
            clock_mailbox=True,
            startup_probe=True,
            trace_logging="on",
            publication_mode="SYNCHRONOUS",
            rmw=freeze["rmw"] if candidate else "rmw_fastrtps_cpp",
            cyclone_config=Path(cyclone_config) if cyclone_config else None,
            fastdds_profile=Path(profile) if profile else None,
            expiry_plugin_dir=freeze["expiry_plugin_dir"],
            instructions=["Go to station", "Inspect storage", "Go to dock"],
        )
        print("HELD_OUT_PHASE33", entry, flush=True)
        result = run_trial(config, args.worlds / entry["world"])
        results.append({**entry, "result": result})
    write_new_json(args.output / "paired_results.json", {"trials": results})
    (args.output / "COMPLETE").touch()


if __name__ == "__main__":
    main()
