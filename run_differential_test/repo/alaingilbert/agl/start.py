import os
import sys
import re
from enum import Enum
import random

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional commands of the 'agl' CLI tool.
    The value of each enum member is a generic template string representing the command structure.
    """
    COMPILE_TO_STDOUT = "agl <file>"
    RUN = "agl run <file>"
    BUILD = "agl build <file>"
    CLEAN = "agl clean"
    # VERSION = "agl version"
    # HELP = "agl help [command]"
    # INVALID_USAGE = "agl <invalid>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class AglAdapter(BaseRepoAdapter):
    """
    Adapter for the 'agl' CLI tool, defining installation and test generation logic.
    """
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of 'agl' from its GitHub repository.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/alaingilbert/agl.git && cd agl && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Copies the local 'agent' code into the container and installs it.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile information from the tool's output, such as file paths and line numbers
        in compiler error messages, to ensure stable diffing.
        """
        # Sanitize compiler error messages like "test.agl:5:3: error..."
        sanitized = re.sub(r'\S+\.agl:\d+:\d+', 'FILE:LINE:COL', raw_stdout)
        # Sanitize absolute file paths that might appear in error messages
        sanitized = re.sub(r'(/tmp/|/test_data/)\S+\.agl', 'FILE_PATH', sanitized)
        # Call super to remove standard noise like ANSI color codes
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def _generate_agl_content(self, is_edge_case: bool) -> str:
        """
        Helper function to generate content for .agl files.
        Generates valid code for normal cases and malicious/boundary content for edge cases.
        """
        if is_edge_case:
            choice = random.random()
            if choice < 0.4:
                # Raw evil string, likely a parse error
                return FuzzHelper.get_evil_string()
            elif choice < 0.8:
                # Evil string inside a valid string literal, requires escaping quotes
                evil_str = FuzzHelper.get_evil_string().replace("\\", "\\\\").replace("\"", "\\\"")
                return f'package main\nfunc main() {{ print("{evil_str}") }}'
            else:
                # Empty content
                return ""
        
        # For normal cases, use a variety of valid, fuzzed, or near-valid AGL code snippets
        snippets = [
            'package main\nfunc main() { print("Hello, Differential Testing!") }',
            f'package main\nfunc main() {{ print({FuzzHelper.get_int(-100, 100)} + {FuzzHelper.get_int(-100, 100)}) }}',
            f'package main\nfunc main() {{ for i in 0..{random.randint(2, 5)} {{ print(i) }} }}',
            'package main\nfunc main() { arr := []int{1, 2, 3, 4, 5}\nsum := arr.Sum()\nprint(sum) }',
            'package main\nfunc getInt() int! { return Ok(100) }\nfunc main() { num := getInt()!\nprint(num) }',
            # Deliberate syntax error to test error reporting
            'package main\nfunc main() { print(some_undefined_variable) }',
            # Deliberate type error
            'package main\nfunc main() { var x int = "hello" }',
            f'package main\nfunc main() {{ name := "{FuzzHelper.get_string(3, 8)}"\nprint(t"Hello, {{name}}") }}',
        ]
        return random.choice(snippets)

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a comprehensive list of test cases covering all command categories.
        Each category includes both normal functional tests and robustness/edge case tests.
        """
        cases = []
        CASES_PER_CATEGORY = 50

        # --- File-based commands ---
        file_based_categories = [CmdCategory.COMPILE_TO_STDOUT, CmdCategory.RUN, CmdCategory.BUILD]
        for category in file_based_categories:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Case 0: Test with a non-existent file
                    if i == 0:
                        cmd = category.value.replace("<file>", f"/test_data/non_existent_{category.name.lower()}_{i}.agl")
                        cases.append(TestCase(command=cmd, category=category.value))
                        continue

                    # Case 1: Edge case content. Other cases: Normal/varied content.
                    is_edge = (i == 1)
                    content = self._generate_agl_content(is_edge_case=is_edge)
                    file_name = f"test_{category.name.lower()}_{i}.agl"
                    cmd = category.value.replace("<file>", f"/test_data/{file_name}")
                    
                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception:
                    continue

        # --- Standalone & Sequence commands ---
        # VERSION commands
        # for cmd_str in ["agl version", "agl --version", "agl -v"]:
        #     cases.append(TestCase(command=cmd_str, category=CmdCategory.VERSION.value))

        # HELP commands
        # for cmd_str in ["agl help", "agl -h", "agl --help", "agl help run", "agl help build"]:
        #     cases.append(TestCase(command=cmd_str, category=CmdCategory.HELP.value))

        # CLEAN command (tested in sequence with build)
        cases.append(TestCase(
            command="agl clean",
            category=CmdCategory.CLEAN.value,
            prep_script="agl build /test_data/clean_target.agl",
            mount_files={"clean_target.agl": 'package main\nfunc main(){}'}
        ))
        # Test clean when there's nothing to clean
        cases.append(TestCase(command="agl clean", category=CmdCategory.CLEAN.value))

        # INVALID USAGE commands
        # for _ in range(CASES_PER_CATEGORY):
        #     try:
        #         invalid_cmd = random.choice([
        #             f"agl {FuzzHelper.get_string(5, 10)}",
        #             f"agl run --invalid-opt={FuzzHelper.get_int()}",
        #             "agl build", # Missing required argument
        #             "agl" # No subcommand
        #         ])
        #         cases.append(TestCase(command=invalid_cmd, category=CmdCategory.INVALID_USAGE.value))
        #     except Exception:
        #         continue
                
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = AglAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))