#!/usr/bin/env python3
"""Generate browsable markdown docs for the anonymous artifact repository."""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path

from excluded_repos import EXCLUDED_REPO_SET

BASE_URL = "https://anonymous.4open.science/r/CLI-Tool-Bench-F303"
REPO_ROOT = Path(__file__).resolve().parent
DOCS_DIR = REPO_ROOT / "docs"


def link(path: str, label: str | None = None) -> str:
    label = label or path.split("/")[-1]
    return f"[{label}]({BASE_URL}/{path})"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_task_list() -> list[str]:
    tasks = []
    with (REPO_ROOT / "run_differential_test" / "full_name.txt").open() as f:
        for line in f:
            line = line.strip()
            if line and line not in EXCLUDED_REPO_SET:
                tasks.append(line)
    return tasks


def task_domain_map(categories: dict) -> dict[str, str]:
    mapping = {}
    for domain, repos in categories.items():
        for repo in repos:
            mapping[repo] = domain
    return mapping


def task_language_map(metadata: list[dict]) -> dict[str, str]:
    langs = {}
    for row in metadata:
        repo = row["instance_id"]
        if repo not in langs:
            langs[repo] = row.get("language", "unknown")
    return langs


def compute_leaderboard(metadata: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in metadata:
        key = f"{row['model_name']} | {row['framework']}"
        grouped[key].append(row)

    rows = []
    z = 1.645
    for key, items in grouped.items():
        model, framework = key.split(" | ", 1)
        n = len(items)
        if n == 0:
            continue

        def avg(field: str) -> float:
            vals = [float(x.get(field, 0) or 0) for x in items]
            return sum(vals) / len(vals)

        sm_vals = [float(x.get("sm", 0) or 0) for x in items]
        sm_avg = sum(sm_vals) / n
        sm_sd = math.sqrt(sum((x - sm_avg) ** 2 for x in sm_vals) / (n - 1 if n > 1 else 1))
        sm_ci = z * (sm_sd / math.sqrt(n))

        rows.append(
            {
                "model": model,
                "framework": framework,
                "n": n,
                "build": avg("build"),
                "exec": avg("exec"),
                "sm": sm_avg,
                "sm_sd": sm_sd,
                "sm_ci": sm_ci,
                "tokens": avg("prompt_tokens") + avg("completion_tokens"),
                "cost": avg("cost"),
            }
        )

    rows.sort(key=lambda r: r["sm"], reverse=True)
    return rows


def best_scores_by_task(metadata: list[dict]) -> dict[str, float]:
    best = {}
    for row in metadata:
        repo = row["instance_id"]
        sm = float(row.get("sm", 0) or 0)
        best[repo] = max(best.get(repo, 0.0), sm)
    return best


def start_py_stats() -> dict[str, int]:
    stats = {}
    repo_dir = REPO_ROOT / "run_differential_test" / "repo"
    for start_py in repo_dir.glob("*/*/start.py"):
        repo_id = f"{start_py.parent.parent.name}/{start_py.parent.name}"
        with start_py.open("r", encoding="utf-8", errors="ignore") as f:
            stats[repo_id] = sum(1 for _ in f)
    return stats


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_leaderboard(rows: list[dict], task_count: int) -> None:
    lines = [
        "# Leaderboard & Statistical Summary",
        "",
        f"Pre-computed from `results_metadata_with_sp.json` ({task_count} tasks × 7 models × 2 frameworks).",
        "Semantic Match (SM) is the primary paper metric. We report **standard deviation (SD)** and **90% confidence intervals (CI)**.",
        "",
        "| Rank | Model | Framework | Build ↑ | Exec ↑ | **SM ↑** | SD | 90% CI | Avg Tokens |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"| {i} | `{row['model']}` | {row['framework']} | "
            f"{pct(row['build'])} | {pct(row['exec'])} | **{pct(row['sm'])}** | "
            f"{row['sm_sd']:.3f} | ±{pct(row['sm_ci'])} | {int(row['tokens']):,} |"
        )

    lines.extend(
        [
            "",
            "## Recompute locally",
            "",
            "```bash",
            "make stats",
            "# or",
            "python compute_confidence_intervals.py",
            "```",
            "",
            "Source JSON: "
            + link("results_metadata_with_sp.json", "results_metadata_with_sp.json"),
        ]
    )
    (DOCS_DIR / "LEADERBOARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_task_catalog(
    tasks: list[str],
    domains: dict[str, str],
    languages: dict[str, str],
    best_sm: dict[str, float],
    start_lines: dict[str, int],
) -> None:
    task_count = len(tasks)
    avg_lines = sum(start_lines.get(t, 0) for t in tasks) / max(task_count, 1)

    lines = [
        f"# Task Catalog ({task_count} Repositories)",
        "",
        "Every benchmark instance links to the **sanitized agent prompt** and the **full differential fuzzing script** (`start.py`).",
        f"Average fuzzing script length: **{avg_lines:.0f} lines** across {task_count} tasks.",
        "",
        "| # | Repository | Domain | Lang | Test Script (LOC) | Best SM | Prompt | Fuzzing Tests |",
        "| ---: | --- | --- | --- | ---: | ---: | --- | --- |",
    ]

    for idx, repo in enumerate(tasks, 1):
        owner, name = repo.split("/", 1)
        prompt_path = f"agent_prompt/{owner}/{name}/agent_prompt.txt"
        test_path = f"run_differential_test/repo/{owner}/{name}/start.py"
        lines.append(
            f"| {idx} | `{repo}` | {domains.get(repo, 'N/A')} | "
            f"{languages.get(repo, 'unknown')} | {start_lines.get(repo, 0)} | "
            f"{pct(best_sm.get(repo, 0.0))} | "
            f"{link(prompt_path, 'prompt')} | {link(test_path, 'start.py')} |"
        )

    lines.extend(
        [
            "",
            "## Quick examples",
            "",
            f"- **prompt-scanner** (file-input program): {link('run_differential_test/repo/alexferrari88/prompt-scanner/start.py', 'start.py')} "
            f"+ {link('agent_prompt/alexferrari88/prompt-scanner/agent_prompt.txt', 'prompt')}",
            f"- **qlog** (environment-specific inputs): {link('run_differential_test/repo/Cosm00/qlog/start.py', 'start.py')} "
            f"+ {link('agent_prompt/Cosm00/qlog/agent_prompt.txt', 'prompt')}",
            f"- **testvet** (multi-command CLI): {link('run_differential_test/repo/LeanerCloud/testvet/start.py', 'start.py')} "
            f"+ {link('agent_prompt/LeanerCloud/testvet/agent_prompt.txt', 'prompt')}",
        ]
    )
    (DOCS_DIR / "TASK_CATALOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_quickstart(task_count: int) -> None:
    text = f"""# Quick Start (Artifact Reproduction)

This guide explains how to use the artifact at `{BASE_URL}/` without downloading unexplained folders.

## 60-Second Tour

1. Browse all tasks: {link("docs/TASK_CATALOG.md", "TASK_CATALOG.md")}
2. Inspect leaderboard + SD/CI: {link("docs/LEADERBOARD.md", "LEADERBOARD.md")}
3. Read evaluation gates (build → side-effects → stdout): {link("docs/EVALUATION.md", "EVALUATION.md")}
4. Download large generated repos (optional): {link("docs/DATA_ACCESS.md", "DATA_ACCESS.md")}

## What is already in this repository?

| Component | Location | Size |
| --- | --- | ---: |
| Example generated codebases (success & failures) | `example_generated_outputs/` | < 1 MB |
| Sanitized agent prompts ({task_count}) | `agent_prompt/` | ~2 MB |
| Differential fuzzing scripts ({task_count}) | `run_differential_test/repo/*/start.py` | ~1 MB |
| Evaluation engine | `run_differential_test/DiffTestEngine.py` | in-repo |
| Full result metadata | `results_metadata_with_sp.json` | ~1 MB |
| Task taxonomy | `category.json` | ~4 KB |

## What is hosted externally (>1 GB)?

Generated agent repositories and raw trajectories exceed anonymous-repo limits and are on Google Drive.
See {link("docs/DATA_ACCESS.md", "DATA_ACCESS.md")} for direct links and checksum instructions.

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
{link("index.html", "index.html")} for a searchable task browser and leaderboard widget.
The canonical artifact entry point remains this repository root.
"""
    (DOCS_DIR / "QUICKSTART.md").write_text(text, encoding="utf-8")


# --- Google Drive Link Configuration ---
# Update these variables after uploading your new ZIP files to Google Drive.
# Replace the URL with your new sharing links.
LINK_OPENHANDS = "YOUR_OPENHANDS_DRIVE_LINK_HERE"
LINK_MINISWE = "YOUR_MINI_SWE_DRIVE_LINK_HERE"
LINK_METADATA = "YOUR_METADATA_DRIVE_LINK_HERE"
LINK_CATEGORY = "YOUR_CATEGORY_DRIVE_LINK_HERE"
LINK_RAW_DATA = "YOUR_RAW_DATA_DRIVE_LINK_HERE"

def write_data_access() -> None:
    text = f"""# Data Access & External Assets

## In-repository (browse on 4open.science)

- Benchmark prompts: {link("agent_prompt/", "agent_prompt/")}
- Fuzzing / differential tests: {link("run_differential_test/", "run_differential_test/")}
- Aggregated metrics: {link("results_metadata_with_sp.json", "results_metadata_with_sp.json")}
- Domain labels: {link("category.json", "category.json")}
- Failure analysis example: {link("zero_file_cases.md", "zero_file_cases.md")}

## Google Drive (large generated artifacts)

| Asset | Size | Link |
| --- | ---: | --- |
| OpenHands generated repositories | ~480 MB | [Download]({LINK_OPENHANDS}) |
| Mini-SWE-Agent generated repositories | ~200 MB | [Download]({LINK_MINISWE}) |
| Full result metadata archive | small | [Download]({LINK_METADATA}) |
| Category metadata | small | [Download]({LINK_CATEGORY}) |
| Raw candidate filtering dataset | large | [Download]({LINK_RAW_DATA}) |

## Why split storage?

Reviewer-facing inspection (prompts, tests, metrics) fits in-repo and is instantly browsable.
Generated codebases and logs (>1 GB) are archived externally to keep clone times reasonable while remaining fully available.

## Oracle stability note

Each `start.py` installs an oracle inside an isolated Docker image, snapshots the filesystem, and reuses committed container images during differential execution (`DiffTestEngine._build_baselines`).
Evaluation of **agent outputs** never clones live GitHub HEAD at scoring time; agents are tested from locally copied workspaces.
"""
    (DOCS_DIR / "DATA_ACCESS.md").write_text(text, encoding="utf-8")


def write_evaluation() -> None:
    text = f"""# Evaluation Pipeline

CLI-Tool-Bench uses **black-box differential testing** with a mandatory filesystem side-effect gate.

## Metric gates (in order)

| Stage | Metric | Meaning |
| ---: | --- | --- |
| 1 | **Build** | Agent-produced repository compiles/installs |
| 2 | **Exec + ΔS′** | Oracle-success paths run; filesystem side-effects must match oracle |
| 3 | **EM / FM / SM** | Terminal stdout equivalence (strict → fuzzy → semantic judge) |

Side-effects are **not optional metadata**. A test only proceeds to stdout comparison when oracle and agent produce identical side-effect deltas.

## Where to read the implementation

- Side-effect diff engine: {link("run_differential_test/DiffTestEngine.py", "DiffTestEngine.py")} (`ENABLE_FS_DIFF = True`)
- Per-repo fuzzing scripts: {link("run_differential_test/repo/", "run_differential_test/repo/")}
- Multi-repo runner: {link("run_differential_test/run_multi.py", "run_multi.py")}

## Fuzzing coverage (example)

`prompt-scanner` generates structured input fixtures and runs multiple end-to-end command paths beyond the prompt example:

{link("run_differential_test/repo/alexferrari88/prompt-scanner/start.py", "prompt-scanner/start.py")}

## Agent interaction model

- Agents receive only the sanitized natural-language prompt.
- Agents may self-test locally, but **never see** our acceptance tests.
- When the agent terminates, we run the full fuzzing suite post-hoc in sandboxed Docker containers without network access.
"""
    (DOCS_DIR / "EVALUATION.md").write_text(text, encoding="utf-8")


def write_task_notes(task_count: int) -> None:
    text = f"""# Task Notes & Representative Examples

All **{task_count}** tasks passed manual quality gates before inclusion. Below are representative instances that illustrate how prompts, fuzzing scripts, and evaluation interact.

| Repository | Illustrates | Where to inspect |
| --- | --- | --- |
| `alexferrari88/prompt-scanner` | File-based inputs with generated fixtures | {link("run_differential_test/repo/alexferrari88/prompt-scanner/start.py", "start.py")} |
| `Cosm00/qlog` | Environment-specific input files | {link("run_differential_test/repo/Cosm00/qlog/start.py", "start.py")} |
| `LeanerCloud/testvet` | Multi-command CLI with broad fuzzing | {link("run_differential_test/repo/LeanerCloud/testvet/start.py", "start.py")} |

## Under-specification vs over-testing

- Agents are **not penalized** for unimplemented functionality beyond oracle-success paths.
- Fuzzing scripts may cover more behaviors than the prompt examples; this is intentional to prevent partial hard-coded solutions from passing.
- Inspect any task instantly via {link("docs/TASK_CATALOG.md", "TASK_CATALOG.md")}.

## Excluded from this artifact release

Six candidate repositories were removed after manual curation review due to ambiguous specifications or evaluation boundaries. See `excluded_repos.py` for the canonical list.
"""
    (DOCS_DIR / "TASK_NOTES.md").write_text(text, encoding="utf-8")


def write_readme(rows: list[dict], tasks: list[str]) -> None:
    top = rows[0]
    task_count = len(tasks)
    text = f"""# CLI-Tool-Bench Artifact

**End-to-End Evaluation for LLM-based 0-to-1 CLI Software Generation**

[![Artifact Available](https://img.shields.io/badge/Artifact-Available-success)](#)
[![Tasks](https://img.shields.io/badge/Tasks-{task_count}-blue)](#)
[![Models × Frameworks](https://img.shields.io/badge/Evaluated-7_models_%C3%97_2_frameworks-orange)](#)

> **Artifact URL (paper):** `{BASE_URL}/`

---

## Start Here (2 minutes)

| Step | What to open | Why |
| ---: | --- | --- |
| 1 | **[Quick Start](docs/QUICKSTART.md)** | Reproduction commands & folder map |
| 2 | **[Task Catalog](docs/TASK_CATALOG.md)** | All {task_count} prompts + fuzzing scripts (click-through links) |
| 3 | **[Leaderboard](docs/LEADERBOARD.md)** | SM scores with **SD** and **90% CI** |
| 4 | **[Evaluation Pipeline](docs/EVALUATION.md)** | Side-effect gate + differential testing details |
| 5 | **[Data Access](docs/DATA_ACCESS.md)** | In-repo vs Google Drive assets |

---

## At a Glance

| Item | Value |
| --- | --- |
| Benchmark tasks | **{len(tasks)}** real-world CLI repositories |
| Languages | Python, JavaScript, Go |
| Agent scaffolds | OpenHands, Mini-SWE-Agent |
| Models evaluated | 7 LLMs (see leaderboard) |
| Best overall SM | **{pct(top['sm'])}** ({top['model']}, {top['framework']}) |
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

- Prompt: [{BASE_URL}/agent_prompt/alexferrari88/prompt-scanner/agent_prompt.txt]({BASE_URL}/agent_prompt/alexferrari88/prompt-scanner/agent_prompt.txt)
- Tests: [{BASE_URL}/run_differential_test/repo/alexferrari88/prompt-scanner/start.py]({BASE_URL}/run_differential_test/repo/alexferrari88/prompt-scanner/start.py)

---

## Repository Layout

```text
.
├── docs/                         # Human-readable artifact guides (start here)
├── example_generated_outputs/    # Browsable success & failure cases (Go, JS, Python)
├── agent_prompt/                 # {task_count} sanitized prompts
├── run_differential_test/        # Differential engine + {task_count} start.py fuzzers
├── results_metadata_with_sp.json # Complete evaluation table
├── category.json                 # Domain taxonomy
├── compute_confidence_intervals.py
├── generate_artifact_docs.py     # Regenerate docs/LEADERBOARD.md etc.
├── index.html                    # Optional interactive browser (same repo)
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
"""
    (REPO_ROOT / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    metadata = [r for r in load_json(REPO_ROOT / "results_metadata_with_sp.json") if r["instance_id"] not in EXCLUDED_REPO_SET]
    categories = load_json(REPO_ROOT / "category.json")
    tasks = load_task_list()

    rows = compute_leaderboard(metadata)
    domains = task_domain_map(categories)
    languages = task_language_map(metadata)
    best_sm = best_scores_by_task(metadata)
    start_lines = start_py_stats()

    write_leaderboard(rows, len(tasks))
    write_task_catalog(tasks, domains, languages, best_sm, start_lines)
    write_quickstart(len(tasks))
    write_data_access()
    write_evaluation()
    write_task_notes(len(tasks))
    write_readme(rows, tasks)

    print(f"Generated artifact docs in {DOCS_DIR}")
    print(f"Updated {REPO_ROOT / 'README.md'}")


if __name__ == "__main__":
    main()
