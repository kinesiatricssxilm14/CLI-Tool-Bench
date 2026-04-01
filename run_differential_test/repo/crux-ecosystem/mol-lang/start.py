import os
import sys
import re
from enum import Enum

# Add the parent directory to the path to import framework modules
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    RUN = "mol run <file.mol>"
    RUN_NO_TRACE = "mol run <file.mol> --no-trace"
    PARSE = "mol parse <file.mol>"
    TRANSPILE_PY = "mol transpile <file.mol>"
    TRANSPILE_JS = "mol transpile <file.mol> -t js"
    BUILD_HTML = "mol build <file.mol>"
    BUILD_JS = "mol build <file.mol> --target js"
    BUILD_NODE = "mol build <file.mol> --target node"
    TEST = "mol test <file.mol>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MolAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/crux-ecosystem/mol-lang.git && cd mol-lang && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        # Sanitize volatile output like timings, object IDs, file paths/sizes, and versions
        # 1. Sanitize pipeline trace timings (e.g., 0.1ms)
        sanitized = re.sub(r"\d+\.\d+ms", "[TIME]ms", raw_stdout)
        # 2. Sanitize trace summary (e.g., 3 steps · 0.3ms total)
        sanitized = re.sub(r"\d+ steps · .* total", "[N] steps · [TIME] total", sanitized)
        # 3. Sanitize object IDs (e.g., <Document:a3f2>)
        sanitized = re.sub(r":([a-f0-9]{4,})", ":[ID]", sanitized)
        # 4. Sanitize file sizes (e.g., 39B)
        sanitized = re.sub(r"\d+B", "[SIZE]B", sanitized)
        # 5. Sanitize line/column numbers in error messages
        sanitized = re.sub(r"line \d+, col \d+", "line [L], col [C]", sanitized)
        # 6. Sanitize file paths in error messages
        sanitized = re.sub(r'File ".*?"', 'File "[PATH]"', sanitized)
        # 7. Sanitize version numbers (e.g., 2.0.1)
        sanitized = re.sub(r"\d+\.\d+\.\d+", "[VERSION]", sanitized)
        
        return super().sanitize_stdout(sanitized)

    def _generate_mol_content(self, is_edge_case: bool, case_index: int) -> str:
        """Helper to generate content for .mol files."""
        if is_edge_case:
            # Generate syntactically incorrect or malicious content
            edge_type = case_index % 4
            if edge_type == 0:
                return FuzzHelper.get_evil_string()
            elif edge_type == 1:
                return ""  # Empty file
            elif edge_type == 2:
                return 'show "unclosed string'
            else: # edge_type == 3
                return "if true then\n  show 1\n" # Missing 'end'
        else:
            # Generate valid MOL code
            normal_type = case_index % 4
            if normal_type == 0:
                return 'show "Hello, MOL!"'
            elif normal_type == 1:
                return 'show ("  a pipeline test  " |> trim |> upper |> split(" "))'
            elif normal_type == 2:
                return 'define add(a, b)\n  return a + b\nend\nshow add(5, 10)'
            else: # normal_type == 3
                return 'test "addition" do\n  assert_eq(1 + 1, 2)\nend'

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The last case for each category is an edge case for file content
                    is_edge_case = (i == CASES_PER_CATEGORY - 1)
                    file_name = f"fuzz_{category.name.lower()}_{i}.mol"
                    content = self._generate_mol_content(is_edge_case, i)
                    
                    cmd = ""
                    file_path = f"/test_data/{file_name}"

                    if category == CmdCategory.RUN:
                        cmd = f"mol run {file_path}"
                    elif category == CmdCategory.RUN_NO_TRACE:
                        cmd = f"mol run {file_path} --no-trace"
                    elif category == CmdCategory.PARSE:
                        cmd = f"mol parse {file_path}"
                    elif category == CmdCategory.TRANSPILE_PY:
                        cmd = f"mol transpile {file_path}"
                    elif category == CmdCategory.TRANSPILE_JS:
                        cmd = f"mol transpile {file_path} -t js"
                    elif category == CmdCategory.BUILD_HTML:
                        cmd = f"mol build {file_path}"
                    elif category == CmdCategory.BUILD_JS:
                        cmd = f"mol build {file_path} --target js"
                    elif category == CmdCategory.BUILD_NODE:
                        cmd = f"mol build {file_path} --target node"
                    elif category == CmdCategory.TEST:
                        cmd = f"mol test {file_path}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception:
                    # Skip generating this test case if any error occurs
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MolAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))