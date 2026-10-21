import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the types of commands to be tested for the 'gotcha' CLI tool.
    The value of each enum member is a generic string representation of the command structure.
    """
    NO_ARGS = "gotcha"
    DISTRO_FLAG = "gotcha -distro <string>"
    CONFIG_FLAG_DISABLE = "gotcha -config <file_with_DISABLE>"
    CONFIG_FLAG_DIVIDER = "gotcha -config <file_with_DIVIDER>"
    CONFIG_FLAG_MOUNTS = "gotcha -config <file_with_MOUNTS>"
    DISTRO_AND_CONFIG = "gotcha -distro <string> -config <file>"
    ENV_NO_COLOR = "NO_COLOR=1 gotcha"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GotchaAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the Go language stack.
        """
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the stdout to remove volatile information like memory usage,
        hostnames, etc., ensuring stable output for comparison.
        """
        # 1. Remove ANSI escape codes first
        sanitized = super().sanitize_stdout(raw_stdout)

        # 2. Sanitize user@host line, which is always the first line
        sanitized = re.sub(r'^\w+@\w+', '[USER]@[HOST]', sanitized, count=1)

        lines = sanitized.split('\n')
        processed_lines = []

        # This list includes all potential volatile keys, including 'OS'
        volatile_keys = ["Host", "OS", "Kernel", "Uptime", "Procs", "Memory", "Disk", "Shell", "DE/WM", "Terminal"]

        # 3. Iterate through all lines to process them
        for i, line in enumerate(lines):
            # Normalize the divider line (second line), whatever it may be
            if i == 1:
                processed_lines.append('---')
                continue

            is_volatile = False
            # Check for volatile keys (starting from the 3rd line)
            if i > 1:
                for key in volatile_keys:
                    # Match "Key - Value" format
                    if re.match(rf"^\s*{re.escape(key)}.*?\s+-\s+", line):
                        # Split only on the first occurrence of " - "
                        parts = re.split(r'\s+-\s+', line, maxsplit=1)
                        if len(parts) == 2:
                            # Reconstruct with a redacted value
                            processed_lines.append(f"{parts[0].rstrip()} - [REDACTED]")
                            is_volatile = True
                            break
            
            if not is_volatile:
                processed_lines.append(line)
                
        return '\n'.join(processed_lines)

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/yehorovye/gotcha.git && cd gotcha && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the development (agent) version of the tool from the local filesystem.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        VALID_DISTROS = ["arch", "debian", "nixos", "void", "gentoo", "bazzite"]
        VALID_DISABLE_FIELDS = ["host", "os", "kernel", "uptime", "shell", "procs", "memory", "disk"]
        # A curated list of "evil" strings that are less likely to break shell syntax
        SAFE_EVIL_STRINGS = [
            "", " ", "../../etc/passwd", "';--", "A" * 50, "中文测试🚀", "-1", "9999999999"
        ]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The first case of each category is an edge case
                    is_edge_case = (i == 0)
                    cmd = ""
                    mount_files = {}
                    env_vars = {}

                    if category == CmdCategory.NO_ARGS:
                        cmd = "gotcha"

                    elif category == CmdCategory.ENV_NO_COLOR:
                        cmd = "gotcha"
                        env_vars = {"NO_COLOR": "1"}

                    elif category == CmdCategory.DISTRO_FLAG:
                        distro_name = random.choice(SAFE_EVIL_STRINGS) if is_edge_case else random.choice(VALID_DISTROS)
                        cmd = f"gotcha -distro \"{distro_name}\""

                    elif category in [CmdCategory.CONFIG_FLAG_DISABLE, CmdCategory.CONFIG_FLAG_DIVIDER, CmdCategory.CONFIG_FLAG_MOUNTS, CmdCategory.DISTRO_AND_CONFIG]:
                        config_file_name = f"config_{category.name}_{i}.conf"
                        config_path = f"/test_data/{config_file_name}"
                        config_content = ""

                        if category == CmdCategory.CONFIG_FLAG_DISABLE:
                            if is_edge_case:
                                disable_val = FuzzHelper.get_evil_string()
                            else:
                                # Select one or two valid fields to disable
                                k = random.randint(1, 2)
                                disable_val = ",".join(random.sample(VALID_DISABLE_FIELDS, k))
                            config_content = f"DISABLE={disable_val}"
                            cmd = f"gotcha -config {config_path}"

                        elif category == CmdCategory.CONFIG_FLAG_DIVIDER:
                            divider = random.choice(SAFE_EVIL_STRINGS) if is_edge_case else FuzzHelper.get_string(1, 5, chars="`~!@#%^&*()_+-=[]{}|;:,.<>/?")
                            config_content = f"DIVIDER={divider}"
                            cmd = f"gotcha -config {config_path}"

                        elif category == CmdCategory.CONFIG_FLAG_MOUNTS:
                            if is_edge_case:
                                mount_path = FuzzHelper.get_evil_string()
                            else:
                                # Use guaranteed-to-exist paths in the container
                                mount_path = random.choice(["/", "/etc", "/tmp"])
                            config_content = f"MOUNTS={mount_path}"
                            cmd = f"gotcha -config {config_path}"
                        
                        elif category == CmdCategory.DISTRO_AND_CONFIG:
                            distro_name = random.choice(VALID_DISTROS)
                            divider = ":::"
                            config_content = f"DIVIDER={divider}"
                            cmd = f"gotcha -distro \"{distro_name}\" -config {config_path}"

                        mount_files[config_file_name] = config_content

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files,
                        env_vars=env_vars
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} (i={i}): {e}")
                    continue
        return cases


if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GotchaAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))