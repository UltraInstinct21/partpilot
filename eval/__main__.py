"""The command line of the PartPilot evaluation harness.

Run ``python -m eval --help`` for the list of the commands.

Commands:

``validate-gold <csv>``
    Check a gold set file and print the problems.
``agreement <csv>``
    Print the agreement between the two members that labelled the set.
``queries``
    Print the 30 test queries and check them.
``charts <results.json>``
    Write the PNG charts of one evaluation run.
``demo``
    Run the six experiments on the recorded fixtures. No network, no key.
"""

from __future__ import annotations

import argparse
import json
import sys

from eval.charts import ChartsUnavailable, load_results, render_all
from eval.gold_set import inter_annotator_agreement, load_gold_set, validate_gold_set
from eval.queries import QUERIES, validate_queries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval",
        description="The PartPilot evaluation harness (plan WP8).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-gold", help="check a gold set CSV file")
    validate.add_argument("path", help="the path of the gold set CSV file")

    agreement = subparsers.add_parser(
        "agreement", help="report the agreement of a gold set CSV file"
    )
    agreement.add_argument("path", help="the path of the gold set CSV file")

    subparsers.add_parser("queries", help="print and check the 30 test queries")

    charts = subparsers.add_parser("charts", help="write the PNG charts of an evaluation run")
    charts.add_argument("path", help="the path of the results JSON file")
    charts.add_argument("--out", default=None, help="the output directory (default: eval/results)")

    demo = subparsers.add_parser("demo", help="run the six experiments on the recorded fixtures")
    demo.add_argument("--out", default=None, help="the output directory (default: eval/results)")
    demo.add_argument("--gold", default=None, help="the path of a gold set CSV file")

    return parser


def _command_validate_gold(path: str) -> int:
    problems = validate_gold_set(path)
    if not problems:
        print(f"{path}: the gold set is valid.")
        return 0
    print(f"{path}: the gold set has {len(problems)} problem(s).")
    for problem in problems:
        print(f"  - {problem}")
    return 1


def _command_agreement(path: str) -> int:
    rows = load_gold_set(path, skip_invalid=True)
    report = inter_annotator_agreement(rows)
    print(json.dumps(report, indent=2))
    return 0


def _command_queries() -> int:
    problems = validate_queries()
    for index, (text, expected) in enumerate(QUERIES, start=1):
        print(f"{index:2d}. {text}")
        print(f"    expected: {json.dumps(expected)}")
    if problems:
        print("")
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("")
    print(f"{len(QUERIES)} queries, all valid.")
    return 0


def _command_charts(path: str, out: str | None) -> int:
    results = load_results(path)
    try:
        written = render_all(results, out)
    except ChartsUnavailable as exc:
        print(f"the charts are not available: {exc}", file=sys.stderr)
        return 2
    if not written:
        print("the charts are not available: matplotlib is not installed.", file=sys.stderr)
        return 2
    for item in written:
        print(item)
    return 0


def _command_demo(out: str | None, gold: str | None) -> int:
    from eval.demo import run_demo

    results = run_demo(gold_path=gold, output_dir=out)
    experiments = results["experiments"]
    print("=== Experiment 1: the tiers ===")
    print(experiments["experiment_1_tiers"]["markdown"])
    print("")
    print("=== Experiment 2: the tiered use against the best tier ===")
    print(experiments["experiment_2_tiered_vs_best"]["markdown"])
    print("")
    print("=== Experiment 3: the validation on and off ===")
    print(experiments["experiment_3_validation_on_off"]["markdown"])
    print("")
    print("=== Experiment 4: the natural-language search ===")
    print(experiments["experiment_4_search"]["markdown"])
    print("")
    print("=== Experiment 5: the alternative finder ===")
    print(experiments["experiment_5_alternatives"]["markdown"])
    print("")
    print("=== Experiment 6: the accuracy per manufacturer ===")
    print(experiments["experiment_6_by_manufacturer"]["markdown"])
    print("")
    print(f"the results are written to {results['results_file']}")
    try:
        written = render_all(results, out)
    except ChartsUnavailable as exc:
        print(f"the charts are not written: {exc}", file=sys.stderr)
    else:
        for item in written:
            print(f"chart: {item}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return the exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate-gold":
        return _command_validate_gold(args.path)
    if args.command == "agreement":
        return _command_agreement(args.path)
    if args.command == "queries":
        return _command_queries()
    if args.command == "charts":
        return _command_charts(args.path, args.out)
    if args.command == "demo":
        return _command_demo(args.out, args.gold)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
