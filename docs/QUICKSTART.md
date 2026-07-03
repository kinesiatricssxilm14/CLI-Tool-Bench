# Quick Start (Artifact Reproduction)

This guide explains how to use the artifact at `https://anonymous.4open.science/r/CLI-Tool-Bench-F303/` without downloading unexplained folders.

## 60-Second Tour

1. Browse all tasks: [TASK_CATALOG.md](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/docs/TASK_CATALOG.md)
2. Inspect leaderboard + SD/CI: [LEADERBOARD.md](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/docs/LEADERBOARD.md)
3. Read evaluation gates (build → side-effects → stdout): [EVALUATION.md](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/docs/EVALUATION.md)
4. Download large generated repos (optional): [DATA_ACCESS.md](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/docs/DATA_ACCESS.md)

## What is already in this repository?

| Component | Location | Size |
| --- | --- | ---: |
| Example generated codebases (success & failures) | `example_generated_outputs/` | < 1 MB |
| Sanitized agent prompts (94) | `agent_prompt/` | ~2 MB |
| Differential fuzzing scripts (94) | `run_differential_test/repo/*/start.py` | ~1 MB |
| Evaluation engine | `run_differential_test/DiffTestEngine.py` | in-repo |
| Full result metadata | `results_metadata_with_sp.json` | ~1 MB |
| Task taxonomy | `category.json` | ~4 KB |

## What is hosted externally (>1 GB)?

Generated agent repositories and raw trajectories exceed anonymous-repo limits and are on Google Drive.
See [DATA_ACCESS.md](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/docs/DATA_ACCESS.md) for direct links and checksum instructions.

## Reproduce paper metrics

```bash
# 1) Install Python deps (matplotlib/scipy if plotting)
pip install scipy matplotlib pandas

# 2) Recompute leaderboard with SD / 90% CI
python compute_confidence_intervals.py

# 3) Optional: regenerate all markdown docs
python generate_artifact_docs.py
```

## Evaluate your own agent

```bash
cd run_differential_test

# Edit full_name.txt to select tasks, then run differential testing
# against a local folder containing the agent-generated repository.
python run_multi.py
```

Inputs:
- Prompt: `agent_prompt/<owner>/<repo>/agent_prompt.txt`
- Oracle fuzzing script: `run_differential_test/repo/<owner>/<repo>/start.py`

Agents receive **no access** to fuzzing scripts during generation; evaluation is strictly post-hoc.

## Optional interactive view

If your browser renders static HTML from the file tree, you may also open
[index.html](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/index.html) for a searchable task browser and leaderboard widget.
The canonical artifact entry point remains this repository root.
