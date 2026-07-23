# Altered Riddles Leaderboard

> 23 models evaluated on the public **auxiliary** set. Main metric: **Conditioned Override Rate** (lower = better), conditioned on solving the original riddle text.

> _Judge provenance:_ verdicts are from the original run's judge (qwen3.5-27b @ local; identity not recorded in source runs). A fresh re-judge of 500 sampled answers (nous laguna-s-2.1) agrees **96.8%** on `correct` and **87.8%** on `gave_original` — so COR carries a ~12% per-label judge-sensitivity band. See `results/judge_agreement.json`.

| Rank | Rank Spread | Model | Reasoning | Effort | Orig Acc ↑ | Alt Acc ↑ | Cond Override ↓ | CI95 | Override Rate ↓ | Tok/riddle | Samp/riddle |
|------|-------------|-------|-----------|--------|-----------|----------|-----------------|------|-----------------|------------|-------------|
| 1 | [1–9] | openai/gpt-5.4-mini | on | high | 92.6% | 42.4% | 33.7% | +/-4.8% | 32.9% | 2807.0 | 1.00 |
| 2 | [1–9] | xiaomi/mimo-v2-pro | on | high | 96.3% | 39.8% | 33.8% | +/-4.5% | 33.7% | 2598.1 | 3.00 |
| 3 | [1–10] | openai/gpt-oss-20b | on | high | 84.0% | 33.8% | 35.5% | +/-5.1% | 32.2% | 4535.7 | 1.00 |
| 4 | [1–10] | zai-org/glm-5.1 | on | high | 97.3% | 36.6% | 35.9% | +/-4.8% | 35.3% | 6088.6 | 1.00 |
| 5 | [1–11] | minimaxai/minimax-m2.7 | on | high | 88.3% | 34.9% | 36.1% | +/-4.9% | 33.4% | 7540.4 | 1.00 |
| 6 | [1–10] | xiaomi/mimo-v2-omni | on | high | 93.6% | 37.8% | 36.2% | +/-4.2% | 35.1% | 2463.9 | 3.00 |
| 7 | [1–11] | google/gemma-4-31b-it | on | high | 96.3% | 37.9% | 36.4% | +/-5.2% | 35.3% | 2413.1 | 1.00 |
| 8 | [1–11] | mistralai/mistral-small-2603 | on | high | 88.3% | 33.2% | 36.6% | +/-4.9% | 33.4% | 2907.1 | 1.00 |
| 9 | [1–12] | openai/gpt-oss-120b | on | high | 90.4% | 35.0% | 37.5% | +/-5.1% | 35.3% | 1134.3 | 1.00 |
| 10 | [5–13] | zai-org/glm-5 | on | high | 96.8% | 35.0% | 39.3% | +/-4.9% | 38.7% | 5346.4 | 1.00 |
| 11 | [7–13] | qwen/qwen3.5-27b | off | - | 84.0% | 27.0% | 42.6% | +/-4.9% | 37.6% | 13.4 | 3.00 |
| 12 | [10–18] | openai/gpt-5.4-mini | off | - | 87.8% | 27.6% | 43.0% | +/-5.0% | 40.2% | 21.0 | 1.00 |
| 13 | [12–20] | moonshotai/kimi-k2.5 | on | high | 96.8% | 33.4% | 45.1% | +/-4.8% | 44.4% | 4075.5 | 1.00 |
| 14 | [12–20] | qwen/qwen3.6-35b-a3b | off | - | 78.2% | 20.5% | 46.6% | +/-5.1% | 42.3% | 13.3 | 3.00 |
| 15 | [13–21] | google/gemma-4-31b-it | off | - | 95.2% | 30.6% | 46.8% | +/-5.0% | 45.4% | 26.2 | 3.00 |
| 16 | [12–21] | moonshotai/kimi-k2.6 | on | high | 97.9% | 33.1% | 47.3% | +/-5.3% | 46.5% | 4322.3 | 1.00 |
| 17 | [12–21] | anthropic/claude-sonnet-4.6 | on | high | 97.3% | 30.7% | 47.3% | +/-5.1% | 46.7% | 248.8 | 1.00 |
| 18 | [12–21] | qwen/qwen3.6-27b | off | - | 83.0% | 26.5% | 48.1% | +/-5.1% | 42.2% | 12.9 | 3.00 |
| 19 | [13–21] | google/gemma-4-26b-a4b-it | off | - | 86.2% | 29.8% | 48.4% | +/-5.0% | 43.7% | 13.0 | 3.00 |
| 20 | [6–21] | liquidai/lfm2-24b-a2b | off | - | 51.1% | 19.6% | 48.8% | +/-6.9% | 25.9% | 14.7 | 3.00 |
| 21 | [16–22] | mistralai/mistral-small-2603 | off | - | 89.1% | 18.9% | 51.4% | +/-5.1% | 47.1% | 14.7 | 1.00 |
| 22 | [20–22] | anthropic/claude-opus-4.7 | on | high | 96.8% | 27.2% | 52.8% | +/-4.7% | 51.2% | 60.2 | 1.00 |
| 23 | [23–23] | moonshotai/kimi-k2.5 | off | - | 96.8% | 21.6% | 56.6% | +/-4.8% | 56.5% | 29.4 | 1.00 |
