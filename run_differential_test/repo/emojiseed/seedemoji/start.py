import os
import sys
import random
import shlex
from enum import Enum
from typing import List

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
    Defines the command categories for the seedemoji tool.
    The tool has a single, simple usage pattern: `seedemoji <word>`.
    """
    LOOKUP = "seedemoji <word>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class EmojiSeedAdapter(BaseRepoAdapter):
    """
    Adapter for the seedemoji CLI tool.
    """
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image for the testing environment.
        seedemoji is a Node.js tool.
        """
        return "node:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = (
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/emojiseed/seedemoji.git && "
            "cd seedemoji && npm install && npm install -g ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the local (agent) version of the tool into the container.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def generate_test_cases(self) -> List[TestCase]:
        """
        Generates a list of test cases covering various scenarios.
        """
        cases: List[TestCase] = []
        CASES_PER_CATEGORY = 50
        
        known_valid_words = [
            "abandon", "ability", "absorb", "abuse", "access", "accident", 
            "account", "accuse", "achieve", "acid", "acoustic", "acquire",
            "trust", "vision", "legal", "zoo"
        ]

        category = CmdCategory.LOOKUP

        for i in range(CASES_PER_CATEGORY):
            try:
                cmd = ""
                # Use a simple switch based on index `i` to create diverse cases
                if i == 0:
                    # Case 1: Known valid word
                    word = random.choice(known_valid_words)
                    cmd = f"seedemoji {shlex.quote(word)}"
                elif i == 1:
                    # Case 2: Random (likely invalid) word-like string
                    word = FuzzHelper.get_string(min_len=3, max_len=8).lower()
                    cmd = f"seedemoji {shlex.quote(word)}"
                elif i == 2:
                    # Case 3: Evil string, properly quoted to be a single argument
                    word = FuzzHelper.get_evil_string()
                    cmd = f"seedemoji {shlex.quote(word)}"
                elif i == 3:
                    # Case 4: No arguments
                    cmd = "seedemoji"
                elif i == 4:
                    # Case 5: Numeric string argument
                    word = str(FuzzHelper.get_int(-1000, 1000))
                    cmd = f"seedemoji {shlex.quote(word)}"
                
                if cmd:
                    cases.append(TestCase(
                        command=cmd,
                        category=category.value
                    ))
            except Exception:
                # In case FuzzHelper or logic fails, skip this case
                # This makes the generation more robust.
                continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = EmojiSeedAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))