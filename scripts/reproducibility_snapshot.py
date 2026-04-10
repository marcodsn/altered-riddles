#!/usr/bin/env python3
"""reproducibility_snapshot.py — Generate a reproducibility manifest.

Captures the exact benchmark configuration, model identifiers,
and settings used for each evaluated model.

The manifest includes:
  - benchmark_version
  - benchmark_stats (total, fixed, auxiliary, by_type, by_source)
  - evaluated_models (list of {model, provider, temperature, num_samples,
    output_file, num_records})
  - timestamp of manifest generation

Usage:
    python -m scripts.reproducibility_snapshot
    python -m scripts.reproducibility_snapshot --version 2604
    python -m scripts.reproducibility_snapshot --output custom_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure the repo root is importable when running as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.core.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_MODEL_OUTPUTS,
    DEFAULT_RESULTS,
    get_benchmark_version,
)
from scripts.core.io_utils import load_jsonl, write_json

# ── Benchmark stats ──────────────────────────────────────────────────


def compute_benchmark_stats(benchmark_path: str) -> dict:
    """Read benchmark.jsonl and compute aggregate statistics.

    Returns a dict with keys: total, fixed, auxiliary, by_type, by_source.
    """
    entries = load_jsonl(benchmark_path)

    total = len(entries)
    fixed = 0
    auxiliary = 0
    by_type: dict[str, int] = defaultdict(int)
    by_source: dict[str, int] = defaultdict(int)

    for entry in entries:
        entry_set = entry.get("set", "")
        if entry_set == "fixed":
            fixed += 1
        elif entry_set == "auxiliary":
            auxiliary += 1

        rtype = entry.get("type", "unknown")
        by_type[rtype] += 1

        source = entry.get("source", "unknown")
        by_source[source] += 1

    return {
        "total": total,
        "fixed": fixed,
        "auxiliary": auxiliary,
        "by_type": dict(sorted(by_type.items())),
        "by_source": dict(sorted(by_source.items())),
    }


# ── Model output scanning ────────────────────────────────────────────


def _extract_model_info_from_records(records: list[dict]) -> dict:
    """Extract model metadata from the first few records of an output file.

    Scans up to the first 10 records to find model name, provider,
    temperature, quantization, and sample count information.
    """
    model = None
    provider = None
    temperature = None
    quantization = None
    sample_indices: set[int] = set()

    for rec in records[:10]:
        if model is None:
            model = rec.get("model")
        if provider is None:
            provider = rec.get("provider")
        if temperature is None:
            temperature = rec.get("temperature")
        if quantization is None:
            quantization = rec.get("quantization")

        si = rec.get("sample_index")
        if si is not None:
            sample_indices.add(si)

    # Also scan all records for sample indices to get accurate count
    all_sample_indices: set[int] = set()
    for rec in records:
        si = rec.get("sample_index")
        if si is not None:
            all_sample_indices.add(si)

    num_samples = max(all_sample_indices) if all_sample_indices else 1

    return {
        "model": model or "unknown",
        "provider": provider or "unknown",
        "temperature": temperature,
        "quantization": quantization,
        "num_samples": num_samples,
    }


def scan_model_outputs(outputs_dir: Path) -> list[dict]:
    """Scan all model output JSONL files and extract metadata.

    Returns a list of dicts, one per output file, containing model
    metadata and record counts.
    """
    if not outputs_dir.exists():
        return []

    output_files = sorted(outputs_dir.glob("*.jsonl"))
    models: list[dict] = []

    for output_file in output_files:
        # Skip backup files
        if output_file.name.endswith(".bak"):
            continue

        try:
            records = _load_jsonl_raw(output_file)
        except Exception as exc:
            print(f"Warning: could not read {output_file.name}: {exc}", file=sys.stderr)
            continue

        if not records:
            continue

        info = _extract_model_info_from_records(records)
        info["output_file"] = output_file.name
        info["num_records"] = len(records)
        models.append(info)

    return models


def _load_jsonl_raw(path: Path) -> list[dict]:
    """Read a JSONL file, skipping malformed lines.

    A lightweight version that doesn't call sys.exit on missing files.
    """
    entries: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


# ── Eval file scanning ────────────────────────────────────────────────


def scan_eval_results(results_dir: Path) -> list[dict]:
    """Scan eval result files for summary-level metadata.

    Returns a list of dicts with model, provider, quantization, and
    key summary metrics extracted from each eval JSON.
    """
    if not results_dir.exists():
        return []

    eval_files = sorted(results_dir.glob("*_eval.json"))
    evals: list[dict] = []

    for eval_file in eval_files:
        try:
            with open(eval_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: skipping {eval_file.name}: {exc}", file=sys.stderr)
            continue

        summary = data.get("summary", {})
        evals.append(
            {
                "model": data.get("model", "unknown"),
                "provider": data.get("provider", "unknown"),
                "quantization": data.get("quantization"),
                "eval_file": eval_file.name,
                "original_accuracy": summary.get("original_accuracy"),
                "altered_accuracy": summary.get("altered_accuracy"),
                "total_score": summary.get("total_score"),
                "num_samples": summary.get("num_samples"),
                "num_riddles": summary.get("num_riddles"),
            },
        )

    return evals


# ── Manifest assembly ────────────────────────────────────────────────


def build_manifest(
    version: str,
    benchmark_stats: dict,
    evaluated_models: list[dict],
    eval_summaries: list[dict],
) -> dict:
    """Assemble the full reproducibility manifest."""
    return {
        "benchmark_version": version,
        "benchmark_stats": benchmark_stats,
        "evaluated_models": evaluated_models,
        "eval_summaries": eval_summaries,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── CLI ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a reproducibility manifest for the current benchmark version."
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Benchmark version (default: read from data/VERSION)",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default=DEFAULT_BENCHMARK,
        help=f"Path to benchmark.jsonl (default: {DEFAULT_BENCHMARK})",
    )
    parser.add_argument(
        "--model-outputs",
        type=str,
        default=DEFAULT_MODEL_OUTPUTS,
        help=f"Base model outputs directory (default: {DEFAULT_MODEL_OUTPUTS})",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=DEFAULT_RESULTS,
        help=f"Base results directory (default: {DEFAULT_RESULTS})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output path for the manifest JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    version = args.version or get_benchmark_version()

    # 1) Benchmark stats
    benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        print(f"Error: benchmark file not found: {benchmark_path}", file=sys.stderr)
        return 1

    print(f"Computing benchmark stats from {args.benchmark} ...")
    benchmark_stats = compute_benchmark_stats(args.benchmark)
    print(f"  Total riddles: {benchmark_stats['total']}")
    print(f"  Fixed: {benchmark_stats['fixed']}, Auxiliary: {benchmark_stats['auxiliary']}")
    print(f"  Types: {benchmark_stats['by_type']}")
    print(f"  Sources: {len(benchmark_stats['by_source'])} model(s)")

    # 2) Scan model output files
    outputs_dir = Path(args.model_outputs) / version
    print(f"\nScanning model outputs in {outputs_dir} ...")
    evaluated_models = scan_model_outputs(outputs_dir)
    if evaluated_models:
        print(f"  Found {len(evaluated_models)} model output file(s):")
        for m in evaluated_models:
            temp_str = f", temp={m['temperature']}" if m["temperature"] is not None else ""
            print(
                f"    {m['model']} ({m['provider']}{temp_str}, "
                f"samples={m['num_samples']}, records={m['num_records']})"
            )
    else:
        print("  No model output files found.")

    # 3) Scan eval results
    results_dir = Path(args.results_dir) / version
    print(f"\nScanning eval results in {results_dir} ...")
    eval_summaries = scan_eval_results(results_dir)
    if eval_summaries:
        print(f"  Found {len(eval_summaries)} eval file(s)")
    else:
        print("  No eval result files found.")

    # 4) Build and save manifest
    manifest = build_manifest(
        version=version,
        benchmark_stats=benchmark_stats,
        evaluated_models=evaluated_models,
        eval_summaries=eval_summaries,
    )

    output_path = args.output or str(results_dir / "reproducibility_manifest.json")
    write_json(output_path, manifest)

    print(f"\n✓ Reproducibility manifest saved: {output_path}")
    print(f"  Version: {version}")
    print(f"  Models:  {len(evaluated_models)} output(s), {len(eval_summaries)} eval(s)")
    print(f"  Time:    {manifest['timestamp']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
