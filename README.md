# Altered Riddles Dataset

## Overview

The **Altered Riddles Dataset** is a curated collection designed to combat a specific type of reasoning failure in LLMs: the tendency to override explicit information when it conflicts with familiar patterns. This dataset contains well-known riddles where key details have been deliberately changed, challenging models to pay closer attention to the actual input.

## Background & Motivation

While working on the [academic-chains](https://huggingface.co/datasets/marcodsn/academic-chains) dataset, I discovered that many powerful LLMs (including `gemini-2.5-pro`, `claude-sonnet-3.7`, and `qwen3-30b-a3b`) fail on simple variations of common riddles. For example:

> *The surgeon, who is the boy's father, says, 'I cannot operate on this boy-he's my son!'. Who is the surgeon to the boy?*

Many models incorrectly answer "The mother" (the answer to the classic riddle) despite the prompt explicitly stating the surgeon is the father. Analysis of token importance gradients suggests **overfitting to the original pattern** - models have seen and memorized standard riddles so often that they appear to ignore crucial, altered details.

## Dataset Structure

Each example includes:

* `original_riddle`: The text of the original, unaltered riddle
* `original_answer`: The correct answer to the original riddle
* `original_reasoning`: The explanation for the original riddle's answer
* `altered_riddle`: The modified version with additional constraints or details
* `altered_answer`: The correct answer to the altered riddle
* `altered_reasoning`: The explanation for the altered riddle's answer
* `model`: The LLM used to generate this dataset entry

## Example Cases

Multiple SOTA models fail these altered riddles. For instance, Gemini 2.5 Pro consistently gives incorrect answers to altered riddles about:
- A riddle where the answer should be "sleep"
- A riddle where the answer should be "A sperm cell or tadpole"
- A riddle where the answer should be "A plant"

## Dataset Creation

### Process
1. **Riddle Selection & Alteration:** Selecting common riddles and adding key details that change the expected answer
2. **Answer & Reasoning Generation:** Using LLMs prompted with few-shot examples
3. **Verification & Formatting:** Checking model performance and structuring into JSONL format

The dataset currently contains a **train split (N=104 examples)**.

## Potential Applications

This dataset can be used to:
- **Test models** and study their behavior
- **Investigate why** LLMs fail on this task
- **Fine-tune models** to:
  - Improve attention to detail
  - Mitigate pattern-based bias
  - Enhance robustness to prompt variations
  - Strengthen chain-of-thought reasoning

We hypothesize that models trained on this dataset might show improved performance on:
- RAG tasks (better grounding in provided documents)
- Instruction following with subtle nuances
- Reasoning tasks requiring careful attention to details

## Evaluation Plans

Future evaluation will focus on:
1. **Fine-tuning** using efficient methods (e.g., LoRA)
2. **Direct Evaluation** on held-out altered riddles
3. **Pattern Bias Probes** testing both altered and original versions
4. **Generalization Tests** on standard reasoning benchmarks
5. **Qualitative Analysis** of reasoning quality

## Limitations

- **Limited Scope:** Currently focuses on a specific failure mode using a limited set of base riddles
- **Generation Artifacts:** LLM-generated reasoning may contain errors
- **Experimental Nature:** Effectiveness requires empirical validation

## Future Plans

If initial experiments show promise:
1. Incorporate generations from additional LLMs
2. Experiment with more complex alterations
3. Scale up generation and refine QC process
4. Develop standardized evaluation procedures
5. Explore cross-lingual pattern-override issues

## Links
- **Dataset on Hugging Face:** [marcodsn/altered-riddles](https://huggingface.co/datasets/marcodsn/altered-riddles)
- **GitHub Repository:** [marcodsn/altered-riddles](https://github.com/marcodsn/altered-riddles)

## Acknowledgements

This experiment was inspired by the `academic-chains` dataset and the [Reasoning Datasets Competition](https://huggingface.co/blog/bespokelabs/reasoning-datasets-competition). Thanks to [HuggingFace](https://huggingface.co/), [Bespoke Labs](https://www.bespokelabs.ai/), and [Together AI](https://together.ai/) for organizing the competition!

## License

This dataset is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt).

## Citation

```bibtex
@misc{marcodsn_2025_alteredriddles,
  title = {Altered Riddles Dataset},
  author = {Marco De Santis},
  month = {May},
  year = {2025},
  url = {https://huggingface.co/datasets/marcodsn/altered-riddles}
}
```

## Development Updates

**[May 3, 2025]** Initial dataset created!
