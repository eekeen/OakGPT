import argparse
import json
from pathlib import Path

from oakgpt.robotics.evaluate import run_study
from oakgpt.robotics.planner import LocalPlanner, deterministic
from oakgpt.robotics.plans import envelope
from oakgpt.robotics.safety import receiver_clock, submit_spool, validate_cpp


def main() -> None:
    parser = argparse.ArgumentParser(prog="oakgpt-robot")
    sub = parser.add_subparsers(dest="command", required=True)
    study = sub.add_parser("evaluate")
    study.add_argument("--config", type=Path, required=True)
    language = sub.add_parser("language")
    language.add_argument("--config", type=Path, required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--instruction", required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--planner", choices=["baseline", "qwen"], default="baseline")
    plan.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    if args.command == "language":
        from oakgpt.robotics.language import run_language

        print(json.dumps(run_language(args.config)["summaries"], indent=2))
        return
    if args.command == "evaluate":
        print(json.dumps(run_study(args.config)["summaries"], indent=2))
        return
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.planner == "qwen":
        raw, proposal = LocalPlanner(config.get("url", "http://127.0.0.1:18082")).propose(
            args.instruction
        )
    else:
        raw, proposal = deterministic(args.instruction)
    if proposal["decision"] == "reject":
        print(raw)
        return
    mission = envelope(
        args.instruction, proposal, receiver_now_ms=receiver_clock(config["clock_command"])
    )
    decision = validate_cpp(mission, config["validator_command"])
    print(json.dumps({"proposal": proposal, "validation": decision, "mission": mission}, indent=2))
    if args.submit and decision["accepted"]:
        spool = (args.config.parent / config["spool"]).resolve()
        print(submit_spool(mission, spool))


if __name__ == "__main__":
    main()
