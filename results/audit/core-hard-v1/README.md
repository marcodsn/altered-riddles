# Altered Riddles — development slice audit

Development diagnostics, not a held-out Hard leaderboard. Failure selection uses these same models and unequal k. No human review is attested. Pairwise intervals are pointwise, not multiple-comparison-adjusted.

COR is response-weighted on each model's familiar sources; accuracy uses all selected items. Shared COR restricts to sources familiar to every included row. Pairwise JSON comparisons are item-balanced on pairwise-shared familiar items.

## core (264 items)

| Model | Thinking | COR ↓ | CI95 | Alt acc ↑ | Shared COR ↓ |
|---|---|---:|---|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | on | 2.0% | 0.7%–3.5% | 96.6% | 2.0% |
| jalapeno:GLM-5.3-Flash | on | 4.2% | 2.5%–6.2% | 94.9% | 4.2% |
| nous:meituan/longcat-2.0:free | on | 4.7% | 2.8%–6.9% | 93.6% | 4.4% |
| nous:meituan/longcat-2.0:free | off | 12.6% | 8.8%–16.6% | 82.4% | 12.8% |
| jalapeno:DeepSeek-V4-Flash-0731 | off | 13.3% | 9.1%–17.7% | 80.9% | 13.5% |

## minimal_insertion_development (16 items)

| Model | Thinking | COR ↓ | CI95 | Alt acc ↑ | Shared COR ↓ |
|---|---|---:|---|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | on | 12.5% | 0.0%–29.2% | 85.4% | 12.5% |
| jalapeno:GLM-5.3-Flash | on | 22.5% | 8.8%–38.8% | 76.2% | 22.5% |
| nous:meituan/longcat-2.0:free | on | 23.8% | 10.0%–41.2% | 76.2% | 23.8% |
| jalapeno:DeepSeek-V4-Flash-0731 | off | 37.5% | 18.8%–58.8% | 60.0% | 37.5% |
| nous:meituan/longcat-2.0:free | off | 40.0% | 20.0%–61.3% | 57.5% | 40.0% |

## observed_thinking_failures_posthoc (35 items)

| Model | Thinking | COR ↓ | CI95 | Alt acc ↑ | Shared COR ↓ |
|---|---|---:|---|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | on | 15.2% | 6.2%–25.8% | 80.0% | 15.2% |
| jalapeno:GLM-5.3-Flash | on | 31.4% | 21.0%–42.4% | 67.4% | 30.9% |
| nous:meituan/longcat-2.0:free | on | 34.3% | 24.0%–45.5% | 60.0% | 32.7% |
| nous:meituan/longcat-2.0:free | off | 42.9% | 28.0%–57.1% | 47.4% | 41.8% |
| jalapeno:DeepSeek-V4-Flash-0731 | off | 45.5% | 30.9%–59.4% | 46.3% | 45.5% |

