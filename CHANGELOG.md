# Changelog

All notable changes to the Altered Riddles benchmark will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [v2604] — 2026-07-10

### Added
- `scripts/annotate_competing.py` — interactive CLI tool for human annotation of competing answers with defensible/not-defensible/promote labels, resume support, `--report-only`, and `--apply` flags
- `data/model_metadata.json` — parameter counts (total and active for MoE models) and cost metadata for all evaluated models
- `--model-metadata` CLI argument in `evaluate.py` for loading model metadata into leaderboard
- `active_parameter_count_billions` field in leaderboard rows for MoE model tracking
- `_clustered_bootstrap_ci()` function in `evaluate.py` for cluster-aware confidence intervals

### Changed
- Confidence intervals in `build_leaderboard` now use **clustered bootstrap** (B=2000, seed=42, clustered by original riddle) instead of Wald CIs; falls back to Wald when fewer than 5 clusters
- `build_leaderboard()` now accepts optional `benchmark_lookup` and `model_metadata` parameters
- Leaderboard rows now populated with parameter counts and costs from `model_metadata.json`

## [v2604] — 2026-04-10

### Added
- `scripts/core/parsing.py` — consolidated duplicated helpers (`parse_riddle_array`, `validate_entry`, `to_benchmark_format`, `split_paren_alternatives`, `parse_validation_response`)
- `pyproject.toml` with core, `[charts]`, and `[dev]` dependency groups (compatible with `uv`)
- `.github/workflows/ci.yml` — CI pipeline (lint, test, validate-data)
- `scripts/validate_schema.py` — benchmark.jsonl schema validation (required fields, no duplicate IDs, type/set constraints)
- `scripts/contamination_analysis.py` — per-model accuracy on self-sourced vs. other-sourced riddles, flags deltas ≥5pp
- `scripts/reproducibility_snapshot.py` — generates `reproducibility_manifest.json` with benchmark version, stats, and per-model settings
- `scripts/charts/06_perTypeBreakdown.py` — grouped bar chart of accuracy by alteration type for top models
- `scripts/charts/07_riddleHeatmap.py` — exports `riddle_heatmap.json` with per-riddle outcomes across all models
- `tests/` — 64 unit tests across 6 files (`test_scoring`, `test_parsing`, `test_leaderboard`, `test_promote`, `test_io_utils`)
- `--competing-weight` flag in `evaluate.py` (default 0.5) — configurable partial-credit weight for competing answers
- `--param-count` and `--cost-per-mtok` flags in `evaluate.py` for tracking model efficiency
- `parameter_count_billions` and `estimated_cost_per_mtok_usd` placeholder fields in leaderboard rows
- Per-type breakdown (`per_type` dict) in evaluation output and leaderboard — accuracy, weighted accuracy, and override rate by alteration type
- Per-source-model stratification (`per_source` dict) in evaluation output and leaderboard
- `--type` flag in `generate.py` and `generate_all.py` for targeted alteration-type generation
- `--re-validate` and `--filter-empty-competing` flags in `validate.py` for re-validating existing entries
- `--max-per-original` flag in `promote.py` (default 3) — caps altered variants per original riddle
- `--report-reuse` flag in `promote.py status` — shows original riddle reuse statistics
- `--adaptive` flag in `benchmark.py` — two-phase sampling that skips extra samples for correctly-answered riddles
- `--originals-samples` flag in `benchmark.py` (default 1) — controls sample count for original riddles independently

### Changed
- `generate.py`, `generate_all.py`, `validate.py` now import shared helpers from `scripts.core.parsing` instead of defining their own copies
- `benchmark.py` `run_benchmark` refactored: extracted `_run_sequential`, `_run_batched`, `_process_response`, `_riddle_text` as standalone functions; removed `# noqa: C901`
- `build_tasks()` in `benchmark.py` now accepts separate `originals_samples` parameter (defaults to 1)
- `prompts/generation.j2` updated with conditional `target_type` block for type-targeted generation
- `_pick_balanced()` in `promote.py` now accepts `max_per_original` and `existing_entries` parameters
- `_score_single_output()` and `evaluate_model()` now accept `competing_weight` parameter

## [v2604] — 2026-04-10

### Added
- Full benchmark pipeline: generate → validate → promote → deduplicate → benchmark → evaluate
- 250 altered riddles (150 fixed + 100 auxiliary) across 4 alteration types
- LLM-as-a-judge evaluation with judgment caching
- Multi-sample support (best-of-N, majority vote, average accuracy)
- 19 models evaluated on the leaderboard
- Multi-family riddle generation (Gemini, GPT, GLM, Qwen, Mistral)
- Pool-based riddle management with `promote.py`
- Pluggable multi-provider LLM client (Gemini, OpenAI-compat, Mistral)
- Async batched API calls with configurable concurrency
- Chart generation suite (5 chart types) with blog variants
- Per-riddle difficulty scores
- Confidence intervals in leaderboard JSON
- Markdown leaderboard table auto-generation
- YYMM versioning with `data/VERSION`
- Resume support for benchmark runs
- HuggingFace dataset integration

### Changed
- Consolidated evaluation into single `evaluate.py` (removed legacy string-matching evaluator)
- Chart scripts refactored to use shared `theme.py` utilities
- Blog chart variants now generated via `--blog` flag instead of separate directory
- `best_of_n` now gives partial credit (0.5×) for competing-only answers
- Conditioned override rate now computed across all samples (not just sample 1)
- Models with fewer than 250 altered riddles excluded from leaderboard
- Migration scripts moved from `scripts/fixing/` to `migrations/`
- Default `--max-output-tokens` set to 16384 for benchmark runs

### Fixed
- `normalize()` regex bug in legacy evaluator (double-escaped `\\b`)
- Verbose answers in `alt_057` and `alt_069` shortened to matchable length

## [v2503] — 2025-03

### Added
- Initial dataset created with manual riddle alterations
- Basic generation and validation pipeline
