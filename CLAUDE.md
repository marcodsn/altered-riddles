# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**Altered Riddles** is an LLM benchmark that measures **conditioned override** — how often models fall back to memorized answers when a familiar riddle is subtly modified. The key metric is the **Conditioned Override Rate (COR)**: among altered riddles where a model correctly answered the original, what percentage did it give the now-wrong original answer? Lower is better.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Add API keys: OPENAI_API_KEY, GEMINI_API_KEY, MISTRAL_API_KEY, HF_API_KEY, TOGETHER_API_KEY, NOUS_API_KEY
```

## Pipeline Commands

All scripts run as modules from the repo root:

```bash
# 1. Filter source riddles to "common" ones (≥60% model accuracy)
python -m scripts.sanity_check solve --solvers local gemini openai
python -m scripts.sanity_check judge --judge-provider local

# 2. Generate altered riddle pairs
python -m scripts.generate --provider gemini --num-calls 50

# 3. Validate alterations (LLM-as-judge)
python -m scripts.validate --provider local --batch-size 20

# 4. Remove near-duplicates
python -m scripts.deduplicate

# 5. Manual review of flagged items
python -m scripts.human_review

# 6. Promote to benchmark (fixed=private, auxiliary=public)
python -m scripts.promote split --fixed-count 100 --auxiliary-count 250
python -m scripts.promote status

# 7. Run models on benchmark
python -m scripts.benchmark --provider local --temperature 1.0 --num-samples 5

# 8. Score outputs (LLM-as-judge: correct / gave_original / competing)
python -m scripts.evaluate --provider local --batch-size 20

# 9. Regenerate leaderboard
python -m scripts.leaderboard
```

## Architecture

### Data Flow
```
data/riddles_source.csv
  → data/generated/raw.jsonl       (generate.py)
  → data/generated/validated.jsonl (validate.py)
  → data/pool.jsonl                (human_review.py)
  → data/benchmark_fixed.jsonl     (promote.py, private fixed set)
  → data/benchmark.jsonl           (promote.py, public auxiliary set)
  → data/model_outputs/<model>.jsonl  (benchmark.py)
  → results/<model>_eval.json      (evaluate.py)
  → results/leaderboard.json + LEADERBOARD.md  (leaderboard.py)
```

### Core Infrastructure (`scripts/core/`)
- **config.py** — Provider registry mapping provider names (gemini, openai, local, mistral, huggingface, together, nous) to API keys and client types
- **llm_client.py** — Unified async/sync LLM interface with retry/backoff; returns `LLMResponse(text, reasoning, input_tokens, output_tokens)`; supports Gemini (with thinking), OpenAI-compatible, and Mistral APIs
- **io_utils.py** — JSONL/JSON/CSV I/O; Jinja2 template loader from `prompts/`; `sanitize_model_name()` for output filenames

### Prompt Templates (`prompts/`)
- **solve.j2** — Riddle-solving; requests structured JSON answer
- **generation.j2** — Generates altered-riddle pairs with 4-type taxonomy (constraint_addition, meaning_shift, context_swap, bias_probe)
- **validation.j2** — Validates alterations; flags ambiguous cases for human review
- **judge.j2** — Scores model answers as correct/gave_original/competing

### Output Filenames
Model output and eval files use `sanitize_model_name()` on the `--model` argument, which converts `/` to `_` and strips special chars. The leaderboard script reads all `results/*_eval.json` files.

### Confidence Intervals
COR uses **clustered bootstrap** (clusters = original riddle ID) to account for non-independence of altered variants from the same source riddle. Rank spread in the leaderboard shows the plausible rank range from CI95.

### Benchmark Split
- **Fixed** (`benchmark_fixed.jsonl`): private test set for reliable leaderboard comparison
- **Auxiliary** (`benchmark.jsonl`): public set that can be refreshed via `promote refresh-auxiliary`
