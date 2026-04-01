import os
import sys
import re
import random
from enum import Enum
from typing import List

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for gomsort command categories.
    The value is the generic command structure template.
    <path> can be a file or a directory.
    """
    BASIC = "gomsort <path>"
    DRY_RUN = "gomsort -n <path>"
    VERBOSE = "gomsort -v <path>"
    DRY_RUN_VERBOSE = "gomsort -n -v <path>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GomsortAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitize output to remove volatile information like file paths.
        """
        # Replace absolute paths to agent/oracle code to be generic
        sanitized = re.sub(r'/[\w/.-]+/repo/repo_to_be_tested', '<AGENT_PATH>', raw_stdout)
        sanitized = re.sub(r'/[\w/.-]+/repo/gomsort', '<ORACLE_PATH>', raw_stdout)
        # Replace temporary paths
        sanitized = re.sub(r'/tmp/[\w/.-]+', '<TMP_PATH>', sanitized)
        # Generalize filenames in output messages (e.g., "Rewriting main.go")
        sanitized = re.sub(r'[\w-]+\.go', '<FILENAME>.go', sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/borovikovd/gomsort.git && cd gomsort && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        # Per rule 1, os.system is used for docker cp without a return code check.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _generate_go_file_content(self, shuffled: bool = True) -> str:
        """Helper to generate Go code with methods that can be sorted."""
        header = "package main\n\nimport \"fmt\"\n\ntype Sorter struct{}\n"
        methods = [
            "func (s *Sorter) publicMethodC() { s.privateHelperA() }",
            "func (s *Sorter) privateHelperA() { fmt.Println(\"helper A\") }",
            "func (s *Sorter) PublicMethodA() { s.privateHelperB() }",
            "func (s *Sorter) privateHelperB() { s.privateHelperA() }",
            "func (s *Sorter) PublicMethodB() { fmt.Println(\"B\") }",
        ]
        if shuffled:
            random.shuffle(methods)
        return header + "\n\n".join(methods)

    def generate_test_cases(self) -> List[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    mount_files = {}
                    target_path = ""
                    
                    # Use index to create a deterministic variety of cases
                    case_type = i % 5

                    if case_type == 0:
                        # Valid case: single well-formed file
                        target_path = "main.go"
                        mount_files[target_path] = self._generate_go_file_content()
                    elif case_type == 1:
                        # Valid case: directory with multiple go files
                        target_path = "."
                        mount_files["file1.go"] = self._generate_go_file_content()
                        mount_files["file2.go"] = self._generate_go_file_content(shuffled=False)
                    elif case_type == 2:
                        # Valid case: directory with mixed file types (gomsort should ignore non-go)
                        target_path = "."
                        mount_files["good.go"] = self._generate_go_file_content()
                        mount_files["not_go.txt"] = "this is not go code"
                    elif case_type == 3:
                        # Edge case: file with evil/malformed content
                        target_path = "evil.go"
                        mount_files[target_path] = FuzzHelper.get_evil_string()
                    else: # case_type == 4
                        # Edge case: empty go file
                        target_path = "empty.go"
                        mount_files[target_path] = ""

                    # Assemble command based on category
                    options = ""
                    if category == CmdCategory.DRY_RUN:
                        options = "-n"
                    elif category == CmdCategory.VERBOSE:
                        options = "-v"
                    elif category == CmdCategory.DRY_RUN_VERBOSE:
                        flags = ["-n", "-v"]
                        random.shuffle(flags)
                        options = " ".join(flags)

                    # Build command, ensuring parts are properly spaced
                    cmd_parts = ["cd /test_data && gomsort"]
                    if options:
                        cmd_parts.append(options)
                    cmd_parts.append(target_path)
                    cmd = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Failsafe to prevent crashing the entire test generation
                    continue
        return cases

# =====================================================================
# 3. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GomsortAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))