# Altered Riddles Benchmark — Technical Report

> **Version:** 2604 (April 2026)
> **Author:** Marco De Santis
> **Repository:** [github.com/marcodsn/altered-riddles](https://github.com/marcodsn/altered-riddles)
> **Dataset:** [huggingface.co/datasets/marcodsn/altered-riddles](https://huggingface.co/datasets/marcodsn/altered-riddles)

---

## 1. What This Benchmark Measures

The Altered Riddles benchmark tests whether language models can **override
memorised patterns** when the details of a well-known riddle are subtly changed.

### The core failure mode

When a model encounters a familiar riddle structure, it frequently under-weights
the tokens that carry the altered information and falls back to its memorised
answer. This is conceptually similar to needle-in-a-haystack failures, but for
**memorised facts** rather than long-context retrieval.

**Classic example:**

> *"The surgeon, who is the boy's father, says 'I cannot operate on this boy,
> he's my son!' — Who is the surgeon?"*

Many LLMs answer **"the mother"** — the answer to the original, well-known
version — despite the prompt explicitly stating the surgeon is the boy's
**father**. The correct answer is simply "the father."

### Key metrics

| Metric | What it tells you |
|---|---|
| **Altered accuracy** | How often the model gives the correct answer to the modified riddle |
| **Pattern override rate** | How often the model gives the *original* (memorised) answer to the *altered* riddle — the central failure signal |
| **Altered weighted accuracy** | Like altered accuracy, but with 0.5× partial credit for valid competing answers |
| **Original accuracy** | Sanity check — can the model solve the unaltered riddles at all? |

A model with high original accuracy but low altered accuracy is exhibiting
exactly the pattern-override failure this benchmark is designed to detect.

---

## 2. What We Generate

Each benchmark entry is a **riddle pair**:

```text
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│  ORIGINAL RIDDLE                 │    │  ALTERED RIDDLE                  │
│  (well-known, widely memorised)  │───▶│  (subtle change → new answer)    │
│  Answer: "a candle"              │    │  Answer: "a plant"               │
└──────────────────────────────────┘    └──────────────────────────────────┘
```

Each alteration is classified into one of four types:

| Type | Description | Example change |
|---|---|---|
| `constraint_addition` | A new physical/functional constraint rules out the original answer | "…and it grows from the ground" |
| `meaning_shift` | A key word takes on a different meaning in the new context | "bucket" → "room" shifts "lighter" from weight to brightness |
| `context_swap` | The context or setting changes the logical answer | Redirecting the question's perspective |
| `bias_probe` | Explicitly states information contradicting a known model bias | "The surgeon, who is the boy's father…" |

### Why riddles?

Riddles are ideal probes for this failure mode because:

1. **They are heavily memorised.** Models have seen them thousands of times during training.
2. **Subtle changes are easy to construct.** Adding or swapping a few words can completely change the answer.
3. **Correctness is unambiguous.** Unlike open-ended questions, riddle answers can be definitively verified.

---

## 3. Architecture Overview

```text
                                    ┌────────────────────┐
  riddles_source.txt ──────────────▶│ scripts.generate   │──▶ data/generated/raw_*.jsonl
                                    │ (or                │
  scripts/core/config.py ─────────▶ │ scripts.generate_  │
    GENERATOR_MODELS                │ all)               │
                                    └─────────┬──────────┘
                                              │
                                              ▼
                                    ┌────────────────────┐
                                    │ scripts.validate   │──▶ data/generated/validated_*.jsonl
                                    └─────────┬──────────┘
                                              │ --append-to-pool
                                              ▼
                                    ┌────────────────────┐
                   data/pool.jsonl ◀│ pool               │
                                    └─────────┬──────────┘
                                              │
                                              ▼
                                    ┌────────────────────┐
  data/benchmark.jsonl ◀────────────│ scripts.promote    │
    (fixed + auxiliary)             └─────────┬──────────┘
                                              │
                             ┌────────────────┘
                             ▼
                   ┌────────────────────┐
                   │ scripts.benchmark  │──▶ data/model_outputs/{version}/*.jsonl
                   └─────────┬──────────┘
                             │
                             ▼
                   ┌────────────────────┐
                   │ scripts.evaluate   │──▶ results/{version}/leaderboard.json
                   └────────────────────┘        + per-model _eval.json
```

---

## 4. Pipeline Stages in Detail

### Stage 1 — Generate

```bash
# Single provider
python -m scripts.generate --provider gemini --num-calls 10

# All configured generators at once
python -m scripts.generate_all --num-calls 5 --validate
```

An LLM takes riddles from `data/riddles_source.txt` and produces altered
variants. The generation prompt (`prompts/generation.j2`) includes few-shot
examples and the classification taxonomy.

**`generate_all.py`** orchestrates generation across all models listed in
`GENERATOR_MODELS` (see `scripts/config.py`). Using 2–3 generators from
different families (e.g. Gemini, GPT-5.4, GLM-5) is the
recommended approach because:

- No single model's reasoning style dominates the benchmark.
- Contamination is roughly equalised across all tested models.
- The benchmark is more diverse stylistically.

Raw outputs are saved to `data/generated/raw_*.jsonl`.

### Stage 2 — Validate

```bash
python -m scripts.validate --input data/generated/raw_*.jsonl --append-to-pool
```

A second LLM pass validates each generated riddle, checking:

- **Answer validity** — does the proposed answer satisfy every clause?
- **Distinctness** — is the altered answer meaningfully different from the original?
- **Logical soundness** — is the riddle coherent and non-contradictory?
- **Subtlety** — could someone plausibly overlook the change?
- **Competing answers** — are there other valid answers? (Not disqualifying — they get partial credit.)

Valid riddles go to `data/pool.jsonl` (with `--append-to-pool`) or directly to
the benchmark (with `--append-to-benchmark`).

### Stage 3 — Deduplicate

```bash
python -m scripts.deduplicate
```

Uses exact matching (after normalisation) and fuzzy matching via
`SequenceMatcher` to remove duplicate or near-duplicate entries. Keeps the entry
with the most accepted answers from each duplicate group.

### Stage 4 — Promote to Benchmark

```bash
python -m scripts.promote add --count 150 --set fixed
python -m scripts.promote add --count 100 --set auxiliary
python -m scripts.promote status
python -m scripts.promote refresh-auxiliary --count 100
```

Moves validated riddles from the pool into the benchmark, tagging them as
**fixed** or **auxiliary** (see [§6 — Benchmark Split](#6-benchmark-split)).

### Stage 5 — Benchmark a Model

```bash
python -m scripts.benchmark --provider openai --model gpt-5.4
python -m scripts.benchmark --provider local --model my-model --batch-size 20
```

Tests a model against all riddles in `data/benchmark.jsonl`. Each riddle is
presented via the solve prompt (`prompts/solve.j2`), and the model's raw
JSON response is stored in `data/model_outputs/{version}/`.

**Key features:**
- **Resume support** — already-answered riddles are skipped (the script won't
  repeat tested riddles when re-running on a new benchmark iteration).
- **Multi-sample mode** — at temperature > 0, collect multiple samples per
  riddle for best-of-n, majority vote, and average accuracy.
- **Token tracking** — input/output tokens logged per call.

### Stage 6 — Evaluate

```bash
python -m scripts.evaluate
```

Scores all model outputs against the accepted answers in the benchmark.
**This step is fully re-runnable** — we can update `altered_accepted_answers`
in `benchmark.jsonl` and re-evaluate without re-running any models.

---

## 5. Scoring System

| Match type | Score | Description |
|---|---|---|
| Primary match (`altered_accepted_answers`) | **1.0** | Model gave the intended altered answer |
| Competing match (`altered_competing_answers`) | **0.5** | Model gave a valid but non-primary answer |
| Original answer | **0.0** | Model fell back to the memorised answer |
| Wrong answer | **0.0** | Unrelated incorrect answer |

**Why partial credit for competing answers?**

The benchmark's primary goal is detecting pattern override. A competing answer
that differs from the original still demonstrates the model is *reasoning about
the altered text* rather than recalling a memorised response. It deserves
partial credit because it proves the model noticed the change.

### Answer matching

Matching is lenient: lowercase, strip punctuation and articles ("a", "an",
"the"), then check for substring containment in either direction. This handles
common variations like "a candle" vs "candle" vs "it's a candle."

### Multi-sample metrics

When `--num-samples > 1` (with temperature > 0):

| Metric | Definition |
|---|---|
| **Best-of-n accuracy** | At least one sample is correct |
| **Majority vote accuracy** | Most common answer is correct |
| **Average accuracy** | Mean per-sample score |

---

## 6. Benchmark Split

To balance stability and contamination resistance, the benchmark is split
into two parts:

### Fixed core (~150 riddles)

- **Never regenerated.**
- Serves as the longitudinal baseline so scores are comparable across runs.
- Tagged with `"set": "fixed"` in `benchmark.jsonl`.

### Fresh auxiliary set (~100–150 riddles)

- **May be regenerated in the future** via `promote.py refresh-auxiliary`.
- Tests generalisation and resists overfitting / contamination.
- Tagged with `"set": "auxiliary"` in `benchmark.jsonl`.

### Sample size justification

For a binary accuracy metric at 95% confidence:

$$n = \frac{z^2 \cdot \hat{p}(1 - \hat{p})}{\varepsilon^2}$$

With $\hat{p} \approx 0.65$, $z = 1.96$:

| Margin of error ε | Min riddles | Notes |
|---|---|---|
| ±10% | ~87 | Rankings unreliable |
| ±7% | ~178 | Safe minimum for rough rankings |
| ±5% | ~350 | Confident ranking, detects ~10pt gaps |
| ±3% | ~972 | Research-grade |

**Target working size: 200–350 riddles** (150 fixed + 50–200 auxiliary).

Beyond ~500 riddles, ranking order rarely changes — diminishing returns set in.

---

## 7. Versioning

The benchmark uses **YYMM** versioning (e.g. `2604` = April 2026).

- **`data/VERSION`** — contains the current version string.
- **Results** are written to `results/{version}/` (e.g. `results/2604/`).
- **Benchmark entries** are tagged with `"version_added"` when promoted.
- **`promote.py refresh-auxiliary`** bumps the version automatically.

This means:
- Historical results are preserved in their version folders.
- We can always trace which riddles were added in which version.
- The leaderboard is also written to `results/leaderboard.json` for convenience.

---

## 8. Provider Configuration

All provider settings live in **`scripts/config.py`**. Adding a new provider
is a one-step process — just add an entry to the `PROVIDERS` dict:

```python
PROVIDERS = {
    "gemini": {
        "default_model": "gemma-4-31b-it",
        "env_key": "GEMINI_API_KEY",
        "client_type": "gemini",
    },
    "openai": {
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "client_type": "openai_compat",
    },
    "local": {
        "default_model": "Mistral-Small-4-119B-2603",
        "env_key": None,
        "client_type": "openai_compat",
        "base_url": "http://10.8.0.5:8083/v1",
        "api_key_override": "local",
    },
    # To add Together AI, Groq, Fireworks, etc.:
    # "together": {
    #     "default_model": "meta-llama/Llama-3-70b-chat-hf",
    #     "env_key": "TOGETHER_API_KEY",
    #     "client_type": "openai_compat",
    #     "base_url": "https://api.together.xyz/v1",
    # },
}
```

Any OpenAI-compatible endpoint works with `client_type: "openai_compat"` — just
set the `base_url`. The `GENERATOR_MODELS` list in the same file controls which
models are used for multi-family riddle generation.

---

## 9. Project Structure

```text
altered-riddles/
├── scripts/
│   ├── config.py              # Provider registry, defaults, paths
│   ├── llm_client.py          # Unified LLM client (sync/async/batched)
│   ├── io_utils.py            # Shared I/O (JSONL, templates, JSON)
│   ├── generate.py            # Generate riddles (single provider)
│   ├── generate_all.py        # Generate riddles (all configured models)
│   ├── validate.py            # Validate generated riddles
│   ├── deduplicate.py         # Remove duplicate riddles
│   ├── promote.py             # Pool → benchmark promotion
│   ├── benchmark.py           # Run benchmark against a model
│   └── evaluate.py            # Score outputs, build leaderboard
├── prompts/
│   ├── generation.j2          # Riddle generation prompt
│   ├── validation.j2          # Riddle validation prompt
│   └── solve.j2               # Benchmark solve prompt
├── data/
│   ├── VERSION                # Current benchmark version (YYMM)
│   ├── benchmark.jsonl        # The benchmark dataset
│   ├── pool.jsonl             # Validated riddles awaiting promotion
│   ├── riddles_source.txt     # Source riddles for generation
│   ├── generated/             # Raw + validated generation outputs
│   ├── model_outputs/         # Raw model answers (versioned subdirs)
│   └── images/                # Example screenshots
├── results/                   # Evaluation results (versioned subdirs)
│   ├── {YYMM}/               # Per-version results
│   └── leaderboard.json       # Latest leaderboard (convenience copy)
├── REPORT.md                  # This file
├── README.md                  # Project overview
└── requirements.txt           # Python dependencies
```

---

## 10. Data Format

### `benchmark.jsonl` entry

```json
{
  "id": "alt_001",
  "original_riddle": "I'm tall when I'm young, and short when I'm old. What am I?",
  "original_answer": "A candle.",
  "original_accepted_answers": ["A candle", "candle"],
  "original_reasoning": "A candle starts tall and becomes shorter as it burns.",
  "altered_riddle": "I'm tall when I'm young, and short when I'm old, and I grow from the ground. What am I?",
  "altered_answer": "A plant.",
  "altered_accepted_answers": ["A plant", "plant", "tree"],
  "altered_competing_answers": ["grass", "flower"],
  "altered_reasoning": "Adding 'grows from the ground' eliminates candle...",
  "source": "gemini-3.1-flash",
  "type": "constraint_addition",
  "set": "fixed",
  "version_added": "2604"
}
```

### Model output record

```json
{
  "riddle_id": "alt_001",
  "riddle_type": "altered",
  "sample_index": 1,
  "riddle_text": "I'm tall when I'm young...",
  "model_answer": "candle",
  "model_reasoning": "A candle starts tall...",
  "raw_response": "{\"answer\": \"candle\", ...}",
  "model": "gpt-5.4",
  "timestamp": "2026-04-03T12:00:00",
  "temperature": 0.0,
  "input_tokens": 142,
  "output_tokens": 38
}
```

---

## 11. Typical Workflow

### Initial setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Add API keys

# Generate riddles from multiple model families
python -m scripts.generate_all --num-calls 10 --validate

# Check the pool
python -m scripts.promote status

# Promote to benchmark
python -m scripts.promote add --count 150 --set fixed
python -m scripts.promote add --count 100 --set auxiliary

# Deduplicate
python -m scripts.deduplicate
```

### Running the benchmark

```bash
# Test a model
python -m scripts.benchmark --provider openai --model gpt-4o

# Test a local model
python -m scripts.benchmark --provider local --model my-model --batch-size 20

# Evaluate all tested models
python -m scripts.evaluate
```

### Refreshing the auxiliary set (new version)

```bash
# Generate fresh riddles
python -m scripts.generate_all --num-calls 10 --validate

# Replace auxiliary riddles with fresh ones from pool
python -m scripts.promote refresh-auxiliary --count 100

# Deduplicate the new benchmark
python -m scripts.deduplicate

# Re-run benchmark (only new/unanswered riddles will be tested)
python -m scripts.benchmark --provider openai --model gpt-4o

# Re-evaluate
python -m scripts.evaluate
```

### HuggingFace upload

Results and the benchmark dataset are uploaded to HuggingFace for public access.

---

## 12. Design Decisions

### Decoupled evaluation

Model answers are stored separately from scoring. You can edit
`altered_accepted_answers` or `altered_competing_answers` in `benchmark.jsonl`
and re-run `evaluate.py` without re-running any models. This is critical for
iterating on answer quality.

### Multiple accepted answers

Riddles can have multiple valid phrasings. The `altered_accepted_answers` list
(full credit) and `altered_competing_answers` list (partial credit) are both
manually editable. Competing answers discovered during validation are
automatically added but can be promoted to full-credit status after review.

### Temperature 0 default

A single deterministic pass per model ensures reproducibility. For RL reasoning
models that perform better at higher temperatures, `--temperature` and
`--num-samples` flags are available.

### Resume support

The benchmark script detects already-answered riddles and skips them. When the
benchmark grows (new auxiliary riddles), re-running the benchmark only tests the
new entries. This makes iterative development practical.

### Multi-family generation

Using generators from different model families (Gemini, GPT-5.4, GLM-5)
ensures no single model's reasoning style dominates the benchmark. The `source`
field in each entry makes it trivial to stratify results by generator later.
