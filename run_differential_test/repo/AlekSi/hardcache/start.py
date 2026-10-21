import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of the 'repo' directory to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Defines the command categories for 'hardcache'.
    Focuses on the 'local trim' subcommand and its argument combinations.
    The 'local trimd' command is a long-running daemon and is unsuitable
    for this differential testing framework.
    """
    TRIM_UNUSED_FOR = "hardcache local trim --dir <dir> --unused-for <duration>"
    TRIM_MAX_SIZE = "hardcache local trim --dir <dir> --max-size <size>"
    TRIM_UNUSED_AND_MAX_SIZE = "hardcache local trim --dir <dir> --unused-for <duration> --max-size <size>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class HardcacheAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/AlekSi/hardcache.git && cd hardcache && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Copies the local (agent) version of the tool into the container and installs it.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the command output to remove volatile information like temporary
        directory paths and specific size/numeric values, ensuring stable diffs.
        """
        # Sanitize volatile cache directory paths (e.g., /test_data/cache_TRIM_UNUSED_FOR_5)
        sanitized = re.sub(r'/test_data/cache_[a-zA-Z_0-9]+', '/test_data/cache_dir', raw_stdout)
        # Sanitize size values (e.g., "10.5GB", "5%", "12345 bytes")
        sanitized = re.sub(r'\d+(\.\d+)?\s*(GB|MB|MiB|KB|B|%)', '<SIZE>', sanitized, flags=re.IGNORECASE)
        # Sanitize any remaining standalone numbers which could be counts, etc.
        sanitized = re.sub(r'\b\d+\b', '<NUM>', sanitized)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases, covering both normal and edge-case scenarios
        for each command category.
        """
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0)
                cache_dir = f"/test_data/cache_{category.name}_{i}"
                
                # A more realistic prep script to create files with different ages.
                # 'touch -d' allows setting a specific modification time, which is crucial for '--unused-for'.
                prep_script = f"""
                mkdir -p {cache_dir}/aa {cache_dir}/bb
                echo "This is an old cache entry" > {cache_dir}/aa/old_file
                touch -d "3 days ago" {cache_dir}/aa/old_file
                sleep 0.1
                echo "This is a recent cache entry" > {cache_dir}/bb/new_file
                """

                cmd = ""
                try:
                    if category == CmdCategory.TRIM_UNUSED_FOR:
                        if is_edge_case:
                            duration = random.choice([
                                FuzzHelper.get_evil_string(), "0", "-1h", "10xyz"
                            ])
                        else:
                            # Create a duration that will definitely trim the old file
                            duration = "2d"
                        cmd = f"hardcache local trim --dir={cache_dir} --unused-for={duration}"

                    elif category == CmdCategory.TRIM_MAX_SIZE:
                        if is_edge_case:
                            size = random.choice([
                                FuzzHelper.get_evil_string(), "0", "-10GB", "150%", "10.5.5GB"
                            ])
                        else:
                            # Set max-size to 0 to force trimming of the oldest file
                            size = "0B"
                        cmd = f"hardcache local trim --dir={cache_dir} --max-size={size}"

                    elif category == CmdCategory.TRIM_UNUSED_AND_MAX_SIZE:
                        if is_edge_case:
                            duration = random.choice([FuzzHelper.get_evil_string(), "0"])
                            size = random.choice([FuzzHelper.get_evil_string(), "0", "150%"])
                        else:
                            # A logical combination that should work
                            duration = "2d"
                            size = f"{FuzzHelper.get_int(1, 99)}%"
                        
                        args = [f"--dir={cache_dir}", f"--unused-for={duration}", f"--max-size={size}"]
                        random.shuffle(args)
                        cmd = f"hardcache local trim {' '.join(args)}"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            prep_script=prep_script
                        ))
                except Exception:
                    # Failsafe to prevent test generation from crashing
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = HardcacheAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))