import os
import sys
import re
import json
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine


# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Defines the types of commands to be tested.
    The tool has two main modes: reading from a file and reading from stdin.
    """
    FILE_INPUT = "remove-unused-vars <file>"
    PIPE_INPUT = "cat <file> | remove-unused-vars"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Node.js environment."""
        return "node:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitize volatile parts of Node.js stack traces, such as internal
        line numbers and absolute paths, to ensure stable diffs.
        """
        # Sanitize node internal paths and line numbers, e.g., "at readFileSync (node:latest:436:20)"
        sanitized = re.sub(r'\(node:[^)]+\)', '(node:latest)', raw_stdout)
        # Sanitize volatile file paths that may differ between oracle and agent
        sanitized = re.sub(r'file:///.*/repo/repo_to_be_tested', '<AGENT_PATH>', raw_stdout)
        sanitized = re.sub(r'file:///.*/repo/remove-unused-vars', '<ORACLE_PATH>', sanitized)
        # Generalize any remaining absolute paths within the container
        sanitized = re.sub(r'(/repo|/workspace|/test_data)/[^"\s\')]+', '<PATH>', sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = (
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/webpro-nl/remove-unused-vars.git && "
            "cd remove-unused-vars && npm install && npm install -g ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent version of the tool from the local directory.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a mix of valid and edge test cases for the CLI tool.
        The tool reads a linter's JSON report and removes unused code from source files.
        """
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                mount_files = {}
                json_content = ""
                
                # Define filenames for clarity
                source_filename = f"source_{category.name.lower()}_{i}.js"
                json_filename = f"report_{category.name.lower()}_{i}.json"
                source_filepath_in_container = f"/test_data/{source_filename}"
                json_filepath_in_container = f"/test_data/{json_filename}"

                # A simple source file for testing modifications
                source_content = "const unused_var = 1;\nfunction unused_func() {}\nconst used = 2; console.log(used);"

                try:
                    # Case 0: Edge Case - Malformed/Evil JSON input
                    if i == 0:
                        json_content = FuzzHelper.get_evil_string()
                        mount_files = {json_filename: json_content}

                    # Case 1: Edge Case - Report points to a non-existent source file
                    elif i == 1:
                        report = [{
                            "filePath": "/tmp/non_existent_file.js",
                            "messages": [{"ruleId": "no-unused-vars", "line": 1, "column": 7, "endLine": 1, "endColumn": 17}]
                        }]
                        json_content = json.dumps(report)
                        mount_files = {json_filename: json_content}

                    # Case 2: Edge Case - Empty but valid JSON report
                    elif i == 2:
                        json_content = "[]"
                        # The tool should do nothing, so the source file should remain unchanged.
                        mount_files = {json_filename: json_content, source_filename: source_content}

                    # Cases 3, 4: Normal, valid cases that should trigger file modification
                    else:
                        # A correct report for the source_content
                        report = [{
                            "filePath": source_filepath_in_container,
                            "messages": [
                                {
                                    "ruleId": "no-unused-vars",
                                    "message": "'unused_var' is defined but never used.",
                                    "line": 1, "column": 7, "endLine": 1, "endColumn": 17
                                },
                                {
                                    "ruleId": "no-unused-vars",
                                    "message": "'unused_func' is defined but never used.",
                                    "line": 2, "column": 10, "endLine": 2, "endColumn": 21
                                }
                            ]
                        }]
                        json_content = json.dumps(report, indent=2)
                        mount_files = {json_filename: json_content, source_filename: source_content}

                    # Construct the command based on the category
                    cmd = ""
                    if category == CmdCategory.FILE_INPUT:
                        cmd = f"remove-unused-vars {json_filepath_in_container}"
                    elif category == CmdCategory.PIPE_INPUT:
                        cmd = f"cat {json_filepath_in_container} | remove-unused-vars"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    # Skip generating this test case if any error occurs
                    print(f"Warning: Failed to generate test case {i} for {category.name}: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))