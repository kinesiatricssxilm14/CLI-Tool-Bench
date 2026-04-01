import os
import sys
import random
import json
from enum import Enum

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
    Enumerates the core functional command combinations for the jsonata CLI tool.
    The value of each enum is a generic template string representing the command structure.
    """
    BASE = "jsonata -e <expr_file> -i <input_file>"
    WITH_COMPACT = "jsonata -e <expr_file> -i <input_file> -c"
    WITH_BINDINGS_FILE = "jsonata -e <expr_file> -i <input_file> -bf <bindings_file>"
    WITH_INPUT_FORMAT = "jsonata -e <expr_file> -i <input_file> -f <format>"
    WITH_CHARSET = "jsonata -e <expr_file> -i <input_file> -ic <charset> -oc <charset>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class JsonataAdapter(BaseRepoAdapter):
    """
    Adapter for the jsonata-python CLI tool.
    """
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image. Python 3.11+ is recommended by the tool
        for full date/time function support. We use a slim version.
        """
        return "python:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the oracle (original) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/rayokota/jsonata-python.git && cd jsonata-python && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent (local) version of the tool.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for fuzzing the jsonata CLI.
        """
        cases: list[TestCase] = []
        CASES_PER_CATEGORY = 50
        
        VALID_EXPRESSIONS = [
            '$',
            '**.value',
            '$sum(example.value)',
            '{"Name": FirstName & " " & Surname, "Cities": **.City}',
            '$keys($)',
            'non_existent_key',
            'Address.City'
        ]
        VALID_CHARSETS = ["utf-8", "utf-16", "latin-1", "ascii"]
        VALID_FORMATS = ["auto", "json", "string"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == CASES_PER_CATEGORY - 1)
                    mount_files = {}

                    input_file = f"input_{category.name}_{i}.json"
                    expr_file = f"expr_{category.name}_{i}.jsonata"

                    if is_edge_case:
                        input_data = json.loads(FuzzHelper.get_json_string(num_keys=3))
                        key_to_poison = random.choice(list(input_data.keys()))
                        input_data[key_to_poison] = FuzzHelper.get_evil_string()
                        input_content = json.dumps(input_data)
                        expr_content = FuzzHelper.get_evil_string()
                    else:
                        input_content = FuzzHelper.get_json_string(num_keys=random.randint(2, 5))
                        expr_content = random.choice(VALID_EXPRESSIONS)

                    mount_files[input_file] = input_content
                    mount_files[expr_file] = expr_content

                    cmd_parts = ["jsonata", f"-e /test_data/{expr_file}", f"-i /test_data/{input_file}"]

                    if category == CmdCategory.WITH_COMPACT:
                        cmd_parts.append("-c")

                    elif category == CmdCategory.WITH_BINDINGS_FILE:
                        bindings_file = f"bindings_{category.name}_{i}.json"
                        if is_edge_case:
                            bindings_data = {"myvar": FuzzHelper.get_evil_string()}
                            bindings_content = json.dumps(bindings_data)
                            mount_files[expr_file] = '$myvar'
                        else:
                            bindings_content = json.dumps({"myvar": "hello from binding", "num": 42})
                            mount_files[expr_file] = random.choice(['$myvar', '$myvar & "!"', '$ > num'])
                        
                        mount_files[bindings_file] = bindings_content
                        cmd_parts.append(f"-bf /test_data/{bindings_file}")

                    elif category == CmdCategory.WITH_INPUT_FORMAT:
                        fmt = "invalid_format" if is_edge_case else random.choice(VALID_FORMATS)
                        cmd_parts.append(f"-f {fmt}")

                    elif category == CmdCategory.WITH_CHARSET:
                        charset = "invalid-charset" if is_edge_case else random.choice(VALID_CHARSETS)
                        cmd_parts.append(f"-ic {charset}")
                        cmd_parts.append(f"-oc {charset}")

                    command = " ".join(cmd_parts)
                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = JsonataAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))