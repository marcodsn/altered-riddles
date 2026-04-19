# Altered Riddles: A Benchmark for Conditioned Override in LLMs

## Overview

**Altered Riddles** is a benchmark designed to measure **Conditioned Override Rate (COR)** — the tendency of language models to fall back on memorized answers when a familiar riddle is subtly modified. This benchmark helps identify when models solve problems based on memorization versus reasoning.

## Links

- **Dataset**: [HuggingFace](https://huggingface.co/datasets/marcodsn/altered-riddles)
- **Generation & Evaluation**: [GitHub](https://github.com/marcodsn/altered-riddles)
- **Leaderboard**: [Altered Riddles Benchmark](https://marcodsn.me/altered-riddles)

## Dataset Description

The benchmark measures how often models fail to adapt when a well-known riddle is altered in meaningful ways. For each altered riddle, models are scored on:

- **Correct**: The model provides the correct answer to the modified riddle
- **Gave Original**: The model gives the (now incorrect) answer from the original riddle
- **Competing**: The model gives a different, non-preferred answer

The **Conditioned Override Rate (COR)** is calculated as: among altered riddles where the model correctly answered the original, what percentage did it give the now-wrong original answer? **Lower COR is better** — indicating the model can adapt to modifications rather than defaulting to memorized solutions.

## Dataset Structure

### Public Auxiliary Set
This release includes **700 items** from the public auxiliary set, comprising:
- **Original riddles** with ground-truth answers
- **Altered versions** created via four modification types:
  - **Constraint Addition**: Adding constraints that eliminate the original answer
  - **Meaning Shift**: Recontextualizing the riddle to shift what is being asked
  - **Context Swap**: Swapping contextual elements to change the solution
  - **Bias Probe**: Testing if models default to stereotypical vs. correct answers

### Private Fixed Set
The benchmark also includes a **private fixed set of 300 items** used for stable model evaluation and leaderboard ranking. This fixed set is not released publicly to prevent optimization/gaming and ensure reliable comparison across models.

## Data Format

Each item in the dataset notably contains:
- `original_riddle`: The source riddle text
- `original_answer`: Correct answer to the original
- `altered_riddle`: The modified riddle text  
- `altered_answer`: Correct answer to the altered version
- `alteration_type`: One of the four types above
- `source`: The model that generated the altered riddle

## Usage

The auxiliary set is suitable for:
- Training and evaluation of reasoning models
- Testing model robustness to input perturbations
- Research on memorization vs. reasoning in LLMs
- Fine-tuning models to improve conditioned override resistance

## Evaluation

Models are evaluated using an LLM-as-parser approach, scoring each output into the three categories above. Metrics include:
- **Accuracy**: Percentage of correct answers
- **Conditioned Override Rate (COR)**: Percentage giving the original answer on altered riddles
- **95% Confidence Intervals** using clustered bootstrap (clustered by source riddle) to account for within-riddle correlation

## Citation

If you use this benchmark, please cite:

```bibtex
@misc{marcodsn_2025_alteredriddles,  
  title = {Altered Riddles Benchmark},  
  author = {Marco De Santis},  
  year = {2026},  
  url = {https://marcodsn.me/altered-riddles} 
}
```

## License

The auxiliary set (700 items) is publicly available under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt). The fixed set (300 items) is private and will not be shared.
