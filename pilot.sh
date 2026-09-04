#!/usr/bin/env bash
# M3 pilot (PLAN.md): 40 gated items, stratified by type, on the Tier-0 models,
# every condition, both thinking modes where the model supports both.
# Measures: real thinking length per model (re-prices the $90), alias coverage
# (deterministic_resolved >= 0.70), guardrails, and produces a labeling sheet
# of 100 answers for the judge-vs-human check.
#
# Usage: ./pilot.sh            (runs everything, ~30-60 min, a few dollars)
set -euo pipefail
PY=.venv/bin/python
RUNS=runs/pilot
ITEMS=data/pilot_items.jsonl
JUDGE=jalapeno:DeepSeek-V4-Flash-0731
RPM=90

# 1. stratified 40-item sample of PASSED items (seeded)
$PY - <<'EOF'
import json, random, collections
rows = [json.loads(l) for l in open("data/gated.jsonl") if l.strip()]
passed = [r for r in rows if r["gate"]["passed"]]
by_type = collections.defaultdict(list)
for r in passed: by_type[r["type"]].append(r)
rng = random.Random(0); pick = []
n_total = 40
for t, rs in sorted(by_type.items()):
    k = max(1, round(n_total * len(rs) / len(passed)))
    rng.shuffle(rs); pick += rs[:k]
pick = pick[:n_total]
with open("data/pilot_items.jsonl", "w") as f:
    for r in pick: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("pilot items:", len(pick), dict(collections.Counter(r["type"] for r in pick)), "sources:", len({r["source"] for r in pick}))
EOF

run() { # model thinking condition samples
  $PY -m altered_riddles.run --model "$1" --thinking "$2" --condition "$3" --samples "$4" \
      --items $ITEMS --runs-dir $RUNS --concurrency 8 --rpm $RPM --timeout 1800
}
score() { $PY -m altered_riddles.score --run "$1" --items $ITEMS --judge $JUDGE; }

# 2. models and modes, one pipeline per model, all in parallel (the provider
#    limit is requests per minute, and thinking calls are few per minute;
#    DeepSeek-V4-Flash-0731 reasons at ~10 tok/s so it gets k=1 when thinking).
#    GLM-5.3-Flash cannot switch thinking off; Qwen3-Next-Instruct has none.
mkdir -p data/probe/pilot_logs
pipeline() { # model  on_k  (thinking-off runs always k=3 unwarned / k=1 warned)
  local M=$1 ONK=$2 LOG=data/probe/pilot_logs/$(echo "$1" | tr '/:' '__').log
  {
    run $M off original 5
    run $M off unwarned 3;  run $M off warned 1
    if [ "$ONK" != "0" ]; then run $M on unwarned $ONK; run $M on warned 1; fi
  } > "$LOG" 2>&1
  echo "pipeline done: $M (exit $?)"
}
pipeline_on_only() { # model on_k : thinking-only models (no off mode)
  local M=$1 ONK=$2 LOG=data/probe/pilot_logs/$(echo "$1" | tr '/:' '__').log
  { run $M off original 5; run $M on unwarned $ONK; run $M on warned 1; } > "$LOG" 2>&1
  echo "pipeline done: $M (exit $?)"
}
pipeline jalapeno:DeepSeek-V4-Flash-0731 1 &
pipeline jalapeno:Qwen3.5-35B-A3B 3 &
pipeline nous:meituan/longcat-2.0:free 3 &
pipeline_on_only jalapeno:GLM-5.3-Flash 3 &
pipeline jalapeno:Qwen3-Next-80B-A3B-Instruct 0 &
wait
echo "all pipelines finished"

# 3. score every run (familiarity first so COR conditioning is available)
for d in $RUNS/*/original-*; do score "$d"; done
for d in $RUNS/*/unwarned-* $RUNS/*/warned-*; do score "$d"; done

# 4. board + labeling sheet (100 random scored answers, blind: no label shown)
$PY -m altered_riddles.board --items $ITEMS --runs-dir $RUNS --out-dir results/pilot --n-boot 1000
$PY - <<'EOF'
import json, glob, random
rows = []
for f in glob.glob("runs/pilot/*/unwarned-*/scored.jsonl") + glob.glob("runs/pilot/*/warned-*/scored.jsonl"):
    for l in open(f):
        s = json.loads(l)
        if s["label"] != "error": rows.append({"run": f.split("/")[2] + "/" + f.split("/")[3], **s})
random.Random(0).shuffle(rows)
items = {json.loads(l)["id"]: json.loads(l) for l in open("data/pilot_items.jsonl")}
with open("results/pilot/labeling_sheet.jsonl", "w") as f:
    for s in rows[:100]:
        it = items[s["unit_id"]]
        f.write(json.dumps({"run": s["run"], "item": s["unit_id"], "riddle": it["text"], "accepted": [it["answer"], *it["aliases"]],
                            "original": [it["original_answer"], *it["original_aliases"]], "model_answer": s["final"],
                            "human_label": "", "_machine_label": s["label"]}, ensure_ascii=False) + "\n")
print("labeling sheet: results/pilot/labeling_sheet.jsonl (fill human_label with correct/original/other/abstain)")
EOF
echo "pilot done: results/pilot/LEADERBOARD.md"
