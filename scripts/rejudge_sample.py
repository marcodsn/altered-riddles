#!/usr/bin/env python3
"""rejudge_sample.py — judge-agreement trust check (B2).

The source leaderboard verdicts were produced by a now-unavailable local
qwen3.5-27b judge whose identity was never recorded. This re-judges a random
sample of the *parsed* model answers (the raw generations are gone) with a
named, reproducible judge (default: a free Nous model) and reports how often it
agrees with the cached verdicts. High agreement => keep the cached numbers with
a footnote; low agreement => a full re-judge is warranted.

No generation, no cost beyond the free judge.

Usage:
    NOUS_API_KEY=... python -m scripts.rejudge_sample --provider nous \
        --model poolside/laguna-s-2.1:free --n 500
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import DEFAULT_BENCHMARK, DEFAULT_BENCHMARK_FIXED, DEFAULT_RESULTS, resolve_provider
from scripts.core.io_utils import load_jsonl_if_exists, load_template, write_json
from scripts.core.llm_client import call_llm_batched
from scripts.evaluate import parse_judge_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def collect_rows(results_dir: Path) -> list[dict]:
    """Every judged detail row (with its cached verdict) across complete eval files."""
    rows = []
    for ef in sorted(results_dir.glob("*_eval.json")):
        data = json.loads(ef.read_text())
        for d in data.get("details", []):
            if "model_answer" not in d:
                continue
            rows.append({
                "eval_file": ef.stem, "riddle_id": d["riddle_id"],
                "riddle_type": d["riddle_type"], "sample_index": d.get("sample_index", 1),
                "model_answer": d["model_answer"],
                "cached_correct": bool(d.get("correct", False)),
                "cached_gave_original": bool(d.get("gave_original_answer", False)),
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="nous")
    ap.add_argument("--model", default="poolside/laguna-s-2.1:free")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS)
    ap.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    ap.add_argument("--judge-template", default="prompts/judge.j2")
    args = ap.parse_args()

    load_dotenv()
    judge_model, judge_api_key = resolve_provider(args.provider, args.model)
    results_dir = Path(args.results_dir)

    bench = load_jsonl_if_exists(args.benchmark) + load_jsonl_if_exists(DEFAULT_BENCHMARK_FIXED)
    lookup = {e.get("id", ""): e for e in bench}
    template = load_template(args.judge_template)

    rows = collect_rows(results_dir)
    rng = random.Random(args.seed)
    sample = rng.sample(rows, min(args.n, len(rows)))
    logger.info("re-judging %d/%d rows with %s (%s)", len(sample), len(rows),
                judge_model, args.provider)

    prompts, meta = [], []
    for r in sample:
        entry = lookup.get(r["riddle_id"])
        if not entry:
            continue
        if r["riddle_type"] == "original":
            riddle = entry.get("original_riddle", "")
            accepted = entry.get("original_accepted_answers", [entry.get("original_answer", "")])
        else:
            riddle = entry.get("altered_riddle", "")
            accepted = entry.get("altered_accepted_answers", [entry.get("altered_answer", "")])
        original = entry.get("original_accepted_answers", [entry.get("original_answer", "")])
        competing = entry.get("altered_competing_answers", [])
        prompts.append(template.render(riddle=riddle, model_answer=r["model_answer"],
                                       accepted=accepted, original=original, competing=competing))
        meta.append(r)

    results = call_llm_batched(prompts, provider=args.provider, model=judge_model,
                               temperature=0.0, api_key=judge_api_key,
                               max_concurrency=args.batch_size)

    n = agree_correct = agree_gave = agree_both = 0
    conf_correct = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}
    disagreements = []
    for r, res in zip(meta, results):
        if isinstance(res, BaseException):
            continue
        p = parse_judge_response(res.text)
        n += 1
        ac = p["correct"] == r["cached_correct"]
        ag = p["gave_original"] == r["cached_gave_original"]
        agree_correct += ac
        agree_gave += ag
        agree_both += ac and ag
        # confusion for `correct`, treating the cached verdict as the reference
        c, pc = r["cached_correct"], p["correct"]
        conf_correct["TP" if (c and pc) else "FN" if (c and not pc)
                     else "FP" if (not c and pc) else "TN"] += 1
        if not (ac and ag) and len(disagreements) < 40:
            disagreements.append({**{k: r[k] for k in ("eval_file", "riddle_id", "riddle_type",
                                                       "model_answer", "cached_correct",
                                                       "cached_gave_original")},
                                  "new_correct": p["correct"], "new_gave_original": p["gave_original"]})

    out = {
        "judge_model": judge_model, "provider": args.provider, "n_scored": n,
        "agreement_correct": round(agree_correct / n, 4) if n else None,
        "agreement_gave_original": round(agree_gave / n, 4) if n else None,
        "agreement_both": round(agree_both / n, 4) if n else None,
        "correct_confusion_vs_cached": conf_correct,
        "seed": args.seed, "disagreement_examples": disagreements,
    }
    write_json(results_dir / "judge_agreement.json", out)
    logger.info("agreement: correct=%.3f gave_original=%.3f both=%.3f (n=%d) -> judge_agreement.json",
                out["agreement_correct"] or 0, out["agreement_gave_original"] or 0,
                out["agreement_both"] or 0, n)


if __name__ == "__main__":
    main()
