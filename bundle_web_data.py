import json
from pathlib import Path

from excluded_repos import EXCLUDED_REPO_SET

repo_dir = Path(__file__).resolve().parent

data = {
    "metadata": [],
    "tasks": {}
}

# 1. Load results_metadata_with_sp.json
metadata_path = repo_dir / "results_metadata_with_sp.json"
if metadata_path.exists():
    with metadata_path.open("r", encoding="utf-8") as f:
        data["metadata"] = [
            row for row in json.load(f) if row.get("instance_id") not in EXCLUDED_REPO_SET
        ]

# 2. Extract Task Prompts and Test Scripts
prompts_dir = repo_dir / "agent_prompt"
tests_dir = repo_dir / "run_differential_test" / "repo"

print("Extracting tasks...")
for prompt_file in prompts_dir.glob("*/*/agent_prompt.txt"):
    owner = prompt_file.parent.parent.name
    repo = prompt_file.parent.name
    repo_id = f"{owner}/{repo}"
    if repo_id in EXCLUDED_REPO_SET:
        continue

    with prompt_file.open("r", encoding="utf-8", errors="ignore") as f:
        prompt_content = f.read()

    test_file = tests_dir / owner / repo / "start.py"
    test_content = "Test script not found."
    if test_file.exists():
        with test_file.open("r", encoding="utf-8", errors="ignore") as f:
            test_content = f.read()
            
    data["tasks"][repo_id] = {
        "prompt": prompt_content,
        "test_script": test_content
    }

print(f"Loaded {len(data['tasks'])} tasks.")

# Write it out as a JS file so it can be loaded directly without CORS/Fetch issues
js_output = repo_dir / "web_explorer_data.js"
with js_output.open("w", encoding="utf-8") as f:
    f.write("window.ARTIFACT_DATA = ")
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    f.write(";")

print(f"Data bundled to {js_output} ({js_output.stat().st_size / 1024 / 1024:.2f} MB)")
