import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of the 'final_differential_test' directory to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine from the root of the project
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures, exhaust all combinations)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for prompt-scanner command categories.
    The value of each enum member is a generic command structure template.
    """
    # Basic Scans
    BASIC_SCAN = "prompt-scanner <path>"
    JSON_OUTPUT = "prompt-scanner --json <path>"
    SCAN_CONFIGS = "prompt-scanner --scan-configs <path>"
    GREEDY_SCAN = "prompt-scanner --greedy <path>"
    USE_GITIGNORE = "prompt-scanner --use-gitignore <path>"

    # Parameterized Scans
    MIN_LEN = "prompt-scanner --min-len <N> <path>"
    VAR_KEYWORDS = "prompt-scanner --var-keywords <kws> <path>"
    CONTENT_KEYWORDS = "prompt-scanner --content-keywords <kws> <path>"
    PLACEHOLDER_PATTERNS = "prompt-scanner --placeholder-patterns <ptns> <path>"

    # Output Formatting
    NO_FILEPATH = "prompt-scanner --no-filepath <path>"
    NO_LINENUMBER = "prompt-scanner --no-linenumber <path>"
    NO_FILEPATH_NO_LINENUMBER = "prompt-scanner --no-filepath --no-linenumber <path>"

    # Complex Combinations
    COMPLEX_1 = "prompt-scanner --json --scan-configs --greedy <path>"
    COMPLEX_2 = "prompt-scanner --min-len <N> --use-gitignore --var-keywords <kws> <path>"
    COMPLEX_3 = "prompt-scanner --json --no-filepath --no-linenumber <path>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class PromptScannerAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the base Docker image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Install the oracle version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/alexferrari88/prompt-scanner.git && cd prompt-scanner && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Install the agent version of the tool from the local path."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitize stdout to remove noise. For this tool, the file paths in the output
        should be consistent if we always scan the same target directory (e.g., /test_data).
        Therefore, no special sanitization is needed beyond the default ANSI code removal.
        """
        return super().sanitize_stdout(raw_stdout)

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """Generate a list of TestCase objects for differential testing."""
        cases = []
        CASES_PER_CATEGORY = 50
        TEST_DIR_PATH = "/test_data/project"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    mount_files = self._create_test_project_files(is_edge_case, i)
                    options = []

                    # Helper to safely quote a value for a shell command argument using the --flag='value' format.
                    def safe_quote(value: str) -> str:
                        # Escapes single quotes for shell's single-quoted string: ' -> '\''
                        return f"'{str(value).replace("'", "'\\'")}'"

                    if category == CmdCategory.BASIC_SCAN:
                        pass
                    elif category == CmdCategory.JSON_OUTPUT:
                        options.append("--json")
                    elif category == CmdCategory.SCAN_CONFIGS:
                        options.append("--scan-configs")
                    elif category == CmdCategory.GREEDY_SCAN:
                        options.append("--greedy")
                    elif category == CmdCategory.USE_GITIGNORE:
                        options.append("--use-gitignore")
                    elif category == CmdCategory.MIN_LEN:
                        val = FuzzHelper.get_int(-10, 0) if is_edge_case else FuzzHelper.get_int(10, 100)
                        options.append(f"--min-len={val}")
                    elif category == CmdCategory.VAR_KEYWORDS:
                        val = self._get_fuzzed_keywords(is_edge_case)
                        options.append(f"--var-keywords={safe_quote(val)}")
                    elif category == CmdCategory.CONTENT_KEYWORDS:
                        val = self._get_fuzzed_keywords(is_edge_case)
                        options.append(f"--content-keywords={safe_quote(val)}")
                    elif category == CmdCategory.PLACEHOLDER_PATTERNS:
                        val = "(*" if is_edge_case else r"\{\{[^}]*\}\},<[^>]*>"
                        options.append(f"--placeholder-patterns={safe_quote(val)}")
                    elif category == CmdCategory.NO_FILEPATH:
                        options.append("--no-filepath")
                    elif category == CmdCategory.NO_LINENUMBER:
                        options.append("--no-linenumber")
                    elif category == CmdCategory.NO_FILEPATH_NO_LINENUMBER:
                        options.extend(["--no-filepath", "--no-linenumber"])
                    elif category == CmdCategory.COMPLEX_1:
                        options.extend(["--json", "--scan-configs", "--greedy"])
                    elif category == CmdCategory.COMPLEX_2:
                        min_len_val = FuzzHelper.get_int(-5, 5) if is_edge_case else FuzzHelper.get_int(20, 80)
                        keywords_val = self._get_fuzzed_keywords(is_edge_case)
                        options.extend([f"--min-len={min_len_val}", "--use-gitignore", f"--var-keywords={safe_quote(keywords_val)}"])
                    elif category == CmdCategory.COMPLEX_3:
                        options.extend(["--json", "--no-filepath", "--no-linenumber"])

                    random.shuffle(options)
                    full_cmd = " ".join(["prompt-scanner"] + options + [TEST_DIR_PATH])

                    cases.append(TestCase(
                        command=full_cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")
        return cases

    def _create_test_project_files(self, is_edge_case: bool, seed: int) -> dict:
        """Helper to generate a dictionary of files for mounting into the container."""
        files = {}
        base_path = "project"

        if is_edge_case:
            # Generate boundary/malicious file content.
            # FuzzHelper.get_evil_string() may include null bytes, which are handled by the test engine's error capture.
            evil_content = FuzzHelper.get_evil_string()
            files[f"{base_path}/main.py"] = f"prompt = '''{evil_content}'''"
            # Ensure JSON is valid even with evil content by escaping it.
            safe_evil_for_json = evil_content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
            files[f"{base_path}/config.json"] = '{"key": "act as a ' + safe_evil_for_json[:50] + '"}'
            files[f"{base_path}/empty.js"] = ""
        else:
            # Generate normal file content with and without prompts
            files[f"{base_path}/main.py"] = (
                "import os\n\n"
                "# This is a valid prompt\n"
                f"system_prompt_{seed} = 'You are an expert coding assistant. Your task is to help users write better code.'\n\n"
                "unrelated_string = 'This is just a regular string, not a prompt.'"
            )
            files[f"{base_path}/service.go"] = (
                'package main\n\n'
                'const anotherPrompt = "Summarize the following article for a 12-year-old reader."\n'
            )
            files[f"{base_path}/prompts.yaml"] = (
                "prompts:\n"
                "  - role: system\n"
                "    content: 'Act as a wise, unbiased career coach. Answer the following question from the user.'\n"
            )
            files[f"{base_path}/.env"] = "API_PROMPT=translate the following text to French:"
            files[f"{base_path}/.gitignore"] = "ignored_dir/\n*.log"
            files[f"{base_path}/ignored_dir/should_be_skipped.py"] = "prompt = 'This should not be found if gitignore is used'"
            files[f"{base_path}/activity.log"] = "some log data"

        return files

    def _get_fuzzed_keywords(self, is_edge_case: bool) -> str:
        """Helper to generate fuzzed comma-separated keywords."""
        if is_edge_case:
            return random.choice([
                "",                          # Empty string
                ",",                         # Just a comma
                "key1,,key3",                # Empty item in list
                FuzzHelper.get_string(100, 120), # Very long keyword
                "key with spaces,another key"  # Keywords with spaces
            ])
        else:
            # Create a clean, comma-separated list of keywords
            return ",".join(
                [FuzzHelper.get_string(5, 10, chars="abcdefghijklmnopqrstuvwxyz_") for _ in range(random.randint(2, 4))]
            )


if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = PromptScannerAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))