import os
import sys
import re
import random
import string
from enum import Enum
from typing import List

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command structures and flag combinations for stropt.
    The value of each enum is the generic command template string.
    """
    STRING_INPUT_BASIC = 'stropt "<type>" "<source>"'
    STRING_INPUT_OPTIMIZE = 'stropt -optimize "<type>" "<source>"'
    FILE_INPUT_BASIC = 'stropt -file <file> "<type>"'
    FILE_INPUT_OPTIMIZE = 'stropt -file <file> -optimize "<type>"'
    FILE_INPUT_VERBOSE = 'stropt -file <file> -verbose "<type>"'
    FILE_INPUT_BARE = 'stropt -file <file> -bare "<type>"'
    FILE_INPUT_OPTIMIZE_VERBOSE = 'stropt -file <file> -optimize -verbose "<type>"'
    FILE_INPUT_OPTIMIZE_BARE = 'stropt -file <file> -optimize -bare "<type>"'
    PLATFORM_32BIT = 'stropt -32bit -file <file> "<type>"'
    PLATFORM_AVR = 'stropt -avr -file <file> "<type>"'
    PLATFORM_CUSTOM_PTR = 'stropt -ptr <size,align> -file <file> "<type>"'
    PLATFORM_CUSTOM_INT = 'stropt -int <size,align> -file <file> "<type>"'
    PLATFORM_CUSTOM_MULTIPLE = 'stropt -ptr <s,a> -long <s,a> -file <file> "<type>"'
    USE_COMPILER = 'stropt -use-compiler -file <file> "<type>"'

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class StroptAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Abathargh/stropt.git && cd stropt && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo") != 0:
            raise Exception("Failed to copy agent code to container")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _generate_c_code(self, is_union=False):
        """
        Generates a C struct/union definition.
        Returns: (type_name, source_code_oneline, file_content_multiline)
        """
        struct_name = "fuzz_struct_" + FuzzHelper.get_string(min_len=4, max_len=8, chars="abcdef")
        keyword = "union" if is_union else "struct"
        type_name = f"{keyword} {struct_name}"
        
        fields = []
        base_types = ["char", "short", "int", "long", "double", "float", "void *", "unsigned char", "unsigned int"]
        for _ in range(random.randint(2, 5)):
            field_type = random.choice(base_types)
            field_name = FuzzHelper.get_string(min_len=3, max_len=8, chars="abcdefghijklmnopqrstuvwxyz")
            if random.random() < 0.2:
                field_name += f"[{random.randint(1, 5)}]"
            fields.append(f"  {field_type} {field_name};")
        
        fields_str_multiline = "\n".join(fields)
        fields_str_oneline = " ".join(f.strip() for f in fields)

        file_content = f"{keyword} {struct_name} {{\n{fields_str_multiline}\n}};"
        source_code_oneline = f"{keyword} {struct_name} {{ {fields_str_oneline} }};"
        
        return type_name, source_code_oneline, file_content

    def generate_test_cases(self) -> List[TestCase]:
        test_cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    command = ""
                    mounts = {}
                    is_simple_case = (i == 0)

                    type_name, source_code_oneline, file_content = self._generate_c_code(is_union=random.random() < 0.2)
                    filename = f"test_{category.name.lower()}_{i}.c"

                    if category in [CmdCategory.STRING_INPUT_BASIC, CmdCategory.STRING_INPUT_OPTIMIZE]:
                        flags = "-optimize" if category == CmdCategory.STRING_INPUT_OPTIMIZE else ""
                        current_type, current_source = type_name, source_code_oneline
                        if not is_simple_case and random.random() < 0.5:
                            current_type = "struct malformed"
                            current_source = "struct malformed { int x; char ; };"
                        command = f'stropt {flags} "{current_type}" "{current_source}"'.strip()
                    else:
                        mounts = {filename: file_content}
                        filepath = f"/test_data/{filename}"
                        cmd_template = 'stropt {flags} -file {filepath} "{type_name}"'
                        flags = ""
                        current_type_name = type_name

                        if category == CmdCategory.FILE_INPUT_OPTIMIZE: flags = "-optimize"
                        elif category == CmdCategory.FILE_INPUT_VERBOSE: flags = "-verbose"
                        elif category == CmdCategory.FILE_INPUT_BARE: flags = "-bare"
                        elif category == CmdCategory.FILE_INPUT_OPTIMIZE_VERBOSE: flags = "-optimize -verbose"
                        elif category == CmdCategory.FILE_INPUT_OPTIMIZE_BARE: flags = "-optimize -bare"
                        elif category == CmdCategory.PLATFORM_32BIT: flags = "-32bit"
                        elif category == CmdCategory.PLATFORM_AVR: flags = "-avr"
                        elif category == CmdCategory.USE_COMPILER:
                            flags = "-use-compiler"
                            if is_simple_case:
                                mounts = {filename: "#include <stdint.h>\nstruct test_inc { int32_t a; };"}
                                current_type_name = "struct test_inc"
                        elif category == CmdCategory.PLATFORM_CUSTOM_PTR:
                            val = "4,4" if is_simple_case else f"{random.choice([4,8,16])},{random.choice([4,8,16])}"
                            flags = f"-ptr {val}"
                        elif category == CmdCategory.PLATFORM_CUSTOM_INT:
                            val = "4,4" if is_simple_case else f"{FuzzHelper.get_int(-1, 0)},{FuzzHelper.get_int(17, 32)}"
                            flags = f"-int {val}"
                        elif category == CmdCategory.PLATFORM_CUSTOM_MULTIPLE:
                            ptr_val = "8,8" if is_simple_case else f"{random.choice([4,8])},{random.choice([4,8])}"
                            long_val = "8,8" if is_simple_case else f"{FuzzHelper.get_int(4,16)},{FuzzHelper.get_int(4,16)}"
                            flags = f"-ptr {ptr_val} -long {long_val}"
                        
                        command = cmd_template.format(flags=flags, filepath=filepath, type_name=current_type_name).strip()
                        command = re.sub(' +', ' ', command)

                    if not command:
                        continue

                    test_cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mounts
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")
                    continue
        return test_cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = StroptAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))