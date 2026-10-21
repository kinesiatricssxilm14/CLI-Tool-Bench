import os
import sys
import re
import random
import string
import shlex
from enum import Enum

# Add the parent directory of the script's location to the Python path
# to ensure that BaseRepoAdapter and DiffTestEngine can be imported.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command structures to be tested for the 'ted' CLI tool.
    The value of each enum member is a generic template string representing the command.
    """
    PROGRAM_FROM_FILE = "ted -f <program_file> <input_file>"
    PROGRAM_AS_ARG = "ted <program_string> <input_file>"
    NO_PRINT = "ted -n -f <program_file> <input_file>"
    WITH_VAR = "ted --var <k=v> -f <program_file> <input_file>"
    WITH_SEPARATOR = "ted -s <sep> -f <program_file> <input_file>"
    WITH_DEBUG = "ted --debug -f <program_file> <input_file>"
    # A complex combination of flags
    NO_PRINT_WITH_VAR_AND_SEPARATOR = "ted -n --var <k=v> -s <sep> -f <program_file> <input_file>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class TedAdapter(BaseRepoAdapter):
    """
    Adapter for the 'ted' CLI tool, providing methods for installation,
    output sanitization, and test case generation.
    """
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image for the testing environment.
        'go 1.22' is required by the tool's README.
        """
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of 'ted' from its GitHub repository.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ahalbert/ted.git && cd ted && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent (local version to be tested) of 'ted'.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the raw stdout to remove volatile parts like parser error line/column numbers.
        This is crucial for stable diffing, especially when using --debug or when parsers fail.
        """
        # Sanitize parser error messages like "line 1:2: ..." to "line X:Y: ..."
        sanitized = re.sub(r'line \d+:\d+:', 'line X:Y:', raw_stdout)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def _generate_ted_program(self, is_edge_case: bool) -> str:
        """
        Helper function to generate 'ted' program content for fuzzing.
        Generates plausible programs for normal cases and malformed ones for edge cases.
        """
        if is_edge_case:
            # For edge cases, generate potentially invalid or tricky syntax
            return FuzzHelper.get_evil_string()

        # For normal cases, generate a syntactically plausible program
        try:
            r1 = FuzzHelper.get_string(3, 5, string.ascii_lowercase)
            r2 = FuzzHelper.get_string(3, 5, string.ascii_lowercase)
            s1 = FuzzHelper.get_string(2, 4, string.ascii_lowercase)
            s2 = FuzzHelper.get_string(2, 4, string.ascii_lowercase)

            templates = [
                f"/{r1}/ {{ print }}",
                f"/{r1}/ -> /{r2}/ {{ println $0 }}",
                f"/{r1}/ {{ start capture -> /{r2}/ }} /{r2}/ {{ stop capture print }}",
                f"/{r1}/ {{ do s/{s1}/{s2}/g }}",
                f"BEGIN {{ println \"Starting\" }} /{r1}/ {{ print }} END {{ println \"Finished\" }}",
                f"state1: /{r1}/ -> state2 state2: /{r2}/ {{ print -> state1 }}"
            ]
            return random.choice(templates)
        except Exception:
            # Fallback in case of any error
            return "/.*/ { print }"

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a comprehensive list of test cases covering various command categories.
        """
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                # The last case in each category is an edge case to test robustness
                is_edge_case = (i == CASES_PER_CATEGORY - 1)

                try:
                    # 1. Generate Input File Content
                    if is_edge_case:
                        input_content = "" if random.random() > 0.5 else FuzzHelper.get_evil_string()
                    else:
                        input_content = "\n".join([FuzzHelper.get_string(5, 20) for _ in range(random.randint(5, 15))])

                    # 2. Generate Program Content
                    program_content = self._generate_ted_program(is_edge_case)

                    # 3. Prepare files and command parts
                    mount_files = {}
                    cmd_parts = ["ted"]

                    # 4. Handle flags
                    if category in [CmdCategory.NO_PRINT, CmdCategory.NO_PRINT_WITH_VAR_AND_SEPARATOR]:
                        cmd_parts.append("-n")

                    if category in [CmdCategory.WITH_VAR, CmdCategory.NO_PRINT_WITH_VAR_AND_SEPARATOR]:
                        if is_edge_case:
                            key = FuzzHelper.get_evil_string().split('=')[0].replace(' ', '_')
                            val = FuzzHelper.get_evil_string().replace(' ', '_')
                        else:
                            key = FuzzHelper.get_string(3, 8, string.ascii_letters)
                            val = FuzzHelper.get_string(3, 15, string.ascii_letters + string.digits)
                        if not key: key = "default_key"
                        cmd_parts.extend(["--var", f"{key}={val}"])

                    if category in [CmdCategory.WITH_SEPARATOR, CmdCategory.NO_PRINT_WITH_VAR_AND_SEPARATOR]:
                        if is_edge_case:
                            sep = FuzzHelper.get_evil_string()
                        else:
                            sep = random.choice([",", ";", "|", "---"])
                        cmd_parts.extend(["-s", sep])

                    if category == CmdCategory.WITH_DEBUG:
                        cmd_parts.append("--debug")

                    # 5. Handle program source (argument vs file)
                    if category == CmdCategory.PROGRAM_AS_ARG:
                        cmd_parts.append(program_content)
                    else:
                        program_file_name = f"program_{i}.fsa"
                        mount_files[program_file_name] = program_content
                        cmd_parts.extend(["-f", f"/test_data/{program_file_name}"])

                    # 6. Add input file
                    input_file_name = f"input_{i}.txt"
                    mount_files[input_file_name] = input_content
                    cmd_parts.append(f"/test_data/{input_file_name}")
                    
                    # 7. Assemble the final command string, quoting each part for shell safety
                    command = " ".join(shlex.quote(p) for p in cmd_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # If case generation fails, just skip it to not crash the whole process
                    continue
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = TedAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))