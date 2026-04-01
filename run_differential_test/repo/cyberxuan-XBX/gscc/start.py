import os
import sys
import re
import random
from enum import Enum
from typing import List
import string

# Add the parent directory of 'final_differential_test' to the Python path
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
    Enumerates the core functional commands of the 'gscc' CLI tool.
    The value of each enum member is a generic string template representing
    the command structure. This is used for categorizing test cases.
    """
    CLASSIFY = 'gscc "<action>"'
    PROMPT = "gscc --prompt"
    TIERS = "gscc --tiers"

# =====================================================================
# 2. Repository Adapter Implementation for 'gscc'
# =====================================================================
class GSCCAdapter(BaseRepoAdapter):
    """
    Adapter for the 'gscc' CLI tool, providing methods for installation
    and test case generation.
    """
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the tool's language stack.
        'gscc' is a Python script, so a Python image is used.
        """
        return "python:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from its GitHub
        repository into the container using standard pip installation.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/cyberxuan-XBX/gscc.git && cd gscc && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the local (agent) version of the tool into the container.
        It copies the local code and installs it using pip.
        """
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
        It includes a mix of valid, boundary, and malformed inputs.
        """
        cases: List[TestCase] = []
        try:
            # Category 1: CLASSIFY - Test with various action strings
            classify_actions = [
                FuzzHelper.get_evil_string(),
                "",  # Empty string
                "--tiers", # An option string passed as an action
                f"Read the quarterly report from {FuzzHelper.get_filepath()}",
                f"Delete the production database {FuzzHelper.get_string(5, 8)}"
            ]
            # Ensure we have exactly CASES_PER_CATEGORY actions
            while len(classify_actions) < CASES_PER_CATEGORY:
                classify_actions.append(f"Analyze user feedback for ticket #{FuzzHelper.get_int(100, 999)}")

            for action in classify_actions:
                # Safely quote the action to handle all special characters.
                # The format '...' is the safest way to pass a literal string in shell.
                # We replace any internal single quotes with '\''
                safe_action = action.replace("'", "'\\''")
                cmd = f"gscc '{safe_action}'"
                cases.append(TestCase(
                    command=cmd,
                    category=CmdCategory.CLASSIFY.value
                ))

            # Category 2: PROMPT - Test the static command with junk arguments
            base_prompt_cmd = "gscc --prompt"
            cases.append(TestCase(command=base_prompt_cmd, category=CmdCategory.PROMPT.value))
            for _ in range(CASES_PER_CATEGORY - 1):
                junk_arg = FuzzHelper.get_string(3, 8, chars=string.ascii_lowercase)
                cmd_variation = random.choice([
                    f"{base_prompt_cmd} {junk_arg}",
                    f"{base_prompt_cmd} --{junk_arg}",
                    f"{base_prompt_cmd} --{junk_arg}={FuzzHelper.get_int()}"
                ])
                cases.append(TestCase(command=cmd_variation, category=CmdCategory.PROMPT.value))

            # Category 3: TIERS - Test the static command with junk arguments
            base_tiers_cmd = "gscc --tiers"
            cases.append(TestCase(command=base_tiers_cmd, category=CmdCategory.TIERS.value))
            for _ in range(CASES_PER_CATEGORY - 1):
                junk_arg = FuzzHelper.get_string(3, 8, chars=string.ascii_lowercase)
                cmd_variation = random.choice([
                    f"{base_tiers_cmd} {junk_arg}",
                    f"{base_tiers_cmd} --{junk_arg}",
                    f"{base_tiers_cmd} --{junk_arg}={FuzzHelper.get_int()}"
                ])
                cases.append(TestCase(command=cmd_variation, category=CmdCategory.TIERS.value))

        except Exception as e:
            print(f"Warning: Test case generation failed: {e}")

        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GSCCAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))