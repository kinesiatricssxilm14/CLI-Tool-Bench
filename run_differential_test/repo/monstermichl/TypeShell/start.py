import os
import sys
import re
import random
from enum import Enum
from typing import List

# Add the parent directory of the 'repo' directory to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine from the root of the project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command combinations for typeshell.
    The primary function is transpiling a .tsh file to a target shell language.
    """
    TRANSPILE_TO_BATCH = "typeshell -i <file> -t batch -o <dir>"
    TRANSPILE_TO_BASH = "typeshell -i <file> -t bash -o <dir>"
    TRANSPILE_TO_BOTH = "typeshell -i <file> -t batch -t bash -o <dir>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class TypeShellAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/monstermichl/TypeShell.git && cd TypeShell && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies the local agent code into the container and installs it."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Removes volatile information like file paths and line numbers from Go panic traces.
        This is crucial for preventing false positives in differential testing.
        Example: '.../tsh.go:73 +0x50b' -> '...<FILE>:<LINE> +0x50b'
        """
        sanitized_output = re.sub(r'\s+[^\s]+\.go:\d+', ' <FILE>:<LINE>', raw_stdout)
        return super().sanitize_stdout(sanitized_output)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def _generate_typeshell_code(self) -> str:
        """Helper function to generate plausible TypeShell code snippets."""
        valid_snippets = [
            'print("hello world")',
            'a := 10\nb := 20\nc := a + b\nprint("Sum is: ", c)',
            'x := "Type"\ny := "Shell"\nprint(x + y)',
            'if 10 > 5 { print("true") } else { print("false") }',
            'for i := 0; i < 3; i++ { print("loop ", i) }',
            'func add(a int, b int) int { return a + b }\nprint(add(5, 7))',
            's := []string{"a", "b", "c"}\nfor i, v := range s { print(i, v) }',
            'write("/test_data/output.txt", "content from typeshell")',
            's := []int{1,2,3}\nprint(len(s))',
        ]
        return random.choice(valid_snippets)

    def generate_test_cases(self) -> List[TestCase]:
        """
        Generates a list of test cases, mixing normal usage with edge cases.
        """
        cases: List[TestCase] = []
        CASES_PER_CATEGORY = 50
        prep_script = "mkdir -p /test_output"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Generate 3 normal cases and 2 edge cases per category
                    is_normal_case = i < 3
                    
                    file_name = f"test_{category.name.lower()}_{i}.tsh"
                    input_file_path = f"/test_data/{file_name}"
                    output_dir = "/test_output"
                    
                    # Base command arguments
                    if category == CmdCategory.TRANSPILE_TO_BATCH:
                        cmd_args = [f"-i {input_file_path}", "-t batch", f"-o {output_dir}"]
                    elif category == CmdCategory.TRANSPILE_TO_BASH:
                        cmd_args = [f"-i {input_file_path}", "-t bash", f"-o {output_dir}"]
                    elif category == CmdCategory.TRANSPILE_TO_BOTH:
                        cmd_args = [f"-i {input_file_path}", "-t batch", "-t bash", f"-o {output_dir}"]
                    else:
                        continue

                    content = self._generate_typeshell_code()

                    if not is_normal_case:
                        fuzz_type = random.choice(['content', 'input_path', 'output_path', 'target'])
                        
                        if fuzz_type == 'content':
                            content = FuzzHelper.get_evil_string()
                        elif fuzz_type == 'input_path':
                            for j, arg in enumerate(cmd_args):
                                if arg.startswith("-i "):
                                    cmd_args[j] = f"-i {FuzzHelper.get_evil_string()}"
                                    break
                        elif fuzz_type == 'output_path':
                            for j, arg in enumerate(cmd_args):
                                if arg.startswith("-o "):
                                    cmd_args[j] = f"-o {FuzzHelper.get_evil_string()}"
                                    break
                        elif fuzz_type == 'target':
                            target_indices = [j for j, arg in enumerate(cmd_args) if arg.startswith('-t ')]
                            if target_indices:
                                idx_to_fuzz = random.choice(target_indices)
                                cmd_args[idx_to_fuzz] = f"-t {FuzzHelper.get_string(3, 8)}"
                    
                    command = f"typeshell {' '.join(cmd_args)}"

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for category {category.name}: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = TypeShellAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))