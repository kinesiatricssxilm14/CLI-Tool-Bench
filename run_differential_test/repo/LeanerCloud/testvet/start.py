import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of the script's location to the Python path
# to be able to import BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 0. Global Settings
# =====================================================================
CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum
# Abstract core commands and their meaningful combinations.
# The value of the enum MUST be the generic structure template string.
# =====================================================================
class CmdCategory(Enum):
    """Enumerates the command-line argument combinations for testvet."""
    # Basic analysis with default settings
    BASIC = "testvet -dir <path>"
    # Test individual flags
    EXCLUDE_PRIVATE = "testvet -dir <path> -exclude-private"
    VERBOSE = "testvet -dir <path> -verbose"
    THRESHOLD = "testvet -dir <path> -threshold <N>"
    NO_COVERAGE = "testvet -dir <path> -use-coverage=false"
    # Test combined flags
    EXCLUDE_PRIVATE_THRESHOLD = "testvet -dir <path> -exclude-private -threshold <N>"
    ALL_FLAGS = "testvet -dir <path> -exclude-private -verbose -threshold <N>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class TestvetAdapter(BaseRepoAdapter):
    """
    Adapter for the testvet CLI tool.
    Handles installation, test case generation, and output sanitization.
    """

    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the oracle (baseline) version of testvet from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/LeanerCloud/testvet.git && cd testvet && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent (local) version of testvet into the container.
        """
        container.exec_run("mkdir -p /repo")
        # The DiffTestEngine now handles the copy, but we ensure the directory exists.
        # A robust implementation would check if the copy is needed, but for now, we follow the old logic's intent.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the stdout to remove volatile information like paths, line numbers,
        and coverage percentages, ensuring stable diffs.
        """
        # Normalize project path
        sanitized = re.sub(r"Project: .*", "Project: <path>", raw_stdout)
        # Normalize file paths and line numbers
        sanitized = re.sub(r"([a-zA-Z0-9/._-]+(\.go|_test\.go)):", "<file>:", sanitized)
        sanitized = re.sub(r"Current file:\s+[a-zA-Z0-9/._-]+", "Current file: <file>", sanitized)
        sanitized = re.sub(r"Expected file:\s+[a-zA-Z0-9/._-]+", "Expected file: <file>", sanitized)
        sanitized = re.sub(r"Line \d+", "Line <num>", sanitized)
        sanitized = re.sub(r"\(line \d+\):", "(line <num>):", sanitized)
        # Normalize coverage-related numbers
        sanitized = re.sub(r"\(\d+\.\d+%\)", "(<coverage>%)", sanitized)
        sanitized = re.sub(r"below \d+\.\d+%", "below <threshold>%", sanitized)
        # Normalize summary line
        sanitized = re.sub(r"Summary:.*", "Summary: <...>", sanitized, flags=re.IGNORECASE)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for differential testing.
        It creates a small Go project and fuzzes both the project files and
        the CLI arguments.
        """
        cases = []
        CONTAINER_PROJ_PATH = "/test_data/test_proj"
        MOUNT_PROJ_PATH = "test_proj"

        # A minimal but valid Go project structure for testing
        base_files = {
            f"{MOUNT_PROJ_PATH}/go.mod": "module testvet-fuzz-project\n\ngo 1.18\n",
            f"{MOUNT_PROJ_PATH}/main.go": "package main\n\nfunc UnusedMainFunc() {}\nfunc main() {}\n",
            f"{MOUNT_PROJ_PATH}/utils/helpers.go": "package utils\n\nfunc ExportedUtil() int { return 1 }\nfunc unexportedUtil() int { return 2 }\n",
            f"{MOUNT_PROJ_PATH}/utils/helpers_test.go": "package utils\n\nimport \"testing\"\n\nfunc TestExportedUtil(t *testing.T) {\n\tif ExportedUtil() != 1 {\n\t\tt.Errorf(\"error\")\n\t}\n}\n",
            f"{MOUNT_PROJ_PATH}/handlers/user.go": "package handlers\n\nfunc GetUser() string { return \"user\" }\n",
            f"{MOUNT_PROJ_PATH}/other/other_test.go": "package other\n\nimport (\n\t\"testing\"\n\t\"testvet-fuzz-project/handlers\"\n)\n\nfunc TestMisplaced(t *testing.T) {\n\tif handlers.GetUser() != \"user\" {\n\t\tt.Errorf(\"error\")\n\t}\n}\n",
        }

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i > 0)
                    mount_files = base_files.copy()
                    args = []

                    # --- Argument Generation ---

                    # 1. Directory argument (-dir)
                    dir_arg = CONTAINER_PROJ_PATH
                    if is_edge_case and random.random() < 0.3:
                        dir_arg = random.choice([
                            FuzzHelper.get_filepath(absolute=True), # Non-existent path
                            ".",
                            "/",
                            FuzzHelper.get_evil_string().replace(" ", "") # Junk string
                        ])
                    args.append(f"-dir {dir_arg}")

                    # 2. Boolean flags
                    if category in [CmdCategory.EXCLUDE_PRIVATE, CmdCategory.EXCLUDE_PRIVATE_THRESHOLD, CmdCategory.ALL_FLAGS]:
                        args.append("-exclude-private")
                    if category in [CmdCategory.VERBOSE, CmdCategory.ALL_FLAGS]:
                        args.append("-verbose")

                    # 3. Threshold argument (-threshold)
                    if category in [CmdCategory.THRESHOLD, CmdCategory.EXCLUDE_PRIVATE_THRESHOLD, CmdCategory.ALL_FLAGS]:
                        if is_edge_case:
                            # Use problematic, but still numeric, values
                            threshold_val = random.choice([
                                FuzzHelper.get_int(-100, -1),
                                FuzzHelper.get_int(101, 500),
                                FuzzHelper.get_float(-10.0, 110.0, 4)
                            ])
                        else:
                            # Use a valid, sensible value for the base case
                            threshold_val = FuzzHelper.get_int(10, 90)
                        args.append(f"-threshold {threshold_val}")

                    # 4. Coverage argument (-use-coverage)
                    if category == CmdCategory.NO_COVERAGE:
                        use_coverage_val = "false"
                        if is_edge_case:
                            # Use other boolean-like strings or junk
                            use_coverage_val = random.choice([
                                FuzzHelper.get_boolean_str(),
                                "yes", "no",
                                FuzzHelper.get_string(3, 8)
                            ])
                        args.append(f"-use-coverage={use_coverage_val}")

                    # --- File Content Fuzzing ---
                    if is_edge_case and random.random() < 0.2:
                        # Corrupt a random file with an evil string
                        file_to_corrupt = random.choice(list(mount_files.keys()))
                        mount_files[file_to_corrupt] = FuzzHelper.get_evil_string()
                    elif is_edge_case and random.random() < 0.1:
                        # Make all files empty
                        for k in mount_files:
                            mount_files[k] = ""

                    # --- Command Assembly ---
                    random.shuffle(args)
                    command = f"testvet {' '.join(args)}"

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        prep_script="",  # prep_script is not needed; engine handles dir creation
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate a test case for category {category.name}. Error: {e}")
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = TestvetAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))