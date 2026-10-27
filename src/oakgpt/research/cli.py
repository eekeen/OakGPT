import argparse
import json
from pathlib import Path

from oakgpt.datasets import prepare_wikitext
from oakgpt.research.experiments import run_suite
from oakgpt.research.figures import plot_results
from oakgpt.research.gpu import verify_gpu
from oakgpt.research.quantization import run_quantization
from oakgpt.research.statistics import prompt_summary


def main() -> None:
    parser = argparse.ArgumentParser(prog="oakgpt-research")
    commands = parser.add_subparsers(dest="command", required=True)
    data = commands.add_parser("prepare-wikitext")
    data.add_argument("--raw", type=Path, required=True)
    data.add_argument("--output", type=Path, required=True)
    data.add_argument("--seed", type=int, default=2026)
    suite = commands.add_parser("suite")
    suite.add_argument("--config", type=Path, required=True)
    summary = commands.add_parser("summarize")
    summary.add_argument("report", type=Path)
    gpu = commands.add_parser("verify-gpu")
    gpu.add_argument("--output", type=Path, required=True)
    gpu.add_argument("--preset", type=Path, default=Path("configs/train_rtx2060.json"))
    quant = commands.add_parser("quantization")
    quant.add_argument("--config", type=Path, required=True)
    figures = commands.add_parser("figures")
    figures.add_argument("--training", type=Path, required=True)
    figures.add_argument("--quantization", type=Path, required=True)
    figures.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare-wikitext":
        result = prepare_wikitext(args.raw, args.output, args.seed)
        print(json.dumps(result["counts"], indent=2))
    elif args.command == "suite":
        result = run_suite(args.config)
        print(json.dumps(result["groups"], indent=2))
    elif args.command == "verify-gpu":
        result = verify_gpu(args.output.resolve(), args.preset)
        print(json.dumps(result["checks"], indent=2))
    elif args.command == "quantization":
        result = run_quantization(args.config)
        print(json.dumps(result["summaries"], indent=2))
    elif args.command == "figures":
        plot_results(args.training, args.quantization, args.output)
    else:
        print(
            json.dumps(
                prompt_summary(json.loads(args.report.read_text(encoding="utf-8"))), indent=2
            )
        )


if __name__ == "__main__":
    main()
