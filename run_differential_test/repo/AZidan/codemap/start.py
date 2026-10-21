import os
import sys
import re
from enum import Enum
import random

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
    Enumerates the core functional command categories for the 'codemap' CLI tool.
    Each enum value is a generic template representing a command and its arguments.
    NOTE: 'watch' command is excluded as it's a long-running process not suitable for this test type.
    """
    INIT_DEFAULT = "codemap init ."
    INIT_LANG = "codemap init . -l <lang>"
    INIT_EXCLUDE = "codemap init . -e <pattern>"
    FIND_BASIC = "codemap find <query>"
    FIND_WITH_TYPE = "codemap find <query> -t <type>"
    FIND_FUZZY = "codemap find <query> --fuzzy"
    SHOW_FILE = "codemap show <filepath>"
    VALIDATE_ALL = "codemap validate"
    VALIDATE_FILE = "codemap validate <filepath>"
    UPDATE_ALL = "codemap update --all"
    UPDATE_FILE = "codemap update <filepath>"
    STATS = "codemap stats"
    LINES = "codemap lines <range_spec>"
    INSTALL_HOOKS = "codemap install-hooks"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CodemapAdapter(BaseRepoAdapter):
    """
    Adapter for the 'codemap' CLI tool, providing methods for installation,
    test case generation, and output sanitization.
    """

    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image. 'codemap' is a Python tool.
        """
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the raw stdout from the CLI tool to remove volatile data like
        hashes, paths, and timestamps for stable diffing.
        """
        sanitized = super().sanitize_stdout(raw_stdout)
        # Sanitize hashes which are volatile
        sanitized = re.sub(r"\(hash: [0-9a-f]+\)", "(hash: SANITIZED)", sanitized)
        sanitized = re.sub(r"hash: [a-f0-9]{8,}", "hash: SANITIZED", sanitized)
        # Sanitize root path which can differ
        sanitized = re.sub(r"Root: /.*", "Root: <WORKDIR>", sanitized)
        # Sanitize timestamps in JSON output
        sanitized = re.sub(r"\"(generated_at|indexed_at)\": \".*?\"", r'"\1": "<TIMESTAMP>"', sanitized)
        return sanitized

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of 'codemap' from its GitHub repository
        according to the strict framework rules.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/AZidan/codemap.git && cd codemap && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the development (agent) version of 'codemap' from the local source code
        according to the strict framework rules.
        """
        container.exec_run("mkdir -p /repo")
        # Use os.system for docker cp as it's a host-to-container operation
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested") != 0:
            raise Exception("Failed to copy agent code to container")
        
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for differential testing.
        It covers all command categories defined in CmdCategory, with a mix of
        normal and edge-case/fuzzing inputs.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        
        def get_sample_files() -> dict[str, str]:
            return {
                "main_app.py": "class MainApp:\n  def run(self):\n    print('Running')\n\ndef start_app():\n  app = MainApp()\n  app.run()",
                "utils/helpers.py": "def format_data(data):\n  return str(data).strip()",
                "README.md": "# Project\nThis is a test project.",
            }

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i % 2 == 1)
                    
                    cmd = ""
                    prep_script = ""
                    mount_files = get_sample_files()
                    
                    # Commands that require an index to be built first
                    prep_needed_commands = [
                        CmdCategory.FIND_BASIC, CmdCategory.FIND_WITH_TYPE, CmdCategory.FIND_FUZZY,
                        CmdCategory.SHOW_FILE, CmdCategory.VALIDATE_ALL, CmdCategory.VALIDATE_FILE,
                        CmdCategory.UPDATE_ALL, CmdCategory.UPDATE_FILE, CmdCategory.STATS, CmdCategory.LINES
                    ]

                    if category in prep_needed_commands:
                        prep_script = "cd /test_data && codemap init ."

                    # --- Command Generation Logic ---
                    # All commands should be run from /test_data where files are mounted
                    base_cmd_prefix = "cd /test_data && "

                    if category == CmdCategory.INIT_DEFAULT:
                        cmd = "codemap init ."
                        if is_edge_case:
                            mount_files = {"empty.py": "", "another/empty.js": ""}
                    
                    elif category == CmdCategory.INIT_LANG:
                        lang = "python" if not is_edge_case else FuzzHelper.get_string(1, 10)
                        cmd = f"codemap init . -l {lang}"

                    elif category == CmdCategory.INIT_EXCLUDE:
                        pattern = "'**/utils/**'" if not is_edge_case else f"'{FuzzHelper.get_string(5, 15)}'"
                        cmd = f"codemap init . -e {pattern}"

                    elif category == CmdCategory.FIND_BASIC:
                        query = "MainApp" if not is_edge_case else FuzzHelper.get_evil_string()
                        cmd = f"codemap find '{query}'"

                    elif category == CmdCategory.FIND_WITH_TYPE:
                        query = "run" if not is_edge_case else FuzzHelper.get_string(3, 8)
                        q_type = "method" if not is_edge_case else FuzzHelper.get_string(3, 8)
                        cmd = f"codemap find '{query}' -t {q_type}"

                    elif category == CmdCategory.FIND_FUZZY:
                        query = "main app" if not is_edge_case else FuzzHelper.get_evil_string()
                        cmd = f"codemap find '{query}' --fuzzy"

                    elif category == CmdCategory.SHOW_FILE:
                        filepath = "main_app.py" if not is_edge_case else FuzzHelper.get_filepath(ext=".py", absolute=False)
                        cmd = f"codemap show {filepath}"

                    elif category == CmdCategory.VALIDATE_ALL:
                        if is_edge_case:
                            prep_script = "cd /test_data && codemap init . && echo '# New line' >> main_app.py"
                        cmd = "codemap validate"

                    elif category == CmdCategory.VALIDATE_FILE:
                        filepath = "main_app.py"
                        if is_edge_case:
                            prep_script = f"cd /test_data && codemap init . && echo '# New line' >> {filepath}"
                        cmd = f"codemap validate {filepath}"

                    elif category == CmdCategory.UPDATE_ALL:
                        prep_script = "cd /test_data && codemap init . && echo '# File changed' >> main_app.py && echo 'new file' > new.txt"
                        cmd = "codemap update --all"

                    elif category == CmdCategory.UPDATE_FILE:
                        filepath = "utils/helpers.py"
                        prep_script = f"cd /test_data && codemap init . && echo '# Helper changed' >> {filepath}"
                        cmd = f"codemap update {filepath}"

                    elif category == CmdCategory.STATS:
                        cmd = "codemap stats"

                    elif category == CmdCategory.LINES:
                        if not is_edge_case:
                            range_spec = "main_app.py:1-3"
                        else:
                            range_spec = f"{FuzzHelper.get_filepath(absolute=False)}:{FuzzHelper.get_int(-10, 0)}-{FuzzHelper.get_int(100, 200)}"
                        cmd = f"codemap lines {range_spec}"

                    elif category == CmdCategory.INSTALL_HOOKS:
                        # This command needs a git repo to exist.
                        prep_script = "cd /test_data && git init"
                        cmd = "codemap install-hooks"

                    if cmd:
                        cases.append(TestCase(
                            command=base_cmd_prefix + cmd,
                            category=category.value,
                            prep_script=prep_script,
                            mount_files=mount_files
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for category {category.name}. Error: {e}")
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CodemapAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))