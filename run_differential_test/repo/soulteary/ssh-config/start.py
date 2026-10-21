import os
import sys
import random
import json
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# This allows importing modules from the framework (BaseRepoAdapter, DiffTestEngine)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command patterns of the ssh-config tool.
    Each enum value is a generic template representing a specific usage pattern.
    This covers conversions between YAML, JSON, and SSH formats, using both
    file-based and pipe-based I/O.
    """
    # File-based input, stdout output
    TO_YAML_FROM_SRC = "ssh-config -to-yaml -src <file>"
    TO_JSON_FROM_SRC = "ssh-config -to-json -src <file>"
    TO_SSH_FROM_SRC = "ssh-config -to-ssh -src <file>"

    # File-based input, file-based output
    TO_YAML_FROM_SRC_TO_DEST = "ssh-config -to-yaml -src <file> -dest <file>"
    TO_JSON_FROM_SRC_TO_DEST = "ssh-config -to-json -src <file> -dest <file>"
    TO_SSH_FROM_SRC_TO_DEST = "ssh-config -to-ssh -src <file> -dest <file>"

    # Pipe-based input, stdout output
    TO_YAML_FROM_PIPE = "cat <file> | ssh-config -to-yaml"
    TO_JSON_FROM_PIPE = "cat <file> | ssh-config -to-json"
    TO_SSH_FROM_PIPE = "cat <file> | ssh-config -to-ssh"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class SshConfigAdapter(BaseRepoAdapter):
    """
    Adapter for the soulteary/ssh-config tool.
    Handles installation, test case generation, and output sanitization.
    """

    # --- Private Helper Methods for Content Generation ---

    def _generate_ssh_config_content(self, num_hosts: int = 3) -> str:
        """Generates plausible SSH config content."""
        content = ""
        for _ in range(num_hosts):
            host = FuzzHelper.get_string(5, 15, chars="abcdefghijklmnopqrstuvwxyz")
            hostname = FuzzHelper.get_domain()
            user = FuzzHelper.get_string(4, 10, chars="abcdefghijklmnopqrstuvwxyz")
            port = FuzzHelper.get_int(1024, 49151)
            content += f"Host {host}\n"
            content += f"  HostName {hostname}\n"
            content += f"  User {user}\n"
            content += f"  Port {port}\n\n"
        return content

    def _generate_yaml_config_content(self, num_hosts: int = 3) -> str:
        """Generates plausible YAML config content as a string."""
        content = ""
        for _ in range(num_hosts):
            host = FuzzHelper.get_string(5, 15, chars="abcdefghijklmnopqrstuvwxyz")
            content += f"{host}:\n"
            content += f"  HostName: {FuzzHelper.get_domain()}\n"
            content += f"  User: {FuzzHelper.get_string(4, 10, chars='abcdefghijklmnopqrstuvwxyz')}\n"
            content += f"  Port: {FuzzHelper.get_int(1024, 49151)}\n"
        return content

    def _generate_json_config_content(self, num_hosts: int = 3) -> str:
        """Generates plausible JSON config content."""
        data = {}
        for _ in range(num_hosts):
            host = FuzzHelper.get_string(5, 15, chars="abcdefghijklmnopqrstuvwxyz")
            data[host] = {
                "HostName": FuzzHelper.get_domain(),
                "User": FuzzHelper.get_string(4, 10, chars="abcdefghijklmnopqrstuvwxyz"),
                "Port": FuzzHelper.get_int(1024, 49151)
            }
        return json.dumps(data, indent=2)

    # --- BaseRepoAdapter Implementation ---

    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/soulteary/ssh-config.git && cd ssh-config && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the local (agent) version of the tool to be tested."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """Generates a list of test cases covering various command patterns."""
        cases = []
        tool_cmd = "ssh-config"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make the first case of each category an edge case for robustness
                    is_edge_case = (i == 0)
                    
                    input_file_name = f"input_{category.name.lower()}_{i}.dat"
                    output_file_name = f"output_{category.name.lower()}_{i}.dat"
                    
                    input_path = f"/test_data/{input_file_name}"
                    output_path = f"/test_data/{output_file_name}"

                    content = ""
                    command = ""
                    mount_files = {}

                    # --- Generate Input Content ---
                    if is_edge_case:
                        content = FuzzHelper.get_evil_string()
                    else:
                        # For normal cases, generate content based on expected input format
                        if category in [CmdCategory.TO_YAML_FROM_SRC, CmdCategory.TO_YAML_FROM_SRC_TO_DEST, CmdCategory.TO_YAML_FROM_PIPE]:
                            content = random.choice([self._generate_ssh_config_content(), self._generate_json_config_content()])
                        elif category in [CmdCategory.TO_JSON_FROM_SRC, CmdCategory.TO_JSON_FROM_SRC_TO_DEST, CmdCategory.TO_JSON_FROM_PIPE]:
                            content = random.choice([self._generate_ssh_config_content(), self._generate_yaml_config_content()])
                        elif category in [CmdCategory.TO_SSH_FROM_SRC, CmdCategory.TO_SSH_FROM_SRC_TO_DEST, CmdCategory.TO_SSH_FROM_PIPE]:
                            content = random.choice([self._generate_yaml_config_content(), self._generate_json_config_content()])
                    
                    mount_files[input_file_name] = content

                    # --- Assemble Command based on Category ---
                    if category == CmdCategory.TO_YAML_FROM_SRC:
                        command = f"{tool_cmd} -to-yaml -src {input_path}"
                    elif category == CmdCategory.TO_JSON_FROM_SRC:
                        command = f"{tool_cmd} -to-json -src {input_path}"
                    elif category == CmdCategory.TO_SSH_FROM_SRC:
                        command = f"{tool_cmd} -to-ssh -src {input_path}"
                    elif category == CmdCategory.TO_YAML_FROM_SRC_TO_DEST:
                        command = f"{tool_cmd} -to-yaml -src {input_path} -dest {output_path}"
                    elif category == CmdCategory.TO_JSON_FROM_SRC_TO_DEST:
                        command = f"{tool_cmd} -to-json -src {input_path} -dest {output_path}"
                    elif category == CmdCategory.TO_SSH_FROM_SRC_TO_DEST:
                        command = f"{tool_cmd} -to-ssh -src {input_path} -dest {output_path}"
                    elif category == CmdCategory.TO_YAML_FROM_PIPE:
                        command = f"cat {input_path} | {tool_cmd} -to-yaml"
                    elif category == CmdCategory.TO_JSON_FROM_PIPE:
                        command = f"cat {input_path} | {tool_cmd} -to-json"
                    elif category == CmdCategory.TO_SSH_FROM_PIPE:
                        command = f"cat {input_path} | {tool_cmd} -to-ssh"

                    if command:
                        cases.append(TestCase(
                            command=command,
                            category=category.value,
                            mount_files=mount_files
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} index {i}: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = SshConfigAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))