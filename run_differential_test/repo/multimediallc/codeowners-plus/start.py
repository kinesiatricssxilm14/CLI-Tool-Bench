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

class CmdCategory(Enum):
    """
    Enumerates the core functional commands of the CLI tool.
    The binary is named 'cli' after installation via 'go install'.
    """
    UNOWNED = "cli unowned"
    VALIDATE = "cli validate"
    OWNER_SINGLE_FILE = "cli owner <file>"
    OWNER_MULTIPLE_FILES = "cli owner <file1> <file2> ..."

class CodeownersPlusAdapter(BaseRepoAdapter):
    """
    Adapter for the multimediallc/codeowners-plus CLI tool.
    """
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        This adheres to the framework's strict installation rules by using 'go install .'
        after navigating to the correct subdirectory containing the main package.
        """
        cmd = (
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/multimediallc/codeowners-plus.git && "
            "cd codeowners-plus/tools/cli && "
            "go install ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent (version to be tested) from the local filesystem.
        This adheres to the framework's strict installation rules.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested/tools/cli && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for fuzzing the CLI tool.
        It covers normal functionality and edge cases for each command category.
        """
        cases = []
        
        # The tool requires a git repository context to function correctly.
        prep_script = (
            "cd /test_data/test_repo && "
            "git init && "
            "git config user.email 'test@example.com' && "
            "git config user.name 'Test User' && "
            "git add . && "
            "git commit -m 'Initial commit' --no-gpg-sign"
        )

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # Generate one edge case per category
                    
                    file_structure = {
                        "test_repo/src/main.go": "package main\nfunc main() {}",
                        "test_repo/src/utils/helpers.js": "function hello() { return 'world'; }",
                        "test_repo/docs/guide.md": "# Guide",
                        "test_repo/config.json": "{ \"key\": \"value\" }",
                        "test_repo/unowned.txt": "This file should be unowned.",
                    }

                    if is_edge_case:
                        # Use evil strings or empty content for edge cases
                        codeowners_content = FuzzHelper.get_evil_string()
                    else:
                        # A valid, reasonable .codeowners file
                        codeowners_content = (
                            "# Default owner\n"
                            "* @default-owner\n"
                            "*.go @go-team\n"
                            "**/*.js @js-team @another-js-dev\n"
                            "docs/ @docs-team\n"
                            "& **/config.json @security-auditor\n"
                        )
                    
                    file_structure["test_repo/.codeowners"] = codeowners_content
                    
                    # The command will be executed from within the test repo directory.
                    # The installed binary is named 'cli'.
                    cmd_prefix = "cd /test_data/test_repo && cli"
                    cmd = ""

                    if category == CmdCategory.UNOWNED:
                        cmd = f"{cmd_prefix} unowned"

                    elif category == CmdCategory.VALIDATE:
                        cmd = f"{cmd_prefix} validate"

                    elif category == CmdCategory.OWNER_SINGLE_FILE:
                        if is_edge_case:
                            # Test with non-existent file or a fuzzed relative path
                            target_file = FuzzHelper.get_filepath(ext=".tmp", absolute=False)
                        else:
                            # Test with a known, existing file
                            target_file = random.choice(["src/main.go", "docs/guide.md", "unowned.txt"])
                        cmd = f"{cmd_prefix} owner {target_file}"

                    elif category == CmdCategory.OWNER_MULTIPLE_FILES:
                        if is_edge_case:
                            files = [
                                "src/main.go", 
                                FuzzHelper.get_filepath(ext=".sh", absolute=False), # Fuzzed relative path
                                "non_existent_file.txt"
                            ]
                        else:
                            files = ["src/main.go", "src/utils/helpers.js", "docs/guide.md"]
                        
                        cmd = f"{cmd_prefix} owner {' '.join(files)}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=file_structure,
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.value}: {e}")
        return cases

if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CodeownersPlusAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))