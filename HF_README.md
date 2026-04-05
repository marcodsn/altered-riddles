---
tags:
- reasoning-datasets-competition
- reasoning
- question-answering
- chain-of-thought
- common-sense
- bias-mitigation
- experimental
- riddles
license: apache-2.0
dataset_info:
  features:
  - name: original_riddle
    dtype: string
  - name: original_answer
    dtype: string
  - name: original_reasoning
    dtype: string
  - name: altered_riddle
    dtype: string
  - name: altered_answer
    dtype: string
  - name: altered_reasoning
    dtype: string
  - name: model
    dtype: string
  splits:
  - name: train
    num_examples: 250
  download_size: 0
  dataset_size: 0
configs:
- config_name: default
  data_files:
  - split: train
    path: data.jsonl
size_categories:
- n<1K
---

<a href="https://github.com/marcodsn/altered-riddles/">
 <img src="https://huggingface.co/datasets/marcodsn/academic-chains-dev/resolve/main/made_with_curator.png" alt="Made with Curator" width=200px>
</a>

# Altered Riddles — HuggingFace Release

This HuggingFace release packages the curated benchmark used to study a specific LLM failure mode: when models rely on memorized, canonical answers to well-known riddles and ignore newly introduced or modified details in the prompt. The dataset contains 250 carefully edited riddle pairs (original + altered) designed to detect and analyze this "pattern override" behavior.

- GitHub: https://github.com/marcodsn/altered-riddles  
- HF dataset page: https://huggingface.co/datasets/marcodsn/altered-riddles

What you get in this release
- `data.jsonl` — The full benchmark (N=250). Each line is a JSON object describing one riddle pair and metadata (schema summarized below).
- `model_outputs/` — Collected model run artifacts. Each subdirectory corresponds to a model / run and contains JSONL records with the raw responses, reasoning (when available), token usage, and run metadata. These artifacts let you inspect failures and reproduce evaluation without re-running models.
- `LICENSE` — Apache-2.0 license for the dataset and accompanying artifacts.

Why this dataset exists
Large language models are trained on massive text corpora and unavoidably see popular riddles many times. When given a slightly modified version of a familiar riddle that changes the correct answer, some models continue to return the memorized response instead of reasoning from the updated input. The classic "surgeon" riddle (explicitly stating the surgeon is the boy's `father`) is a recurring motivating example: despite the prompt, some models answer "mother" because they default to the canonical riddle pattern.

This dataset collects controlled variations that flip or change a riddle's intended answer so you can:
- Measure how often models fall back to memorized answers.
- Inspect model outputs and explanations to diagnose token-level or reasoning failures.
- Evaluate mitigation strategies (e.g., fine-tuning, instruction tuning, or prompt engineering) that aim to improve attention to altered details.

Data schema (summary)
Each line in `data.jsonl` is a JSON object with (at least) the following keys:

- `id`: unique identifier (e.g., `alt_001`)  
- `original_riddle`: canonical riddle text  
- `original_answer`: canonical answer  
- `original_accepted_answers`: list of accepted phrasings for the original answer  
- `original_reasoning`: explanation for the original answer  
- `altered_riddle`: the modified riddle with added/changed details  
- `altered_answer`: the correct answer to the altered riddle  
- `altered_accepted_answers`: list of accepted phrasings for the altered answer (full credit)  
- `altered_competing_answers`: other valid answers discovered during validation (partial credit)  
- `altered_reasoning`: explanation of why the altered answer is correct  
- `source`: how the entry was created (e.g., `manual`, or model name used for generation)  
- `type`: alteration type (e.g., `constraint_addition`, `meaning_shift`, `context_swap`, `bias_probe`)  
- `set`: `fixed` or `auxiliary`  
- `version_added`: YYMM when the entry was added

Model output records (in `model_outputs/`) include:
- `riddle_id`, `model`, `timestamp`, `temperature`, `input_tokens`, `output_tokens`, `model_answer`, `model_reasoning`, and `raw_response`.

Intended uses
- Benchmarking model susceptibility to memorized-pattern overrides on short, familiar contexts.
- Analyzing token-level importance or gradient-based explanations for failures.
- Evaluating fine-tuning or instruction-based interventions that improve attention to prompt details.
- Generating targeted test suites for RAG and instruction-following systems where grounding matters.

Limitations
- Narrow focus: this collection targets a single failure mode (pattern override in riddles) rather than general reasoning. Treat it as a diagnostic/benchmarking dataset, not a comprehensive reasoning corpus.
- Generation artifacts: several examples and reasoning fields were generated or validated with LLMs. Reasoning text can contain imperfections and should be inspected before use in training.
- English-only: current release is in English.

License
This dataset is released under the Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0

How to cite
```bibtex
@misc{marcodsn_2025_alteredriddles,
  title = {Altered Riddles Dataset},
  author = {Marco De Santis},
  month = {May},
  year = {2025},
  url = {https://huggingface.co/datasets/marcodsn/altered-riddles}
}
```

### Acknowledgements
Developed for the Reasoning Datasets Competition and produced with Bespoke Curator. Thanks to HuggingFace and the research community for feedback and hosting.

Notes
- The project repository contains the complete pipeline (generation, validation, benchmarking, evaluation) and a technical report (`REPORT.md`) explaining design choices, scoring, and versioning rationale. The HuggingFace release intentionally provides the dataset and model outputs so researchers can analyze results without re-running expensive model calls.
