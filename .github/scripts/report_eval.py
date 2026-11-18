#!/usr/bin/env python3
"""
LangSmith evaluation report generator.
Processes evaluation results and creates PR comments with test results.
"""

import argparse
import glob
import json
import operator
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

from langsmith import Client

# Operator map for threshold comparisons
OP_MAP = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


def parse_threshold(threshold_str: str) -> tuple:
    """Parse threshold expression and return operator and value."""
    for symbol in sorted(OP_MAP.keys(), key=len, reverse=True):
        if threshold_str.startswith(symbol):
            return OP_MAP[symbol], float(threshold_str[len(symbol) :])
    raise ValueError(f"Invalid threshold format: {threshold_str}")


def format_score(value: Optional[float]) -> str:
    """Format score for display."""
    return f"{value:.2f}" if value is not None else "N/A"


def process_config(config_path: str, client: Client) -> Dict[str, Any]:
    """Process a single evaluation config file."""
    print(f"🔍 Processing evaluation config: {config_path}")

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Failed to read config {config_path}: {e}")
        return {}

    experiment_name = config.get("experiment_name")
    criteria = config.get("criteria", {})

    if not experiment_name:
        print(f"❌ No experiment_name found in {config_path}")
        return {}

    try:
        runs = list(client.list_runs(project_name=experiment_name))
        if not runs:
            print(f"⚠️  No runs found for experiment: {experiment_name}")
            return {"experiment_name": experiment_name, "results": []}

        run_ids = [r.id for r in runs]
        feedbacks = client.list_feedback(run_ids=run_ids)

        feedback_by_key = defaultdict(list)
        for fb in feedbacks:
            if fb.score is not None:
                feedback_by_key[fb.key].append(fb.score)

        table_rows = []
        num_passed = 0
        num_failed = 0

        for key, scores in feedback_by_key.items():
            avg_score = sum(scores) / len(scores) if scores else None
            threshold_expr = criteria.get(key)
            passed = "N/A"
            check = "–"

            if threshold_expr:
                try:
                    op, value = parse_threshold(threshold_expr)
                    result = op(avg_score, value)
                    passed = "✅" if result else "❌"
                    check = threshold_expr
                    if result:
                        num_passed += 1
                    else:
                        num_failed += 1
                except ValueError as e:
                    print(
                        f"⚠️  Invalid threshold '{threshold_expr}' for key '{key}': {e}"
                    )
                    passed = "❌"
                    num_failed += 1

            display_score = format_score(avg_score)
            table_rows.append((key, display_score, check, passed))

        # A judge that errored leaves no feedback, so its threshold would
        # otherwise be skipped rather than failed.
        for key, threshold_expr in criteria.items():
            if key not in feedback_by_key:
                table_rows.append((key, format_score(None), threshold_expr, "❌"))
                num_failed += 1

        return {
            "experiment_name": experiment_name,
            "table_rows": table_rows,
            "num_passed": num_passed,
            "num_failed": num_failed,
            "total": num_passed + num_failed,
        }

    except Exception as e:
        print(f"❌ Error processing experiment {experiment_name}: {e}")
        return {"experiment_name": experiment_name, "error": str(e)}


def failed_experiments(results: List[Dict[str, Any]]) -> List[str]:
    """Names of experiments that errored, have no results, or missed a threshold."""
    failed = []
    for result in results:
        errored = "error" in result
        empty = not result.get("table_rows")
        missed_threshold = result.get("num_failed", 0) > 0
        if errored or empty or missed_threshold:
            failed.append(result.get("experiment_name", "Unknown"))
    return failed


def write_markdown_report(
    results: List[Dict[str, Any]], output_file: str = "eval_comment.md"
):
    """Write evaluation results to markdown file."""
    print(f"📝 Writing report to {output_file}")

    with open(output_file, "w") as f:
        f.write("# 🧪 LangSmith Evaluation Results\n\n")

        for result in results:
            experiment_name = result.get("experiment_name", "Unknown")

            if "error" in result:
                f.write(f"### ❌ {experiment_name}\n\n")
                f.write(f"**Error:** {result['error']}\n\n")
                continue

            if not result.get("table_rows"):
                f.write(f"### ⚠️ {experiment_name}\n\n")
                f.write("No evaluation results found.\n\n")
                continue

            f.write(f"### 📊 {experiment_name}\n\n")
            f.write("| Feedback Key | Avg Score | Criterion | Pass? |\n")
            f.write("|--------------|-----------|-----------|--------|\n")

            for row in result["table_rows"]:
                f.write(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |\n")

            total = result.get("total", 0)
            if total > 0:
                num_passed = result.get("num_passed", 0)
                num_failed = result.get("num_failed", 0)
                summary = f"**✅ {num_passed} Passed, ❌ {num_failed} Failed**"
            else:
                summary = "No thresholds defined."

            f.write(f"\n{summary}\n\n")

    print(f"✅ Report written to {output_file}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate LangSmith evaluation reports for PR comments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all evaluation config files
  python report_eval.py

  # Process specific config files
  python report_eval.py evaluation_config__*.json

  # Process single config file
  python report_eval.py evaluation_config__my_experiment.json
        """,
    )

    parser.add_argument(
        "config_files",
        nargs="*",
        help="Evaluation config files to process (default: evaluation_config__*.json)",
    )

    parser.add_argument(
        "--output",
        "-o",
        default="eval_comment.md",
        help="Output markdown file (default: eval_comment.md)",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    # Set up LangSmith client
    try:
        client = Client()
    except Exception as e:
        print(f"❌ Failed to initialize LangSmith client: {e}")
        print("Make sure LANGSMITH_API_KEY environment variable is set.")
        sys.exit(1)

    # Determine config files to process
    if args.config_files:
        config_files = args.config_files
    else:
        config_files = glob.glob("evaluation_config__*.json")

    if not config_files:
        print("❌ No evaluation config files found.")
        print("Expected files matching pattern: evaluation_config__*.json")
        sys.exit(1)

    if args.verbose:
        print(f"🔍 Found {len(config_files)} config files: {config_files}")

    # Process all config files
    results = []
    for config_path in config_files:
        if not os.path.exists(config_path):
            print(f"⚠️  Config file not found: {config_path}")
            continue

        result = process_config(config_path, client)
        if result:
            results.append(result)

    if not results:
        print("❌ No valid evaluation results to process.")
        sys.exit(1)

    # Write report
    write_markdown_report(results, args.output)

    # Summary
    total_experiments = len(results)
    successful_experiments = sum(1 for r in results if "error" not in r)
    print(
        f"✅ Processed {successful_experiments}/{total_experiments} experiments successfully"
    )

    # Fail only after the report exists, so the PR comment still shows why.
    failed = failed_experiments(results)
    if failed:
        print(f"❌ Evaluation thresholds not met: {', '.join(failed)}")
        sys.exit(1)
    print("✅ All evaluation thresholds met.")


if __name__ == "__main__":
    main()
