import os
import sys
import re
import random
from enum import Enum

# Add the root of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command combinations for folder2txt.
    The value of each enum is the generic command structure template.
    """
    BASIC = "folder2txt"
    OUTPUT = "folder2txt -o <file>"
    THRESHOLD = "folder2txt -t <MB>"
    INCLUDE_ALL = "folder2txt --include-all"
    DEBUG = "folder2txt --debug"
    OUTPUT_THRESHOLD = "folder2txt -o <file> -t <MB>"
    OUTPUT_INCLUDE_ALL = "folder2txt -o <file> --include-all"
    THRESHOLD_INCLUDE_ALL = "folder2txt -t <MB> --include-all"
    OUTPUT_DEBUG = "folder2txt -o <file> --debug"

# =====================================================================
# 2. Repository Adapter Implementation for 'folder2txt'
# =====================================================================
class Folder2txtAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Node.js environment."""
        return "node:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/thetwopct/folder2txt.git && cd folder2txt && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Copies and installs the local (agent) version of the tool.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes tool output to remove volatile data before comparison.
        The tool's primary output is a file; stdout is used for logs/errors.
        We sanitize potential volatile paths from debug logs.
        """
        # Sanitize paths that might appear in debug logs
        sanitized = re.sub(r"(/repo/repo_to_be_tested|/test_data)", "[PATH]", raw_stdout)
        # Sanitize file sizes which can be volatile
        sanitized = re.sub(r"Size: \d+(\.\d+)? [KMGT]?B", "Size: [SIZE]", sanitized)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases covering various scenarios.
        """
        cases = []
        CASES_PER_CATEGORY = 50

        def _create_test_files(is_edge_case: bool):
            """Helper to generate a dictionary of files for mounting."""
            files = {}
            num_files = random.randint(2, 4)
            for j in range(num_files):
                prefix = "subdir/" if j % 2 == 0 else ""
                filename = ""
                content = ""

                if is_edge_case:
                    choice = random.randint(0, 2)
                    if choice == 0: # File with problematic content
                        filename = f"{prefix}evil_content_{j}.txt"
                        content = FuzzHelper.get_evil_string()
                    elif choice == 1: # Empty file
                        filename = f"{prefix}empty_{j}.txt"
                        content = ""
                    else: # Binary-like file
                        filename = f"{prefix}binary_{j}.dat"
                        content = "hello\0world" + FuzzHelper.get_string(50, 100)
                else: # Normal text file
                    filename = f"{prefix}normal_file_{j}.txt"
                    content = FuzzHelper.get_string(min_len=20, max_len=100)

                if filename:
                    files[filename] = content
            return files

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # First case in each category is an edge case
                    mount_files = _create_test_files(is_edge_case)
                    
                    # Build the tool command and its arguments first
                    tool_cmd_parts = ["folder2txt"]

                    if 'OUTPUT' in category.name:
                        out_file = f"out_{FuzzHelper.get_string(5, 10)}.txt"
                        if is_edge_case:
                            # Use targeted, non-destructive but tricky filenames
                            out_file = random.choice(["../bad.txt", "new_dir/out.txt", ".hidden.txt"])
                        tool_cmd_parts.extend(["-o", out_file])

                    if 'THRESHOLD' in category.name:
                        threshold = str(FuzzHelper.get_float(0.01, 0.5, 3))
                        if is_edge_case:
                            threshold = random.choice(["-1", "not_a_number", "99999"])
                        tool_cmd_parts.extend(["-t", threshold])

                    if 'INCLUDE_ALL' in category.name:
                        tool_cmd_parts.append("--include-all")

                    if 'DEBUG' in category.name:
                        tool_cmd_parts.append("--debug")

                    tool_command = " ".join(tool_cmd_parts)
                    
                    # Prepend the directory change to run the command in the correct context
                    command = f"cd /test_data && {tool_command}"

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files,
                    ))
                except Exception as e:
                    # This ensures that if one case generation fails, it doesn't stop the whole process
                    print(f"Skipping test case generation for {category.name} due to error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = Folder2txtAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))