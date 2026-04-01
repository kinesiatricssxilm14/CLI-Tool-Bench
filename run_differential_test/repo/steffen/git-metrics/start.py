import os
import sys
import re
import base64
from enum import Enum

# Add the parent directory of the 'final_differential_test' directory to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line usage patterns of the git-metrics tool.
    The value of each enum member is a generic string representing the command structure.
    """
    ANALYZE_CURRENT_DIR = "git-metrics"
    ANALYZE_SPECIFIC_DIR = "git-metrics --repository <path>"
    DEBUG = "git-metrics --debug"
    NO_PROGRESS = "git-metrics --no-progress"
    DEBUG_NO_PROGRESS = "git-metrics --debug --no-progress"
    ANALYZE_SPECIFIC_DIR_DEBUG = "git-metrics --repository <path> --debug"
    ANALYZE_SPECIFIC_DIR_NO_PROGRESS = "git-metrics --repository <path> --no-progress"
    ANALYZE_SPECIFIC_DIR_DEBUG_NO_PROGRESS = "git-metrics --repository <path> --debug --no-progress"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GitMetricsAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image for the testing environment.
        The tool is written in Go and requires git. The golang image includes git.
        """
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Removes volatile and non-deterministic information from the tool's output
        to enable stable differential testing.
        """
        # Remove volatile run information
        sanitized = re.sub(r"^\s*Run at:.*$", "", raw_stdout, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*Repository path:.*$", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*Remote URL:.*$", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*Version:.*$", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*Git version:.*$", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*First commit:.*$", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*Last commit:.*$", "", sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r"^\s*Repository age:.*$", "", sanitized, flags=re.MULTILINE)
        
        # Remove future growth projection lines, which are marked with '*'
        sanitized = re.sub(r"^.*\*.*$", "", sanitized, flags=re.MULTILINE)
        
        # Remove blank lines that may result from the substitutions
        sanitized = "\n".join([line for line in sanitized.splitlines() if line.strip()])
        
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/steffen/git-metrics.git && cd git-metrics && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent version of the tool from the local path."""
        container.exec_run("mkdir -p /repo")
        # The DiffTestEngine handles copying the local agent, so we just need to install it.
        # However, the rules require this specific structure.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    @staticmethod
    def _generate_repo_prep_script(repo_path: str, is_edge_case: bool, seed: int) -> str:
        """
        Generates a shell script to create a git repository for testing.
        Handles both normal and edge-case repository states.
        """
        fh = FuzzHelper
        script_parts = [
            "set -e",
            f"mkdir -p {repo_path}",
            f"cd {repo_path}",
            "git init -b main",
            "git config --global user.name 'Test User'",
            "git config --global user.email 'test@example.com'",
        ]

        if is_edge_case:
            edge_type = seed % 4
            if edge_type == 0:  # Empty repo
                pass
            elif edge_type == 1:  # Repo with one empty commit
                script_parts.append("git commit --allow-empty -m 'Initial empty commit'")
            elif edge_type == 2:  # Repo with evil filename
                try:
                    evil_str = fh.get_evil_string()
                    if evil_str and evil_str.strip(): # Avoid empty or whitespace-only strings
                        evil_name_b64 = base64.b64encode(evil_str.encode()).decode()
                        script_parts.append(f"touch \"$(echo '{evil_name_b64}' | base64 -d)\"")
                        script_parts.append("git add .")
                        script_parts.append("git commit -m 'Commit with evil filename' --no-verify || true")
                except Exception:
                    pass
            elif edge_type == 3:  # Repo with evil commit message
                try:
                    evil_str = fh.get_evil_string()
                    if evil_str: # Avoid empty string for message
                        evil_msg_b64 = base64.b64encode(evil_str.encode()).decode()
                        script_parts.append("echo 'normal file' > normal.txt")
                        script_parts.append("git add .")
                        script_parts.append(f"git commit -m \"$(echo '{evil_msg_b64}' | base64 -d)\" --no-verify || true")
                except Exception:
                    pass
        else:  # Normal case
            num_commits = fh.get_int(2, 4)
            for i in range(num_commits):
                num_files = fh.get_int(1, 3)
                for j in range(num_files):
                    fname = f"file_{i}_{j}.txt"
                    content = fh.get_string(10, 50).replace("'", "''")
                    script_parts.append(f"echo '{content}' > {fname}")
                script_parts.append("git add .")
                script_parts.append(f"git commit -m 'Commit {i}'")
        
        return " && ".join(script_parts)

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        fh = FuzzHelper

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Ensure at least one edge case and some normal cases per category
                    is_edge_case = (i == 0)
                    repo_name = f"repo_{category.name.lower()}_{i}"
                    repo_path = f"/tmp/{repo_name}"

                    # The prep script always creates a repository, which might be an edge-case repo.
                    prep_script = self._generate_repo_prep_script(repo_path, is_edge_case, i)
                    
                    flags = []
                    if "DEBUG" in category.name:
                        flags.append("--debug")
                    if "NO_PROGRESS" in category.name:
                        flags.append("--no-progress")
                    
                    flags_str = " ".join(flags)
                    
                    if "SPECIFIC_DIR" in category.name:
                        path_arg = repo_path
                        if is_edge_case:
                            # FIX: Instead of an evil string, use a more logical edge case for a path argument,
                            # such as a non-existent path. This tests the tool's error handling for invalid paths.
                            path_arg = "/tmp/non_existent_repo_" + fh.get_string(5, 10)
                        
                        command = f"git-metrics {flags_str} --repository '{path_arg}'".strip()
                    else:
                        # For commands analyzing the current directory, we run inside the generated repo.
                        # If it's an edge case, the repo itself will be the edge case (e.g., empty, evil filenames).
                        command = f"cd {repo_path} && git-metrics {flags_str}".strip()

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        prep_script=prep_script
                    ))
                except Exception:
                    # If a single test case generation fails, skip it and continue.
                    continue
        return cases

# =====================================================================
# 3. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GitMetricsAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))