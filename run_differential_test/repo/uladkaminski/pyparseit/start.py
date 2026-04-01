import os
import sys
import re
import random
from enum import Enum
from typing import List, Dict

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command combinations for pyparseit.
    The values are used for categorizing tests in the final report.
    """
    FILE_INPUT_NO_FILTER = "pyparseit <file>"
    FILE_INPUT_WITH_LANG = "pyparseit <file> -l <lang>"
    STRING_INPUT_NO_FILTER = "pyparseit -s <string>"
    STRING_INPUT_WITH_LANG = "pyparseit -s <string> -l <lang>"
    FILE_INPUT_WITH_OUTPUT = "pyparseit <file> -o <outfile>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class PyParseitAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the oracle version of the tool in the container.
        Added '--no-input' to pip to prevent it from hanging in non-interactive environments.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/uladkaminski/pyparseit.git && cd pyparseit && pip install --no-input ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent (local) version of the tool in the container.
        Added '--no-input' to pip to prevent it from hanging in non-interactive environments.
        """
        container.exec_run("mkdir -p /repo")
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested") != 0:
            raise Exception("Failed to copy agent code to container")
        cmd = "cd /repo/repo_to_be_tested && pip install --no-input ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def _generate_markdown_content(self, is_evil=False) -> str:
        """
        Helper function to generate random Markdown content with code blocks.
        """
        if is_evil:
            return "" if random.random() < 0.5 else FuzzHelper.get_evil_string()

        langs = ["python", "javascript", "json", "rust", "go", "bash", FuzzHelper.get_string(3, 7)]
        content_parts = [FuzzHelper.get_string(10, 50)]

        num_blocks = random.randint(1, 3)
        for _ in range(num_blocks):
            lang = random.choice(langs)
            lines = random.randint(1, 5)
            code_content = "\n".join([f"line_{i} = {FuzzHelper.get_string(5, 20)};" for i in range(lines)])
            
            content_parts.append(f"\n\n```{lang}\n{code_content}\n```\n")
            content_parts.append(FuzzHelper.get_string(10, 50))

        return "".join(content_parts)

    def generate_test_cases(self) -> List[TestCase]:
        cases: List[TestCase] = []
        KNOWN_LANGS = ["python", "javascript", "json", "rust", "go", "bash"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    
                    input_file_name = f"input_{category.name.lower()}_{i}.md"
                    content = self._generate_markdown_content(is_evil=is_edge_case)
                    mount_files = {input_file_name: content}
                    input_arg_path = f"/test_data/{input_file_name}"
                    
                    cmd_parts = ["pyparseit"]
                    
                    # LOGIC FIX: Assemble options BEFORE the positional argument.
                    # The CLI format is `pyparseit [options] input`.

                    # 1. Add all options based on category
                    if category in [CmdCategory.STRING_INPUT_NO_FILTER, CmdCategory.STRING_INPUT_WITH_LANG]:
                        cmd_parts.append("-s")

                    if category in [CmdCategory.FILE_INPUT_WITH_LANG, CmdCategory.STRING_INPUT_WITH_LANG]:
                        if is_edge_case:
                            lang = FuzzHelper.get_evil_string()
                        else:
                            lang = random.choice(KNOWN_LANGS) if random.random() < 0.7 else FuzzHelper.get_string(3, 8)
                        cmd_parts.append(f"-l '{lang}'")

                    if category == CmdCategory.FILE_INPUT_WITH_OUTPUT:
                        output_file = f"output_{category.name.lower()}_{i}.txt"
                        cmd_parts.append(f"-o /test_data/{output_file}")

                    # 2. Add the final positional 'input' argument
                    if category in [CmdCategory.STRING_INPUT_NO_FILTER, CmdCategory.STRING_INPUT_WITH_LANG]:
                        # For string input, the argument is the file content, expanded by the shell.
                        # This robustly handles special characters and newlines.
                        input_argument = f'"$(cat {input_arg_path})"'
                    else:
                        # For file input, the argument is simply the path.
                        input_argument = input_arg_path
                    
                    cmd_parts.append(input_argument)
                    
                    command = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")
                    continue
        return cases

# =====================================================================
# 3. Main Entry Point (Strictly follow the framework's convention)
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = PyParseitAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))