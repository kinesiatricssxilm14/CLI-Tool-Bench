import os
import sys
import re
from enum import Enum
import random
import string

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
    Enumerates the different command structures to be tested.
    The value of each enum member is a generic string representation
    of the command, which is used for categorizing test results.
    """
    FROM_FILE = "subwords -i <file>"
    FROM_FILE_LIMIT = "subwords -i <file> -limit <N>"
    FROM_FILE_STATS = "subwords -i <file> -stats"
    FROM_FILE_LIMIT_STATS = "subwords -i <file> -limit <N> -stats"
    FROM_STDIN = "cat <file> | subwords"
    FROM_STDIN_LIMIT = "cat <file> | subwords -limit <N>"
    FROM_STDIN_STATS = "cat <file> | subwords -stats"
    FROM_STDIN_LIMIT_STATS = "cat <file> | subwords -limit <N> -stats"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class SubwordsAdapter(BaseRepoAdapter):
    """
    Adapter for the 'subwords' CLI tool.
    """
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/bebiksior/subwords.git && cd subwords && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        # Use docker cp to copy the local agent code into the container
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the raw output of the CLI tool to remove non-deterministic elements.
        For 'subwords', words with the same frequency might be printed in a random
        order. Sorting the output lines alphabetically ensures consistency.
        """
        stdout = super().sanitize_stdout(raw_stdout)
        lines = stdout.strip().split('\n')
        # Filter out empty lines that might result from splitting
        lines = [line for line in lines if line.strip()]
        # Sort lines to ensure deterministic output
        lines.sort()
        return '\n'.join(lines)

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        # Generate 1 edge case and 4 normal cases per category
        EDGE_CASE_COUNT = 1

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i < EDGE_CASE_COUNT)
                    
                    file_name = f"fuzz_{category.name.lower()}_{i}.txt"
                    input_file_path = f"/test_data/{file_name}"

                    # 1. Generate Input File Content
                    if is_edge_case:
                        # For edge cases, use an evil string or an empty file
                        content = FuzzHelper.get_evil_string() if i % 2 == 0 else ""
                    else:
                        # For normal cases, generate a valid list of subdomains
                        content = FuzzHelper.get_subdomains_content(min_lines=10, max_lines=50)

                    # 2. Assemble Command Parts
                    parts = []
                    
                    if "-limit <N>" in category.value:
                        if is_edge_case:
                            # Generate invalid or edge-case values for the integer limit
                            limit_val_choices = [
                                str(FuzzHelper.get_int(-100, -1)), # Negative number
                                "0",                               # Valid edge case (all)
                                FuzzHelper.get_string(3, 8, chars=string.ascii_letters), # Non-numeric string
                                "99999999999999999999999999999"    # Out-of-range integer
                            ]
                            limit_val = random.choice(limit_val_choices)
                        else:
                            # Generate a valid limit
                            limit_val = str(FuzzHelper.get_int(1, 50))
                        parts.append(f"-limit {limit_val}")

                    if "-stats" in category.value:
                        parts.append("-stats")
                    
                    # Shuffle flag order for robustness
                    random.shuffle(parts)
                    args_str = " ".join(parts)

                    # 3. Construct Final Command
                    if "cat <file>" in category.value:
                        cmd = f"cat {input_file_path} | subwords {args_str}".strip()
                    else:
                        cmd = f"subwords -i {input_file_path} {args_str}".strip()

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    # Log and skip if a single test case generation fails
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")
                    continue
        return cases

# =====================================================================
# 3. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = SubwordsAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))