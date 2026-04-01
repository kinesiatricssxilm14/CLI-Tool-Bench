import os
import sys
import re
from enum import Enum
import random

# Add the project's root directory to the Python path to allow importing framework modules.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command structures to be tested for gomi-rename.
    Each value is a generic template representing a specific usage pattern.
    """
    RENAME_SINGLE_FILE = "gomi-rename <filepath>"
    RENAME_MULTI_FILE = "gomi-rename <filepath...>"
    RENAME_WITH_NUMBER = "gomi-rename --number <N> <filepath>"
    RENAME_WITH_NUMBER_MULTI = "gomi-rename --number <N> <filepath...>"
    DRYRUN_SINGLE_FILE = "gomi-rename --dryrun <filepath>"
    DRYRUN_MULTI_FILE = "gomi-rename --dryrun <filepath...>"
    DRYRUN_WITH_NUMBER = "gomi-rename --dryrun --number <N> <filepath>"
    DRYRUN_WITH_NUMBER_MULTI = "gomi-rename --dryrun --number <N> <filepath...>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GomiRenameAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Clones and installs the oracle (original) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/sweatyvise/gomi-rename.git && cd gomi-rename && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the agent (local) version of the tool."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the stdout to make it deterministic for comparison.
        The tool generates random filenames, which must be normalized.
        Example: "test.txt -> 💩test.txt" becomes "test.txt -> [RENAMED]"
        """
        sanitized_lines = []
        for line in raw_stdout.splitlines():
            # Replace the randomly generated new filename with a static placeholder
            sanitized_line = re.sub(r' -> .*$', ' -> [RENAMED]', line)
            sanitized_lines.append(sanitized_line)
        
        sanitized_output = "\n".join(sanitized_lines)
        # Call parent sanitizer to remove ANSI codes etc.
        return super().sanitize_stdout(sanitized_output)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        DATA_DIR = "/test_data"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == CASES_PER_CATEGORY - 1) # Make the last case an edge case
                    mount_files = {}
                    
                    # --- File Generation ---
                    num_files = 1
                    if "MULTI" in category.name:
                        num_files = random.randint(2, 3)
                    
                    filepaths_to_process = []
                    for j in range(num_files):
                        # For some edge cases, use a non-existent file path to test error handling
                        if is_edge_case and random.random() < 0.3:
                            filepaths_to_process.append(f"{DATA_DIR}/non_existent_{i}_{j}.tmp")
                            continue

                        # Generate filename
                        if is_edge_case:
                            fname_base = FuzzHelper.get_evil_string()
                            # Sanitize filename to be valid on most filesystems, avoiding framework errors
                            fname_safe = re.sub(r'[\\/:\*\?"<>\|\x00]', '_', fname_base)[:50] + f"_{i}_{j}.txt"
                            if not fname_safe or fname_safe.startswith('_'): 
                                fname_safe = f"valid_name_{i}_{j}.txt"
                        else:
                            fname_safe = f"test_file_{i}_{j}.txt"
                        
                        content = "This is a test file."
                        mount_files[fname_safe] = content
                        filepaths_to_process.append(f"{DATA_DIR}/{fname_safe}")

                    # --- Command Assembly ---
                    command_parts = ["gomi-rename"]
                    flags_to_add = []
                    
                    # Handle --number flag
                    if "NUMBER" in category.name:
                        if is_edge_case:
                            # Inject invalid or boundary values for --number
                            number_val = random.choice([
                                FuzzHelper.get_int(-10, 0), # Negative or zero
                                "'abc'", # Non-numeric string
                                "99999999999999999999999999999" # Large number
                            ])
                        else:
                            number_val = FuzzHelper.get_int(1, 10)
                        flags_to_add.append(f"--number {number_val}")

                    # Handle --dryrun flag
                    if "DRYRUN" in category.name:
                        flags_to_add.append("--dryrun")
                    
                    # Shuffle flags to test for order independence
                    random.shuffle(flags_to_add)
                    command_parts.extend(flags_to_add)
                    
                    # Add file paths, ensuring they are quoted to handle special characters
                    for p in filepaths_to_process:
                        command_parts.append(f"'{p}'")

                    command = " ".join(command_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Skip case generation if any error occurs, ensuring the process continues
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GomiRenameAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))