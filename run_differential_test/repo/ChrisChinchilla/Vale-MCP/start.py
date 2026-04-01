import os
import sys
import re
import json
import random
from enum import Enum

# Add the parent directory of the script's location to the Python path
# to ensure that the BaseRepoAdapter and DiffTestEngine can be imported.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

class CmdCategory(Enum):
    """
    Enumerates the types of commands to be tested for the vale-cli tool.
    The values are generic command structure templates that reflect how the
    MCP server is invoked via stdin.
    """
    STATUS = "echo '<mcp_json>' | vale-cli"
    STATUS_DEBUG = "echo '<mcp_json>' | vale-cli --debug"
    SYNC = "echo '<mcp_json>' | vale-cli"
    SYNC_WITH_CONFIG = "echo '<mcp_json>' | vale-cli"
    SYNC_DEBUG = "echo '<mcp_json>' | vale-cli --debug"
    CHECK_FILE = "echo '<mcp_json>' | vale-cli"
    CHECK_FILE_DEBUG = "echo '<mcp_json>' | vale-cli --debug"
    CHECK_FILE_WITH_ENV_CONFIG = "VALE_CONFIG_PATH=<path> echo '<mcp_json>' | vale-cli"


class ValeCliAdapter(BaseRepoAdapter):
    """
    Adapter for the vale-cli repository, providing methods for installation,
    test case generation, and output sanitization.
    """

    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image for the test environment.
        Node.js v22+ is required by the tool.
        """
        return "node:latest"

    def _install_dependencies(self, container) -> None:
        """Helper to install the 'vale' binary, a required dependency for the tool to run."""
        vale_version = "3.4.1"
        install_cmd = f"""
            apt-get update && apt-get install -y --no-install-recommends wget git ca-certificates && \\
            wget https://github.com/errata-ai/vale/releases/download/v{vale_version}/vale_{vale_version}_Linux_64-bit.tar.gz && \\
            tar -xvzf vale_{vale_version}_Linux_64-bit.tar.gz && \\
            mv vale /usr/local/bin/ && \\
            rm -f vale_{vale_version}_Linux_64-bit.tar.gz
        """
        if container.exec_run(f"sh -c '{install_cmd}'").exit_code != 0:
            raise Exception("Dependency (vale) Installation Failed")

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool from its Git repository."""
        self._install_dependencies(container)
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ChrisChinchilla/Vale-MCP.git && cd Vale-MCP && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent (local) version of the tool."""
        self._install_dependencies(container)
        container.exec_run("mkdir -p /repo")
        # The local_agent_path is the path to 'repo_to_be_tested', so we copy it to '/repo'
        # which results in '/repo/repo_to_be_tested' inside the container.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the command output to remove volatile information like
        request IDs, version numbers, and absolute file paths.
        """
        sanitized = re.sub(r'"id":\s*".*?"', '"id": "sanitized"', raw_stdout)
        sanitized = re.sub(r'Vale MCP Server v[\d.]+', 'Vale MCP Server v_sanitized', sanitized)
        sanitized = re.sub(r'vale-cli@[\d.]+', 'vale-cli@sanitized', sanitized)
        sanitized = re.sub(r'vale v[\d.]+', 'vale v_sanitized', sanitized)
        # Normalize paths, including those in error messages
        sanitized = re.sub(r"The path '[^']+'", "The path '<PATH>'", sanitized)
        sanitized = re.sub(r'(/repo/|/test_data/)[^"\s,]+', r'<PATH>', sanitized)
        sanitized = re.sub(r'line \d+, col \d+', 'line X, col Y', sanitized)
        return super().sanitize_stdout(sanitized)

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases covering the core functionalities
        of the vale-cli tool, including normal and edge cases.
        """
        cases = []
        
        vale_ini_content = """
StylesPath = styles
MinAlertLevel = suggestion
Packages = write-good, proselint

[*]
BasedOnStyles = write-good, proselint
"""
        markdown_content = "# Test Documant\n\nSo, this is a test doc to check vale linting. It has a typo."

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    fuzz_id = f"{category.name}_{i}"
                    
                    payload = {"id": f"req_{fuzz_id}"}
                    cmd_suffix = ""
                    mount_files = {}
                    env_vars = {}
                    mcp_json = ""

                    if "DEBUG" in category.name:
                        cmd_suffix = " --debug"

                    if "STATUS" in category.name:
                        payload["tool"] = "vale_status"
                        if is_edge_case:
                            mcp_json = random.choice(['{}', '{"tool": "invalid_tool"}', 'not a valid json'])
                        else:
                            mcp_json = json.dumps(payload)

                    elif "SYNC" in category.name:
                        payload["tool"] = "vale_sync"
                        config_filename = f"vale_{fuzz_id}.ini"

                        if category == CmdCategory.SYNC_WITH_CONFIG:
                            if is_edge_case:
                                payload["params"] = {"config_path": FuzzHelper.get_filepath(ext=".ini")}
                            else:
                                mount_files[config_filename] = vale_ini_content
                                payload["params"] = {"config_path": f"/test_data/{config_filename}"}
                        else: # SYNC and SYNC_DEBUG
                            if is_edge_case:
                                mount_files[".vale.ini"] = FuzzHelper.get_evil_string()
                            else:
                                mount_files[".vale.ini"] = vale_ini_content
                        mcp_json = json.dumps(payload)

                    elif "CHECK_FILE" in category.name:
                        payload["tool"] = "check_file"
                        doc_filename = f"doc_{fuzz_id}.md"

                        if is_edge_case:
                            # Use evil string for the path parameter, a common vulnerability
                            payload["params"] = {"path": FuzzHelper.get_evil_string()}
                            # Also mount a file with evil content, but don't point to it
                            mount_files[doc_filename] = FuzzHelper.get_evil_string()
                        else:
                            # For normal cases, provide a valid file and config to ensure success
                            mount_files[doc_filename] = markdown_content
                            mount_files[".vale.ini"] = vale_ini_content
                            payload["params"] = {"path": f"/test_data/{doc_filename}"}
                        
                        mcp_json = json.dumps(payload)

                        if category == CmdCategory.CHECK_FILE_WITH_ENV_CONFIG:
                            config_filename = f"vale_env_{fuzz_id}.ini"
                            if is_edge_case:
                                env_vars["VALE_CONFIG_PATH"] = FuzzHelper.get_filepath(ext=".ini")
                            else:
                                mount_files[config_filename] = vale_ini_content
                                env_vars["VALE_CONFIG_PATH"] = f"/test_data/{config_filename}"

                    if not mcp_json:
                        mcp_json = json.dumps(payload)
                    
                    # Ensure mcp_json is a non-empty string to avoid shell errors
                    if not mcp_json.strip():
                        mcp_json = "{}"

                    # The framework's runner will escape this, but we do it here for clarity
                    safe_mcp_json = mcp_json.replace("'", "'\\''")
                    
                    command = f"echo '{safe_mcp_json}' | vale-cli{cmd_suffix}"

                    cases.append(TestCase(
                        command=command.strip(),
                        category=category.value,
                        mount_files=mount_files,
                        env_vars=env_vars
                    ))
                except Exception as e:
                    print(f"      ⚠️  Skipping test case generation for {category.name}_{i} due to error: {e}")
                    continue
        return cases


if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ValeCliAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))