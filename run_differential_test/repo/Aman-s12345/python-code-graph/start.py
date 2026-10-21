import os
import sys
import re
from enum import Enum
import shlex

# Add the project's root directory to the Python path to allow importing framework modules.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command structures to be tested for python-code-graph.
    The value of each enum is the generic command template string.
    """
    BASIC = "python-code-graph <directory>"
    WITH_OUTPUT = "python-code-graph <directory> -o <file>"
    WITH_NAME = "python-code-graph <directory> -n <name>"
    WITH_CONCURRENCY = "python-code-graph <directory> -c <N>"
    WITH_EXCLUDE_SINGLE = "python-code-graph <directory> -e <pattern>"
    WITH_EXCLUDE_MULTIPLE = "python-code-graph <directory> -e <p1> -e <p2>"
    WITH_NO_CACHE = "python-code-graph <directory> --no-cache"
    WITH_CACHE_DIR = "python-code-graph <directory> --cache-dir <dir>"
    WITH_DEBUG = "python-code-graph <directory> -d"
    COMPLEX_OUTPUT_NAME_CONCURRENCY = "python-code-graph <directory> -o <file> -n <name> -c <N>"
    COMPLEX_EXCLUDE_NOCACHE_DEBUG = "python-code-graph <directory> -e <pattern> --no-cache -d"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class PythonCodeGraphAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes stdout by removing volatile information like log levels.
        """
        sanitized = re.sub(r'^(DEBUG|INFO|WARNING|ERROR|CRITICAL):[\w\.]+:?', '', raw_stdout, flags=re.MULTILINE)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool from its GitHub repository."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Aman-s12345/python-code-graph.git && cd python-code-graph && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies the local agent code into the container and installs it."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        dummy_project_files = {
            "test_project/main.py": "from utils.helpers import helper_function\n\nclass MainClass:\n    def run(self):\n        helper_function()",
            "test_project/utils/helpers.py": "def helper_function():\n    pass",
            "test_project/utils/__init__.py": "",
            "test_project/data/ignore.txt": "this is a text file to be ignored",
            "test_project/__init__.py": "",
        }

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    
                    target_dir = "/test_data/test_project"
                    mount_files = dummy_project_files.copy()

                    if is_edge_case:
                        # Alternate edge cases for directory argument
                        if i % 2 == 0:
                            target_dir = "/test_data/empty_dir"
                            mount_files = {"empty_dir/.gitkeep": ""}
                        else:
                            target_dir = "/test_data/non_existent_dir"
                            mount_files = {} # Tool should handle non-existent directory

                    # Base command with positional argument
                    cmd_parts = ["python-code-graph", shlex.quote(target_dir)]
                    
                    # Helper for quoting arguments
                    def quote(s):
                        return shlex.quote(str(s))

                    # Build command based on category
                    if category in [CmdCategory.WITH_OUTPUT, CmdCategory.COMPLEX_OUTPUT_NAME_CONCURRENCY]:
                        val = FuzzHelper.get_evil_string() if is_edge_case else f"/test_data/output_{i}.json"
                        cmd_parts.extend(["-o", quote(val)])

                    if category in [CmdCategory.WITH_NAME, CmdCategory.COMPLEX_OUTPUT_NAME_CONCURRENCY]:
                        val = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(5, 15)
                        cmd_parts.extend(["-n", quote(val)])

                    if category in [CmdCategory.WITH_CONCURRENCY, CmdCategory.COMPLEX_OUTPUT_NAME_CONCURRENCY]:
                        # FIX: Concurrency requires an integer. Edge case uses evil string, normal case uses valid int.
                        val = FuzzHelper.get_evil_string() if is_edge_case else str(FuzzHelper.get_int(1, 8))
                        cmd_parts.extend(["-c", quote(val)])

                    if category == CmdCategory.WITH_EXCLUDE_SINGLE:
                        val = FuzzHelper.get_evil_string() if is_edge_case else "*.txt"
                        cmd_parts.extend(["-e", quote(val)])

                    if category == CmdCategory.WITH_EXCLUDE_MULTIPLE:
                        p1 = FuzzHelper.get_evil_string() if is_edge_case else "data/"
                        p2 = FuzzHelper.get_evil_string() if is_edge_case else "*helpers.py"
                        cmd_parts.extend(["-e", quote(p1), "-e", quote(p2)])
                    
                    if category in [CmdCategory.WITH_NO_CACHE, CmdCategory.COMPLEX_EXCLUDE_NOCACHE_DEBUG]:
                        cmd_parts.append("--no-cache")

                    if category == CmdCategory.WITH_CACHE_DIR:
                        val = FuzzHelper.get_evil_string() if is_edge_case else f"/test_data/cache_dir_{i}"
                        cmd_parts.extend(["--cache-dir", quote(val)])

                    if category in [CmdCategory.WITH_DEBUG, CmdCategory.COMPLEX_EXCLUDE_NOCACHE_DEBUG]:
                        cmd_parts.append("-d")
                    
                    if category == CmdCategory.COMPLEX_EXCLUDE_NOCACHE_DEBUG:
                        # This option is already handled by the flags above, just need to add the -e part
                        val = FuzzHelper.get_evil_string() if is_edge_case else "*.py"
                        cmd_parts.extend(["-e", quote(val)])

                    command = " ".join(cmd_parts)
                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate case for {category.name} (i={i}): {e}")
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = PythonCodeGraphAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))