import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the command-line argument combinations for source-to-llm.
    The value of each enum member is a generic string representing the command structure.
    """
    BASIC = "source-to-llm -d <dir>"
    PATTERN = "source-to-llm --pattern <patterns...> -d <dir>"
    IGNORE = "source-to-llm --pattern <patterns...> --ignore <patterns...> -d <dir>"
    SEPARATOR = "source-to-llm --separator <string> -d <dir>"
    DIR = "source-to-llm --dir <path>"
    PATTERN_SEPARATOR = "source-to-llm --pattern <patterns...> --separator <string> -d <dir>"
    PATTERN_DIR = "source-to-llm --pattern <patterns...> --dir <path>"
    ALL_OPTIONS = "source-to-llm --pattern <patterns...> --ignore <patterns...> --separator <string> --dir <path>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class SourceToLlmAdapter(BaseRepoAdapter):
    """
    Adapter for the source-to-llm CLI tool.
    Handles installation and test case generation.
    """
    @property
    def base_image(self) -> str:
        """
        The tool requires Node.js >= 18.0.0.
        """
        return "node:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the oracle version of the tool according to framework rules.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ai-belov/source-to-llm.git && cd source-to-llm && npm install --silent && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent version of the tool according to framework rules.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && npm install --silent && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _create_mock_files(self, is_edge_case: bool) -> dict:
        """
        Helper to generate a dictionary of filenames and content for mounting.
        """
        files = {
            "main.js": "console.log('hello world');",
            "src/component.tsx": "export const MyComponent = () => <div />;",
            "src/utils/api.ts": "fetch('/api/data');",
            "docs/guide.md": "# Guide",
            "data.py": "print('hello from python')",
            "src/test/main.test.js": "assert(true);",
            "node_modules/some_lib/index.js": "// lib code"
        }
        if is_edge_case:
            files["empty.js"] = ""
            files["evil.ts"] = FuzzHelper.get_evil_string()
            evil_name = FuzzHelper.get_string(5, 10, chars="abc_-. ") + ".js"
            files[evil_name] = "file with a tricky name"
        return files

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # Make first case an edge case
                    cmd = ""
                    mount_files = self._create_mock_files(is_edge_case)
                    prep_script = ""
                    base_data_dir = "/test_data"

                    # Helper to safely quote arguments for the shell
                    def quote(s):
                        return f'"{s}"'

                    if category == CmdCategory.BASIC:
                        cmd = f"source-to-llm -d {base_data_dir}"

                    elif category == CmdCategory.PATTERN:
                        if is_edge_case:
                            patterns = [quote(FuzzHelper.get_evil_string())]
                        else:
                            num_patterns = random.randint(1, 2)
                            exts = random.sample(['py', 'md', 'js', 'ts', 'tsx'], k=num_patterns)
                            patterns = [quote(f'**/*.{ext}') for ext in exts]
                        cmd = f"source-to-llm --pattern {' '.join(patterns)} -d {base_data_dir}"

                    elif category == CmdCategory.IGNORE:
                        pattern_arg = quote('**/*.*s')
                        if is_edge_case:
                            ignore_arg = quote(FuzzHelper.get_evil_string())
                        else:
                            ignore_arg = quote('**/test/**')
                        cmd = f"source-to-llm --pattern {pattern_arg} --ignore {ignore_arg} -d {base_data_dir}"

                    elif category == CmdCategory.SEPARATOR:
                        if is_edge_case:
                            separator = quote(FuzzHelper.get_evil_string())
                        else:
                            separator = quote(f'==== {FuzzHelper.get_string(5, 15)} ====')
                        cmd = f"source-to-llm --separator {separator} -d {base_data_dir}"

                    elif category == CmdCategory.DIR:
                        sub_dir_name = "project_dir"
                        mount_files = {f"{sub_dir_name}/{k}": v for k, v in self._create_mock_files(is_edge_case).items()}
                        if is_edge_case:
                            target_dir = "non_existent_dir" if i % 2 == 0 else quote(FuzzHelper.get_evil_string())
                        else:
                            target_dir = f"{base_data_dir}/{sub_dir_name}"
                        cmd = f"source-to-llm --dir {target_dir}"

                    elif category == CmdCategory.PATTERN_SEPARATOR:
                        pattern_arg = quote('**/*.py')
                        if is_edge_case:
                            separator_arg = quote(FuzzHelper.get_evil_string())
                        else:
                            separator_arg = quote('---FILE---')
                        cmd = f"source-to-llm --pattern {pattern_arg} --separator {separator_arg} -d {base_data_dir}"

                    elif category == CmdCategory.PATTERN_DIR:
                        sub_dir_name = "project_dir_pd"
                        mount_files = {f"{sub_dir_name}/{k}": v for k, v in self._create_mock_files(is_edge_case).items()}
                        dir_arg = f"{base_data_dir}/{sub_dir_name}"
                        if is_edge_case:
                            pattern_arg = quote(FuzzHelper.get_evil_string())
                        else:
                            pattern_arg = quote('**/*.py')
                        cmd = f"source-to-llm --pattern {pattern_arg} --dir {dir_arg}"

                    elif category == CmdCategory.ALL_OPTIONS:
                        sub_dir_name = "project_dir_all"
                        mount_files = {f"{sub_dir_name}/{k}": v for k, v in self._create_mock_files(is_edge_case).items()}
                        dir_arg = f"{base_data_dir}/{sub_dir_name}"

                        if is_edge_case:
                            choice = i % 4
                            pattern_arg = quote('**/*.js')
                            ignore_arg = quote('**/test/**')
                            separator_arg = quote('---')
                            final_dir_arg = dir_arg
                            if choice == 0: pattern_arg = quote(FuzzHelper.get_evil_string())
                            elif choice == 1: ignore_arg = quote(FuzzHelper.get_evil_string())
                            elif choice == 2: separator_arg = quote(FuzzHelper.get_evil_string())
                            else: final_dir_arg = quote(FuzzHelper.get_evil_string())
                        else:
                            pattern_arg = f"{quote('**/*.js')} {quote('**/*.ts')}"
                            ignore_arg = quote('**/node_modules/**')
                            separator_arg = quote('--- File Boundary ---')
                            final_dir_arg = dir_arg

                        cmd = f"source-to-llm --pattern {pattern_arg} --ignore {ignore_arg} --separator {separator_arg} --dir {final_dir_arg}"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files=mount_files,
                            prep_script=prep_script
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
    adapter = SourceToLlmAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))