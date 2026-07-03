# Task Notes & Representative Examples

All **94** tasks passed manual quality gates before inclusion. Below are representative instances that illustrate how prompts, fuzzing scripts, and evaluation interact.

| Repository | Illustrates | Where to inspect |
| --- | --- | --- |
| `alexferrari88/prompt-scanner` | File-based inputs with generated fixtures | [start.py](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/repo/alexferrari88/prompt-scanner/start.py) |
| `Cosm00/qlog` | Environment-specific input files | [start.py](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/repo/Cosm00/qlog/start.py) |
| `LeanerCloud/testvet` | Multi-command CLI with broad fuzzing | [start.py](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/repo/LeanerCloud/testvet/start.py) |

## Under-specification vs over-testing

- Agents are **not penalized** for unimplemented functionality beyond oracle-success paths.
- Fuzzing scripts may cover more behaviors than the prompt examples; this is intentional to prevent partial hard-coded solutions from passing.
- Inspect any task instantly via [TASK_CATALOG.md](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/docs/TASK_CATALOG.md).

## Excluded from this artifact release

Six candidate repositories were removed after manual curation review due to ambiguous specifications or evaluation boundaries. See `excluded_repos.py` for the canonical list.
