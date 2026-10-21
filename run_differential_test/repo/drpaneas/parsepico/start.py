import os
import sys
import re
import random
import string
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures, exhaust all combinations)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line flag combinations for the parsepico tool.
    The value of each enum member is a generic template string representing the command structure.
    """
    CART_ONLY = "parsepico --cart <file>"
    CART_CLEAN = "parsepico --cart <file> --clean"
    CART_3 = "parsepico --cart <file> --3"
    CART_4 = "parsepico --cart <file> --4"
    CART_3_4 = "parsepico --cart <file> --3 --4"
    CART_3_CLEAN = "parsepico --cart <file> --3 --clean"
    CART_4_CLEAN = "parsepico --cart <file> --4 --clean"
    CART_3_4_CLEAN = "parsepico --cart <file> --3 --4 --clean"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ParsepicoAdapter(BaseRepoAdapter):
    """
    Adapter for the parsepico CLI tool, providing methods for installation,
    test case generation, and output sanitization.
    """

    def _generate_p8_content(self, valid_hex=True, complete=True, gfx_lines=64, map_lines=32) -> str:
        """
        Helper to generate content for a .p8 file, for both normal and edge cases.
        Reduced line counts to keep tests fast.
        """
        header = "pico-8 cartridge // http://www.pico-8.com\nversion 29\n__lua__\n-- fuzzed code\n"
        
        sections = {}

        # Generate GFX data
        gfx_data = []
        for _ in range(gfx_lines):
            if valid_hex:
                line = "".join(random.choices(string.hexdigits.lower(), k=128))
            else:
                line = FuzzHelper.get_string(128, 128, chars=string.hexdigits.lower() + "g-zG-Z!@#$%^&*()")
            gfx_data.append(line)
        sections["__gfx__"] = "\n".join(gfx_data) + "\n"

        # Generate MAP data
        map_data = []
        for _ in range(map_lines):
            if valid_hex:
                line = "".join(random.choices(string.hexdigits.lower(), k=256))
            else:
                line = FuzzHelper.get_string(256, 256, chars=string.hexdigits.lower() + "g-zG-Z!@#$%^&*()")
            map_data.append(line)
        sections["__map__"] = "\n".join(map_data) + "\n"
        
        # Add dummy sections for completeness
        sections["__gff__"] = "0000\n"
        sections["__sfx__"] = "0000100000000000000000000000000000000000000000000000000000000000\n" * 2
        sections["__music__"] = "00 00 00 00 00\n" * 2

        content = header
        
        if complete:
            # Generate a structurally valid file
            for section_name, section_data in sections.items():
                content += f"{section_name}\n{section_data}"
        else:
            # Randomly omit sections for edge case testing
            if sections:
                num_sections_to_include = random.randint(0, len(sections))
                if num_sections_to_include > 0:
                    for section_name, section_data in random.sample(list(sections.items()), k=num_sections_to_include):
                        content += f"{section_name}\n{section_data}"
                
        return content

    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile information from the tool's output.
        The default cart path is user-specific and should be normalized.
        """
        sanitized = re.sub(r'/Users/pgeorgia/Library/Application Support/pico-8/carts/test\.p8', '<DEFAULT_CART_PATH>', raw_stdout)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/drpaneas/parsepico.git && cd parsepico && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0: raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0: raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The first case of each category is an edge case, the rest are normal
                    is_edge_case = (i == 0)
                    
                    file_name = f"fuzz_cart_{category.name.lower()}_{i}.p8"
                    cart_path = f"/test_data/{file_name}"
                    content = ""

                    if is_edge_case:
                        # Generate boundary, malicious, or malformed inputs
                        edge_type = random.randint(0, 3)
                        if edge_type == 0:
                            # Completely random evil string as file content
                            content = FuzzHelper.get_evil_string()
                        elif edge_type == 1:
                            # Empty file
                            content = ""
                        elif edge_type == 2:
                            # Incomplete file structure (missing sections)
                            content = self._generate_p8_content(complete=False)
                        else:
                            # Structurally complete but with malformed hex data
                            content = self._generate_p8_content(valid_hex=False)
                    else:
                        # Generate a valid .p8 file for normal execution
                        content = self._generate_p8_content(valid_hex=True, complete=True)

                    mount_files = {file_name: content}

                    # Assemble command based on category template
                    cmd = category.value.replace("<file>", cart_path)

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Failsafe to prevent the entire generation from crashing
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ParsepicoAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))