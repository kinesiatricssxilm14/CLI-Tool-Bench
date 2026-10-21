import os
import sys
import re
import random
from enum import Enum
from typing import List

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command categories for qlog.
    Each enum value is a generic template representing the command structure.
    """
    INDEX = "qlog index <patterns...>"
    INDEX_FORCE = "qlog index --force <patterns...>"
    SEARCH_BASIC = "qlog search <query>"
    SEARCH_CONTEXT = "qlog search -c <N> <query>"
    SEARCH_MAX_RESULTS = "qlog search -n <N> <query>"
    SEARCH_JSON = "qlog search --json <query>"
    SEARCH_CONTEXT_MAX = "qlog search -c <N> -n <M> <query>"
    STATS = "qlog stats"
    CLEAR = "qlog clear"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class QlogAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Overrides the base method to remove volatile, non-deterministic output
        before comparison. This is crucial for tools that output performance
        metrics, timestamps, or varying counts.
        """
        # First, call parent to remove ANSI color codes
        sanitized = super().sanitize_stdout(raw_stdout)
        
        # Sanitize performance metrics like "in 0.05s"
        sanitized = re.sub(r"in \d+\.\d+s", "in [TIME]s", sanitized)
        # Sanitize index size, which can vary slightly (e.g., "12.34 MB")
        sanitized = re.sub(r"Index Size: .*?B", "Index Size: [SIZE]", sanitized)
        # Sanitize varying counts of lines, files, terms (e.g., "1,234" or "1234")
        sanitized = re.sub(r"(\d+,)*\d+ files", "[COUNT] files", sanitized)
        sanitized = re.sub(r"(\d+,)*\d+ lines", "[COUNT] lines", sanitized)
        sanitized = re.sub(r"Indexed Files: (\d+,)*\d+", "Indexed Files: [COUNT]", sanitized)
        sanitized = re.sub(r"Total Lines: (\d+,)*\d+", "Total Lines: [COUNT]", sanitized)
        sanitized = re.sub(r"Unique Terms: (\d+,)*\d+", "Unique Terms: [COUNT]", sanitized)
        # Sanitize file paths in search results, which are absolute and different
        sanitized = re.sub(r"/test_data/[^:]+", "[FILE_PATH]", sanitized)
        # Sanitize line numbers in search results (e.g., "123: some log line")
        sanitized = re.sub(r"^\s*\d+:", "[LINE_NUM]:", sanitized, flags=re.MULTILINE)
        # Sanitize timestamps
        sanitized = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "[TIMESTAMP]", sanitized)
        
        return sanitized

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Cosm00/qlog.git && cd qlog && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the local (agent) version of the tool into the container."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> List[TestCase]:
        """
        Generates a list of test cases covering all command categories.
        Integrates both normal and edge/malicious cases for robustness testing.
        """
        cases: List[TestCase] = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make the last two cases per category edge cases for targeted testing
                    is_edge_case = i >= (CASES_PER_CATEGORY - 2)

                    # --- Test Data Generation ---
                    # Always generate a valid file to mount. The "edginess" will come
                    # from the command arguments, not from broken file content.
                    test_id = len(cases) + 1
                    file_name = f"fuzz_test_{test_id}.log"
                    searchable_word = f"magic_word_{test_id}"
                    
                    lines = [FuzzHelper.get_string(20, 80) for _ in range(10)]
                    lines.insert(random.randint(0, len(lines)), f"INFO: This line contains the {searchable_word} to find.")
                    content = "\n".join(lines)
                    
                    mount_files = {file_name: content}
                    prep_script = ""
                    cmd_parts = ["qlog"]

                    # --- Command Assembly ---
                    if category in [CmdCategory.INDEX, CmdCategory.INDEX_FORCE]:
                        cmd_parts.append("index")
                        if category == CmdCategory.INDEX_FORCE:
                            cmd_parts.append("--force")
                        
                        # For normal cases, use valid paths; for edge cases, use potentially problematic strings.
                        path_arg = f"/test_data/{file_name}" if not is_edge_case else FuzzHelper.get_evil_string()
                        cmd_parts.append(f"'{path_arg}'")

                    elif category.name.startswith("SEARCH"):
                        # All search commands need a pre-existing index for meaningful tests.
                        prep_script = f"qlog index /test_data/{file_name}"
                        query = searchable_word if not is_edge_case else FuzzHelper.get_evil_string()

                        cmd_parts.append("search")
                        if category == CmdCategory.SEARCH_CONTEXT:
                            context_val = FuzzHelper.get_int(1, 5) if not is_edge_case else FuzzHelper.get_int(-5, 0)
                            cmd_parts.extend(["-c", str(context_val)])
                        elif category == CmdCategory.SEARCH_MAX_RESULTS:
                            max_val = FuzzHelper.get_int(1, 5) if not is_edge_case else FuzzHelper.get_int(-5, 0)
                            cmd_parts.extend(["-n", str(max_val)])
                        elif category == CmdCategory.SEARCH_JSON:
                            cmd_parts.append("--json")
                        elif category == CmdCategory.SEARCH_CONTEXT_MAX:
                            context_val = FuzzHelper.get_int(1, 3)
                            max_val = FuzzHelper.get_int(1, 5)
                            cmd_parts.extend(["-c", str(context_val), "-n", str(max_val)])
                        
                        cmd_parts.append(f"'{query}'")

                    elif category == CmdCategory.STATS:
                        cmd_parts.append("stats")
                        # For normal case, create an index first to get meaningful stats.
                        # For edge case, run on an empty/non-existent index.
                        if not is_edge_case:
                            prep_script = f"qlog index /test_data/{file_name}"

                    elif category == CmdCategory.CLEAR:
                        cmd_parts.append("clear")
                        # For normal case, create an index first to have something to clear.
                        # For edge case, run when there's nothing to clear.
                        if not is_edge_case:
                            prep_script = f"qlog index /test_data/{file_name}"

                    # Join parts to form the final command, ensuring no double spaces
                    command = " ".join(cmd_parts)
                    if len(cmd_parts) <= 1:
                        continue  # Skip if only "qlog" was generated

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=mount_files
                    ))
                except Exception:
                    # This ensures that if one case generation fails, the whole process doesn't stop.
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = QlogAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))