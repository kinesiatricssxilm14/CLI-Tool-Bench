import os
import sys
import re
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the command categories for gpad.
    - DEFAULT: Runs gpad in the current directory.
    - VERBOSE: Runs gpad in the current directory with verbose output.
    - PATH: Runs gpad on a specified directory path.
    - PATH_VERBOSE: Runs gpad on a specified directory path with verbose output.
    """
    DEFAULT = "gpad"
    VERBOSE = "gpad -v"
    PATH = "gpad -path <path>"
    PATH_VERBOSE = "gpad -path <path> -v"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GpadAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the stdout by removing volatile information like timestamps.
        The 'Time Taken' value is dynamic and needs to be normalized for comparison.
        """
        sanitized = re.sub(r"Time Taken:\s+.*", "Time Taken: <sanitized>", raw_stdout)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool from its GitHub repository."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/devasherr/gpad.git && cd gpad && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies the local agent code into the container and installs it."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _generate_go_file_content(self, is_edge_case: bool) -> str:
        """Helper function to generate content for Go source files."""
        if is_edge_case:
            roll = FuzzHelper.get_int(min_val=1, max_val=3)
            if roll == 1:
                return ""  # Empty file
            elif roll == 2:
                return "package main\n\nfunc main() {\n\tprintln(\"no structs here\")\n}"
            else:
                # FuzzHelper.get_evil_string() has no parameters
                return FuzzHelper.get_evil_string()

        return """
package main

// UnoptimizedStruct is designed to be reordered by gpad.
type UnoptimizedStruct struct {
    B bool    // 1 byte
    C int32   // 4 bytes
    A int64   // 8 bytes
    E float64 // 8 bytes
    D string  // 16 bytes
}
"""

    def generate_test_cases(self) -> list:
        """Generates a list of TestCase objects for differential testing."""
        test_cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    project_dir = f"project_{category.name}_{i}"
                    go_file_rel_path = f"{project_dir}/main.go"
                    go_file_content = self._generate_go_file_content(is_edge_case=not is_edge_case) # Use normal content for most cases
                    
                    mount_files = {go_file_rel_path: go_file_content}
                    target_dir = f"/test_data/{project_dir}"
                    command = ""

                    if category == CmdCategory.DEFAULT:
                        command = f"cd {target_dir} && gpad"
                    
                    elif category == CmdCategory.VERBOSE:
                        command = f"cd {target_dir} && gpad -v"

                    elif category == CmdCategory.PATH:
                        path_arg = target_dir
                        if is_edge_case:
                            roll = FuzzHelper.get_int(1, 3)
                            if roll == 1:
                                path_arg = FuzzHelper.get_evil_string()
                            elif roll == 2:
                                path_arg = "/test_data/non_existent_dir_abc123"
                            else:
                                # Test with an empty directory
                                empty_dir_rel_path = f"empty_dir_{i}/.placeholder"
                                mount_files[empty_dir_rel_path] = ""
                                path_arg = f"/test_data/empty_dir_{i}"
                        command = f"gpad -path {path_arg}"

                    elif category == CmdCategory.PATH_VERBOSE:
                        path_arg = target_dir
                        if is_edge_case:
                            roll = FuzzHelper.get_int(1, 2)
                            if roll == 1:
                                path_arg = FuzzHelper.get_filepath(ext="")
                            else:
                                # Invalid usage: path points to a file, not a directory
                                path_arg = f"/test_data/{go_file_rel_path}"
                        command = f"gpad -path {path_arg} -v"

                    if command:
                        # The framework handles shell escaping. Do not add quotes here.
                        test_cases.append(TestCase(
                            command=command,
                            category=category.value,
                            mount_files=mount_files
                        ))

                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} due to: {e}")
                    continue
        return test_cases

# =====================================================================
# 3. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GpadAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))