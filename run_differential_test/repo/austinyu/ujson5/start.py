import os
import sys
import re
import random
import json
from enum import Enum
from typing import List

# Add the parent directory of the 'final_differential_test' directory to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine from the root of the project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command structures and argument combinations for ujson5.
    The value of each enum is the generic command template string.
    """
    # Basic I/O methods
    INFILE_TO_STDOUT = "ujson5 <infile>"
    INFILE_TO_OUTFILE = "ujson5 <infile> <outfile>"
    STDIN_TO_STDOUT = "echo '<json5>' | ujson5"

    # Single formatting flag tests
    SORT_KEYS = "ujson5 <infile> --sort-keys"
    NO_ENSURE_ASCII = "ujson5 <infile> --no-ensure-ascii"
    INDENT = "ujson5 <infile> --indent <N>"
    NO_INDENT = "ujson5 <infile> --no-indent"
    COMPACT = "ujson5 <infile> --compact"

    # Combined formatting flags tests
    SORT_KEYS_AND_INDENT = "ujson5 <infile> --sort-keys --indent <N>"
    SORT_KEYS_AND_NO_ASCII = "ujson5 <infile> --sort-keys --no-ensure-ascii"
    ALL_FLAGS = "ujson5 <infile> --sort-keys --no-ensure-ascii --indent <N>"


# =====================================================================
# 2. Repository Adapter Implementation for ujson5
# =====================================================================
class Ujson5Adapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/austinyu/ujson5.git && cd ujson5 && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies the local agent code into the container and installs it."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> List[TestCase]:
        """Generates a list of TestCase objects for differential testing."""
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == CASES_PER_CATEGORY - 1)

                    # --- 1. Generate Input Content ---
                    content = ""
                    if is_edge_case:
                        choice = random.random()
                        if choice < 0.4:
                            content = FuzzHelper.get_evil_string()
                        elif choice < 0.8:
                            content = FuzzHelper.get_json_string(num_keys=3)[:-2]  # Malformed
                        else:
                            content = ""  # Empty
                    else:
                        # Generate valid JSON and augment it to be JSON5
                        json_data = json.loads(FuzzHelper.get_json_string(num_keys=random.randint(2, 5)))

                        if category in [CmdCategory.NO_ENSURE_ASCII, CmdCategory.SORT_KEYS_AND_NO_ASCII, CmdCategory.ALL_FLAGS]:
                            json_data["你好世界"] = f"test_{FuzzHelper.get_string(3,5)}"

                        content = json.dumps(json_data)

                        # Randomly add JSON5 features to valid JSON
                        if random.random() > 0.5:
                            content = f"// Random comment {FuzzHelper.get_string(5, 15)}\n{content}"
                        if random.random() > 0.5:
                            # FIX: Use a robust regex to add a trailing comma to non-empty objects
                            content = re.sub(r'(\S)\s*\}$', r'\1,\n}', content, 1)

                    infile_name = f"input_{category.name}_{i}.json5"
                    outfile_name = f"output_{category.name}_{i}.json"
                    mount_files = {}
                    cmd = ""

                    # --- 2. Assemble Command Based on Category ---
                    if category == CmdCategory.STDIN_TO_STDOUT:
                        escaped_content = content.replace("'", "'\\''")
                        cmd = f"echo '{escaped_content}' | ujson5"
                    else:
                        mount_files[infile_name] = content
                        command_parts = [f"ujson5 /test_data/{infile_name}"]

                        if category == CmdCategory.INFILE_TO_OUTFILE:
                            # FIX: Rely on FS diff, do not `cat` the output file to stdout
                            command_parts.append(f"/test_data/{outfile_name}")

                        flags = []
                        if category in [CmdCategory.SORT_KEYS, CmdCategory.SORT_KEYS_AND_INDENT, CmdCategory.SORT_KEYS_AND_NO_ASCII, CmdCategory.ALL_FLAGS]:
                            flags.append("--sort-keys")
                        if category in [CmdCategory.NO_ENSURE_ASCII, CmdCategory.SORT_KEYS_AND_NO_ASCII, CmdCategory.ALL_FLAGS]:
                            flags.append("--no-ensure-ascii")
                        if category == CmdCategory.NO_INDENT:
                            flags.append("--no-indent")
                        if category == CmdCategory.COMPACT:
                            flags.append("--compact")
                        if category in [CmdCategory.INDENT, CmdCategory.SORT_KEYS_AND_INDENT, CmdCategory.ALL_FLAGS]:
                            indent_val = ""
                            if is_edge_case:
                                # FIX: Use safer invalid values
                                indent_val = random.choice([
                                    str(FuzzHelper.get_int(-10, 0)),
                                    FuzzHelper.get_string(3, 8, string.ascii_letters)
                                ])
                            else:
                                indent_val = str(FuzzHelper.get_int(1, 8))
                            # FIX: Do not wrap the indent value in quotes
                            flags.append(f"--indent {indent_val}")

                        random.shuffle(flags)
                        command_parts.extend(flags)
                        cmd = " ".join(command_parts)

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Skipping test case generation for category {category.name} due to error: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Execution Block
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = Ujson5Adapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))