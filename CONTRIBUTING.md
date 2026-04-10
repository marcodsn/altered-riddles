# Contributing to Altered Riddles

Thank you for your interest in contributing! This document explains how to
participate in the benchmark, whether by submitting model results, proposing
new riddles, or improving the codebase.

## Submitting Model Results

1. **Run the benchmark** on your model:
   ```bash
   python -m scripts.benchmark --provider <provider> --model <model>
   ```
2. **Evaluate** the results:
   ```bash
   python -m scripts.evaluate
   ```
3. **Open a Pull Request** with:
   - The model output file(s) in `data/model_outputs/{version}/`
   - The evaluation result in `results/{version}/`
   - A brief description of the model (name, parameter count, quantisation, provider)

## Proposing New Source Riddles

We're always looking for well-known riddles to add to `data/riddles_source.txt`.
Good candidates are:

- **Widely known** — the riddle should be familiar enough that LLMs have likely
  memorised it during training.
- **Alterable** — it should be possible to add or change a detail that shifts
  the correct answer.
- **Unambiguous** — the original riddle should have a clear, widely agreed-upon
  answer.

Open an issue or PR with your proposed riddles and a brief note on why they're
good candidates for alteration.

## Code Contributions

### Setup

```bash
# Clone the repo
git clone https://github.com/marcodsn/altered-riddles.git
cd altered-riddles

# Install dependencies (pick one)
pip install -e ".[dev]"        # editable install with dev tools (pytest, ruff)
pip install -e ".[dev,charts]" # include chart dependencies too
uv pip install -e ".[dev]"     # or use uv

# Copy environment template and add API keys
cp .env.example .env
```

### Code Style

- We use Python 3.10+ with type hints.
- Format with `ruff format` and lint with `ruff check`.
- Configuration is in `pyproject.toml` (line-length 99, select E/F/W/I/UP).
- Keep functions focused and well-documented.
- Shared parsing helpers live in `scripts/core/parsing.py` — add new shared
  logic there rather than duplicating across scripts.

### Running Tests

```bash
# Run the full test suite
pytest tests/ -v

# Validate benchmark data integrity
python -m scripts.validate_schema
```

CI runs automatically on PRs via GitHub Actions (lint → test → validate-data).

### Pull Request Guidelines

- **One concern per PR.** Don't mix unrelated changes.
- **Include tests** for new scoring or evaluation logic. The test suite lives
  in `tests/` — see existing tests for conventions.
- **Update documentation** (README, REPORT, CHANGELOG) if your change affects
  user-facing behaviour.
- **Don't commit** `__pycache__/`, `.env`, or large model output files.

## How Evaluation Works

Understanding the scoring system helps you verify your contributions:

1. **Primary match** (`altered_accepted_answers`): **1.0** — the model gave the
   intended altered answer.
2. **Competing match** (`altered_competing_answers`): **0.5** — the model gave
   a valid but non-primary answer.
3. **Original answer**: **0.0** — the model fell back to its memorised answer
   (counted as a pattern override).
4. **Wrong answer**: **0.0** — unrelated incorrect answer.

The competing-answer weight (default 0.5×) is configurable via
`--competing-weight` when running `evaluate.py`.

The leaderboard ranks models by `average_accuracy` (the mean weighted score
across all samples). Models must be tested on at least 250 altered riddles
to appear on the leaderboard. Evaluation also reports per-alteration-type
and per-source-model accuracy breakdowns.

### Useful CLI flags for contributors

- `python -m scripts.benchmark --adaptive` — skip extra samples for riddles
  answered correctly (saves cost).
- `python -m scripts.generate --type bias_probe` — generate a specific
  alteration type to rebalance the dataset.
- `python -m scripts.validate --re-validate --filter-empty-competing` —
  re-validate entries missing competing answers.
- `python -m scripts.promote status --report-reuse` — check original riddle
  reuse in the benchmark.
- `python -m scripts.contamination_analysis` — check for contamination effects.

## Reporting Issues

- Use GitHub Issues for bug reports, feature requests, or data quality concerns.
- For riddles with incorrect or missing accepted answers, please include the
  `riddle_id` and your proposed correction.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt).