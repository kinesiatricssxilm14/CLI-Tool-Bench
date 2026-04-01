import os
import sys
import re
import string
from enum import Enum

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command structures of the 'sanitext' CLI tool.
    """
    STRING_ONLY = 'sanitext --string "<text>"'
    STRING_DETECT = 'sanitext --string "<text>" --detect'
    STRING_VERBOSE = 'sanitext --string "<text>" --verbose'
    STRING_VERY_VERBOSE = 'sanitext --string "<text>" --very-verbose'
    STRING_ALLOW_EMOJI = 'sanitext --string "<text>" --allow-emoji'
    STRING_ALLOW_CHARS = 'sanitext --string "<text>" --allow-chars "<chars>"'
    STRING_ALLOW_FILE = 'sanitext --string "<text>" --allow-file <file>'
    
    # Combinations
    STRING_DETECT_ALLOW_EMOJI = 'sanitext --string "<text>" --detect --allow-emoji'
    STRING_DETECT_ALLOW_CHARS = 'sanitext --string "<text>" --detect --allow-chars "<chars>"'
    STRING_DETECT_ALLOW_FILE = 'sanitext --string "<text>" --detect --allow-file <file>'
    STRING_ALLOW_CHARS_AND_EMOJI = 'sanitext --string "<text>" --allow-chars "<chars>" --allow-emoji'


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class SanitextAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/panispani/sanitext.git && cd sanitext && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo") != 0:
            raise Exception("Failed to copy agent code to container")
        
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        # The output of sanitext is deterministic, so no extra sanitization is needed.
        return super().sanitize_stdout(raw_stdout)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        
        def shell_escape(s: str) -> str:
            """Safely escapes a string for use in a shell command, wrapped in single quotes."""
            return "'" + s.replace("'", "'\\''") + "'"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Generate a mix of normal, evil, and empty strings for robust testing
                    if i == 0: # First case is a simple, valid one with non-ascii chars
                        base_str = "Héllø, “Wörld” 1×2=2 😊"
                    elif i == 1: # Second case is an evil string
                        base_str = FuzzHelper.get_evil_string()
                        # FIX: Null bytes from evil strings can break shell command execution.
                        base_str = base_str.replace('\x00', '')
                    elif i == 2: # Third case is an empty string
                        base_str = ""
                    else: # Other cases are random
                        base_str = f"{FuzzHelper.get_string(5, 15)} with some unicode «ταБЬℓσ»"

                    cmd = ""
                    mount_files = {}
                    
                    base_cmd = f"sanitext --string {shell_escape(base_str)}"

                    if category == CmdCategory.STRING_ONLY:
                        cmd = base_cmd
                    elif category == CmdCategory.STRING_DETECT:
                        cmd = f"{base_cmd} --detect"
                    elif category == CmdCategory.STRING_VERBOSE:
                        cmd = f"{base_cmd} --verbose"
                    elif category == CmdCategory.STRING_VERY_VERBOSE:
                        cmd = f"{base_cmd} --very-verbose"
                    elif category == CmdCategory.STRING_ALLOW_EMOJI:
                        cmd = f"{base_cmd} --allow-emoji"
                    elif category == CmdCategory.STRING_ALLOW_CHARS:
                        allow_chars_str = "αβγ" if i == 0 else FuzzHelper.get_string(1, 10, "αβγδε" + string.ascii_letters)
                        cmd = f"{base_cmd} --allow-chars {shell_escape(allow_chars_str)}"
                    elif category == CmdCategory.STRING_ALLOW_FILE:
                        file_name = f"allow_{category.name.lower()}_{i}.txt"
                        file_content = "øñç" if i == 0 else FuzzHelper.get_string(10, 20)
                        mount_files = {file_name: file_content}
                        cmd = f"{base_cmd} --allow-file /test_data/{file_name}"
                    elif category == CmdCategory.STRING_DETECT_ALLOW_EMOJI:
                        cmd = f"{base_cmd} --detect --allow-emoji"
                    elif category == CmdCategory.STRING_DETECT_ALLOW_CHARS:
                        allow_chars_str = "αβγ" if i == 0 else FuzzHelper.get_string(1, 10, "αβγδε" + string.ascii_letters)
                        cmd = f"{base_cmd} --detect --allow-chars {shell_escape(allow_chars_str)}"
                    elif category == CmdCategory.STRING_DETECT_ALLOW_FILE:
                        file_name = f"allow_detect_{category.name.lower()}_{i}.txt"
                        file_content = "øñç" if i == 0 else FuzzHelper.get_string(10, 20)
                        mount_files = {file_name: file_content}
                        cmd = f"{base_cmd} --detect --allow-file /test_data/{file_name}"
                    elif category == CmdCategory.STRING_ALLOW_CHARS_AND_EMOJI:
                        allow_chars_str = "αβγ" if i == 0 else FuzzHelper.get_string(1, 10, "αβγδε" + string.ascii_letters)
                        cmd = f"{base_cmd} --allow-chars {shell_escape(allow_chars_str)} --allow-emoji"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd.strip(),
                            category=category.value,
                            mount_files=mount_files
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = SanitextAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))