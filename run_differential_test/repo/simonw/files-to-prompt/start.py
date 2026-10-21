import os
import sys
import re
from enum import Enum
import random
import string

# Add the parent directory of the 'final_differential_test' directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line argument combinations for files-to-prompt.
    The value of each enum member is a generic string template of the command.
    """
    # Basic and Formatting Options
    BASIC = "files-to-prompt <paths>"
    CXML_FORMAT = "files-to-prompt <paths> --cxml"
    MARKDOWN_FORMAT = "files-to-prompt <paths> --markdown"
    LINE_NUMBERS = "files-to-prompt <paths> --line-numbers"
    CXML_WITH_LINE_NUMBERS = "files-to-prompt <paths> --cxml --line-numbers"
    MARKDOWN_WITH_LINE_NUMBERS = "files-to-prompt <paths> --markdown --line-numbers"

    # Filtering Options
    FILTER_EXTENSION = "files-to-prompt <paths> -e <ext>"
    FILTER_MULTIPLE_EXTENSIONS = "files-to-prompt <paths> -e <ext1> -e <ext2>"
    INCLUDE_HIDDEN = "files-to-prompt <paths> --include-hidden"
    IGNORE_PATTERN = "files-to-prompt <paths> --ignore <pattern>"
    IGNORE_PATTERN_FILES_ONLY = "files-to-prompt <paths> --ignore <pattern> --ignore-files-only"
    IGNORE_GITIGNORE = "files-to-prompt <paths> --ignore-gitignore"

    # I/O and Stdin Options
    OUTPUT_TO_FILE = "files-to-prompt <paths> -o <file>"
    STDIN_BASIC = "cat paths.txt | files-to-prompt"
    STDIN_NULL = "cat paths.bin | files-to-prompt --null"
    STDIN_WITH_ARGS = "cat paths.txt | files-to-prompt <path_arg>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class FilesToPromptAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/simonw/files-to-prompt.git && cd files-to-prompt && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _create_test_files(self) -> dict:
        """Helper to generate a standard set of files for testing."""
        return {
            "test_dir/file1.py": "import os\n\ndef main():\n    print('Hello from Python')\n",
            "test_dir/file2.txt": "This is a simple text file.\nIt has multiple lines.",
            "test_dir/subdir/file3.md": "# Markdown File\n\n- Item 1\n- Item 2\n```\ncode block\n```",
            "test_dir/.hidden_file": "key=value",
            "test_dir/temp.log": "INFO: Application started.",
            "test_dir/another.log": "DEBUG: Another log entry.",
            ".gitignore": "*.log\n.hidden_file",
            "test_dir/file with spaces.txt": "Content for file with spaces.",
            "empty_file.txt": "",
        }

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        base_path = "/test_data/test_dir"
        mount_files = self._create_test_files()

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    cmd = ""
                    prep_script = ""
                    
                    # Use a simple f-string with single quotes for arguments.
                    # The framework's `_escape_shell_cmd` handles the outer `sh -c` quoting.
                    def shell_quote(s):
                        return f"'{s}'"

                    if category in [
                        CmdCategory.BASIC, CmdCategory.CXML_FORMAT, CmdCategory.MARKDOWN_FORMAT,
                        CmdCategory.LINE_NUMBERS, CmdCategory.CXML_WITH_LINE_NUMBERS,
                        CmdCategory.MARKDOWN_WITH_LINE_NUMBERS, CmdCategory.INCLUDE_HIDDEN,
                        CmdCategory.IGNORE_GITIGNORE
                    ]:
                        opts = {
                            CmdCategory.BASIC: "",
                            CmdCategory.CXML_FORMAT: "--cxml",
                            CmdCategory.MARKDOWN_FORMAT: "--markdown",
                            CmdCategory.LINE_NUMBERS: "--line-numbers",
                            CmdCategory.CXML_WITH_LINE_NUMBERS: "--cxml --line-numbers",
                            CmdCategory.MARKDOWN_WITH_LINE_NUMBERS: "--markdown --line-numbers",
                            CmdCategory.INCLUDE_HIDDEN: "--include-hidden",
                            CmdCategory.IGNORE_GITIGNORE: "--ignore-gitignore",
                        }
                        cmd = f"files-to-prompt {base_path} {opts[category]}"

                    elif category == CmdCategory.FILTER_EXTENSION:
                        ext = random.choice(["py", "txt", "md", "nonexistent", FuzzHelper.get_string(1, 5)])
                        cmd = f"files-to-prompt {base_path} -e {shell_quote(ext)}"

                    elif category == CmdCategory.FILTER_MULTIPLE_EXTENSIONS:
                        ext1 = random.choice(["py", "txt"])
                        ext2 = random.choice(["md", "log", "nonexistent"])
                        cmd = f"files-to-prompt {base_path} -e {shell_quote(ext1)} -e {shell_quote(ext2)}"

                    elif category == CmdCategory.IGNORE_PATTERN:
                        pattern = random.choice(["*.log", "subdir", "file*", FuzzHelper.get_string(3, 8), ""])
                        cmd = f"files-to-prompt {base_path} --ignore {shell_quote(pattern)}"

                    elif category == CmdCategory.IGNORE_PATTERN_FILES_ONLY:
                        pattern = random.choice(["subdir", "*.log", "file*"])
                        cmd = f"files-to-prompt {base_path} --ignore {shell_quote(pattern)} --ignore-files-only"

                    elif category == CmdCategory.OUTPUT_TO_FILE:
                        output_file = f"/test_data/output_{i}.txt"
                        cmd = f"files-to-prompt {base_path} -o {output_file}"

                    elif category == CmdCategory.STDIN_BASIC:
                        paths_to_pipe = ["/test_data/test_dir/file1.py", "/test_data/test_dir/file2.txt"]
                        quoted_paths = " ".join([shell_quote(p) for p in paths_to_pipe])
                        prep_script = f"printf '%s\\n' {quoted_paths} > /tmp/paths.txt"
                        cmd = "cat /tmp/paths.txt | files-to-prompt"

                    elif category == CmdCategory.STDIN_NULL:
                        paths_to_pipe = ["/test_data/test_dir/file with spaces.txt", "/test_data/empty_file.txt"]
                        quoted_paths = " ".join([shell_quote(p) for p in paths_to_pipe])
                        prep_script = f"printf '%s\\0' {quoted_paths} > /tmp/paths.bin"
                        cmd = "cat /tmp/paths.bin | files-to-prompt --null"

                    elif category == CmdCategory.STDIN_WITH_ARGS:
                        path_arg = "/test_data/test_dir/file1.py"
                        paths_to_pipe = ["/test_data/test_dir/file2.txt"]
                        quoted_paths = " ".join([shell_quote(p) for p in paths_to_pipe])
                        prep_script = f"printf '%s\\n' {quoted_paths} > /tmp/paths.txt"
                        cmd = f"cat /tmp/paths.txt | files-to-prompt {path_arg}"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd.strip(),
                            category=category.value,
                            mount_files=mount_files,
                            prep_script=prep_script
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = FilesToPromptAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))