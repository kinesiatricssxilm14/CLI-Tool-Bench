import os
import sys
import re
import json
import random
import string
import uuid
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command categories for cbomkit-theia.
    The 'image' command is excluded as it requires a Docker daemon inside the
    test container, which is not supported by the current framework setup.
    We focus on the fully testable 'dir' command.
    """
    DIR_SCAN = "cbomkit-theia dir <path>"
    DIR_SCAN_WITH_BOM = "cbomkit-theia dir <path> --bom <file>"
    DIR_SCAN_WITH_IGNORE = "cbomkit-theia dir <path> --ignore <pattern>"
    DIR_SCAN_WITH_PLUGINS = "cbomkit-theia dir <path> --plugins <list>"
    DIR_SCAN_ALL_FLAGS = "cbomkit-theia dir <path> --bom <file> --ignore <pattern> --plugins <list>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CbomkitTheiaAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the raw stdout to remove volatile or non-deterministic content.
        - Removes the ASCII art banner.
        - Normalizes volatile fields in the JSON output (timestamp, serialNumber) if present.
        """
        # Remove the multi-line ASCII art banner
        sanitized = re.sub(r'^\s*██████╗.*╚═╝\s*by IBM Research\s*', '', raw_stdout, flags=re.DOTALL | re.MULTILINE)
        sanitized = sanitized.strip()

        try:
            # Attempt to parse as JSON, which is the expected output format
            bom_data = json.loads(sanitized)
            if isinstance(bom_data, dict):
                # Normalize metadata timestamp
                if 'metadata' in bom_data and isinstance(bom_data.get('metadata'), dict):
                    if 'timestamp' in bom_data['metadata']:
                        bom_data['metadata']['timestamp'] = "TIMESTAMP_REMOVED"
                
                # Normalize top-level serialNumber
                if 'serialNumber' in bom_data:
                    bom_data['serialNumber'] = "SERIAL_NUMBER_REMOVED"

            # Re-serialize the JSON with sorted keys for consistent ordering
            sanitized = json.dumps(bom_data, sort_keys=True, indent=2)
        except json.JSONDecodeError:
            # If it's not valid JSON (e.g., an error message), leave it as is.
            pass

        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Clones and installs the oracle (original) version of the tool."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/cbomkit/cbomkit-theia.git && cd cbomkit-theia && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the agent (local) version of the tool."""
        container.exec_run("mkdir -p /repo")
        # Use os.system for simplicity as per framework examples
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _shell_quote(self, s: str) -> str:
        """Quotes a string for safe use as a single argument in a shell command."""
        return "'" + s.replace("'", "'\\''") + "'"

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases for the 'dir' command.
        The first case in each category is a simple, valid command, followed by
        fuzzed and edge case inputs.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        all_plugins = ["certificates", "javasecurity", "secrets", "opensslconf", "problematicca"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_normal_case = (i == 0)
                    
                    mount_files = {}
                    command_parts = ["cbomkit-theia", "dir"]
                    
                    # --- Setup scan directory and files ---
                    scan_dir_name = f"scan_dir_{category.name.lower()}_{i}"
                    scan_path_in_container = f"/test_data/{scan_dir_name}"
                    command_parts.append(scan_path_in_container)
                    
                    file_to_mount_rel_path = f"{scan_dir_name}/file_to_scan.txt"
                    if is_normal_case:
                        mount_files[file_to_mount_rel_path] = "This is a normal test file."
                    else:
                        mount_files[file_to_mount_rel_path] = FuzzHelper.get_evil_string()
                        mount_files[f"{scan_dir_name}/another.dat"] = FuzzHelper.get_string(10, 50)

                    # --- Handle flags based on category ---
                    if "WITH_BOM" in category.name or "ALL_FLAGS" in category.name:
                        bom_file_name = f"bom_{i}.json"
                        bom_path_in_container = f"/test_data/{bom_file_name}"
                        if is_normal_case:
                            bom_content = json.dumps({
                                "bomFormat": "CycloneDX", "specVersion": "1.6",
                                "serialNumber": f"urn:uuid:{uuid.uuid4()}", "version": 1,
                                "components": []
                            }, indent=2)
                        else:
                            bom_content = '{"invalid_json":,}' # Malformed JSON
                        mount_files[bom_file_name] = bom_content
                        command_parts.extend(["--bom", bom_path_in_container])

                    if "WITH_IGNORE" in category.name or "ALL_FLAGS" in category.name:
                        if is_normal_case:
                            ignore_pattern = "*.log,temp/"
                            mount_files[f"{scan_dir_name}/ignored.log"] = "This file should be ignored."
                        else:
                            ignore_pattern = FuzzHelper.get_evil_string()
                        command_parts.extend(["--ignore", self._shell_quote(ignore_pattern)])

                    if "WITH_PLUGINS" in category.name or "ALL_FLAGS" in category.name:
                        if is_normal_case:
                            subset_size = random.randint(1, len(all_plugins))
                            plugin_list = ",".join(random.sample(all_plugins, subset_size))
                        else:
                            plugin_list = FuzzHelper.get_evil_string()
                        command_parts.extend(["--plugins", self._shell_quote(plugin_list)])

                    command = " ".join(command_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} (i={i}): {e}")
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CbomkitTheiaAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))