#!/usr/bin/env python3
"""
Run all chart scripts in this directory.

This script discovers Python files in the same directory (except itself and
special files) and executes them from the repository root so that relative
paths used by the chart scripts (e.g. "results/leaderboard.json" and
"data/images/...") resolve correctly.

Usage:
    python generate_all_charts.py            # run all charts, stop on first error
    python generate_all_charts.py --continue-on-error
    python generate_all_charts.py --timeout 300
    python generate_all_charts.py --list      # show discovered scripts and exit
    python generate_all_charts.py --scripts 01_performanceChart.py,04_tokenEfficiency.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import traceback
from pathlib import Path
from typing import List, Tuple


def discover_scripts(this_file: Path) -> List[Path]:
    """Return a sorted list of chart script paths in the same directory, excluding this file."""
    directory = this_file.parent
    candidates = sorted(directory.glob("*.py"))
    result = []
    for p in candidates:
        name = p.name
        if name == this_file.name:
            continue
        if name.startswith("_"):
            # skip private/utility scripts
            continue
        if name == "__init__.py":
            continue
        result.append(p)
    return result


def run_script(
    script_path: Path, cwd: Path, timeout: int, verbose: bool
) -> Tuple[bool, str]:
    """
    Execute a single script using the current Python interpreter.

    Returns (success, combined_output).
    """
    cmd = [sys.executable, str(script_path.resolve())]
    if verbose:
        print(f"> Running: {' '.join(cmd)} (cwd={cwd}, timeout={timeout}s)")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ""
        if proc.stdout:
            out += proc.stdout
        if proc.stderr:
            # include stderr after stdout for easier debugging
            out += ("\n" if out else "") + "STDERR:\n" + proc.stderr
        success = proc.returncode == 0
        return success, out
    except subprocess.TimeoutExpired as exc:
        tb = "".join(traceback.format_exc())
        return False, f"Timeout after {timeout} seconds\n{tb}"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Generate all chart images by running chart scripts."
    )
    ap.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all scripts even if some fail; exit with non-zero code if any failed.",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-script timeout in seconds (default: 120).",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="List discovered chart scripts and exit.",
    )
    ap.add_argument(
        "--scripts",
        type=str,
        default="",
        help="Comma-separated subset of script filenames to run (relative to this directory).",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print more verbose progress information and command lines.",
    )
    return ap.parse_args()


def main() -> int:
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[
        3
    ]  # altered-riddles/scripts/charts/blog -> parents[0]=blog, [1]=charts, [2]=scripts, [3]=repo root
    discovered = discover_scripts(this_file)

    args = parse_args()

    if args.scripts:
        requested = [s.strip() for s in args.scripts.split(",") if s.strip()]
        filtered = []
        names = {p.name: p for p in discovered}
        for name in requested:
            if name not in names:
                print(
                    f"Warning: requested script '{name}' not found in {this_file.parent}",
                    file=sys.stderr,
                )
            else:
                filtered.append(names[name])
        scripts_to_run = filtered
    else:
        scripts_to_run = discovered

    if not scripts_to_run:
        print("No chart scripts found to run.")
        return 0

    if args.list:
        print("Discovered chart scripts (in execution order):")
        for p in scripts_to_run:
            print(" -", p.name)
        return 0

    failures = []
    successes = []

    print(f"Repository root resolved to: {repo_root}")
    print(f"Found {len(scripts_to_run)} script(s) to run:")
    for p in scripts_to_run:
        print("  -", p.name)
    print("Starting execution...\n")

    for script in scripts_to_run:
        print(f"--- Running {script.name} ---")
        ok, output = run_script(
            script, cwd=repo_root, timeout=args.timeout, verbose=args.verbose
        )
        if output:
            print(output.rstrip())
        if ok:
            print(f"+++ {script.name} completed successfully.\n")
            successes.append(script.name)
        else:
            print(f"!!! {script.name} failed.\n")
            failures.append(script.name)
            if not args.continue_on_error:
                print("Stopping due to failure (use --continue-on-error to proceed).")
                break

    print("\nExecution summary:")
    print(f"  Successes: {len(successes)}")
    for s in successes:
        print("   -", s)
    print(f"  Failures: {len(failures)}")
    for f in failures:
        print("   -", f)

    if failures:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
