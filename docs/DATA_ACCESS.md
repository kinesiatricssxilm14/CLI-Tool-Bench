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
| OpenHands generated repositories | ~480 MB | [Download](https://drive.google.com/file/d/1jWK3CM3AA-AfyawXCq_MbVCvVo4WP07J/view?usp=sharing) |
| Mini-SWE-Agent generated repositories | ~200 MB | [Download](https://drive.google.com/file/d/1H5CXRHzxemnO8j_pPF2aziTfq_p0IjFl/view?usp=sharing) |
| Full result metadata archive | ~1 MB | [In-Repo Link](https://github.com/kinesiatricssxilm14/CLI-Tool-Bench/blob/main/results_metadata_with_sp.json) |
| Category metadata | ~3 KB | [In-Repo Link](https://github.com/kinesiatricssxilm14/CLI-Tool-Bench/blob/main/category.json) |
| Raw candidate filtering dataset | large | [Download](https://drive.google.com/file/d/1nqUUYhUPclafc11yVuWAxh4PeIED0UG-/view?usp=drive_link) |

## Why split storage?

Reviewer-facing inspection (prompts, tests, metrics) fits in-repo and is instantly browsable.
Generated codebases and logs (>1 GB) are archived externally to keep clone times reasonable while remaining fully available.

## Oracle stability note

Each `start.py` installs an oracle inside an isolated Docker image, snapshots the filesystem, and reuses committed container images during differential execution (`DiffTestEngine._build_baselines`).
Evaluation of **agent outputs** never clones live GitHub HEAD at scoring time; agents are tested from locally copied workspaces.
