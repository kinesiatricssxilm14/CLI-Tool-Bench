# Leaderboard & Statistical Summary

Pre-computed from `results_metadata_with_sp.json` (94 tasks × 7 models × 2 frameworks).
Semantic Match (SM) is the primary paper metric. We report **standard deviation (SD)** and **90% confidence intervals (CI)**.

| Rank | Model | Framework | Build ↑ | Exec ↑ | **SM ↑** | SD | 90% CI | Avg Tokens |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `kimi-k2.5` | Mini-SWE-Agent | 95.7% | 79.2% | **51.2%** | 0.377 | ±6.4% | 375,804 |
| 2 | `minimax-2.5` | Mini-SWE-Agent | 95.7% | 80.1% | **39.1%** | 0.364 | ±6.2% | 2,445,877 |
| 3 | `kimi-k2.5` | OpenHands | 90.4% | 69.6% | **36.4%** | 0.358 | ±6.1% | 1,340,922 |
| 4 | `glm-5` | Mini-SWE-Agent | 78.7% | 63.5% | **33.2%** | 0.361 | ±6.1% | 235,253 |
| 5 | `gpt-5.4` | Mini-SWE-Agent | 85.1% | 61.1% | **31.8%** | 0.343 | ±5.8% | 20,891 |
| 6 | `qwen3.5-plus` | Mini-SWE-Agent | 76.6% | 61.3% | **30.8%** | 0.358 | ±6.1% | 930,818 |
| 7 | `minimax-2.5` | OpenHands | 79.8% | 66.1% | **30.1%** | 0.341 | ±5.8% | 4,236,376 |
| 8 | `gpt-5.4` | OpenHands | 79.8% | 59.7% | **28.9%** | 0.322 | ±5.5% | 168,498 |
| 9 | `qwen3.5-plus` | OpenHands | 73.4% | 59.0% | **28.9%** | 0.345 | ±5.9% | 1,114,026 |
| 10 | `glm-5` | OpenHands | 76.6% | 59.0% | **28.5%** | 0.331 | ±5.6% | 238,783 |
| 11 | `DeepSeek-V3.2` | OpenHands | 80.9% | 61.8% | **27.4%** | 0.341 | ±5.8% | 2,050,048 |
| 12 | `DeepSeek-V3.2` | Mini-SWE-Agent | 72.3% | 60.1% | **27.4%** | 0.338 | ±5.7% | 818,636 |
| 13 | `claude-sonnet-4-6` | Mini-SWE-Agent | 52.1% | 31.7% | **14.0%** | 0.267 | ±4.5% | 99,586 |
| 14 | `claude-sonnet-4-6` | OpenHands | 37.2% | 18.4% | **7.2%** | 0.189 | ±3.2% | 203,825 |

## Recompute locally

```bash
make stats
# or
python compute_confidence_intervals.py
```

Source JSON: [results_metadata_with_sp.json](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/results_metadata_with_sp.json)
