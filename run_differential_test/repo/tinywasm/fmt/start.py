import os
import sys
import re
import random
from enum import Enum

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command structures of the 'fmt' tool.
    """
    BASIC = "fmt <file>"
    WIDTH = "fmt -w <WIDTH> <file>"
    CROWN_MARGIN = "fmt -c <file>"
    PREFIX = "fmt -p <STRING> <file>"
    SPLIT_ONLY = "fmt -s <file>"
    TAGGED_PARAGRAPH = "fmt -t <file>"
    UNIFORM_SPACING = "fmt -u <file>"
    GOAL = "fmt -g <WIDTH> <file>"
    WIDTH_AND_CROWN = "fmt -w <WIDTH> -c <file>"
    WIDTH_AND_SPLIT = "fmt -w <WIDTH> -s <file>"
    WIDTH_AND_UNIFORM = "fmt -w <WIDTH> -u <file>"
    WIDTH_AND_GOAL = "fmt -w <WIDTH> -g <WIDTH> <file>"
    CROWN_AND_UNIFORM = "fmt -c -u <file>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class FmtAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool from its Git repository."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/tinywasm/fmt.git && cd fmt && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            # The base image (golang:latest) contains coreutils, so `fmt` command should be available.
            # This failure is expected as the repo is a library, not a CLI tool.
            # We proceed, relying on the system's `fmt`.
            print("Warning: Oracle 'go install' for 'tinywasm/fmt' did not produce an executable as expected. Falling back to system 'fmt'.")


    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent version of the tool from the local path."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent 'go install' failed. This might be expected if it's a library. The test will rely on system 'fmt'.")

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    file_name = f"fuzz_input_{category.name.lower()}_{i}.txt"
                    is_edge_case = (i == 0)

                    # A. Generate input file content
                    if is_edge_case:
                        content_type = random.choice(['empty', 'whitespace', 'long_line', 'evil', 'long_word'])
                        if content_type == 'empty':
                            content = ""
                        elif content_type == 'whitespace':
                            content = " \t\n \r\n\t " * 10
                        elif content_type == 'long_line':
                            content = "word " * 100
                        elif content_type == 'long_word':
                            content = "a" * 200
                        else: # evil
                            content = FuzzHelper.get_evil_string()
                    else:
                        # Normal content: multiple paragraphs of random text
                        content = "\n\n".join([
                            FuzzHelper.get_string(min_len=50, max_len=200)
                            for _ in range(random.randint(2, 4))
                        ])

                    # B. Build command arguments based on category
                    options = []
                    width = FuzzHelper.get_int(20, 120)

                    # Handle options that require a value
                    if "<WIDTH>" in category.value:
                        width_val = random.choice([-1, 0, 99999]) if is_edge_case else width
                        options.append(f"-w {width_val}")

                    if "-g <WIDTH>" in category.value:
                        goal_val = random.choice([-1, 0, width + 50]) if is_edge_case else int(width * 0.9)
                        options.append(f"-g {goal_val}")

                    if "<STRING>" in category.value:
                        prefix_val = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(1, 8)
                        
                        # Make the test meaningful by actually adding the prefix to some lines
                        lines = content.split('\n')
                        if lines and prefix_val:
                            num_lines_to_prefix = random.randint(1, len(lines))
                            lines_to_prefix = random.sample(range(len(lines)), num_lines_to_prefix)
                            for line_idx in lines_to_prefix:
                                lines[line_idx] = prefix_val + lines[line_idx]
                            content = '\n'.join(lines)
                        
                        # Properly escape the prefix for the shell command
                        safe_prefix = prefix_val.replace("'", "'\\''")
                        options.append(f"-p '{safe_prefix}'")

                    # Handle flag options
                    if "-c" in category.value and "-w" not in category.value: options.append("-c")
                    if "-s" in category.value and "-w" not in category.value: options.append("-s")
                    if "-t" in category.value: options.append("-t")
                    if "-u" in category.value and "-w" not in category.value: options.append("-u")
                    
                    # Handle combined flags
                    if category == CmdCategory.WIDTH_AND_CROWN: options.append("-c")
                    if category == CmdCategory.WIDTH_AND_SPLIT: options.append("-s")
                    if category == CmdCategory.WIDTH_AND_UNIFORM: options.append("-u")
                    if category == CmdCategory.CROWN_AND_UNIFORM: options.extend(["-c", "-u"])


                    # C. Assemble final command
                    cmd = f"fmt {' '.join(options)} /test_data/{file_name}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    print(f"Skipping test case generation for {category.name} due to error: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = FmtAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))