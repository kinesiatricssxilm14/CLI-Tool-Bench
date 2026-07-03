# Data Access & External Assets

## In-repository (browse on 4open.science)

- Benchmark prompts: [agent_prompt/](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/agent_prompt/)
- Fuzzing / differential tests: [run_differential_test/](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/run_differential_test/)
- Aggregated metrics: [results_metadata_with_sp.json](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/results_metadata_with_sp.json)
- Domain labels: [category.json](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/category.json)
- Failure analysis example: [zero_file_cases.md](https://anonymous.4open.science/r/CLI-Tool-Bench-F303/zero_file_cases.md)

## Google Drive (large generated artifacts)

| Asset | Size | Link |
| --- | ---: | --- |
| OpenHands generated repositories | ~523 MB | [Download](https://drive.google.com/file/d/17EIXINJ7JK-K7F8bRIBwBA9gtLBotwv3/view?usp=drive_link) |
| Mini-SWE-Agent generated repositories | ~216 MB | [Download](https://drive.google.com/file/d/1asdPwLFh-__Sz374WWi5B42SqldIDw43/view?usp=drive_link) |
| Full result metadata archive | small | [Download](https://drive.google.com/file/d/1Xz8cAiZ5quceI2ypvOf7bYBqGc1KKEOX/view?usp=drive_link) |
| Category metadata | small | [Download](https://drive.google.com/file/d/1XVHt1QYw1lbyFILgRJKzyuX-Tz_C-yWU/view?usp=drive_link) |
| Raw candidate filtering dataset | large | [Download](https://drive.google.com/file/d/1nqUUYhUPclafc11yVuWAxh4PeIED0UG-/view?usp=drive_link) |

## Why split storage?

Reviewer-facing inspection (prompts, tests, metrics) fits in-repo and is instantly browsable.
Generated codebases and logs (>1 GB) are archived externally to keep clone times reasonable while remaining fully available.

## Oracle stability note

Each `start.py` installs an oracle inside an isolated Docker image, snapshots the filesystem, and reuses committed container images during differential execution (`DiffTestEngine._build_baselines`).
Evaluation of **agent outputs** never clones live GitHub HEAD at scoring time; agents are tested from locally copied workspaces.
