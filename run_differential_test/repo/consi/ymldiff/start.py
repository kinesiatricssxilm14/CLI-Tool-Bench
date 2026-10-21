import os
import sys
import re
import json
import random
import copy
from enum import Enum

# PyYAML is required for this script. If not installed, run: pip install pyyaml
try:
    import yaml
except ImportError:
    print("Error: PyYAML library not found. Please install it using 'pip install pyyaml'")
    sys.exit(1)

sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line argument combinations for ymldiff.
    The value of each enum member is a generic command structure template.
    """
    BASIC = "ymldiff <file1> <file2>"
    DISABLE_COMMENTS = "ymldiff --disable-comments <file1> <file2>"
    NO_DOC_COMMENT = "ymldiff --no-doc-comment <file1> <file2>"
    NO_COLOR = "ymldiff --no-color <file1> <file2>"
    DISABLE_COMMENTS_NO_DOC = "ymldiff -cd <file1> <file2>"
    DISABLE_COMMENTS_NO_COLOR = "ymldiff -cn <file1> <file2>"
    NO_DOC_NO_COLOR = "ymldiff -dn <file1> <file2>"
    ALL_OPTIONS = "ymldiff -cdn <file1> <file2>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/consi/ymldiff.git && cd ymldiff && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make the first case of each category an edge case for predictability
                    is_edge_case = (i == 0)
                    
                    file1_name = f"fuzz_file1_{category.name.lower()}_{i}.yaml"
                    file2_name = f"fuzz_file2_{category.name.lower()}_{i}.yaml"
                    content1, content2 = "", ""

                    if is_edge_case:
                        # Generate boundary, malicious, or malformed inputs
                        edge_choice = random.randint(0, 3)
                        if edge_choice == 0: # Both files contain evil strings
                            content1 = FuzzHelper.get_evil_string()
                            content2 = FuzzHelper.get_evil_string()
                        elif edge_choice == 1: # One file is empty, one is evil
                            content1 = ""
                            content2 = FuzzHelper.get_evil_string()
                        elif edge_choice == 2: # One file is valid YAML, one is non-yaml
                            valid_dict = json.loads(FuzzHelper.get_json_string(num_keys=3))
                            content1 = yaml.dump(valid_dict, Dumper=yaml.SafeDumper)
                            content2 = FuzzHelper.get_csv_string(rows=5, cols=2)
                        else: # Both files are empty
                            content1 = ""
                            content2 = ""
                    else:
                        # Generate two similar, valid YAML files to get meaningful diffs
                        base_dict = json.loads(FuzzHelper.get_json_string(num_keys=random.randint(3, 8)))
                        modified_dict = copy.deepcopy(base_dict)

                        # Apply one random modification to create a diff
                        mod_choice = random.randint(0, 2)
                        keys = list(modified_dict.keys())
                        
                        if keys:
                            if mod_choice == 0: # Modify a value
                                key_to_mod = random.choice(keys)
                                modified_dict[key_to_mod] = FuzzHelper.get_string(5, 10)
                            elif mod_choice == 1 and len(keys) > 1: # Delete a key
                                key_to_del = random.choice(keys)
                                del modified_dict[key_to_del]
                            else: # Add a new key
                                new_key = FuzzHelper.get_string(5, 10, chars="abcdef") # Avoid special chars in keys
                                modified_dict[new_key] = FuzzHelper.get_int(0, 1000)
                        else: # if base_dict was empty, add a key
                             modified_dict['new_key'] = 'new_value'

                        content1 = yaml.dump(base_dict, Dumper=yaml.SafeDumper)
                        content2 = yaml.dump(modified_dict, Dumper=yaml.SafeDumper)

                    # Assemble the command based on the category template
                    template = category.value
                    cmd = template.replace("<file1>", f"/test_data/{file1_name}").replace("<file2>", f"/test_data/{file2_name}")

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file1_name: content1, file2_name: content2}
                    ))
                except Exception as e:
                    # Ensure test case generation does not crash the main process
                    print(f"Warning: Failed to generate a test case for {category.name}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter() # 替换为实际的 Adapter 类名
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))