import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for gitree (gt) command categories.
    The value of each enum member is a generic command structure template.
    """
    # Basic Listing
    BASIC_LIST = "gt <path>"
    FULL_LIST = "gt --full <path>"
    EMOJI_LIST = "gt --emoji <path>"
    FULL_EMOJI_LIST = "gt -fe <path>"

    # Listing Options
    MAX_DEPTH = "gt --max-depth <N> <path>"
    MAX_ITEMS = "gt --max-items <N> <path>"
    SHOW_HIDDEN = "gt -a <path>"
    SHOW_SIZE = "gt -s <path>"
    FILES_FIRST = "gt --files-first <path>"
    ONLY_DIRS = "gt --no-files <path>"
    FILTER_CODE = "gt --code <path>"

    # Output/Export
    EXPORT_JSON = "gt -x <basename> --format json <path>"
    EXPORT_MD = "gt -x <basename> --format md <path>"
    
    # Zipping
    ZIP_BASIC = "gt -z <basename> <path>"
    ZIP_WITH_GITIGNORE = "gt -gz <basename> <path>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GitreeAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ShahzaibAhmad05/gitree.git && cd gitree && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    @staticmethod
    def _create_test_fs(use_gitignore: bool = False) -> dict:
        """Helper to create a file system structure for testing."""
        fs = {
            "main.py": "print('hello world')",
            "src/component.js": "export default () => {};",
            "src/styles.css": "body { color: blue; }",
            "data/input.csv": FuzzHelper.get_csv_string(5, 3),
            "data/config.json": FuzzHelper.get_json_string(3),
            ".hidden_file": "secret",
            "docs/README.md": "# Docs",
            "empty_dir/.placeholder": "" # This correctly creates the directory
        }
        
        if use_gitignore:
            fs[".gitignore"] = "*.csv\ndocs/\nempty_dir/"
            
        return fs

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        TEST_DATA_DIR = "/test_data"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)

                    use_gitignore = category == CmdCategory.ZIP_WITH_GITIGNORE
                    fs_content = self._create_test_fs(use_gitignore)
                    
                    if is_edge_case:
                        fs_content["evil'file.txt"] = FuzzHelper.get_evil_string()

                    cmd_prefix = f"cd {TEST_DATA_DIR} && gt"
                    path_arg = "."
                    cmd = ""

                    if category in [CmdCategory.BASIC_LIST, CmdCategory.FULL_LIST, CmdCategory.EMOJI_LIST, CmdCategory.FULL_EMOJI_LIST, CmdCategory.SHOW_HIDDEN, CmdCategory.SHOW_SIZE, CmdCategory.FILES_FIRST, CmdCategory.ONLY_DIRS, CmdCategory.FILTER_CODE]:
                        flag = {
                            CmdCategory.BASIC_LIST: "",
                            CmdCategory.FULL_LIST: "--full",
                            CmdCategory.EMOJI_LIST: "--emoji",
                            CmdCategory.FULL_EMOJI_LIST: "-fe",
                            CmdCategory.SHOW_HIDDEN: "-a",
                            CmdCategory.SHOW_SIZE: "-s",
                            CmdCategory.FILES_FIRST: "--files-first",
                            CmdCategory.ONLY_DIRS: "--no-files",
                            CmdCategory.FILTER_CODE: "--code"
                        }[category]
                        cmd = f"{cmd_prefix} {flag} {path_arg}"

                    elif category == CmdCategory.MAX_DEPTH:
                        val = FuzzHelper.get_int(-1, 0) if is_edge_case else FuzzHelper.get_int(1, 5)
                        cmd = f"{cmd_prefix} --max-depth {val} {path_arg}"
                    
                    elif category == CmdCategory.MAX_ITEMS:
                        val = FuzzHelper.get_int(-1, 0) if is_edge_case else FuzzHelper.get_int(1, 5)
                        cmd = f"{cmd_prefix} --max-items {val} {path_arg}"

                    elif category in [CmdCategory.EXPORT_JSON, CmdCategory.EXPORT_MD]:
                        format_type = "json" if category == CmdCategory.EXPORT_JSON else "md"
                        basename = f"output_{i}"
                        full_filename = f"{basename}.{format_type}"
                        cmd = f"{cmd_prefix} -x {basename} --format {format_type} {path_arg} && cat {full_filename}"

                    elif category in [CmdCategory.ZIP_BASIC, CmdCategory.ZIP_WITH_GITIGNORE]:
                        basename = f"archive_{i}"
                        flag = "-z" if category == CmdCategory.ZIP_BASIC else "-gz"
                        cmd = f"{cmd_prefix} {flag} {basename} {path_arg}"

                    if cmd:
                        cmd = ' '.join(cmd.split())
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files=fs_content
                        ))
                except Exception as e:
                    print(f"Skipping test case generation for {category.name} due to error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GitreeAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))