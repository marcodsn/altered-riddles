---
tags:
- reasoning-datasets-competition
- reasoning
- question-answering
- chain-of-thought
- common-sense
- bias-mitigation
- experimental
language:
- en
license: apache-2.0
pretty_name: Altered Idioms Dataset
size_categories:
- n<1K
---

<a href="https://github.com/bespokelabsai/curator/">
 <img src="https://huggingface.co/datasets/marcodsn/academic-chains-dev/resolve/main/made_with_curator.png" alt="Made with Curator" width=200px>
</a>

# Dataset Card for Altered Idioms Dataset

## Dataset Description

*   **GitHub:** [marcodsn/altered-idioms](https://github.com/marcodsn/altered-idioms)
*   **Dataset:** [marcodsn/altered-idioms](https://huggingface.co/datasets/marcodsn/altered-idioms) (This page)

While working on the [academic-chains](https://huggingface.co/datasets/marcodsn/academic-chains) dataset, I tested a well known alteration of a common riddle, "just for fun":

> **The Prompt:** "The surgeon, who is the boy's father says, 'I cannot operate on this boy, he's my son!'. Who is the surgeon to the boy?"

You likely immediately thought "The father!", but surprisingly, many powerful LLMs (including `gemini-2.5-pro`, `claude-sonnet-3.7`, and `qwen3-30b-a3b` in my tests) fail this simple variation. The classic riddle expects "The mother" as the answer, revealing societal biases. But when the text *explicitly states* the father is the surgeon, why do models get stuck?

My investigation, including looking at token importance gradients, suggests **overfitting to the original pattern**. Models have seen the standard riddle so often they appear to ignore the crucial, altered details in the prompt.

*(Image below: Importance gradients for Llama-3-8B, showing low importance on "father")*
![Importance Gradients - Affected Model](importance_gradients_bad.png)

*(Image below: Importance gradients for Qwen-3-4B, correctly focusing on "father")*
![Importance Gradients - Unaffected Model](importance_gradients_good.png)

> [!IMPORTANT]
> Gradient-based token importance leverages backpropagation to measure how sensitive the model's prediction (specifically, the logit of the predicted token) is to changes in the embedding of each input token. The "affected" model seemingly **ignored** the word "father" because the ingrained pattern of the original riddle overrides the actual input.

**This Dataset:** The "Altered Idioms" dataset is a curated collection designed to combat this specific type of reasoning failure. It contains familiar scenarios, riddles, and idioms where **key details have been deliberately changed**. Each entry includes:
1.  The altered scenario text.
2.  A direct question about the scenario.
3.  A detailed reasoning chain (`<think>` block) explaining *how* the answer is derived *from the altered text*, often explicitly noting the deviation from the expected pattern.
4.  The final answer.

This dataset is an experiment born from the observations during the [Reasoning Datasets Competition](https://huggingface.co/blog/bespokelabs/reasoning-datasets-competition). The central question: **Can fine-tuning on a relatively small dataset of these "trick" variations force models to pay closer attention to input details, overriding ingrained patterns and potentially improving robustness?** We hypothesize this could also lead to downstream improvements in areas like RAG (better adherence to provided context) and long-context reasoning.

## Dataset Structure

Each example in this dataset includes the following features (subject to refinement):

*   `scenario_id`: A unique identifier for this specific scenario instance.
*   `original_scenario` (Optional): The text of the original, unaltered idiom/riddle for context.
*   `altered_scenario`: The core text of the scenario with modified details.
*   `question`: The question posed about the `altered_scenario`.
*   `conversations`: List of dictionaries representing the interaction, mirroring the `academic-chains` format:
    *   `role`: "user" (for the question) or "assistant" (for the thinking process and answer).
    *   `content`: The text, including `<think>` tags for the reasoning process.
*   `model`: The LLM used to *generate* the reasoning chain and answer for this example (e.g., `gpt-4`, `claude-3-opus`, potentially manually curated).
*   `category`: Type of base scenario (e.g., 'riddle', 'idiom', 'common-sense').

## Dataset Creation

### Source Data

The base scenarios are common English riddles, idioms, and simple common-sense problems often found in LLM training data or benchmarks. Sources include public domain collections, online resources, and common knowledge examples. The core creative step is the **alteration** – identifying a key detail (like the surgeon's identity) and changing it in a way that invalidates the standard answer/interpretation.

### Data Generation Pipeline

1.  **Scenario Selection & Alteration:** Manually or semi-automatically selecting base scenarios and applying meaningful alterations.
2.  **Question Formulation:** Crafting a direct question whose answer depends critically on recognizing the alteration.
3.  **Reasoning Chain Generation\*:** Using LLMs (e.g., `gemini-2.5-flash-preview-04-17`) prompted with few-shot examples.
    *   **Prompting Strategy:** The prompt explicitly instructs the model to:
        *   Base its reasoning *solely* on the provided `altered_scenario`.
        *   Pay extremely close attention to all details.
        *   *If applicable*, note how the scenario differs from a more common version within the `<think>` block.
        *   Provide a step-by-step thought process before the final answer.
4.  **Quality Control Step 1: Automated Filtering (Planned):** Initial checks to ensure presence of `<think>` tags, completeness of generation, and absence of placeholder text.
5.  **Quality Control Step 2: Manual Review / Verification (Ongoing/Planned):** Given the subtle nature of the task, manual review is crucial to confirm:
    *   The reasoning correctly identifies and uses the altered detail.
    *   The model didn't fall back on the original pattern despite the altered input.
    *   The explanation is clear and logical.
6.  **Final Formatting:** Structuring the data into the final JSONL format.

*\*Using [Bespoke Curator](https://github.com/bespokelabsai/curator/).*

### Splits

This repository currently contains a **`train` split (N=[120] examples)**. More details about the size and how it was created/filtered will be provided soon.

## Example Uses

This dataset is primarily designed for fine-tuning LLMs to:

*   **Improve Attention to Detail:** Train models to scrutinize input text more carefully, especially in familiar-seeming contexts.
*   **Mitigate Pattern-Based Bias:** Reduce the tendency to rely on memorized patterns from training data when the input explicitly contradicts them.
*   **Enhance Robustness:** Make models less brittle and more adaptable to variations in prompts and scenarios (and to their own thinking process!)
*   **Explicit Chain-of-Thought:** Reinforce structured reasoning using the `<think>` tag format.

We hypothesize that models trained on this dataset (potentially mixed with other high-quality instruction/reasoning data) might show improved performance on:
*   RAG tasks (better grounding in provided documents).
*   Instruction following with subtle nuances.
*   Fact-checking or anomaly detection.

## Planned Evaluation

Evaluation of models fine-tuned on this dataset will focus on:

1.  **Fine-tuning:** Using efficient methods (e.g., LoRA via [unsloth](https://unsloth.ai/)) on models known to exhibit the original issue (e.g., Llama-3 variants) and potentially robust models (to check for negative impacts).
2.  **Direct Evaluation:** Testing performance on a held-out set of altered idioms. Does the fine-tuned model correctly answer and provide appropriate reasoning?
3.  **Pattern Bias Probes:** Testing the fine-tuned model on *both* the altered *and* original versions of scenarios. Can it now handle both correctly, or has the new training introduced different failure modes?
4.  **Generalization Tests:** Evaluating performance on standard reasoning benchmarks (e.g., MMLU, GSM8K, HellaSwag) to see if the targeted training has broader positive or negative effects.
5.  **Qualitative Analysis:** Examining the generated `<think>` blocks for clarity, logical consistency, and explicit recognition of the scenario's altered nature.

Results will be shared in this repository once available.

## Limitations and Biases

*   **Limited Scope:** The dataset currently focuses on a specific failure mode (pattern override) using a limited set of base scenarios (mostly English idioms). It may not generalize to all types of reasoning errors.
*   **Source Bias:** The underlying biases of the original idioms might still be present or influence the generation, despite the alterations.
*   **Generation Artifacts:** LLM-generated reasoning might contain errors or not perfectly reflect human-like awareness of the alteration.
*   **Experimental Nature:** This is an exploratory dataset targeting a specific hypothesis. Its effectiveness requires empirical validation.

## Scaling Plan

If initial experiments show promise, future plans include:

1.  **Expanding Scenario Base:** Incorporating a wider variety of base scenarios, including different cultural contexts, logical puzzles, and simplified technical problems.
2.  **More Diverse Alterations:** Experimenting with different *types* of alterations beyond simple detail changes (e.g., logical structure changes, reversing implications).
3.  **Increased Volume:** Scaling up generation and refining the QC process (potentially incorporating LLM-based verification similar to `academic-chains` if patterns emerge).
4.  **Cross-lingual Exploration:** Investigating similar pattern-override issues in other languages.
5.  **New Datasets:** Developing additional small datasets on the same line, like `altered-riddles`

## Acknowledgements

This experiment was inspired by the work on the `academic-chains` dataset and the stimulating environment of the Reasoning Datasets Competition. Thanks to [HuggingFace](https://huggingface.co/), [Bespoke Labs](https://www.bespokelabs.ai/), and [Together AI](https://together.ai/) for organizing the competition!

## Licensing Information

This dataset is licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt).

## Citation Information

```
@misc{yourname_2025_alteredidioms,
title = {Altered Idioms Dataset},
author = {Marco De Santis},
month = {May},
year = {2025},
url = {https://huggingface.co/datasets/marcodsn/altered-idioms}
}
```

## Development Updates

> [!Note]
> **[03/05/2025]** Initial dataset created!
