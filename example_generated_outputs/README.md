# Showcase: LLM Generated Repositories

This folder contains representative examples of repositories generated entirely from scratch by autonomous LLM agents. We include both **success cases** (which pass all evaluation gates) and **failure cases** (illustrating different failure modes identified in our benchmark).

These examples allow reviewers to easily inspect the code quality, repository structure, and failure patterns directly in the repository without downloading the multi-gigabyte results archive.

---

## 🟢 Success Cases (100% Validated)

These agents achieved near 100% Semantic Match and passed both the Execution and Side-Effect validation gates.

### 1. `01_success_deepseek-v3.2_openhands_local-gitingest`
- **Language:** Go
- **Task:** `bigwhite/local-gitingest` (Batch File Processing)
- **Agent/Model:** OpenHands with DeepSeek-V3.2
- **Description:** A perfectly generated Go repository handling directory traversals and text extraction. Notice how the agent independently planned the `main.go` and `go.mod` structure.

### 2. `02_success_kimi-k2.5_miniswe_mp4analyzer`
- **Language:** Python
- **Task:** `andrewx-bu/mp4analyzer` (Utility Libraries)
- **Agent/Model:** Mini-SWE-Agent with Kimi-k2.5
- **Description:** A Python package using `pyproject.toml` and standard CLI argument parsing. Demonstrates that the agent correctly sets up package entry points to be installable and runnable as a system CLI.

---

## 🔴 Failure Cases (Common Failure Modes)

These examples represent the primary failure modes evaluated in CLI-Tool-Bench.

### 3. Build Failure (`03_fail_build_deepseek-v3.2_openhands_mkbrr`)
- **Language:** Go
- **Task:** `autobrr/mkbrr`
- **Agent/Model:** OpenHands with DeepSeek-V3.2
- **Why it failed:** The agent attempted to generate a complex Go application but failed to resolve internal module imports and dependency management in `go.mod`, resulting in a compilation error (Build Gate Failure).

### 4. Execution Failure (`04_fail_exec_deepseek-v3.2_openhands_cc-safe`)
- **Language:** JavaScript (Node.js)
- **Task:** `ykdojo/cc-safe`
- **Agent/Model:** OpenHands with DeepSeek-V3.2
- **Why it failed:** The agent successfully initialized the Node.js project and dependencies (Build Gate Passed). However, the generated script crashes at runtime due to unhandled promise rejections and missing logic when tested against the black-box fuzzing suite (Execution Gate Failure).

### 5. Logic / Semantic Failure (`05_fail_logic_kimi-k2.5_openhands_todo-bridge`)
- **Language:** Python
- **Task:** `MehdiSaraeian/todo-bridge`
- **Agent/Model:** OpenHands with Kimi-k2.5
- **Why it failed:** The tool builds and runs perfectly without crashing. It even produces the correct file system side-effects (Side-Effect Gate Passed). However, the standard output format and informational payload completely mismatch the oracle's output semantics, resulting in a Semantic Match (SM) score of 0.

### 6. Hallucinated Workspace (`06_fail_hallucination_minimax-2.5_miniswe_parsepico`)
- **Language:** Go
- **Task:** `drpaneas/parsepico`
- **Agent/Model:** Mini-SWE-Agent with MiniMax-2.5
- **Why it failed:** Instead of working in the intended repository directory provided by the sandbox, the agent issued absolute path commands (`mkdir -p /workspace && cd /workspace`). It wrote the entire application out-of-bounds. As a result, the target repository folder contains almost nothing (only a `go.mod` file), failing the Side-Effect Gate.

---
*Note: Metadata such as `run.log`, evaluation `output.json`, and oracle `.git` files have been stripped from these preview folders to save space.*
