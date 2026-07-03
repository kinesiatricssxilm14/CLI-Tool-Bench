# CLI-Tool-Bench Artifact

**End-to-End Evaluation for LLM-based 0-to-1 CLI Software Generation**

[![Artifact Available](https://img.shields.io/badge/Artifact-Available-success)](#)
[![Tasks](https://img.shields.io/badge/Tasks-94-blue)](#)
[![Models × Frameworks](https://img.shields.io/badge/Evaluated-7_models_%C3%97_2_frameworks-orange)](#)
[![Interactive Web Explorer](https://img.shields.io/badge/Web_Explorer-Click_Here!-ff69b4.svg)](https://kinesiatricssxilm14.github.io/CLI-Tool-Bench/)

> **Artifact URL (paper):** `https://anonymous.4open.science/r/CLI-Tool-Bench-F303/`

---

## 🌟 Interactive Web Explorer (NEW!)

We have built an interactive Web Dashboard directly into this repository! 

👉 **[Open the Web Explorer (Interactive Dashboard)](https://kinesiatricssxilm14.github.io/CLI-Tool-Bench/)** 👈

**In the Web Explorer, you can:**
1. View the **Interactive Leaderboard** (complete with Standard Deviation and Confidence Intervals).
2. Browse all **94 Tasks** via the Task Explorer.
3. Instantly view the **Sanitized Agent Prompts** and the **Differential Fuzzing Test Scripts (`start.py`)** side-by-side.

---

---

## Start Here (2 minutes)

| Step | What to open | Why |
| ---: | --- | --- |
| 1 | **[Quick Start](docs/QUICKSTART.md)** | Reproduction commands & folder map |
| 2 | **[Task Catalog](docs/TASK_CATALOG.md)** | All 94 prompts + fuzzing scripts (click-through links) |
| 3 | **[Leaderboard](docs/LEADERBOARD.md)** | SM scores with **SD** and **90% CI** |
| 4 | **[Evaluation Pipeline](docs/EVALUATION.md)** | Side-effect gate + differential testing details |
| 5 | **[Data Access](docs/DATA_ACCESS.md)** | In-repo vs Google Drive assets |

---

## At a Glance

| Item | Value |
| --- | --- |
| Benchmark tasks | **94** real-world CLI repositories |
| Languages | Python, JavaScript, Go |
| Agent scaffolds | OpenHands, Mini-SWE-Agent |
| Models evaluated | 7 LLMs (see leaderboard) |
| Best overall SM | **51.2%** (kimi-k2.5, Mini-SWE-Agent) |
| Primary metric | Semantic Match (SM) after Build + Exec + ΔS′ gates |

---

## What reviewers can verify immediately (no multi-GB download)

```text
agent_prompt/<owner>/<repo>/agent_prompt.txt       # Sanitized intent given to agents
run_differential_test/repo/<owner>/<repo>/start.py # Full fuzzing + differential oracle
results_metadata_with_sp.json                      # All per-model scores
run_differential_test/DiffTestEngine.py            # Side-effect + stdout checking
example_generated_outputs/                         # Representative success and failure case examples
```

Reviewers can browse the **[`example_generated_outputs/`](example_generated_outputs/)** directory to see real codebases representing successful builds, compilation errors, runtime crashes, and hallucinated workspaces without downloading the 1GB archive.

Example — **prompt-scanner** (file-input CLI with programmatic fuzz fixtures):

- Prompt: [https://anonymous.4open.science/r/CLI-Tool-Bench-F303/agent_prompt/alexferrari88/prompt-scanner/agent_prompt.txt](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/agent_prompt/alexferrari88/prompt-scanner/agent_prompt.txt)
- Tests: [https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/repo/alexferrari88/prompt-scanner/start.py](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/repo/alexferrari88/prompt-scanner/start.py)

---

## Repository Layout

```text
.
├── docs/                         # Human-readable artifact guides (start here)
├── example_generated_outputs/    # Browsable success & failure cases (Go, JS, Python)
├── agent_prompt/                 # 94 sanitized prompts
├── run_differential_test/        # Differential engine + 94 start.py fuzzers
├── results_metadata_with_sp.json # Complete evaluation table
├── category.json                 # Domain taxonomy
├── compute_confidence_intervals.py
├── generate_artifact_docs.py     # Regenerate docs/LEADERBOARD.md etc.
├── index.html                    # Local interactive dashboard (open in browser)
└── zero_file_cases.md            # Qualitative failure analysis
```

---

## Reproduce metrics locally

```bash
python compute_confidence_intervals.py   # prints SD + 90% CI
python generate_artifact_docs.py         # refresh docs/ markdown tables
```

Large generated repositories remain on Google Drive — see [docs/DATA_ACCESS.md](docs/DATA_ACCESS.md).

---

## Evaluate a new agent

1. Give your agent the prompt from `agent_prompt/.../agent_prompt.txt`.
2. Let it finish in an isolated workspace (no internet, no test access).
3. Run `run_differential_test/run_multi.py` against the produced folder.

---

## Integrity guarantees

- **No test leakage:** fuzzing scripts are never shown to agents during generation.
- **Side-effects are enforced:** stdout is compared only after filesystem deltas match the oracle (see [docs/EVALUATION.md](docs/EVALUATION.md)).
- **De-identified prompts:** author names, URLs, and branding removed before agent execution.
- **Isolated sandboxes:** agent runs use Docker without network connectivity.
