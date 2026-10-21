import os
import sys
import re
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional commands of the 'malang' compiler.
    The value of each enum member is a generic template representing the command structure.
    """
    EXECUTE = "malang <file>"
    PRINT_TOKENS = "malang -tokens <file>"
    PRINT_AST = "malang -ast <file>"
    PRINT_GOCODE = "malang -gocode <file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MalangAdapter(BaseRepoAdapter):
    """
    Adapter for the 'malang' compiler, providing logic for installation
    and test case generation.
    """

    @property
    def base_image(self) -> str:
        """The 'malang' tool is written in Go."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline version of 'malang' from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Rohith04MVK/malang.git && cd malang && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Copies the local agent code into the container and installs it.
        """
        container.exec_run("mkdir -p /repo")
        # Correctly copy the local agent directory into the container's /repo directory
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the raw stdout from the CLI tool.
        Compiler error messages with line/column numbers are deterministic and
        should not be sanitized. No other volatile output is expected.
        """
        return super().sanitize_stdout(raw_stdout)

    def _generate_malang_code(self, is_edge_case: bool) -> str:
        """
        Helper function to generate Malang source code for fuzzing.
        """
        if is_edge_case:
            # 50% chance of an evil string, 50% chance of an empty file
            return FuzzHelper.get_evil_string() if FuzzHelper.get_int(0, 1) == 0 else ""

        # Generate a small program with a mix of language constructs
        lines = []
        num_constructs = FuzzHelper.get_int(1, 3)

        for _ in range(num_constructs):
            try:
                construct_type = FuzzHelper.get_int(1, 4)
                
                if construct_type == 1:  # Basic output
                    content = FuzzHelper.get_string(1, 25).replace('"', '\\"')
                    lines.append(f'parayu("{content}")')

                elif construct_type == 2:  # If-else statement
                    var_name = "num" + FuzzHelper.get_string(1, 3, chars="abcdefghijklmnopqrstuvwxyz")
                    val = FuzzHelper.get_int(0, 100)
                    lines.append(f'{var_name} = {val}')
                    lines.append(f'ith_sheriyano ({var_name} > 50) enkil {{ parayu("greater") }} alle {{ parayu("lesser") }}')

                elif construct_type == 3:  # While loop
                    lines.append('counter = 0')
                    loop_limit = FuzzHelper.get_int(1, 3)
                    lines.append(f'ellam_sheriyano (counter < {loop_limit}) enkil {{')
                    lines.append('    parayu("looping...")')
                    lines.append('    counter = counter + 1')
                    lines.append('}')

                elif construct_type == 4:  # For loop
                    start = FuzzHelper.get_int(1, 3)
                    end = start + FuzzHelper.get_int(1, 2)
                    lines.append(f'oron_ayi i edukk ({start}..{end}) {{')
                    lines.append('    parayu("for loop iter")')
                    lines.append('}')
            except Exception:
                # If any generation step fails, just skip it and continue
                continue
        
        return "\n".join(lines)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for differential testing.
        It covers normal execution, AST/token/gocode printing, and includes
        both valid and malformed/edge-case inputs.
        """
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # First case is normal, rest have a chance to be edge cases
                    is_edge_case = (i > 0 and FuzzHelper.get_int(1, 5) == 1)
                    
                    file_name = f"fuzz_{category.name.lower()}_{i}.malang"
                    content = self._generate_malang_code(is_edge_case)
                    
                    # The tool expects a file path as its primary argument
                    file_arg = f"/test_data/{file_name}"
                    cmd = ""

                    if category == CmdCategory.EXECUTE:
                        cmd = f"malang {file_arg}"
                    elif category == CmdCategory.PRINT_TOKENS:
                        cmd = f"malang -tokens {file_arg}"
                    elif category == CmdCategory.PRINT_AST:
                        cmd = f"malang -ast {file_arg}"
                    elif category == CmdCategory.PRINT_GOCODE:
                        cmd = f"malang -gocode {file_arg}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception:
                    # Failsafe to prevent crashing the entire test generation
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MalangAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))