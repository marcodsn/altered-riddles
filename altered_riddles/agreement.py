"""altered_riddles.agreement — judge-vs-human agreement (PLAN.md, H4).

Reads a blind labeling sheet (one JSON row per answer with `human_label` filled
in by a person) and its key (the machine labels the sheet hid), and writes
results/judge_agreement.json: agreement rate, Cohen's kappa, the confusion
matrix, and the disagreements listed for inspection.

Usage:
    .venv/bin/python -m altered_riddles.agreement \
        --sheet results/pilot/labeling_sheet_judge_only.jsonl \
        --key results/pilot/labeling_sheet_judge_only.key.jsonl \
        --out results/judge_agreement.json

Rows whose `human_label` is empty are skipped and counted as unlabeled. The
legacy 100-row sheet carries its machine label inline as `_machine_label` and
needs no key.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

LABELS = ("correct", "original", "other", "abstain")
ALIASES = {"abstain_or_flags_trick": "abstain", "flags_trick": "abstain", "orig": "original", "ok": "correct"}


def norm_label(x: str | None) -> str | None:
    if x is None:
        return None
    x = str(x).strip().lower()
    if not x:
        return None
    x = ALIASES.get(x, x)
    if x not in LABELS:
        raise SystemExit(f"unknown label {x!r}; use one of {LABELS}")
    return x


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[l] * cb[l] for l in LABELS) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--key", default=None, help="key file with the machine labels (omit for the legacy inline sheet)")
    ap.add_argument("--out", default="results/judge_agreement.json")
    args = ap.parse_args()

    sheet = load(Path(args.sheet))
    key: dict[int, dict] = {}
    if args.key:
        key = {k["n"]: k for k in load(Path(args.key))}
    pairs: list[tuple[str, str]] = []
    disagreements: list[dict] = []
    unlabeled = 0
    for r in sheet:
        h = norm_label(r.get("human_label"))
        if h is None:
            unlabeled += 1
            continue
        if args.key:
            k = key[r["n"]]
            m, det, judge = k["label"], k.get("det"), k.get("judge")
        else:
            m, det, judge = r["_machine_label"], None, None
        pairs.append((h, m))
        if h != m:
            disagreements.append({"item": r["item"], "run": r["run"], "model_answer": r["model_answer"], "human": h, "machine": m,
                                  "det": det, "judge": judge})
    n = len(pairs)
    agree = sum(1 for a, b in pairs if a == b)
    conf: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for h, m in pairs:
        conf[h][m] += 1
    # the label COR depends on: does the machine ever call something 'original' that a human would not, or miss one?
    orig_h = sum(1 for h, _ in pairs if h == "original")
    orig_hits = sum(1 for h, m in pairs if h == "original" and m == "original")
    orig_false = sum(1 for h, m in pairs if h != "original" and m == "original")
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sheet": args.sheet, "key": args.key, "n_labeled": n, "n_unlabeled": unlabeled,
        "agreement": round(agree / n, 4) if n else None, "cohen_kappa": (round(kappa(pairs), 4) if kappa(pairs) is not None else None),
        "original_recall": (round(orig_hits / orig_h, 4) if orig_h else None), "original_false_positives": orig_false,
        "confusion": {h: dict(conf[h]) for h in LABELS if h in conf},
        "disagreements": disagreements,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"labeled {n} (unlabeled {unlabeled}): agreement {out['agreement']}, kappa {out['cohen_kappa']}, "
          f"'original' recall {out['original_recall']} with {orig_false} false positives; {len(disagreements)} disagreements", file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
