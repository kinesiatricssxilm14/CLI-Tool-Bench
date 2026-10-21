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
    Enumerates the core command structures and argument combinations for the 'toon' CLI tool.
    The value of each enum member is a generic string template representing the command.
    """
    # Auto-detection based on file extension
    AUTODETECT_ENCODE = "toon <input.json> -o <output.toon>"
    AUTODETECT_DECODE = "toon <input.toon> -o <output.json>"

    # Explicit Encoding with various options
    ENCODE_BASIC = "toon <input.json> --encode"
    ENCODE_DELIMITER = "toon <input.json> --encode --delimiter <char>"
    ENCODE_INDENT = "toon <input.json> --encode --indent <N>"
    ENCODE_LENGTH_MARKER = "toon <input.json> --encode --length-marker"
    ENCODE_ALL_OPTIONS = "toon <input.json> --encode --delimiter <char> --indent <N> --length-marker"

    # Explicit Decoding with various options
    DECODE_BASIC = "toon <input.toon> --decode"
    DECODE_NO_STRICT = "toon <input.toon> --decode --no-strict"
    DECODE_INDENT = "toon <input.toon> --decode --indent <N>"
    DECODE_ALL_OPTIONS = "toon <input.toon> --decode --no-strict --indent <N>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ToonAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image.
        """
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool from GitHub."""
        full_name = "toon-format/toon-python"
        repo_name = "toon-python"
        cmd = f"mkdir -p /repo && cd /repo && git clone https://github.com/{full_name}.git && cd {repo_name} && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the local (agent) version of the tool."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for differential testing.
        It covers all command categories, mixing normal and edge-case inputs.
        """
        cases: list[TestCase] = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # 1/5 edge cases
                    base_cmd = ""
                    mount_files = {}
                    options = []

                    # --- ENCODING TEST CASES (JSON -> TOON) ---
                    if "encode" in category.name.lower() or "AUTODETECT_ENCODE" in category.name:
                        input_file = f"input_{i}.json"
                        output_file = f"output_{i}.toon"
                        
                        if is_edge_case:
                            # Malformed JSON (trailing comma) or an evil string
                            content = '{"key": "value",}' if i % 2 == 0 else FuzzHelper.get_evil_string()
                        else:
                            content = FuzzHelper.get_json_string(num_keys=FuzzHelper.get_int(1, 5))

                        mount_files = {input_file: content}
                        base_cmd = f"toon /test_data/{input_file}"
                        options.append(f"-o /test_data/{output_file}")

                        if "ENCODE" in category.name:
                            options.append("--encode")

                        if category in [CmdCategory.ENCODE_DELIMITER, CmdCategory.ENCODE_ALL_OPTIONS]:
                            delim = random.choice([',', '\t', '|'])
                            options.append(f'--delimiter "{delim}"')

                        if category in [CmdCategory.ENCODE_INDENT, CmdCategory.ENCODE_ALL_OPTIONS]:
                            indent = FuzzHelper.get_int(0, 8) if not is_edge_case else FuzzHelper.get_int(-5, -1)
                            options.append(f"--indent {indent}")

                        if category in [CmdCategory.ENCODE_LENGTH_MARKER, CmdCategory.ENCODE_ALL_OPTIONS]:
                            options.append("--length-marker")

                    # --- DECODING TEST CASES (TOON -> JSON) ---
                    elif "decode" in category.name.lower() or "AUTODETECT_DECODE" in category.name:
                        input_file = f"input_{i}.toon"
                        output_file = f"output_{i}.json"

                        if is_edge_case:
                            # Malformed TOON or an evil string
                            content = FuzzHelper.get_evil_string() if i % 2 == 0 else "key: value\nkey2:"
                        else:
                            rand_choice = random.randint(0, 2)
                            if rand_choice == 0:  # Simple object
                                content = f"name: {FuzzHelper.get_string(5, 10)}\nage: {FuzzHelper.get_int(1, 100)}"
                            elif rand_choice == 1:  # Primitive array
                                items = [str(FuzzHelper.get_int(1, 100)) for _ in range(FuzzHelper.get_int(1, 5))]
                                content = f"items[{len(items)}]: {','.join(items)}"
                            else:  # Tabular array
                                num_rows = FuzzHelper.get_int(2, 5)
                                rows = [f"  {FuzzHelper.get_int(1, 100)},{FuzzHelper.get_string(5, 10)}" for _ in range(num_rows)]
                                content = f"users[{num_rows},]{{id,name}}:\n" + "\n".join(rows)

                        mount_files = {input_file: content}
                        base_cmd = f"toon /test_data/{input_file}"
                        options.append(f"-o /test_data/{output_file}")

                        if "DECODE" in category.name:
                            options.append("--decode")

                        if category in [CmdCategory.DECODE_NO_STRICT, CmdCategory.DECODE_ALL_OPTIONS]:
                            options.append("--no-strict")

                        if category in [CmdCategory.DECODE_INDENT, CmdCategory.DECODE_ALL_OPTIONS]:
                            # FIX: Use an integer for indent, not a string, to avoid trivial argparse errors.
                            indent = FuzzHelper.get_int(1, 8) if not is_edge_case else FuzzHelper.get_int(-5, 0)
                            options.append(f"--indent {indent}")

                    # Assemble the final command and create the TestCase
                    if base_cmd and mount_files:
                        random.shuffle(options)
                        cmd = f"{base_cmd} {' '.join(options)}"
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files=mount_files
                        ))
                except Exception:
                    # Failsafe to prevent a single broken generator from stopping the whole process
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ToonAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))