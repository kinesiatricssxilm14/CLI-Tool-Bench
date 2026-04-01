import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the command categories for the 'obfuscator' CLI tool.
    Each enum value is a generic template representing a specific usage pattern.
    """
    OBFUSCATE_BASIC = "obfuscator -in <dir> -out <dir> -key <key>"
    OBFUSCATE_LICENSE = "obfuscator -in <dir> -out <dir> -key <key> -license <file>"
    OBFUSCATE_PROTECT = "obfuscator -in <dir> -out <dir> -key <key> -protect <tokens>"
    OBFUSCATE_IGNORE = "obfuscator -in <dir> -out <dir> -key <key> -ignore <dirs>"
    OBFUSCATE_LICENSE_PROTECT = "obfuscator -in <dir> -out <dir> -key <key> -license <file> -protect <tokens>"
    OBFUSCATE_PROTECT_IGNORE = "obfuscator -in <dir> -out <dir> -key <key> -protect <tokens> -ignore <dirs>"
    OBFUSCATE_ALL_OPTS = "obfuscator -in <dir> -out <dir> -key <key> -license <file> -protect <tokens> -ignore <dirs>"
    DEOBFUSCATE_BASIC = "obfuscator -deobfuscate -in <dir> -out <dir> -key <key>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ObfuscatorAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Clones and installs the oracle (original) version of the tool."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/devOpifex/obfuscator.git && cd obfuscator && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the agent (local) version of the tool."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """Generates a list of test cases covering various command categories."""
        cases = []
        CASES_PER_CATEGORY = 50

        def generate_r_code():
            """Helper to generate a simple R script with identifiable variables."""
            func1 = FuzzHelper.get_string(4, 8, "abcdefg")
            func2 = FuzzHelper.get_string(4, 8, "hijklmn")
            return f"""
# Test R script
{func1} <- \\(x) {{
  x + {FuzzHelper.get_int(1, 100)}
}}
{func2} <- \\(x) {{
  {func1}(x * {FuzzHelper.get_int(1, 10)})
}}
result <- {func2}({FuzzHelper.get_int(1, 50)})
print(result)
""", [func1, func2]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The first case is a valid, simple one; the rest are more random/edge.
                    is_normal_case = (i == 0)
                    
                    mount_files = {}
                    prep_script = "mkdir -p /test_data/in /test_data/out"
                    
                    if category == CmdCategory.DEOBFUSCATE_BASIC:
                        obfuscated_content = "fOAaPAYPA=\\(xOA){xOA+0x1;};bOAMPAbPA=\\(xOA){fOAaPAYPA(xOA);};bOAMPAjPA=\\(xOA){bOAMPAbPA(xOA);};bOAMPAjPA(0x2a);"
                        mount_files["in/deobfuscate_me.R"] = obfuscated_content
                        key = "secret" if is_normal_case else FuzzHelper.get_string(1, 10)
                        cmd = f'obfuscator -deobfuscate -in /test_data/in -out /test_data/out -key "{key}"'

                    else: # All obfuscation cases
                        r_code, identifiers = generate_r_code()
                        
                        if is_normal_case:
                            file_content = r_code
                        elif i % 2 == 1:
                            file_content = FuzzHelper.get_evil_string()
                        else:
                            file_content = "" # Test empty file
                        
                        mount_files[f"in/script_{i}.R"] = file_content

                        key = FuzzHelper.get_string(5, 20) if is_normal_case else FuzzHelper.get_evil_string()
                        
                        # Use double quotes for all values to handle spaces, empty strings, and special characters.
                        cmd_parts = [f'obfuscator -in /test_data/in -out /test_data/out -key "{key}"']

                        if category in [CmdCategory.OBFUSCATE_LICENSE, CmdCategory.OBFUSCATE_LICENSE_PROTECT, CmdCategory.OBFUSCATE_ALL_OPTS]:
                            license_content = "Test License File\n(c) 2024" if is_normal_case else FuzzHelper.get_evil_string()
                            mount_files["license.txt"] = license_content
                            cmd_parts.append('-license "/test_data/license.txt"')

                        if category in [CmdCategory.OBFUSCATE_PROTECT, CmdCategory.OBFUSCATE_LICENSE_PROTECT, CmdCategory.OBFUSCATE_PROTECT_IGNORE, CmdCategory.OBFUSCATE_ALL_OPTS]:
                            if is_normal_case:
                                # Use a valid comma-separated list for the normal case
                                protect_val = ",".join(identifiers)
                            else:
                                protect_val = FuzzHelper.get_evil_string()
                            cmd_parts.append(f'-protect "{protect_val}"')

                        if category in [CmdCategory.OBFUSCATE_IGNORE, CmdCategory.OBFUSCATE_PROTECT_IGNORE, CmdCategory.OBFUSCATE_ALL_OPTS]:
                            ignore_dir = "renv"
                            prep_script += f" && mkdir -p /test_data/in/{ignore_dir}"
                            mount_files[f"in/{ignore_dir}/ignored.R"] = "print('This file should be ignored')"
                            ignore_val = ignore_dir if is_normal_case else FuzzHelper.get_evil_string()
                            cmd_parts.append(f'-ignore "{ignore_val}"')
                        
                        cmd = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files,
                        prep_script=prep_script
                    ))
                except Exception as e:
                    print(f"Warning: Skipped generating a test case for {category.name} due to an error: {e}")

        return cases

# =====================================================================
# 4. Main Entry Point (Strictly follow Rule 3)
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ObfuscatorAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))