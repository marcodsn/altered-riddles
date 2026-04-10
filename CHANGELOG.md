# Changelog

All notable changes to the Altered Riddles benchmark will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [v2604] — 2026-04

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