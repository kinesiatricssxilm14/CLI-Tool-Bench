import os
import sys
import re
import random
from enum import Enum

# Ensure the script can find the base classes
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional commands of the 'daad' CLI tool.
    'run' is the default command when a file is provided.
    """
    RUN = "daad <file>"
    TOKENIZE = "daad tokenize <file>"
    AST = "daad ast <file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class DaadAdapter(BaseRepoAdapter):
    """
    Adapter for the 'daad' Arabic programming language interpreter.
    """

    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image for the testing environment.
        The tool is built with Go, so a Go image is used.
        """
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of 'daad' from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/daadLang/daad.git && cd daad && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent version of 'daad' from the local filesystem.
        """
        container.exec_run("mkdir -p /repo")
        # Use os.system for simplicity as per framework design, assuming docker cp is in PATH
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Removes volatile information like line/column numbers from the output
        to prevent false positives in differential testing.
        """
        # Sanitize token positions like [1:1], [2:5], etc.
        sanitized = re.sub(r'\[\d+:\d+\]', '[L:C]', raw_stdout)
        # Sanitize error messages like "خطأ في السطر 5:"
        sanitized = re.sub(r'في السطر \d+', 'في السطر L', sanitized)
        # Sanitize AST position info, e.g., (Pos: 1, Line: 1, Col: 1)
        sanitized = re.sub(r'\(Pos: \d+, Line: \d+, Col: \d+\)', '(Pos:P, Line:L, Col:C)', sanitized)
        # A more generic cleanup for any remaining line/col numbers
        sanitized = re.sub(r'Line: \d+', 'Line: L', sanitized)
        sanitized = re.sub(r'Col: \d+', 'Col: C', sanitized)
        
        # Call the parent's sanitizer to remove ANSI codes
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def _generate_daad_code(self, is_edge_case: bool) -> str:
        """
        Helper function to generate 'daad' language source code for testing.
        """
        try:
            if is_edge_case:
                # Edge/malicious cases
                choice = random.randint(0, 4)
                if choice == 0:
                    return ""  # Empty file
                elif choice == 1:
                    # Malicious string injection into a print statement
                    evil_str = FuzzHelper.get_evil_string()
                    # Escape backslashes, then double quotes, and remove null bytes for safety.
                    escaped_evil_str = evil_str.replace('\\', '\\\\').replace('"', '\\"').replace('\x00', '')
                    return f'اطبع("{escaped_evil_str}")'
                elif choice == 2:
                    # Syntax error: missing colon
                    return "إذا صحيح\n    اطبع(\"خطأ\")"
                elif choice == 3:
                    # Semantic error: undefined variable
                    return "اطبع(متغير_غير_معرف)"
                else:
                    # File with only whitespace
                    return " \t\n\r \t "
            else:
                # Normal, valid code
                choice = random.randint(0, 4)
                if choice == 0:
                    # Simple print with fuzzed string
                    return f'اطبع("مرحبا {FuzzHelper.get_string(5, 15)}")'
                elif choice == 1:
                    # Arithmetic operations
                    a = FuzzHelper.get_int(1, 100)
                    b = FuzzHelper.get_int(1, 100)
                    return f"متغير = {a} + {b}\nاطبع(متغير)"
                elif choice == 2:
                    # Conditional logic
                    num = FuzzHelper.get_int(-100, 100)
                    return f"""
درجة = {num}
إذا درجة > 0:
    اطبع("موجب")
وإذا درجة == 0:
    اطبع("صفر")
وإلا:
    اطبع("سالب")
"""
                elif choice == 3:
                    # 'for' loop
                    return """
أسماء = ["علي", "أحمد", "محمد"]
لكل اسم في أسماء:
    اطبع("مرحبا يا " + اسم)
"""
                else:
                    # 'while' loop
                    count = FuzzHelper.get_int(1, 5)
                    return f"""
س = 0
طالما س < {count}:
    اطبع(س)
    س = س + 1
"""
        except Exception:
            # Fallback on any generation error to ensure the process doesn't stop
            return 'اطبع("Hello World from fallback")'

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases for each command category.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        file_extensions = [".daad", ".dad", ".ض"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                # Ensure the first case is an edge case, the rest are normal.
                is_edge_case = (i == 0)
                
                code_content = self._generate_daad_code(is_edge_case)
                
                ext = random.choice(file_extensions)
                file_name = f"test_{category.name.lower()}_{i}{ext}"
                
                # Assemble the command robustly using the enum value as a template.
                cmd_template = category.value
                command = cmd_template.replace("<file>", f"/test_data/{file_name}")

                cases.append(TestCase(
                    command=command,
                    category=category.value,
                    mount_files={file_name: code_content}
                ))
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = DaadAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))