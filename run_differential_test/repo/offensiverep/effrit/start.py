import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of the 'final_differential_test' directory to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine from the root of the project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for core functional commands of the 'effrit' tool.
    Focus is on the 'scan' subcommand and its various flag combinations.
    """
    SCAN_BASIC = "scan"
    SCAN_WITH_COLOR = "scan --color"
    SCAN_WITH_PROJECT_NAME = "scan --scan-project-name <name>"
    SCAN_WITH_PARALLEL_FILES = "scan --scan-parallel-files <N>"
    SCAN_ALL_FLAGS = "scan --color --scan-project-name <name> --scan-parallel-files <N>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class EffritAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the Go language stack.
        """
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile output from effrit, such as absolute paths in the table output.
        Example: /test_data/fuzz_proj_1/pkg -> [PROJECT_DIR]/pkg
        """
        sanitized = re.sub(r"/test_data/fuzz_proj_\d+", "[PROJECT_DIR]", raw_stdout)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of effrit from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/offensiverep/effrit.git && cd effrit && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent version of effrit from the local source code.
        """
        container.exec_run("mkdir -p /repo")
        # Use os.system for docker cp as it's simpler for directory copying
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo") != 0:
            raise Exception("Failed to copy agent code to container")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _generate_go_project(self, project_name: str, is_edge_case: bool, case_index: int) -> dict:
        """
        Helper method to generate a dictionary of file paths and contents for a mock Go project.
        """
        files = {}
        # A go.mod file is fundamental for a Go project.
        files[f"{project_name}/go.mod"] = f"module {project_name}"

        if is_edge_case:
            # Cycle through different types of malformed/edge project structures for robustness testing.
            edge_type = case_index % 4
            if edge_type == 0:  # Valid Go file containing an evil string in a comment and a literal
                evil_str = str(FuzzHelper.get_evil_string()).replace('\x00', '').replace('"', '\\"')
                files[f"{project_name}/main.go"] = f'package main\n\n// {evil_str}\n\nfunc main() {{\n\t_ = "{evil_str}"\n}}'
            elif edge_type == 1:  # Empty Go file
                files[f"{project_name}/pkg1/a.go"] = ""
            elif edge_type == 2:  # Circular dependency
                files[f"{project_name}/pkg1/a.go"] = f'package pkg1\nimport "{project_name}/pkg2"'
                files[f"{project_name}/pkg2/b.go"] = f'package pkg2\nimport "{project_name}/pkg1"'
            else:  # Project with no .go files
                files[f"{project_name}/README.md"] = "This project has no go files."
        else:
            # A simple, valid project structure with a clear dependency chain.
            files[f"{project_name}/main.go"] = f'package main\nimport "{project_name}/pkg1"\nfunc main() {{}}'
            files[f"{project_name}/pkg1/a.go"] = f'package pkg1\nimport "{project_name}/pkg2"\nfunc A() {{}}'
            files[f"{project_name}/pkg2/b.go"] = 'package pkg2\nimport "fmt"\nfunc B() { fmt.Println("B") }'
        
        return files

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for differential testing.
        """
        cases = []
        
        # Define a set of "evil" strings that are safe to use in shell commands
        SAFE_EVIL_STRINGS = ["", " ", "../../etc/passwd", "';--", "A" * 80, "-1", "9999999999999999"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # First case of each category is an edge case, rest are normal
                    is_edge_case = (i == 0)
                    project_name = f"fuzz_proj_{i}_{random.randint(100,999)}"

                    mount_files = self._generate_go_project(project_name, is_edge_case, i)

                    command_part = ""
                    if category == CmdCategory.SCAN_BASIC:
                        command_part = "scan"
                    
                    elif category == CmdCategory.SCAN_WITH_COLOR:
                        command_part = "scan --color"

                    elif category == CmdCategory.SCAN_WITH_PROJECT_NAME:
                        name = random.choice(SAFE_EVIL_STRINGS) if is_edge_case else f"proj_{FuzzHelper.get_string(5, 10)}"
                        command_part = f"scan --scan-project-name '{name}'"

                    elif category == CmdCategory.SCAN_WITH_PARALLEL_FILES:
                        n = FuzzHelper.get_int(-10, 0) if is_edge_case else FuzzHelper.get_int(1, 10)
                        command_part = f"scan --scan-parallel-files {n}"

                    elif category == CmdCategory.SCAN_ALL_FLAGS:
                        name = random.choice(SAFE_EVIL_STRINGS) if is_edge_case else f"proj_{FuzzHelper.get_string(5, 10)}"
                        n = FuzzHelper.get_int(-10, 0) if is_edge_case else FuzzHelper.get_int(1, 10)
                        command_part = f"scan --color --scan-project-name '{name}' --scan-parallel-files {n}"

                    # Command to run inside the project dir.
                    # After running, it sanitizes the output JSON file in-place to remove volatile absolute paths,
                    # ensuring file content diffs are meaningful.
                    # The `if/then/fi` structure makes it robust against runs that don't produce the file.
                    full_command = (
                        f"cd /test_data/{project_name} && effrit {command_part}; "
                        f"if [ -f effrit_package_data.json ]; then "
                        f"sed -i 's#\"Dir\":\\s*\"[^\"]*\"#\"Dir\": \"[REDACTED]\"#g' effrit_package_data.json; "
                        f"fi"
                    )

                    cases.append(TestCase(
                        command=full_command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Failsafe to prevent a single broken test case from stopping the whole process
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = EffritAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))