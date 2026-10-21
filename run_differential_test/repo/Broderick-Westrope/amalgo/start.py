import os
import sys
import re
import random
import string
from enum import Enum

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the command categories for amalgo.
    The value of each enum is the generic command structure template.
    """
    # Basic functionality
    BASIC = "amalgo <dir> --stdout"
    
    # Filtering features
    FILTER = "amalgo <dir> --stdout --filter '<pattern>'"
    GITIGNORE = "amalgo <dir> --stdout --gitignore <file>"
    FILTER_GITIGNORE = "amalgo <dir> --stdout --filter '<pattern>' --gitignore <file>"

    # Output content control
    NO_TREE = "amalgo <dir> --stdout --no-tree"
    NO_DUMP = "amalgo <dir> --stdout --no-dump"
    OUTLINE = "amalgo <dir> --stdout --outline"
    NO_TREE_NO_DUMP = "amalgo <dir> --stdout --no-tree --no-dump"
    NO_DUMP_OUTLINE = "amalgo <dir> --stdout --no-dump --outline"

    # Other flags
    INCLUDE_BINARY = "amalgo <dir> --stdout --include-binary"
    FORMAT_JSON = "amalgo <dir> --stdout --format json"
    
    # Complex combinations
    JSON_OUTLINE = "amalgo <dir> --stdout --format json --outline"
    FILTER_OUTLINE_JSON = "amalgo <dir> --stdout --filter '<pattern>' --outline --format json"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class AmalgoAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Install the baseline version of amalgo from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Broderick-Westrope/amalgo.git && cd amalgo && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Install the agent (local version) of amalgo."""
        container.exec_run("mkdir -p /repo")
        # Per rule, use os.system to copy. The destination /repo will result in /repo/repo_to_be_tested inside container.
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo") != 0:
            raise Exception("Agent code copy failed")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitize the stdout to remove volatile parts.
        The base implementation already removes ANSI codes, which is sufficient.
        """
        return super().sanitize_stdout(raw_stdout)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        TEST_DIR = "/test_data"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # First case is a sane, logical one; others are for fuzzing.
                    is_sane_case = (i == 0)

                    # Determine file content requirements
                    needs_go = "OUTLINE" in category.name
                    needs_binary = category == CmdCategory.INCLUDE_BINARY
                    
                    mount_files = self._create_random_files(not is_sane_case, needs_go, needs_binary)
                    
                    cmd_parts = ["amalgo", TEST_DIR, "--stdout"]
                    
                    # --- Flag construction based on category ---
                    
                    if "FILTER" in category.name:
                        if is_sane_case:
                            pattern = "**/*.txt,*.go,!**/vendor/*"
                        else:
                            # Generate fuzzy but shell-safe patterns (no single quotes)
                            safe_chars = string.ascii_letters + string.digits + "*,!/."
                            pattern = FuzzHelper.get_string(5, 15, chars=safe_chars)
                        cmd_parts.append(f"--filter='{pattern}'")

                    if "GITIGNORE" in category.name:
                        gitignore_filename = "test.gitignore"
                        if is_sane_case:
                            gitignore_content = "*.log\n/dist\n"
                        else:
                            if random.random() > 0.5:
                                # Use non-evil but random string content
                                gitignore_content = FuzzHelper.get_string(10, 50)
                            else:
                                # Point to a non-existent file path
                                gitignore_filename = FuzzHelper.get_string(5, 10) + ".ignore"
                        
                        mount_files[gitignore_filename] = gitignore_content
                        cmd_parts.append(f"--gitignore={TEST_DIR}/{gitignore_filename}")

                    if "NO_TREE" in category.name:
                        cmd_parts.append("--no-tree")
                    
                    if "NO_DUMP" in category.name:
                        cmd_parts.append("--no-dump")

                    if "OUTLINE" in category.name:
                        cmd_parts.append("--outline")

                    if "INCLUDE_BINARY" in category.name:
                        cmd_parts.append("--include-binary")

                    if "JSON" in category.name:
                        if is_sane_case:
                            format_val = "json"
                        else:
                            format_val = FuzzHelper.get_string(3, 8)
                        cmd_parts.append(f"--format={format_val}")

                    command = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for category {category.name}. Error: {e}")
                    continue
        return cases

    def _create_random_files(self, is_edge_case: bool, include_go: bool, include_binary: bool) -> dict:
        """Helper to generate a random file structure for testing."""
        files = {}
        num_files = random.randint(2, 4)
        
        for i in range(num_files):
            content = FuzzHelper.get_string(50, 200)
            ext = random.choice(['.txt', '.md', '.log'])
            dir_prefix = random.choice(['', 'src/', 'docs/guides/'])
            path = f"{dir_prefix}file_{i}{ext}"
            files[path] = content

        if include_go:
            go_content = 'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("hello world")\n}\n'
            files["main.go"] = go_content
            files["utils/helpers.go"] = "package utils\n\n// Helper does things\nfunc Helper() {}"

        if include_binary:
            # Simulate binary content with non-utf8-like characters
            binary_content = ''.join(chr(random.randint(128, 255)) for _ in range(100))
            files["app.bin"] = binary_content

        if is_edge_case:
            # Add an empty file for edge cases
            files["empty_file.txt"] = ""
            # Add a file with a weird name
            files["-tricky-name.sh"] = "echo 'hello'"
            # Add a file with evil content
            files["evil.txt"] = FuzzHelper.get_evil_string()

        return files

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = AmalgoAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))