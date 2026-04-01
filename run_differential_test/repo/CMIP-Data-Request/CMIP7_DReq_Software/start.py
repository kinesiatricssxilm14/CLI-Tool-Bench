import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'repo' to the Python path
# This path is relative to the final_differential_test/repo/[author]/[repo_name]/ directory
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional commands of CMIP7_data_request_api_config.
    The value of each enum member is a generic string representation of the command.
    """
    NO_ARGS_INIT = "CMIP7_data_request_api_config"
    INIT = "CMIP7_data_request_api_config init"
    LIST = "CMIP7_data_request_api_config list"
    RESET = "CMIP7_data_request_api_config reset"
    SET_CACHE_DIR = "CMIP7_data_request_api_config cache_dir <path>"
    SET_CHECK_API_VERSION = "CMIP7_data_request_api_config check_api_version <bool>"
    SET_CONSOLIDATE = "CMIP7_data_request_api_config consolidate <bool>"
    SET_EXPORT = "CMIP7_data_request_api_config export <value>"
    SET_LOG_FILE = "CMIP7_data_request_api_config log_file <path>"
    SET_LOG_LEVEL = "CMIP7_data_request_api_config log_level <level>"
    SET_OFFLINE = "CMIP7_data_request_api_config offline <bool>"
    SET_VARIABLE_NAME = "CMIP7_data_request_api_config variable_name \"<name>\""

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CMIP7Adapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile output, such as home directory paths, before comparison.
        The tool writes config paths relative to the user's home directory.
        """
        # In the Docker container, the home directory is /root.
        # Replace it with a stable placeholder to ensure diffs are consistent.
        sanitized = re.sub(r'/root', '<HOME>', raw_stdout)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Installs the baseline version of the tool from its GitHub repository."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/CMIP-Data-Request/CMIP7_DReq_Software.git && cd CMIP7_DReq_Software && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent (local version to be tested) into the container."""
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

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make the first case for each category an edge case
                    is_edge_case = (i == 0)
                    cmd = ""
                    prep_script = ""

                    # Helper to safely quote values for the shell
                    def quote(value: str) -> str:
                        return f'"{str(value).replace("\"", "\\\"")}"'

                    if category in [CmdCategory.NO_ARGS_INIT, CmdCategory.INIT]:
                        cmd = category.value

                    elif category == CmdCategory.LIST:
                        # Set a known value before listing to make the output predictable
                        prep_script = f'CMIP7_data_request_api_config offline {random.choice(["true", "false"])}'
                        cmd = "CMIP7_data_request_api_config list"

                    elif category == CmdCategory.RESET:
                        # Set a value so reset has something to do
                        prep_script = f'CMIP7_data_request_api_config offline {random.choice(["true", "false"])}'
                        cmd = "CMIP7_data_request_api_config reset"

                    elif category == CmdCategory.SET_CACHE_DIR:
                        value = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_filepath(absolute=True)
                        cmd = f"CMIP7_data_request_api_config cache_dir {quote(value)}"

                    elif category in [CmdCategory.SET_CHECK_API_VERSION, CmdCategory.SET_CONSOLIDATE, CmdCategory.SET_OFFLINE]:
                        key_map = {
                            CmdCategory.SET_CHECK_API_VERSION: "check_api_version",
                            CmdCategory.SET_CONSOLIDATE: "consolidate",
                            CmdCategory.SET_OFFLINE: "offline"
                        }
                        key = key_map[category]
                        if is_edge_case:
                            value = FuzzHelper.get_evil_string()
                            # Evil strings must be quoted to avoid shell interpretation
                            cmd = f"CMIP7_data_request_api_config {key} {quote(value)}"
                        else:
                            # Valid boolean strings should not be quoted
                            value = random.choice(["true", "false"])
                            cmd = f"CMIP7_data_request_api_config {key} {value}"

                    elif category == CmdCategory.SET_EXPORT:
                        if is_edge_case:
                            value = FuzzHelper.get_evil_string()
                            cmd = f"CMIP7_data_request_api_config export {quote(value)}"
                        else:
                            value = random.choice(["raw", "release"])
                            cmd = f"CMIP7_data_request_api_config export {value}"

                    elif category == CmdCategory.SET_LOG_FILE:
                        value = FuzzHelper.get_evil_string() if is_edge_case else random.choice([FuzzHelper.get_filepath(ext=".log"), "default"])
                        cmd = f"CMIP7_data_request_api_config log_file {quote(value)}"

                    elif category == CmdCategory.SET_LOG_LEVEL:
                        if is_edge_case:
                            value = FuzzHelper.get_evil_string()
                            cmd = f"CMIP7_data_request_api_config log_level {quote(value)}"
                        else:
                            value = random.choice(["debug", "info"])
                            cmd = f"CMIP7_data_request_api_config log_level {value}"

                    elif category == CmdCategory.SET_VARIABLE_NAME:
                        if is_edge_case:
                            value = FuzzHelper.get_evil_string()
                        else:
                            value = random.choice([
                                "CMIP7 Compound Name",
                                "CMIP6 Compound Name",
                                FuzzHelper.get_string(10, 25)
                            ])
                        # This value can contain spaces, so it should always be quoted.
                        cmd = f"CMIP7_data_request_api_config variable_name {quote(value)}"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            prep_script=prep_script
                        ))
                except Exception as e:
                    # Log and continue if a single test case generation fails
                    print(f"Warning: Failed to generate test case for category {category.name}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CMIP7Adapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))