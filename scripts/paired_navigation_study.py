"""Execute a previously generated held-out cohort without tuning or replacing failures."""

import argparse
import json
import random
import subprocess
from pathlib import Path
from types import SimpleNamespace

from navigation_study import run_trial

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def check_freeze(path):
    freeze = json.loads(path.read_text())
    for name, digest in freeze["files_sha256"].items():
        if sha256(Path(name)) != digest:
            raise ValueError("Frozen source/config changed: " + name)
    linux = freeze["linux_artifacts_sha256"]
    captured = subprocess.check_output(
        ["wsl.exe", "-d", "Ubuntu-24.04", "--", "sha256sum", *linux], text=True
    )
    actual = dict(
        (name, digest)
        for digest, name in (line.split(maxsplit=1) for line in captured.splitlines())
    )
    if actual != linux:
        raise ValueError("Installed runtime or validator differs from freeze")
    return freeze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worlds", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", default="/home/eekeen/projects/oak-ros-phase32-v5")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    freeze = check_freeze(args.freeze)
    generation = json.loads((args.worlds / "generation.json").read_text())
    if generation["split"] != "held_out" or generation["freeze_sha256"] != sha256(args.freeze):
        raise ValueError("World generation does not match this freeze")
    worlds = sorted(p.parent for p in args.worlds.glob("*/world.json"))
    if len(worlds) != 12:
        raise ValueError("Expected twelve frozen held-out worlds")
    args.output.mkdir(parents=True, exist_ok=args.resume)
    rng = random.Random(generation["master_seed"] ^ 0x32BADC)
    rng.shuffle(worlds)
    corrected_first = [True] * 6 + [False] * 6
    rng.shuffle(corrected_first)
    schedule = []
    for world, corrected in zip(worlds, corrected_first, strict=True):
        variants = ["corrected_nav2", "original_nav2"]
        if not corrected:
            variants.reverse()
        schedule.extend({"world": world.name, "variant": variant} for variant in variants)
    assets = {
        str(p.relative_to(args.worlds)): sha256(p) for p in args.worlds.rglob("*") if p.is_file()
    }
    specification = {
        "schedule": schedule,
        "world_assets_sha256": assets,
        "freeze_sha256": sha256(args.freeze),
    }
    schedule_path = args.output / "schedule.json"
    if args.resume:
        if json.loads(schedule_path.read_text()) != specification:
            raise ValueError("Persisted schedule/assets differ; refusing to resume")
    else:
        write_new_json(schedule_path, specification)
    for variant in ["original_nav2", "corrected_nav2"]:
        (args.output / variant).mkdir(exist_ok=args.resume)
    results = []
    for entry in schedule:
        check_freeze(args.freeze)
        for name, digest in assets.items():
            if sha256(args.worlds / name) != digest:
                raise ValueError("Held-out world changed: " + name)
        variant = entry["variant"]
        case = args.output / variant / entry["world"]
        if case.exists():
            if not args.resume or not (case / "result.json").exists():
                raise RuntimeError(
                    "Preserved incomplete trial requires process/evidence inspection: " + str(case)
                )
            result = json.loads((case / "result.json").read_text())
            results.append({**entry, "result": result})
            continue
        trial = SimpleNamespace(
            output=args.output / variant,
            install=args.install,
            launch="expiry.launch.py",
            overlay=Path(freeze["corrected_overlay"]) if variant == "corrected_nav2" else None,
            progress_trace=True,
            instructions=["Go to station", "Inspect storage", "Go to dock"],
            expiry_plugin_dir=freeze["expiry_plugin_dir"],
            fastdds_profile=Path(freeze["fastdds_profile"]),
        )
        print("HELD_OUT", entry, flush=True)
        result = run_trial(trial, args.worlds / entry["world"])
        results.append({**entry, "result": result})
    write_new_json(args.output / "paired_results.json", {"trials": results})


if __name__ == "__main__":
    main()
