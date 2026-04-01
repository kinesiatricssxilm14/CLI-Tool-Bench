import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of 'final_differential_test' to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 0. Constants
# =====================================================================
CASES_PER_CATEGORY = 50
REPO_FULL_NAME = "tawandakembo/code-collator"
REPO_NAME = "code-collator"

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line argument combinations for code-collator.
    The value of each enum member is a generic template string representing the command structure.
    """
    PATH_ONLY = "code-collator --path <path>"
    PATH_AND_OUTPUT = "code-collator --path <path> --output <output>"
    PATH_AND_COMMENTS_OFF = "code-collator --path <path> --comments off"
    PATH_AND_COMMENTS_ON = "code-collator --path <path> --comments on"
    PATH_OUTPUT_COMMENTS_OFF = "code-collator --path <path> --output <output> --comments off"
    PATH_OUTPUT_COMMENTS_ON = "code-collator --path <path> --output <output> --comments on"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CodeCollatorAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle (original) version of the tool in the container."""
        cmd = f"mkdir -p /repo && cd /repo && git clone https://github.com/{REPO_FULL_NAME}.git && cd {REPO_NAME} && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent (local) version of the tool in the container."""
        container.exec_run("mkdir -p /repo")
        # Per Rule 1, copy the local agent repo into the container's /repo directory
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo") != 0:
            raise Exception("Failed to copy agent code to container")
        # The agent code is now at /repo/repo_to_be_tested
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for differential testing.
        This function creates a variety of file structures and command arguments,
        including normal and edge cases.
        """
        cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make the first case of each category an edge case, the rest normal
                    is_edge_case = (i == 0)

                    # --- 1. Define file paths and directories ---
                    src_dir_name = f"fuzz_src_{category.name.lower()}_{i}"
                    src_dir_path_container = f"/test_data/{src_dir_name}"
                    output_filename = f"output_{category.name.lower()}_{i}.md"
                    output_filepath_container = f"/test_data/{output_filename}"

                    # --- 2. Generate a random source tree to collate ---
                    mount_files = {}
                    num_files = FuzzHelper.get_int(1, 5)

                    if random.random() < 0.4:
                        mount_files[f"{src_dir_name}/.gitignore"] = "*.log\nbuild/"
                        mount_files[f"{src_dir_name}/ignored_file.log"] = "This content should not appear."
                        mount_files[f"{src_dir_name}/build/ignored.txt"] = "This dir should be ignored."

                    for j in range(num_files):
                        ext = random.choice(['.py', '.js', '.txt', '.md'])
                        dir_prefix = random.choice(['', 'app/', 'utils/'])
                        
                        filename_base = f"file_{j}"
                        if is_edge_case and j == 0:
                            raw_evil = FuzzHelper.get_evil_string()
                            # Sanitize to prevent creating invalid file paths in the test framework
                            sanitized_evil = re.sub(r'[\x00/\\ \t\n\r]', '_', raw_evil)
                            filename_base = sanitized_evil or "sanitized_empty_name"
                        
                        filepath = f"{src_dir_name}/{dir_prefix}{filename_base}{ext}"

                        content = ""
                        if is_edge_case:
                            content = FuzzHelper.get_evil_string()
                        else:
                            if ext == '.py':
                                content = "# Python comment\ndef main():\n  print('Hello from Python')\n"
                            elif ext == '.js':
                                content = "// JS comment\nconsole.log('Hello from JS');"
                            else:
                                content = FuzzHelper.get_string(min_len=20, max_len=100)
                        
                        # IMPORTANT: Remove null bytes from content to prevent file writing errors
                        if isinstance(content, str):
                            content = content.replace('\x00', '')
                        
                        mount_files[filepath] = content

                    # --- 3. Assemble the command based on the category ---
                    command = category.value
                    
                    path_val = src_dir_path_container
                    output_val = output_filepath_container
                    
                    if is_edge_case:
                        # For edge cases, replace path/output with potentially problematic but sanitized strings
                        if "<path>" in command and random.random() < 0.5:
                            # Use an evil string, but sanitize it to avoid breaking the command itself
                            # Remove null bytes, and replace quotes to avoid shell parsing errors
                            evil_str = FuzzHelper.get_evil_string().replace('\x00', '').replace('"', "'")
                            path_val = evil_str
                        if "<output>" in command and random.random() < 0.5:
                            evil_str = FuzzHelper.get_evil_string().replace('\x00', '').replace('"', "'")
                            output_val = evil_str
                        
                        # DO NOT fuzz the 'on'/'off' value for --comments.
                        # The CLI help message specifies `{on,off}`. Fuzzing this value only
                        # tests the standard argparse library, not the tool's core logic,
                        # and will not produce meaningful differential results.

                    command = command.replace("<path>", f'"{path_val}"')
                    command = command.replace("<output>", f'"{output_val}"')

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate a test case for {category.name}: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CodeCollatorAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))