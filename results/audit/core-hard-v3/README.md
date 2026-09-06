# Altered Riddles — development slice audit

Development diagnostics, not a held-out Hard leaderboard. Failure selection uses these same models and unequal k. No human review is attested. Pairwise intervals are pointwise, not multiple-comparison-adjusted.

COR is response-weighted on each model's familiar sources; accuracy uses all selected items. Shared COR restricts to sources familiar to every included row. Pairwise JSON comparisons are item-balanced on pairwise-shared familiar items.

## core (264 items)

| Model | Thinking | COR ↓ | CI95 | Alt acc ↑ | Shared COR ↓ |
|---|---|---:|---|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | on | 2.0% | 0.7%–3.5% | 96.6% | 2.0% |
| jalapeno:GLM-5.3-Flash | on | 3.8% | 2.1%–5.8% | 95.3% | 3.8% |
| nous:meituan/longcat-2.0:free | on | 4.7% | 2.8%–6.9% | 93.6% | 4.4% |
| nous:meituan/longcat-2.0:free | off | 12.0% | 8.3%–15.9% | 83.0% | 12.3% |
| jalapeno:DeepSeek-V4-Flash-0731 | off | 12.8% | 8.8%–17.1% | 81.1% | 13.0% |

## minimal_insertion_development (16 items)

| Model | Thinking | COR ↓ | CI95 | Alt acc ↑ | Shared COR ↓ |
|---|---|---:|---|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | on | 12.5% | 0.0%–29.2% | 85.4% | 12.5% |
| jalapeno:GLM-5.3-Flash | on | 20.0% | 5.0%–36.2% | 78.8% | 20.0% |
| nous:meituan/longcat-2.0:free | on | 23.8% | 10.0%–41.2% | 76.2% | 23.8% |
| jalapeno:DeepSeek-V4-Flash-0731 | off | 35.0% | 15.0%–57.5% | 61.3% | 35.0% |
| nous:meituan/longcat-2.0:free | off | 40.0% | 20.0%–61.3% | 57.5% | 40.0% |

## observed_thinking_failures_posthoc (32 items)

| Model | Thinking | COR ↓ | CI95 | Alt acc ↑ | Shared COR ↓ |
|---|---|---:|---|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | on | 16.7% | 6.9%–28.7% | 78.1% | 16.7% |
| jalapeno:GLM-5.3-Flash | on | 31.2% | 20.0%–42.6% | 67.5% | 30.7% |
| nous:meituan/longcat-2.0:free | on | 37.5% | 26.0%–48.1% | 56.2% | 36.0% |
| jalapeno:DeepSeek-V4-Flash-0731 | off | 42.7% | 27.5%–58.6% | 47.5% | 42.7% |
| nous:meituan/longcat-2.0:free | off | 45.0% | 30.0%–60.0% | 44.4% | 44.7% |

