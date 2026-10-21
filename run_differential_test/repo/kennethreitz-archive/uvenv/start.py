import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for the core commands of uvenv.
    The value of each enum member is a generic string representation
    of the command structure.
    """
    LOCK = "uvenv lock"
    INSTALL = "uvenv install"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class UvenvAdapter(BaseRepoAdapter):
    """
    Adapter for the 'uvenv' CLI tool.
    """
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image for the testing environment.
        'uvenv' is a Python tool that requires 'uv'.
        """
        return "python:latest"

    @property
    def ignore_patterns(self) -> list[str]:
        """
        Extends base ignore patterns to include the .venv directory created by uvenv.
        """
        base_patterns = super().ignore_patterns
        base_patterns.append(r"^/\.venv(/|$)") # Ignore default venv directory
        return base_patterns

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the stdout to remove volatile information like timings,
        speeds, and specific versions before comparison.
        """
        # Sanitize uv version string, e.g., "uv 0.2.5" -> "uv [VERSION]"
        sanitized = re.sub(r'uv \d+\.\d+\.\d+', 'uv [VERSION]', raw_stdout)
        # Sanitize timings, e.g., "in 1.23s" or "in 45ms" -> "in [DURATION]"
        sanitized = re.sub(r'in \d+(\.\d+)?(s|ms)', 'in [DURATION]', sanitized)
        # Sanitize download/processing speeds, e.g., "12.3 MiB/s" -> "[SPEED]"
        sanitized = re.sub(r'\d+(\.\d+)? (?:[KMGT]i)?B/s', '[SPEED]', sanitized)
        # Sanitize package counts, e.g., "Resolved 12 packages" -> "Resolved [N] packages"
        sanitized = re.sub(r'(Resolved|Downloaded|Installed) \d+ packages?', r'\\1 [N] packages', sanitized)
        # Call parent sanitizer to remove ANSI codes
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """
        Installs the oracle version of uvenv from its GitHub repository,
        following the strict framework rules.
        """
        cmd = "pip install uv && mkdir -p /repo && cd /repo && git clone https://github.com/kennethreitz-archive/uvenv.git && cd uvenv && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent version of uvenv from the local source code,
        following the strict framework rules.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "pip install uv && cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases for 'uvenv', covering both normal
        and edge-case scenarios for each command category.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        VALID_PACKAGES = ['requests', 'click', 'flask', 'numpy', 'pandas', 'django', 'pytz']

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # Make the first case an edge case
                    use_env_vars = (i % 2 == 1) # Alternate using env vars

                    base_cmd = category.value
                    # CRITICAL FIX: Run commands inside /test_data to ensure files are found
                    # and .venv is created in a predictable, observable location.
                    cmd = f"cd /test_data && {base_cmd}"
                    
                    mount_files = {}
                    env_vars = {}
                    
                    num_packages = random.randint(1, 3)

                    if category == CmdCategory.LOCK:
                        in_filename = "requirements.in"
                        
                        if is_edge_case:
                            # Malicious, empty, or boundary content for requirements.in
                            content = FuzzHelper.get_evil_string()
                        else:
                            # Normal content for requirements.in
                            pkgs = random.sample(VALID_PACKAGES, num_packages)
                            content = "\n".join(pkgs)

                        if use_env_vars:
                            in_filename = f"custom_reqs_{i}.in"
                            out_filename = f"custom_lock_{i}.txt"
                            env_vars = {
                                "UVENV_REQUIREMENTS_IN": f"/test_data/{in_filename}",
                                "UVENV_REQUIREMENTS_TXT": f"/test_data/{out_filename}"
                            }
                        
                        mount_files[in_filename] = content

                    elif category == CmdCategory.INSTALL:
                        txt_filename = "requirements.txt"

                        if is_edge_case:
                            # Malicious, malformed, or boundary content for requirements.txt
                            content = FuzzHelper.get_evil_string()
                        else:
                            # Normal content for requirements.txt (lockfile format)
                            pkgs = random.sample(VALID_PACKAGES, num_packages)
                            content = "\n".join([f"{p}=={random.randint(1,5)}.{random.randint(0,10)}.{random.randint(0,20)}" for p in pkgs])

                        if use_env_vars:
                            txt_filename = f"custom_lock_{i}.txt"
                            venv_dir = f"custom_venv_{i}"
                            env_vars = {
                                "UVENV_REQUIREMENTS_TXT": f"/test_data/{txt_filename}",
                                "UVENV_VENV_DIR": f"/test_data/{venv_dir}"
                            }
                        
                        mount_files[txt_filename] = content

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files,
                        env_vars=env_vars
                    ))
                except Exception:
                    # Failsafe to prevent the generator from crashing
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = UvenvAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))