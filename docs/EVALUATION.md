# Evaluation Pipeline

CLI-Tool-Bench uses **black-box differential testing** with a mandatory filesystem side-effect gate.

## Metric gates (in order)

| Stage | Metric | Meaning |
| ---: | --- | --- |
| 1 | **Build** | Agent-produced repository compiles/installs |
| 2 | **Exec + ΔS′** | Oracle-success paths run; filesystem side-effects must match oracle |
| 3 | **EM / FM / SM** | Terminal stdout equivalence (strict → fuzzy → semantic judge) |

Side-effects are **not optional metadata**. A test only proceeds to stdout comparison when oracle and agent produce identical side-effect deltas.

## Where to read the implementation

- Side-effect diff engine: [DiffTestEngine.py](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/DiffTestEngine.py) (`ENABLE_FS_DIFF = True`)
- Per-repo fuzzing scripts: [run_differential_test/repo/](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/repo/)
- Multi-repo runner: [run_multi.py](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/run_multi.py)

## Fuzzing coverage (example)

`prompt-scanner` generates structured input fixtures and runs multiple end-to-end command paths beyond the prompt example:

[prompt-scanner/start.py](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/repo/alexferrari88/prompt-scanner/start.py)

## Agent interaction model

- Agents receive only the sanitized natural-language prompt.
- Agents may self-test locally, but **never see** our acceptance tests.
- When the agent terminates, we run the full fuzzing suite post-hoc in sandboxed Docker containers without network access.
