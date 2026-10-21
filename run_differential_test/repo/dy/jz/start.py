import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of the script's location to the Python path
# to ensure that the BaseRepoAdapter and DiffTestEngine can be imported.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum
# Define the core command structures for the 'jz' CLI tool.
# =====================================================================
class CmdCategory(Enum):
    EVAL_EXPRESSION = "jz \"<expression>\""
    EVAL_FILE = "jz <file.js>"
    COMPILE_DEFAULT = "jz compile <file.js>"
    COMPILE_TO_WAT = "jz compile <file.js> --output <file.wat>"
    COMPILE_TO_WASM = "jz compile <file.js> --output <file.wasm>"
    RUN_FILE = "jz run <file.js>"

# =====================================================================
# 2. Repository Adapter Implementation for 'jz'
# =====================================================================
class JzAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image. 'jz' is a Node.js tool.
        """
        return "node:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of 'jz' from its Git repository.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/dy/jz.git && cd jz && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Copies the local agent code into the container and installs it globally.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Cleans the command output to remove volatile information like file paths
        and source map comments, ensuring stable diffs.
        """
        # Remove source map comments, e.g., ";;@ C:\Users\...\program.js:1:20"
        sanitized = re.sub(r';;@.*', '', raw_stdout)
        # Normalize file paths in error messages
        sanitized = re.sub(r'in .*?fuzz_test_\d+\.js', 'in [fuzz_file.js]', sanitized)
        # Normalize line/column numbers in error messages, e.g., "at 1:5" -> "at L:C"
        sanitized = re.sub(r'at \d+:\d+', 'at L:C', sanitized)
        # Call parent sanitizer to remove ANSI color codes
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator for 'jz'
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    
                    js_content = ""
                    # Generate JS content: valid for normal cases, potentially invalid for edge cases.
                    if is_edge_case:
                        js_content = FuzzHelper.get_evil_string()
                    else:
                        # Generate simple, valid JS for normal cases based on README examples.
                        js_options = [
                            f"{FuzzHelper.get_int(-100, 100)} {random.choice(['+', '-', '*', '/'])} {FuzzHelper.get_int(1, 100)}",
                            f"export const result = (a, b) => a {random.choice(['+', '-', '*'])} b;",
                            "let { sin, PI } = Math; export let sine = (t) => sin(t * PI * 2);",
                            f"const val = {FuzzHelper.get_int()}; export const getVal = () => val;"
                        ]
                        js_content = random.choice(js_options)

                    cmd = ""
                    mount_files = {}

                    if category == CmdCategory.EVAL_EXPRESSION:
                        if is_edge_case:
                            expr = FuzzHelper.get_evil_string().replace('"', '\\"')
                        else:
                            expr = f"{FuzzHelper.get_int(-100, 100)} {random.choice(['+', '-', '*'])} {FuzzHelper.get_int(-100, 100)}"
                        cmd = f"jz \"{expr}\""

                    else: # File-based commands
                        file_name = f"fuzz_test_{i}.js"
                        mount_files = {file_name: js_content}
                        input_path = f"/test_data/{file_name}"

                        if category == CmdCategory.EVAL_FILE:
                            cmd = f"jz {input_path}"
                        
                        elif category == CmdCategory.RUN_FILE:
                            cmd = f"jz run {input_path}"

                        elif category == CmdCategory.COMPILE_DEFAULT:
                            cmd = f"jz compile {input_path}"

                        elif category == CmdCategory.COMPILE_TO_WAT or category == CmdCategory.COMPILE_TO_WASM:
                            ext = ".wat" if category == CmdCategory.COMPILE_TO_WAT else ".wasm"
                            
                            if is_edge_case:
                                # For edge cases, use a malicious but path-like string for the output file.
                                # Using a full evil string is often invalid syntax for a CLI flag.
                                evil_paths = ["../../etc/passwd", "/dev/null", f"long_name_{'a'*80}{ext}"]
                                output_path = random.choice(evil_paths)
                            else:
                                output_file = f"fuzz_out_{i}{ext}"
                                output_path = f"/test_data/{output_file}"
                            
                            cmd = f"jz compile {input_path} -o {output_path}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # If case generation fails for any reason, just skip it to not block the whole process.
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = JzAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))