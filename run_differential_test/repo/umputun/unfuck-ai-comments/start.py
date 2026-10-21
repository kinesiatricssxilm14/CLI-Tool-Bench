import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of the script's location to the Python path
# to ensure that the BaseRepoAdapter and DiffTestEngine can be imported.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# Define the core functional command combinations to be tested.
# The value of each enum member is a generic string template of the command.
# =====================================================================
class CmdCategory(Enum):
    # Basic commands (default 'title' mode)
    RUN_DEFAULT = "unfuck-ai-comments run <path>"
    DIFF_DEFAULT = "unfuck-ai-comments diff <path>"
    PRINT_DEFAULT = "unfuck-ai-comments print <path>"

    # --full mode
    RUN_FULL = "unfuck-ai-comments --full run <path>"
    DIFF_FULL = "unfuck-ai-comments --full diff <path>"
    PRINT_FULL = "unfuck-ai-comments --full print <path>"

    # --fmt mode
    RUN_FMT = "unfuck-ai-comments --fmt run <path>"
    DIFF_FMT = "unfuck-ai-comments --fmt diff <path>"
    PRINT_FMT = "unfuck-ai-comments --fmt print <path>"

    # Combined modes
    RUN_FULL_FMT = "unfuck-ai-comments --full --fmt run <path>"
    DIFF_FULL_FMT = "unfuck-ai-comments --full --fmt diff <path>"
    PRINT_FULL_FMT = "unfuck-ai-comments --full --fmt print <path>"

    # File handling options
    DIFF_SKIP = "unfuck-ai-comments --skip <pattern> diff <path>"
    RUN_BACKUP = "unfuck-ai-comments --backup run <path>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class UnfuckAiCommentsAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image suitable for the Go tool."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle version from GitHub following the framework's strict rules."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/umputun/unfuck-ai-comments.git && cd unfuck-ai-comments && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the local agent code following the framework's strict rules."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def _generate_go_content(self, is_edge_case: bool) -> str:
        """
        Helper method to generate Go source file content for testing.
        """
        if is_edge_case:
            # 50% chance of an evil string (which is invalid Go code), 50% chance of an empty file
            return FuzzHelper.get_evil_string() if random.choice([True, False]) else ""

        # Normal case: generate a Go file with various comment styles
        comments_to_fix = [
            "// " + FuzzHelper.get_string(5, 15).upper(),
            "// " + FuzzHelper.get_string(5, 15).capitalize(),
            "// A Multi Word Title To Be Fixed.",
        ]
        comments_to_preserve = [
            "// TODO: " + FuzzHelper.get_string(10, 20),
            "// FIXME: " + FuzzHelper.get_string(10, 20),
            "// PascalCaseIdentifier and camelCaseOne should be preserved.",
            "// A comment with a directive // nolint:gosec",
        ]
        
        all_comments = comments_to_fix + comments_to_preserve
        random.shuffle(all_comments)
        body_comments = "\n    ".join(all_comments)

        return f'''
package main

import "fmt"

// This is a package-level comment, IT SHOULD BE PRESERVED.

// MyFunction is a test function. IT SHOULD BE PRESERVED.
func MyFunction(arg int) {{
    {body_comments}
    
    fmt.Println("Hello, World!")
}}

type MyStruct struct {{
    // A STRUCT FIELD COMMENT TO BE FIXED.
    Field int
}}
'''

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        tool_name = "unfuck-ai-comments"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0)
                
                try:
                    if category == CmdCategory.DIFF_SKIP:
                        file_to_process = "process_me.go"
                        file_to_skip = "skip_me.go"
                        content1 = self._generate_go_content(is_edge_case=False)
                        content2 = self._generate_go_content(is_edge_case=False)
                        
                        mount_files = {file_to_process: content1, file_to_skip: content2}
                        
                        skip_pattern = file_to_skip
                        if is_edge_case:
                            skip_pattern = FuzzHelper.get_evil_string()

                        safe_skip_pattern = skip_pattern.replace("'", "'\\''")
                        cmd = f"{tool_name} --skip '{safe_skip_pattern}' diff /test_data/..."
                        
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files=mount_files
                        ))
                        continue

                    file_name = f"fuzz_{i}.go"
                    content = self._generate_go_content(is_edge_case)
                    mount_files = {file_name: content}
                    target_path = f"/test_data/{file_name}"
                    
                    options = []
                    command_verb = ""

                    if 'FULL' in category.name:
                        options.append("--full")
                    if 'FMT' in category.name:
                        options.append("--fmt")
                    if category == CmdCategory.RUN_BACKUP:
                        options.append("--backup")

                    if 'RUN' in category.name:
                        command_verb = 'run'
                    elif 'DIFF' in category.name:
                        command_verb = 'diff'
                    elif 'PRINT' in category.name:
                        command_verb = 'print'

                    random.shuffle(options)
                    options_str = " ".join(options)
                    
                    cmd_parts = [tool_name, options_str, command_verb, target_path]
                    cmd = " ".join(filter(None, cmd_parts))

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Skipping test case generation for {category.name} due to error: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = UnfuckAiCommentsAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))