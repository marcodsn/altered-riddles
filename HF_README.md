---
tags:
- reasoning-datasets-competition
- reasoning
- question-answering
- chain-of-thought
- common-sense
- bias-mitigation
- benchmark
- riddles
license: apache-2.0
dataset_info:
  features:
  - name: id
    dtype: string
  - name: original_riddle
    dtype: string
  - name: original_answer
    dtype: string
  - name: original_accepted_answers
    sequence: string
  - name: original_reasoning
    dtype: string
  - name: altered_riddle
    dtype: string
  - name: altered_answer
    dtype: string
  - name: altered_accepted_answers
    sequence: string
  - name: altered_competing_answers
    sequence: string
  - name: altered_reasoning
    dtype: string
  - name: source
    dtype: string
  - name: type
    dtype: string
  - name: set
    dtype: string
  - name: version_added
    dtype: string
  splits:
  - name: train
    num_bytes: 79702
    num_examples: 102
  download_size: 44515
  dataset_size: 79702
configs:
- config_name: default
  data_files:
  - split: train
    path: benchmark.jsonl
size_categories:
- n<1K
---

# Dataset Card for Altered Riddles Benchmark

## Dataset Description

- **Benchmark:** [https://marcodsn.me/altered-riddles](https://marcodsn.me/altered-riddles)
- **GitHub:** [https://github.com/marcodsn/altered-riddles](https://github.com/marcodsn/altered-riddles)
- **Dataset:** [https://huggingface.co/datasets/marcodsn/altered-riddles](https://huggingface.co/datasets/marcodsn/altered-riddles) (This page)  

While working on the [academic-chains](https://huggingface.co/datasets/marcodsn/academic-chains) dataset, I tested a well-known alteration of a common riddle, "just for fun":

> *The surgeon, who is the boy's father, says, 'I cannot operate on this boy—he's my son!'. Who is the surgeon to the boy?*

(*Below is the original riddle for reference*)
> *A man and his son are in a terrible accident and are rushed to the hospital in critical condition. The doctor looks at the boy and exclaims, "I can't operate on this boy; he's my son!" How could this be?*

You likely immediately thought, *"The father!"*, but surprisingly, many powerful LLMs (including `claude-sonnet-4-6`, `gemini-3.1-flash`, and others in my tests) fail this simple variation. The classic riddle expects *"The mother"* as the answer, revealing societal biases. However, when the text *explicitly states* the father is the surgeon, why do models get it wrong?

My investigation suggests **overfitting to the original pattern**. Models—especially large ones—have seen and memorized standard riddles so often that they appear to ignore crucial, altered details in the prompt.

*(Image below: Failure by Claude Sonnet 4.6; the answer should simply be "the father"!)*  
![Example of pattern override failure with the surgeon riddle](images/failed-riddle-1-sonnet-4-6.png)

*(Image below: Failure by Gemini 3.1 Flash with Thinking; a correct answer could have been "a plant"!)*  
![Example of pattern override failure with another riddle](images/failed-riddle-2-gemini-3-1-flash.png)

**This Benchmark:** The `altered-riddles` benchmark is a curated collection designed to combat this specific type of reasoning failure. It contains familiar riddles where **key details have been deliberately changed**. Each entry includes:  
1. The original riddle and its answer  
2. The altered version with additional or modified details  
3. The correct answer to the altered riddle  
4. Detailed reasoning explaining the solution for both versions

## Repository Contents

This HuggingFace repository contains the full benchmark release for version `2604` (April 2026):

- **`benchmark.jsonl`** — The benchmark dataset (fixed + auxiliary riddle sets)  
- **`leaderboard.json`** — Aggregated leaderboard across all evaluated models (includes 95% confidence intervals)  
- **`riddle_difficulty.json`** — Per-riddle difficulty scores  
- **`model_outputs/2604/`** — Raw per-model answer files  
- **`results/2604/`** — Detailed per-model evaluation results  
- **`results/{version}/contamination_report.json`** — Cross-model contamination analysis  
- **`results/{version}/reproducibility_manifest.json`** — Frozen benchmark snapshot for reproducibility  
- **`results/LEADERBOARD.md`** — Markdown leaderboard table  
- **`images/`** — Charts and result visualizations  

## Dataset Structure

Each example in `benchmark.jsonl` includes the following features:  

* `id`: Unique identifier for the riddle pair (e.g., `"alt_001"`).  
* `original_riddle`: The text of the original, unaltered riddle.  
* `original_answer`: The canonical answer to the original riddle.  
* `original_accepted_answers`: List of accepted phrasings for the original answer.  
* `original_reasoning`: The explanation for the original riddle's answer.  
* `altered_riddle`: The modified version of the riddle with additional constraints or details.  
* `altered_answer`: The correct answer to the altered riddle.  
* `altered_accepted_answers`: List of accepted phrasings for the altered answer — **full credit (1.0×)**.  
* `altered_competing_answers`: Other valid answers discovered during validation — **partial credit (0.5×)**. May be promoted to `altered_accepted_answers` after manual review.  
* `altered_reasoning`: The explanation for the altered riddle's answer, often explicitly noting the deviation from the expected pattern.  
* `source`: How the entry was created (`manual`, or the generating model name).  
* `type`: Alteration type — one of `constraint_addition`, `meaning_shift`, `context_swap`, or `bias_probe`.  
* `set`: `fixed` (longitudinal baseline, never regenerated) or `auxiliary` (may be refreshed for contamination resistance).  
* `version_added`: The YYMM benchmark version when this entry was added.  

### Alteration Types

| Type | Description | Example change |
|---|---|---|
| `constraint_addition` | A new physical/functional constraint rules out the original answer | "…and it grows from the ground" |
| `meaning_shift` | A key word takes on a different meaning in the new context | "bucket" → "room" shifts "lighter" from weight to brightness |
| `context_swap` | The context or setting changes the logical answer | Redirecting the question's perspective |
| `bias_probe` | Explicitly states information contradicting a known model bias | "The surgeon, who is the boy's father…" |

## Scoring

Evaluation uses **weighted scoring** to distinguish primary answers from competing ones:

| Match type | Score | Description |
|---|---|---|
| Primary match (`altered_accepted_answers`) | **1.0** | Model gave the intended altered answer |
| Competing match (`altered_competing_answers`) | **0.5** | Model gave a valid but non-primary answer |
| Original answer | **0.0** | Model fell back to the memorized answer (counted as pattern override) |
| Wrong answer | **0.0** | Model gave an unrelated incorrect answer |

The key insight: a competing answer that differs from the original still demonstrates the model is **reasoning about the altered text** rather than recalling a memorised response. It deserves partial credit because the benchmark's primary goal is detecting pattern override, not requiring a single exact phrasing.

The headline metric **`total_score`** equals **`average_accuracy`** — the mean weighted score across all samples. In best-of-N evaluation, competing-only answers also receive partial credit (0.5×).

The partial-credit weight for competing answers (default 0.5×) is configurable via `--competing-weight`, allowing researchers to test how sensitive rankings are to this choice.

> [!Important]
> Models must be tested on at least **250 altered riddles** to appear on the leaderboard. 95% confidence intervals for all metrics are included in [`leaderboard.json`](https://huggingface.co/datasets/marcodsn/altered-riddles/blob/main/leaderboard.json).

### Key Metrics

| Metric | What it tells you |
|---|---|
| **Altered accuracy** | How often the model gives the correct answer to the modified riddle |
| **Pattern override rate** | How often the model gives the *original* (memorised) answer to the *altered* riddle — the central failure signal |
| **Altered weighted accuracy** | Like altered accuracy, but accounting for partial credit from competing answers |
| **Original accuracy** | Sanity check — can the model solve the unaltered riddles at all? |
| **Per-type accuracy** | Accuracy broken down by alteration type (constraint_addition, meaning_shift, context_swap, bias_probe) |
| **Per-source accuracy** | Accuracy stratified by which model generated the riddle |

A model with high original accuracy but low altered accuracy is probably exhibiting the pattern-override failure this benchmark is designed to detect.

### Evaluation Setup

Models are tested using the **temperature recommended by their original creators** when available (e.g., a reasoning model's suggested thinking temperature). The default `--max-output-tokens` is **16384** for benchmark runs.

When temperature > 0, each riddle is sampled **3 times** (resource-constrained for now) and scores are reported as the **average accuracy** across samples. The leaderboard also shows best-of-3 and majority-vote accuracy for these models.

## Benchmark Split

To balance stability and contamination resistance, the benchmark is split into two parts:

- **Fixed core (~150 riddles):** Never regenerated. Serves as the longitudinal baseline so scores are comparable across versions. Tagged `"set": "fixed"`.  
- **Auxiliary set (~100–150 riddles):** May be refreshed in future versions to resist contamination. Tagged `"set": "auxiliary"`.  

**Target working size: 200–350 riddles.** Statistical justification: at ~200 riddles and p≈0.65, the margin of error is ±7% at 95% confidence — sufficient for rough model rankings. Beyond ~500 riddles, diminishing returns set in. Current version has 250 riddles.

## Benchmark Results (2604)

Results are based on the top-10 ranked models evaluated on the full `2604` benchmark. All charts are generated from [leaderboard.json](https://huggingface.co/datasets/marcodsn/altered-riddles/blob/main/leaderboard.json) (check the linked file for the full leaderboard).

### Performance Comparison

![Performance comparison chart — altered accuracy with 95% confidence intervals](images/performance_chart.png)

Each bar shows a model's **altered accuracy** (solid fill) against its **weighted accuracy** (faint extension), which includes partial-credit competing answers. Error bars are 95% confidence intervals. A large gap between the faint and solid portions means competing answers are carrying a significant share of the score.

### Original vs. Altered Accuracy

![Dumbbell chart of original accuracy vs. altered accuracy](images/original_vs_altered_chart.png)

This dumbbell chart compares each model's **original accuracy** (hollow marker) against its **altered accuracy** (solid marker). The connecting segment shows how far performance drops once key details in the riddle are changed, making the pattern-override gap much easier to see model by model. Models are ordered by their original leaderboard rank, shown in the boxes on the left.

### The True Trap Rate

![Conditioned override rate chart — the true trap rate](images/conditioned_override_chart.png)

This chart isolates a model's **conditioned override rate** — how often it falls for the trap and defaults to the original answer, given that it successfully solved the original version. Models are sorted with the most resilient (lowest override rate) at the top. This is the key failure signal this benchmark is designed to detect. A high conditioned override rate means the model is heavily overfitting to the original pattern and ignoring critical altered details.

### Sampling Gain Comparison

![Sampling gain chart showing majority vote and best-of-N gains over average accuracy](images/sampling_gain_chart.png)

Each bar starts at the model's **average single-sample accuracy**, then shows the gain from **best-of-3** (gold segment) and **majority vote** (green or red segment). Best-of-3 gain is always non-negative — it only requires one correct sample out of three. Majority vote gain can go negative, meaning the model's most common answer across samples is worse than any individual sample.

### Token Efficiency

![Token efficiency scatter plot — output tokens per sample vs. altered accuracy, log scale](images/token_efficiency_chart.png)

Each row compares a model’s **token-efficiency rank** (hollow circle; fewer output tokens per altered riddle is better) with its **altered accuracy rank** (solid circle). Points further right are better on both scales, and the line between them shows the trade-off: a large gap means the model’s cost and performance rankings diverge substantially.

## Dataset Creation

### Source Data  
The base scenarios use common riddles found in LLM knowledge. The core creative step is identifying familiar riddles and adding key details that change the expected answer.  

### Data Generation Pipeline  
1. **Riddle Generation:** Use LLMs prompted with few-shot examples (via `prompts/generation.j2`) to produce altered riddle pairs from `data/riddles_source.txt`. Riddles are generated by 2–3 models from **different families** (e.g., Gemini, GPT-5.4, GLM-5) to maximise stylistic diversity and equalise contamination. Use `--type` to target generation of specific alteration types.  
2. **Validation:** A second LLM pass (`prompts/validation.j2`) checks answer validity, distinctness, logical soundness, subtlety, and identifies any competing answers.  
3. **Pool & Promotion:** Valid riddles land in `data/pool.jsonl` before being promoted to the benchmark via `scripts/promote.py`. This decouples generation from benchmark composition.  
4. **Deduplication:** Exact and fuzzy matching removes near-duplicate entries.  
5. **Benchmark & Evaluate:** Models are tested with `scripts/benchmark.py` and scored with `scripts/evaluate.py` (`python -m scripts.evaluate`), which uses an LLM judge. Evaluation is fully re-runnable — accepted answers can be edited and scores regenerated without re-running any models.  

### Splits  
The benchmark currently contains a **`train` split** used as the challenge/evaluation set. The fixed core provides a stable longitudinal baseline; the auxiliary set is refreshable per version.  

## Example Uses  

Given that our altered riddles are difficult for current SOTA LLMs, the main uses of this benchmark are to:  
- **Test models** and study their pattern-override behavior.  
- **Investigate why** LLMs fail on this task and how to address it.  

## Scaling Plan  
If initial experiments show promise, future plans include:  
1. **More Diverse Models:** Incorporate generations from additional LLMs to increase riddle and alteration diversity.  
2. **More Complex Alterations:** Experiment with different types of modifications beyond simple additions.  
3. **Increased Volume:** Scale up generation and refine the QC process.  
4. **Testing Framework:** Develop a standardized evaluation procedure for model performance.  
5. **Cross-lingual Exploration:** Investigate pattern-override issues in riddles from other languages (soon™️).  

## Limitations and Biases  
- **Limited Scope:** The dataset currently focuses on a specific failure mode (pattern override) using a limited set of base riddles.  
- **Generation Artifacts:** LLM-generated reasoning may contain errors or lack human-like awareness of alterations.  
- **Experimental Nature:** This is an exploratory benchmark targeting a specific hypothesis; its effectiveness requires empirical validation.  

## Acknowledgements  
This experiment was inspired by the `academic-chains` dataset and the [Reasoning Datasets Competition](https://huggingface.co/blog/bespokelabs/reasoning-datasets-competition). Thanks to [HuggingFace](https://huggingface.co/), [Bespoke Labs](https://www.bespokelabs.ai/), and [Together AI](https://together.ai/) for organizing the competition!  

## Licensing Information  
This dataset is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt).  

## Citation Information  
```bibtex  
@misc{marcodsn_2025_alteredriddles,  
  title = {Altered Riddles Benchmark},  
  author = {Marco De Santis},  
  year = {2025},  
  url = {https://huggingface.co/datasets/marcodsn/altered-riddles}  
}  
```  

## Development Updates  
> [!Note]  
> **[03/05/2025]** Initial dataset created!  

> [!Note]  
> **[05/04/2026]** Benchmark v2604 published! Repository now includes `benchmark.jsonl` with fixed + auxiliary riddle sets, `leaderboard.json`, per-model outputs under `model_outputs/2604/`, detailed per-model results under `results/2604/`, and result charts. The project has grown from a simple dataset into a full evaluation benchmark with a multi-stage generation, validation, and scoring pipeline.

> [!Note]
> **[06/04/2026]** Codebase improvements: consolidated evaluation into single `evaluate.py`, added shared chart utilities, per-riddle difficulty scores, confidence intervals in leaderboard, Markdown leaderboard table, minimum coverage requirement (250 riddles), and partial credit in best-of-N scoring.

> [!Note]
> **[08/07/2026]** Major codebase improvements: consolidated duplicated helpers into `core/parsing.py`, added `pyproject.toml` with dependency groups, CI pipeline with GitHub Actions, 64 unit tests, configurable competing-answer weight (`--competing-weight`), per-type and per-source accuracy breakdowns in evaluation output, adaptive sampling (`--adaptive`) and originals-samples control in benchmark runs, type-targeted riddle generation (`--type`), promote reuse caps (`--max-per-original`), re-validation support (`--re-validate`), contamination analysis script, reproducibility manifest, per-type chart, riddle heatmap data export, and schema validation script.
