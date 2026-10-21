import os
import sys
import re
import random
import string
import json
from enum import Enum
from typing import List, Dict

# Add the parent directory of the 'repo' directory to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Defines the command categories for jsondetective.
    The value of each enum member is a generic command structure template.
    """
    SCHEMA_ONLY = "jsondetective <JSON_FILE>"
    DATACLASS_STDOUT = "jsondetective <JSON_FILE> --create-dataclass"
    DATACLASS_WITH_NAME = "jsondetective <JSON_FILE> -d -c <TEXT>"
    DATACLASS_WITH_OUTPUT = "jsondetective <JSON_FILE> -d -o <PATH>"
    DATACLASS_FULL = "jsondetective <JSON_FILE> -d -c <TEXT> -o <PATH>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class JSONDetectiveAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Clones and installs the oracle (baseline) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/timf34/JSONDetective.git && cd JSONDetective && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the agent (local) version of the tool."""
        container.exec_run("mkdir -p /repo")
        # Note: The trailing '/' on the destination path is important for docker cp
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo/") != 0:
            raise Exception("Failed to copy agent code to container")
        
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _generate_json_content(self, is_edge: bool) -> str:
        """Generates JSON content, including edge cases and feature-specific data."""
        if is_edge:
            choice = random.choice(['evil_string', 'empty', 'malformed', 'text'])
            if choice == 'evil_string':
                return FuzzHelper.get_evil_string()
            elif choice == 'empty':
                return ""
            elif choice == 'malformed':
                # Malformed JSON (e.g., trailing comma)
                return '{"key1": "value1", "key2": 123,}'
            else: # text
                return FuzzHelper.get_string(50, 100)
        else:
            # For normal cases, sometimes generate date-like keys to test the core feature
            if random.random() < 0.4: # 40% chance
                data = {}
                for i in range(random.randint(3, 7)):
                    date_key = f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
                    data[date_key] = {
                        "views": FuzzHelper.get_int(0, 10000),
                        "likes": FuzzHelper.get_int(0, 1000)
                    }
                return json.dumps(data)
            else:
                return FuzzHelper.get_json_string(num_keys=FuzzHelper.get_int(3, 8))

    def generate_test_cases(self) -> list[TestCase]:
        """Generates a list of test cases, including normal and targeted edge cases."""
        cases = []
        
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge = (i == 0)
                    
                    file_name = f"test_{category.name.lower()}_{i}.json"
                    content = self._generate_json_content(is_edge)
                    input_file_path = f"/test_data/{file_name}"
                    
                    cmd = ""
                    mount_files = {file_name: content}
                    prep_script = ""

                    if category == CmdCategory.SCHEMA_ONLY:
                        cmd = f"jsondetective {input_file_path}"

                    elif category == CmdCategory.DATACLASS_STDOUT:
                        cmd = f"jsondetective {input_file_path} -d"

                    elif category == CmdCategory.DATACLASS_WITH_NAME:
                        class_name = FuzzHelper.get_string(8, 15, chars=string.ascii_letters).capitalize()
                        if is_edge:
                            # Use problematic but simple names that the CLI might mishandle
                            class_name = random.choice(['"My Root"', '123', '_Test', '""'])
                        cmd = f"jsondetective {input_file_path} -d -c {class_name}"

                    elif category == CmdCategory.DATACLASS_WITH_OUTPUT:
                        output_path = f"/test_data/output_{category.name.lower()}_{i}.py"
                        if is_edge:
                            # Use a path that is a directory, which should cause a file write error
                            output_path = "/test_data/"
                        cmd = f"jsondetective {input_file_path} -d -o {output_path}"

                    elif category == CmdCategory.DATACLASS_FULL:
                        class_name = FuzzHelper.get_string(8, 15, chars=string.ascii_letters).capitalize()
                        output_path = f"/test_data/output_full_{i}.py"
                        if is_edge:
                            class_name = '"Invalid Class Name"'
                            # Try to write to a location that should not be writable
                            output_path = "/root/unauthorized_output.py"
                        cmd = f"jsondetective {input_file_path} -d -c {class_name} -o {output_path}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files,
                        prep_script=prep_script
                    ))
                except Exception:
                    # Skip any test case that fails during generation, ensuring the process continues
                    continue
        return cases

# =====================================================================
# 3. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = JSONDetectiveAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))