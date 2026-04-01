import os
import sys
import re
from enum import Enum
import random
import json

# Add parent directories to sys.path to import framework modules
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 0. Constants
# =====================================================================
CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    # Encode JSON -> TOON from file
    ENCODE_BASIC = "toon <input.json>"
    ENCODE_FORCE = "toon <input.json> --encode"
    ENCODE_DELIMITER_TAB = 'toon <input.json> --delimiter "\\t"'
    ENCODE_DELIMITER_PIPE = 'toon <input.json> --delimiter "|"'
    ENCODE_INDENT = "toon <input.json> --indent <N>"
    ENCODE_LENGTH_MARKER = "toon <input.json> --length-marker"
    
    # Decode TOON -> JSON from file
    DECODE_BASIC = "toon <input.toon>"
    DECODE_FORCE = "toon <input.toon> --decode"
    DECODE_NO_STRICT = "toon <input.toon> --no-strict"

    # Stdin/Stdout cases
    ENCODE_STDIN = "echo <json> | toon -"
    DECODE_STDIN = "echo <toon> | toon -"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ToonAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool in the container."""
        full_name = "xaviviro/python-toon"
        repo_name = "python-toon"
        cmd = f"mkdir -p /repo && cd /repo && git clone https://github.com/{full_name}.git && cd {repo_name} && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the local (agent) version of the tool in the container."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Test Case Generation Helpers
    # =====================================================================
    def _generate_json_object(self, is_edge_case: bool) -> any:
        """Helper to generate a Python object for JSON serialization. This is safer than building strings."""
        if is_edge_case:
            choice = random.randint(0, 4)
            if choice == 0:
                # Safely include evil string by letting json.dumps handle escaping
                return {"key_with_evil_str": FuzzHelper.get_evil_string()}
            if choice == 1:
                # Test special string quoting for keywords and numbers
                return {"null_keyword": "null", "num_string": "42", "bool_string": "true"}
            if choice == 2:
                # Test whitespace quoting
                return {"leading_space": " hello", "trailing_space": "world "}
            if choice == 3:
                return {}  # Empty object
            if choice == 4:
                return []  # Empty array
        else:
            # Generate a more complex, valid object based on README examples
            return {
                "metadata": {"version": FuzzHelper.get_int(1, 5), "author": FuzzHelper.get_string(5, 10)},
                "items": [
                    {"id": FuzzHelper.get_int(1, 100), "name": FuzzHelper.get_string(5, 10), "active": random.choice([True, False])},
                    {"id": FuzzHelper.get_int(101, 200), "name": FuzzHelper.get_string(5, 10), "active": random.choice([True, False])}
                ],
                "tags": [FuzzHelper.get_string(3, 7) for _ in range(random.randint(2, 4))]
            }

    def _generate_toon_content(self, is_edge_case: bool) -> str:
        """Helper to generate TOON formatted strings for decoding tests."""
        if is_edge_case:
            choice = random.randint(0, 4)
            if choice == 0:
                return ""  # Empty content
            elif choice == 1:
                return FuzzHelper.get_evil_string() # Malicious/garbage input
            elif choice == 2:
                # Malformed: missing colon
                return f"{FuzzHelper.get_string(3, 8)} {FuzzHelper.get_string(3, 8)}"
            elif choice == 3:
                # Malformed: length mismatch (strict mode should fail)
                return f"items[3,]{{id,name}}:\n  1,Alice\n  2,Bob"
            else:
                # Malformed: inconsistent indentation
                return f"key:\n  value1\n   value2"
        else:
            # Generate valid TOON content
            choice = random.randint(0, 2)
            if choice == 0:
                # Simple key-value
                key = FuzzHelper.get_string(3, 8, 'abcdefghijklmnopqrstuvwxyz')
                value = FuzzHelper.get_string(5, 10)
                return f"{key}: {value}\nother_key: {FuzzHelper.get_int()}"
            elif choice == 1:
                # Primitive array
                items = [FuzzHelper.get_string(3, 5) for _ in range(random.randint(2, 5))]
                return f"my_list[{len(items)}]: {','.join(items)}"
            else:
                # Tabular array
                return "users[2,]{id,name}:\n  1,Alice\n  2,Bob"

    def generate_test_cases(self) -> list[TestCase]:
        """Generates a list of TestCase objects for differential testing."""
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    cmd = ""
                    mount_files = {}
                    
                    if category.name.endswith("_STDIN"):
                        if category == CmdCategory.ENCODE_STDIN:
                            json_obj = self._generate_json_object(is_edge_case)
                            content = json.dumps(json_obj)
                            escaped_content = content.replace("'", "'\\''")
                            cmd = f"echo '{escaped_content}' | toon -"
                        elif category == CmdCategory.DECODE_STDIN:
                            content = self._generate_toon_content(is_edge_case)
                            escaped_content = content.replace("'", "'\\''")
                            cmd = f"echo '{escaped_content}' | toon -"
                    
                    else:
                        file_name = f"input_{category.name.lower()}_{i}"
                        
                        if category.name.startswith("ENCODE"):
                            file_name += ".json"
                            json_obj = self._generate_json_object(is_edge_case)
                            content = json.dumps(json_obj, indent=2)
                            mount_files[file_name] = content
                            
                            input_path = f"/test_data/{file_name}"
                            base_cmd = f"toon {input_path}"

                            if category == CmdCategory.ENCODE_BASIC:
                                cmd = base_cmd
                            elif category == CmdCategory.ENCODE_FORCE:
                                cmd = f"{base_cmd} --encode"
                            elif category == CmdCategory.ENCODE_DELIMITER_TAB:
                                cmd = f'{base_cmd} --delimiter "\t"'
                            elif category == CmdCategory.ENCODE_DELIMITER_PIPE:
                                cmd = f'{base_cmd} --delimiter "|"'
                            elif category == CmdCategory.ENCODE_INDENT:
                                indent_val = random.choice(["-1", "abc"]) if is_edge_case else FuzzHelper.get_int(0, 8)
                                cmd = f"{base_cmd} --indent {indent_val}"
                            elif category == CmdCategory.ENCODE_LENGTH_MARKER:
                                cmd = f"{base_cmd} --length-marker"

                        elif category.name.startswith("DECODE"):
                            file_name += ".toon"
                            if category == CmdCategory.DECODE_NO_STRICT and is_edge_case:
                                content = "[3,]{id,name}:\n  1,Alice\n  2,Bob" # Guaranteed length mismatch
                            else:
                                content = self._generate_toon_content(is_edge_case)
                            
                            mount_files[file_name] = content
                            input_path = f"/test_data/{file_name}"
                            base_cmd = f"toon {input_path}"

                            if category == CmdCategory.DECODE_BASIC:
                                cmd = base_cmd
                            elif category == CmdCategory.DECODE_FORCE:
                                cmd = f"{base_cmd} --decode"
                            elif category == CmdCategory.DECODE_NO_STRICT:
                                cmd = f"{base_cmd} --no-strict"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files=mount_files
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}: {e}", file=sys.stderr)
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ToonAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))