"""altered_riddles.run — run one model on the benchmark items (PLAN.md, D6).

One invocation = one model x one thinking mode x one condition x k samples.
Conditions:

  original   the SOURCE riddle, thinking off, 16 tokens, the familiarity
             probe (Probe A) for this model: COR conditions on it.
  unwarned   the altered item, neutral prompt.
  warned     the altered item, with the "this is a modified version of a
             well-known riddle" warning. The override gap is warned minus
             unwarned accuracy.

The prompt is identical for thinking on and off; only the API switch
differs. Raw replies are appended to runs/<model>/<config>/raw.jsonl and
are the evidence a leaderboard row is derived from; the run is resumable.
config.json records provider, model, switches, prompt text, items file
hash, git commit and start time. summary.json applies the guardrails:

  * thinking on  and median reasoning tokens < 50   -> FAIL (not served)
  * thinking off and > 5% of replies show reasoning -> FAIL (leaked)
  * > 5% unrecoverable errors                       -> FAIL (error rate)

Both reasoning guardrails read llm.effective_reasoning_tokens, which falls back
to the length of the reasoning text on routes that serve a chain of thought but
never populate the usage counter. Guardrails are recomputed from raw.jsonl on
every invocation, so rerunning the same command re-judges an existing run.

A failed run is kept on disk but must not be scored onto the board.

Usage:
    .venv/bin/python -m altered_riddles.run --model jalapeno:DeepSeek-V4-Flash-0731 \\
        --thinking on --condition unwarned --samples 5 --items data/gated.jsonl --passed-only
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from altered_riddles.llm import Client, effective_reasoning_tokens, gather_limited, thinking_extra
from altered_riddles.probe import parse_model_spec
from altered_riddles.review_validity import request_tags

PROMPTS = {
    "original": "Solve this riddle. Reply with only the answer, in a few words, and nothing else.\n\n{text}",
    "unwarned": "{text}\n\nReply with a single line of the form:\nAnswer: <your answer in a few words>",
    "warned": (
        "This is a modified version of a well-known riddle or puzzle. The usual answer may be wrong "
        "here. Read every word and answer the question exactly as written.\n\n{text}\n\n"
        "Reply with a single line of the form:\nAnswer: <your answer in a few words>"
    ),
}
MAX_TOKENS = {"original": 16, "original_thinking": 4000, "off": 200, "on": 16000}
GUARD_MIN_MEDIAN_REASONING = 50
GUARD_MAX_LEAK_RATE = 0.05
GUARD_MAX_ERROR_RATE = 0.05


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_items(path: Path, passed_only: bool) -> list[dict[str, Any]]:
    items = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    if passed_only:
        items = [i for i in items if i.get("gate", {}).get("passed", True)]
    return items


async def run(args: argparse.Namespace) -> None:
    provider, model = parse_model_spec(args.model, "jalapeno")
    items_path = Path(args.items)
    items = load_items(items_path, args.passed_only)
    if args.limit:
        items = items[: args.limit]
    thinking_on = args.thinking == "on"
    if args.condition == "original":
        # Familiarity probe: thinking OFF by default. Thinking-only models
        # (GLM-5.3-Flash on Jalapeno) may run it with --thinking on; the row
        # then records familiarity_mode = "thinking" and the board says so.
        seen: dict[str, dict[str, Any]] = {}
        for it in items:
            seen.setdefault(it["source"], {"id": it["source"], "text": it["original_text"]})
        units = list(seen.values())
        max_tokens = MAX_TOKENS["original"] if not thinking_on else MAX_TOKENS["original_thinking"]
    else:
        units = [{"id": it["id"], "text": it["text"]} for it in items]
        max_tokens = MAX_TOKENS["on" if thinking_on else "off"]

    cap_override = getattr(args, "max_tokens", None)
    if cap_override is not None:
        if cap_override < 1:
            raise ValueError("max_tokens must be positive")
        max_tokens = cap_override

    cfg_name = f"{args.condition}-think{'on' if thinking_on else 'off'}-k{args.samples}"
    if cap_override is not None:
        # A cap change is a new experiment, never a retry of selected failures.
        cfg_name += f"-cap{max_tokens}"
    out_dir = Path(args.runs_dir) / sanitize(f"{provider}_{model}") / cfg_name
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "raw.jsonl"

    config_path = out_dir / "config.json"
    if raw_path.exists():
        if not config_path.exists():
            raise ValueError("raw outputs without config.json; use a new runs directory")
        stored = json.loads(config_path.read_text())
        requested = {"max_tokens": max_tokens, "temperature": args.temperature,
                     "prompt": PROMPTS[args.condition],
                     "thinking_request_params": thinking_extra(model, thinking_on)}
        changed = [key for key, value in requested.items() if stored.get(key) != value]
        if changed:
            raise ValueError(f"run settings changed ({', '.join(changed)}); use a new runs directory")

    # A stored reply is reusable only while the unit's text is unchanged: rows
    # whose text_sha no longer matches (item rephrased or removed) are dropped.
    text_sha = {u["id"]: hashlib.sha256(u["text"].encode()).hexdigest()[:16] for u in units}
    done: set[tuple[str, int]] = set()
    if raw_path.exists():
        kept: list[str] = []
        stale = 0
        unknown: dict[str, int] = {}
        rows_in: list[tuple[dict[str, Any], str]] = []
        for line in raw_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows_in.append((row, line))
            if row["unit_id"] not in text_sha:
                unknown[row["unit_id"]] = unknown.get(row["unit_id"], 0) + 1
        # A unit the items file does not know at all is usually the WRONG items file
        # (renamed/repaired ids, a different split), not an intentional item drop, and
        # its replies would be deleted for good: refuse unless the caller says so.
        if unknown and not getattr(args, "allow_prune", False):
            sample_ids = ", ".join(sorted(unknown)[:10])
            raise SystemExit(
                f"{sum(unknown.values())} existing rows in {raw_path} belong to {len(unknown)} unit ids that are "
                f"not in {items_path} ({sample_ids}). Resuming would delete those replies permanently.\n"
                f"Check that --items is the item file this run was made with "
                f"(config.json records items_file={json.loads(config_path.read_text()).get('items_file')!r}); "
                f"pass --allow-prune only if dropping those replies is intended.")
        for row, line in rows_in:
            if row.get("text_sha") != text_sha.get(row["unit_id"]):
                stale += 1
                continue
            kept.append(line)
            if not row["reply"].get("error"):
                done.add((row["unit_id"], row["sample"]))
        if stale:
            raw_path.write_text("".join(l + "\n" for l in kept))
            print(f"dropped {stale} stale rows whose unit text changed or unit was removed", file=sys.stderr)

    config = {
        "provider": provider, "model": model, "condition": args.condition,
        "thinking": "on" if thinking_on else "off", "thinking_request_params": thinking_extra(model, thinking_on),
        "familiarity_mode": (None if args.condition != "original" else ("thinking" if thinking_on else "direct")),
        "samples": args.samples, "temperature": args.temperature, "max_tokens": max_tokens,
        "prompt": PROMPTS[args.condition], "items_file": str(items_path), "items_sha256": sha256_file(items_path),
        "n_units": len(units), "passed_only": args.passed_only, "user_tag": args.user_tag, "git_commit": git_commit(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=1))

    client = Client(provider, concurrency=args.concurrency, retries=args.retries, rpm=args.rpm, timeout=args.timeout)
    jobs = [(u, s) for u in units for s in range(args.samples) if (u["id"], s) not in done]
    print(f"{provider}:{model} {cfg_name}: units={len(units)} calls={len(units)*args.samples} done={len(done)} todo={len(jobs)}", file=sys.stderr)
    fh = raw_path.open("a")

    async def one(job):
        unit, sample = job
        prompt = PROMPTS[args.condition].format(text=unit["text"])
        reply = await client.chat(model, [{"role": "user", "content": prompt}], max_tokens=max_tokens,
                                  thinking=thinking_on, temperature=args.temperature,
                                  extra_body=request_tags(args.user_tag) or None)
        fh.write(json.dumps({"unit_id": unit["id"], "sample": sample, "text_sha": text_sha[unit["id"]],
                             "reply": reply.as_dict()}, ensure_ascii=False) + "\n")
        fh.flush()
        return reply

    t0 = time.monotonic()
    if jobs:
        await gather_limited([one(j) for j in jobs], progress_every=100, label=f"{sanitize(model)} ")
    fh.close()
    elapsed = time.monotonic() - t0

    # ------------------------------------------------------------- summary + guardrails
    rows = [json.loads(l) for l in raw_path.read_text().splitlines() if l.strip()]
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for r in rows:  # last write wins; an error row is superseded by a later success
        key = (r["unit_id"], r["sample"])
        if key not in latest or not r["reply"].get("error"):
            latest[key] = r
    replies = [r["reply"] for r in latest.values()]
    n = len(replies)
    errors = sum(1 for r in replies if r.get("error"))
    ok = [r for r in replies if not r.get("error")]
    rts = [effective_reasoning_tokens(r) for r in ok]
    estimated = sum(1 for r, rt in zip(ok, rts) if rt and not (r.get("reasoning_tokens") or 0))
    cts = [r.get("completion_tokens") or 0 for r in ok]
    median_rt = statistics.median(rts) if rts else 0
    leak_rate = (sum(1 for x in rts if x > 0) / len(rts)) if rts else 0.0
    truncated = sum(1 for r in ok if r.get("finish_reason") == "length")
    fails = []
    if thinking_on and median_rt < GUARD_MIN_MEDIAN_REASONING:
        fails.append(f"thinking requested but median reasoning tokens = {median_rt}")
    if not thinking_on and leak_rate > GUARD_MAX_LEAK_RATE:
        fails.append(f"thinking off but {leak_rate:.1%} of replies report reasoning tokens")
    if n and errors / n > GUARD_MAX_ERROR_RATE:
        fails.append(f"error rate {errors/n:.1%}")
    summary = {
        "config": cfg_name, "n_expected": len(units) * args.samples, "n_rows": n, "errors": errors,
        "error_rate": round(errors / n, 4) if n else None, "median_reasoning_tokens": median_rt,
        "mean_reasoning_tokens": round(statistics.mean(rts), 1) if rts else None,
        "mean_completion_tokens": round(statistics.mean(cts), 1) if cts else None,
        "reasoning_leak_rate": round(leak_rate, 4), "reasoning_tokens_estimated_rows": estimated,
        "truncated": truncated,
        "total_prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in ok),
        "total_completion_tokens": sum(cts), "elapsed_s_this_invocation": round(elapsed, 1),
        "guardrail": "PASS" if not fails else "FAIL", "guardrail_reasons": fails,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    print(f"wrote {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="provider:model, e.g. jalapeno:DeepSeek-V4-Flash-0731")
    ap.add_argument("--thinking", choices=["on", "off"], default="off")
    ap.add_argument("--condition", choices=["original", "unwarned", "warned"], default="unwarned")
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--temperature", type=float, default=None, help="default: provider default")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="explicit output cap; creates a separate -capN run, never replaces default-cap replies")
    ap.add_argument("--items", default="data/gated.jsonl")
    ap.add_argument("--passed-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--allow-prune", action="store_true",
                    help="permit resuming with an items file that does not contain some already-answered "
                         "unit ids; their replies are deleted (default: refuse, it is usually the wrong file)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--rpm", type=int, default=None, help="cap requests per minute per provider")
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds per request; slow reasoning models need 1800+")
    ap.add_argument("--retries", type=int, default=8, help="attempts per call before recording an error")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--user-tag", default=None,
                     help="Nous tags entry user=VALUE; required by some Nous routes (e.g. step-3.7-flash, solar-pro4)")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
