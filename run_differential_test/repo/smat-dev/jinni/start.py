import os
import sys
import re
from enum import Enum
import random
import string

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
    Defines the command categories for the jinni CLI tool.
    The value of each enum member is a generic command structure template.
    --no-copy is added to all commands to ensure clean, deterministic output.
    """
    BASIC = "jinni --no-copy <path>"
    MULTIPLE_PATHS = "jinni --no-copy <path1> <path2>"
    LIST_ONLY = "jinni --no-copy --list-only <path>"
    OUTPUT_FILE = "jinni --no-copy --output <file> <path>"
    WITH_ROOT = "jinni --no-copy --root <dir> <path>"
    SIZE_LIMIT = "jinni --no-copy --size-limit-mb <MB> <path>"
    OVERRIDES = "jinni --no-copy --overrides <file> <path>"
    EXCLUDE_NOT = "jinni --no-copy --not <keyword> <path>"
    EXCLUDE_NOT_IN = "jinni --no-copy --not-in <path:keywords> <path>"
    EXCLUDE_NOT_FILES = "jinni --no-copy --not-files <pattern> <path>"
    KEEP_ONLY = "jinni --no-copy --keep-only <modules> <path>"
    COMPLEX_EXCLUSION = "jinni --no-copy --not <keyword> --not-files <pattern> <path>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class JinniAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/smat-dev/jinni.git && cd jinni && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent version of the tool from the local path."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        
        # Common setup for most test cases
        prep_script = "mkdir -p /test_data/proj/src /test_data/proj/docs /test_data/proj/tests /test_data/proj/data /test_data/output_dir"
        base_path = "/test_data/proj"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0)
                
                # Reset mount files for each test case to ensure independence
                mount_files = {
                    'proj/main.py': 'print("hello world from main")',
                    'proj/src/app.py': 'import os\n\nclass App: pass',
                    'proj/docs/README.md': '# Project Documentation',
                    'proj/tests/test_app.py': 'def test_app(): assert True',
                    'proj/data/data.csv': 'id,value\n1,a\n2,b',
                    'proj/.gitignore': 'data/\n*.log\n__pycache__/',
                }
                
                cmd = ""
                
                try:
                    if category == CmdCategory.BASIC:
                        if is_edge_case:
                            # Test with a file containing potentially problematic content
                            mount_files['proj/src/evil.txt'] = FuzzHelper.get_evil_string()
                        cmd = f"jinni --no-copy {base_path}"

                    elif category == CmdCategory.MULTIPLE_PATHS:
                        if is_edge_case:
                            # Test with one existing and one non-existing path
                            cmd = f"jinni --no-copy {base_path}/src /non_existent_dir"
                        else:
                            cmd = f"jinni --no-copy {base_path}/src {base_path}/docs"

                    elif category == CmdCategory.LIST_ONLY:
                        if is_edge_case:
                            # Test with a file having special characters in its name
                            mount_files['proj/src/!@#$.tmp'] = 'special name'
                        cmd = f"jinni --no-copy --list-only {base_path}"

                    elif category == CmdCategory.OUTPUT_FILE:
                        output_file = f"/test_data/output_dir/out_{i}.txt"
                        if is_edge_case:
                            # Test writing to a directory with no permissions
                            cmd = f"jinni --no-copy --output /root/no_permission/out.txt {base_path}"
                        else:
                            cmd = f"jinni --no-copy --output {output_file} {base_path}"

                    elif category == CmdCategory.WITH_ROOT:
                        if is_edge_case:
                            # Test with a non-existent root directory
                            cmd = f"jinni --no-copy --root /non_existent_root {base_path}"
                        else:
                            # Test with a valid root, paths in output should be relative to it
                            cmd = f"jinni --no-copy --root /test_data {base_path}"

                    elif category == CmdCategory.SIZE_LIMIT:
                        if is_edge_case:
                            # Test with an invalid (negative) size limit
                            limit = FuzzHelper.get_int(-10, 0)
                        else:
                            limit = 1 # A valid, small limit
                        cmd = f"jinni --no-copy --size-limit-mb {limit} {base_path}"

                    elif category == CmdCategory.OVERRIDES:
                        rules_file = "/test_data/override.rules"
                        if is_edge_case:
                            # Test with a rules file containing junk content
                            mount_files['override.rules'] = FuzzHelper.get_evil_string()
                        else:
                            # Test with a valid overrides file
                            mount_files['override.rules'] = "*.py\n!tests/"
                        cmd = f"jinni --no-copy --overrides {rules_file} {base_path}"

                    elif category == CmdCategory.EXCLUDE_NOT:
                        if is_edge_case:
                            # Test with a keyword that looks like a path traversal attempt
                            keyword = "../../etc/passwd"
                        else:
                            keyword = "tests"
                        cmd = f"jinni --no-copy --not '{keyword}' {base_path}"

                    elif category == CmdCategory.EXCLUDE_NOT_IN:
                        if is_edge_case:
                            # Test with a malformed spec (missing colon)
                            spec = FuzzHelper.get_string(5, 20)
                        else:
                            spec = "src:app"
                        cmd = f"jinni --no-copy --not-in '{spec}' {base_path}"

                    elif category == CmdCategory.EXCLUDE_NOT_FILES:
                        if is_edge_case:
                            # Test with a very long, nonsensical pattern
                            pattern = "A" * 100
                        else:
                            pattern = "*.md"
                        cmd = f"jinni --no-copy --not-files '{pattern}' {base_path}"

                    elif category == CmdCategory.KEEP_ONLY:
                        if is_edge_case:
                            # Test with an incorrectly formatted list (semicolon instead of comma)
                            modules = "src;docs"
                        else:
                            modules = "src,docs"
                        cmd = f"jinni --no-copy --keep-only {modules} {base_path}"

                    elif category == CmdCategory.COMPLEX_EXCLUSION:
                        if is_edge_case:
                            # Exclude a valid directory and a valid file pattern
                            keyword = "data"
                            pattern = "*.py"
                        else:
                            keyword = "tests"
                            pattern = "*.md"
                        cmd = f"jinni --no-copy --not '{keyword}' --not-files '{pattern}' {base_path}"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            prep_script=prep_script,
                            mount_files=mount_files
                        ))
                except Exception as e:
                    # Skip generating this specific test case if any error occurs
                    print(f"Skipping case generation for {category} due to error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = JinniAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))