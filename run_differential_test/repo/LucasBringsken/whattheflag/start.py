import os
import sys
import re
from enum import Enum
import random

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# List of tools supported by whattheflag, extracted from the README
SUPPORTED_TOOLS = [
    "awk", "curl", "df", "docker", "du", "find", "git", "grep", "gzip", "jq",
    "kubectl", "nc", "ps", "rsync", "sed", "ssh", "tar", "top", "unzip",
    "wget", "xargs", "yq", "zip"
]

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for the different command categories of whattheflag.
    The value is the generic command structure template.
    """
    TOOLS = "whattheflag tools"
    EXPLAIN_TOOL_ONLY = "whattheflag <tool>"
    EXPLAIN_TOOL_WITH_FLAGS = "whattheflag <tool> <flags...>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class WhattheflagAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image for the testing environment.
        whattheflag is a Python tool.
        """
        return "python:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the oracle (baseline) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/LucasBringsken/whattheflag.git && cd whattheflag && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent (local) version of the tool.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # First case is always an edge case
                    cmd = ""

                    if category == CmdCategory.TOOLS:
                        cmd = "whattheflag tools"
                        if is_edge_case:
                            # Add junk arguments for robustness testing.
                            # This tests how the 'tools' command handles unexpected extra arguments.
                            cmd += f" {FuzzHelper.get_evil_string()}"

                    elif category == CmdCategory.EXPLAIN_TOOL_ONLY:
                        tool = ""
                        if is_edge_case:
                            # Use an invalid or malicious tool name, ensuring it's not empty.
                            # An empty string would change the command structure to `whattheflag`,
                            # which is not the intended test for this category.
                            tool = FuzzHelper.get_evil_string()
                            while not tool:
                                tool = FuzzHelper.get_evil_string()
                        else:
                            # Use a valid, randomly selected tool
                            tool = random.choice(SUPPORTED_TOOLS)
                        cmd = f"whattheflag {tool}"

                    elif category == CmdCategory.EXPLAIN_TOOL_WITH_FLAGS:
                        tool = ""
                        flags = ""
                        if is_edge_case:
                            # Use malicious strings, ensuring the tool part is not empty to maintain command structure.
                            tool = FuzzHelper.get_evil_string()
                            while not tool:
                                tool = FuzzHelper.get_evil_string()
                            flags = FuzzHelper.get_evil_string()
                        else:
                            # Use a valid tool and generate various flag patterns
                            tool = random.choice(SUPPORTED_TOOLS)
                            flag_type = random.randint(0, 3)
                            
                            if flag_type == 0: # Single short flag
                                flags = f"-{FuzzHelper.get_string(min_len=1, max_len=1, chars='abcdefghijklmnopqrstuvwxyz')}"
                            elif flag_type == 1: # Single long flag
                                flags = f"--{FuzzHelper.get_string(min_len=3, max_len=10, chars='abcdefghijklmnopqrstuvwxyz-')}"
                            elif flag_type == 2: # Combined short flags
                                num_flags = random.randint(2, 5)
                                flags = f"-{''.join(random.sample('abcdefghijklmnopqrstuvwxyz', num_flags))}"
                            elif flag_type == 3: # Multiple mixed flags
                                num_short = random.randint(1, 3)
                                num_long = random.randint(1, 2)
                                short_flags = [f"-{c}" for c in random.sample('abcdefghijklmnopqrstuvwxyz', num_short)]
                                long_flags = [f"--{FuzzHelper.get_string(min_len=3, max_len=8)}" for _ in range(num_long)]
                                all_flags = short_flags + long_flags
                                random.shuffle(all_flags)
                                flags = ' '.join(all_flags)

                        cmd = f"whattheflag {tool} {flags}"

                    if cmd: # Ensure command was generated
                        cases.append(TestCase(
                            command=cmd.strip(),
                            category=category.value,
                        ))
                except Exception:
                    # Skip case generation on error, don't crash the whole process
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = WhattheflagAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))