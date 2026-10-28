"""Generate separate development worlds and held-out worlds only after configuration freeze."""

import argparse
import json
import random
from pathlib import Path

from prepare_robotics_worlds import create_world

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["development", "held_out"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze", type=Path)
    args = parser.parse_args()
    if args.split == "held_out":
        if not args.freeze:
            raise ValueError("Held-out generation requires a prior source/configuration freeze")
        freeze = json.loads(args.freeze.read_text())
        for name, digest in freeze["files_sha256"].items():
            if sha256(Path(name)) != digest:
                raise ValueError("Frozen configuration/source changed: " + name)
        master = random.SystemRandom().randrange(1_000_000, 2_000_000_000)
        seeds = random.Random(master).sample(range(1_000_000, 2_000_000_000), 4)
    else:
        master, seeds = None, [210, 211, 212]
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(Path("configs/robotics/phase32_protocol.json").read_text())
    bounds = protocol["held_out"]["geometry"]
    for family in ["empty", "block", "wall"]:
        for seed in seeds:
            rng = random.Random(seed ^ 0xA05132)
            obstacles = []
            if family == "block":
                size = rng.uniform(*bounds["block_size"])
                obstacles = [
                    {
                        "x": rng.uniform(*bounds["block_x"]),
                        "y": rng.uniform(*bounds["block_y"]),
                        "sx": size,
                        "sy": size,
                    }
                ]
            elif family == "wall":
                obstacles = [
                    {
                        "x": rng.uniform(*bounds["wall_x"]),
                        "y": rng.uniform(*bounds["wall_y"]),
                        "sx": bounds["wall_width"],
                        "sy": rng.uniform(*bounds["wall_length"]),
                    }
                ]
            create_world(args.output / f"{family}-{seed}", family, seed, obstacles)
    write_new_json(
        args.output / "generation.json",
        {
            "split": args.split,
            "master_seed": master,
            "start_seeds": seeds,
            "freeze_sha256": sha256(args.freeze) if args.freeze else None,
            "generator_sha256": sha256(Path(__file__)),
            "protocol_sha256": sha256(Path("configs/robotics/phase32_protocol.json")),
        },
    )


if __name__ == "__main__":
    main()
