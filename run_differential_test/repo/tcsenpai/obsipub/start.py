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

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line argument combinations for obsipub.
    The value of each enum member is a generic string template of the command.
    """
    BASIC = "obsipub <vault_path> <output_epub_path>"
    WITH_TITLE = "obsipub <vault_path> <output_epub_path> --title <title>"
    WITH_AUTHOR = "obsipub <vault_path> <output_epub_path> --author <author>"
    WITH_TITLE_AUTHOR = "obsipub <vault_path> <output_epub_path> --title <title> --author <author>"
    NO_ATTACHMENTS = "obsipub <vault_path> <output_epub_path> --no-attachments"
    INCLUDE_TAGS = "obsipub <vault_path> <output_epub_path> --include-tags"
    VERBOSE = "obsipub <vault_path> <output_epub_path> --verbose"
    NO_ATTACHMENTS_AND_TAGS = "obsipub <vault_path> <output_epub_path> --no-attachments --include-tags"
    ALL_FLAGS = "obsipub <vault_path> <output_epub_path> --title <title> --author <author> --no-attachments --include-tags --verbose"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ObsipubAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the target tool.
        obsipub is a Python tool that requires pandoc.
        """
        return "python:latest"

    def install_oracle(self, container) -> None:
        """
        Installs dependencies, clones the original repository, and installs it in a single command.
        """
        cmd = (
            "apt-get update && apt-get install -y pandoc && "
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/tcsenpai/obsipub.git && "
            "cd obsipub && pip install ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs dependencies, copies the local agent code, and installs it.
        """
        # Install dependency required by the tool
        if container.exec_run("sh -c 'apt-get update && apt-get install -y pandoc'").exit_code != 0:
            raise Exception("Dependency Installation Failed: pandoc")

        # Copy and install the agent as per the strict rule pattern
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Removes volatile and non-deterministic parts from the tool's output.
        """
        sanitized = super().sanitize_stdout(raw_stdout)
        # Sanitize volatile time measurements (e.g., "in 0.001 seconds")
        sanitized = re.sub(r'in \d+\.\d+ seconds', 'in X.XX seconds', sanitized)
        # Sanitize volatile file counts (e.g., "Found 5 files")
        sanitized = re.sub(r'Found \d+ files', 'Found N files', sanitized)
        sanitized = re.sub(r'Found \d+ attachments', 'Found N attachments', sanitized)
        # Sanitize volatile, dynamically generated paths in logs and commands
        sanitized = re.sub(r'/test_data/vault_[^/]+', '/test_data/vault_X', sanitized)
        sanitized = re.sub(r'/test_data/output_[^/]+\.epub', '/test_data/output_X.epub', sanitized)
        # Sanitize pandoc version which might differ between base image updates
        sanitized = re.sub(r'pandoc \d+\.\d+(\.\d+)*', 'pandoc X.Y.Z', sanitized)
        return sanitized

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects, covering both normal and
        edge-case scenarios for each command category.
        """
        cases = []
        
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # First case in each category is an edge case
                    is_edge_case = (i == 0)

                    vault_dir = f"vault_{category.name}_{i}"
                    output_file = f"output_{category.name}_{i}.epub"
                    vault_path_in_container = f"/test_data/{vault_dir}"
                    output_path_in_container = f"/test_data/{output_file}"
                    
                    mount_files = {}

                    if is_edge_case:
                        # Edge case: Create an empty vault or a vault with problematic names
                        if i % 2 == 0:
                             mount_files[f"{vault_dir}/.placeholder"] = "" # Empty vault
                        else:
                             vault_dir = FuzzHelper.get_string(5,10) # Vault with random name
                             vault_path_in_container = f"/test_data/{vault_dir}"
                             mount_files[f"{vault_dir}/note.md"] = "hello"
                    else:
                        # Normal case: Generate a standard vault with a few notes and an attachment
                        mount_files = {
                            f"{vault_dir}/note1.md": f"# Note 1\n\nThis is a test note with a tag #project and a link to [[note2]].",
                            f"{vault_dir}/subfolder/note2.md": f"## Note 2\n\nThis note is in a subfolder and includes an image: ![[image.png]]",
                            f"{vault_dir}/subfolder/image.png": "dummy_binary_image_data" # Placeholder for binary data
                        }

                    # Base command structure
                    cmd_parts = ["obsipub", vault_path_in_container, output_path_in_container]
                    
                    # Add optional arguments based on category
                    if category in [CmdCategory.WITH_TITLE, CmdCategory.WITH_TITLE_AUTHOR, CmdCategory.ALL_FLAGS]:
                        title = FuzzHelper.get_string(5, 20)
                        cmd_parts.append(f'--title "{title}"')

                    if category in [CmdCategory.WITH_AUTHOR, CmdCategory.WITH_TITLE_AUTHOR, CmdCategory.ALL_FLAGS]:
                        author = FuzzHelper.get_string(5, 15)
                        cmd_parts.append(f'--author "{author}"')

                    if category in [CmdCategory.NO_ATTACHMENTS, CmdCategory.NO_ATTACHMENTS_AND_TAGS, CmdCategory.ALL_FLAGS]:
                        cmd_parts.append("--no-attachments")

                    if category in [CmdCategory.INCLUDE_TAGS, CmdCategory.NO_ATTACHMENTS_AND_TAGS, CmdCategory.ALL_FLAGS]:
                        cmd_parts.append("--include-tags")
                    
                    if category in [CmdCategory.VERBOSE, CmdCategory.ALL_FLAGS]:
                        cmd_parts.append("--verbose")

                    command = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Skipping test case generation for category {category.name} due to error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ObsipubAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))