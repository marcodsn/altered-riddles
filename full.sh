#!/usr/bin/env bash
# Full Tier-0 runs on every gate-passed item (profiles from PLAN.md section 6).
# Resumable: run again after adding items; rows whose item text changed are re-answered.
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
ITEMS=data/gated.jsonl
JUDGE=jalapeno:DeepSeek-V4-Flash-0731
RPM=90
LOGS=data/probe/full_logs; mkdir -p $LOGS

# 0. gate every item: cached replies are reused, only new or rephrased items cost calls
#    (SKIP_GATE=1 starts the runs on the current data/gated.jsonl while a gate runs elsewhere)
[ "${SKIP_GATE:-0}" = "1" ] || $PY -m altered_riddles.gate --models DeepSeek-V4-Flash-0731 GLM-5.3-Flash Qwen3-Next-80B-A3B-Thinking Qwen3.5-35B-A3B \
    --rpm $RPM --timeout 1800 --concurrency 8 > $LOGS/gate.log 2>&1 || { echo "gate failed, see $LOGS/gate.log"; exit 1; }
tail -3 $LOGS/gate.log

run() { $PY -m altered_riddles.run --model "$1" --thinking "$2" --condition "$3" --samples "$4" \
        --items $ITEMS --passed-only --concurrency 8 --rpm $RPM --timeout 1800; }
score() { $PY -m altered_riddles.score --run "$1" --items $ITEMS --judge $JUDGE; }

# thinking-off rows are off-full (k=5 both conditions); thinking-on k per model
pipeline() { # model on_k on_warned_k
  local M=$1 ONK=$2 ONW=$3 LOG=$LOGS/$(echo "$1" | tr '/:' '__').log
  {
    run $M off original 5
    run $M off unwarned 5; run $M off warned 5
    if [ "$ONK" != "0" ]; then run $M on unwarned $ONK; run $M on warned $ONW; fi
  } > "$LOG" 2>&1
  echo "pipeline done: $M"
}
pipeline_on_only() { # thinking-only models: familiarity run in thinking mode, board says so
  local M=$1 ONK=$2 ONW=$3 LOG=$LOGS/$(echo "$1" | tr '/:' '__').log
  { run $M on original 5; run $M on unwarned $ONK; run $M on warned $ONW; } > "$LOG" 2>&1
  echo "pipeline done: $M"
}
pipeline jalapeno:DeepSeek-V4-Flash-0731 3 3 &
pipeline_on_only jalapeno:GLM-5.3-Flash 5 5 &
pipeline nous:meituan/longcat-2.0:free 5 5 &
wait

for d in runs/*/original-*; do score "$d"; done
for d in runs/*/unwarned-* runs/*/warned-*; do score "$d"; done
$PY -m altered_riddles.board --items $ITEMS --runs-dir runs --out-dir results/v2
echo "full runs done: results/v2/LEADERBOARD.md"
