import os
import sys
import re
import json
import random
import string
from enum import Enum
from typing import List, Dict

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for the different test categories.
    cc-filter's behavior is primarily modified by stdin content and config files,
    not by command-line arguments. The command is always 'cc-filter' with
    input piped from stdin.
    """
    STDIN_FILTER_DEFAULT = "cc-filter < (stdin with default config)"
    STDIN_FILTER_PROJECT_CONFIG = "cc-filter < (stdin with project config.yaml)"
    STDIN_FILTER_JSON_HOOK = "cc-filter < (stdin with Claude Code JSON hook)"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CCFilterAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/wissem/cc-filter.git && cd cc-filter && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitize volatile output like timestamps, durations, and temporary file paths.
        """
        # Sanitize timestamps from logs, e.g., "2025/09/09 10:30:45"
        sanitized = re.sub(r'\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}', '[TIMESTAMP]', raw_stdout)
        # Sanitize ISO timestamps, e.g., "2025-09-09T10:30:45-07:00"
        sanitized = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[-|+]\d{2}:\d{2}', '[TIMESTAMP_ISO]', sanitized)
        # Sanitize processing duration, e.g., "Duration: 2.1ms"
        sanitized = re.sub(r'Duration: [\d\.]+m?s', 'Duration: [DURATION]', sanitized)
        # Sanitize temporary redacted file paths, e.g., "/tmp/claude/redacted/..."
        sanitized = re.sub(r'/tmp/claude/redacted/[^ \n\t]+', '[REDACTED_FILE_PATH]', sanitized)
        # Sanitize original file paths in headers, e.g., "Original: /path/to/your/file.swift"
        sanitized = re.sub(r'Original: [/\w\.-]+', 'Original: [SANITIZED_PATH]', sanitized)
        # Sanitize log file path
        sanitized = re.sub(r'~/\.cc-filter/filter\.log', '[LOG_FILE_PATH]', sanitized)
        
        return super().sanitize_stdout(sanitized)

    def _get_sensitive_string(self) -> str:
        """Helper to generate various sensitive strings based on README."""
        alphanumeric = string.ascii_letters + string.digits
        patterns = [
            f"api_key={FuzzHelper.get_string(16, 32)}",
            f"secret-key: {FuzzHelper.get_string(16, 32)}",
            f"access_token = '{FuzzHelper.get_string(20, 40)}'",
            f"password: \"{FuzzHelper.get_string(8, 16)}\"",
            f"postgres://user:{FuzzHelper.get_string(8,12)}@host.com:5432/dbname",
            f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{FuzzHelper.get_string(40, 60, chars='-_' + alphanumeric)}.{FuzzHelper.get_string(30, 50, chars='-_' + alphanumeric)}",
            f"sk-{FuzzHelper.get_string(48, 48, chars=alphanumeric)}",
            f"xoxb-{FuzzHelper.get_string(50, 50, chars=alphanumeric + '-')}",
            f"CLIENT_SECRET={FuzzHelper.get_string(32, 32, chars=alphanumeric).upper()}"
        ]
        return random.choice(patterns)

    def generate_test_cases(self) -> List[TestCase]:
        cases: List[TestCase] = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0) # Generate one edge case per category for stability
                
                content = ""
                mount_files: Dict[str, str] = {}
                
                try:
                    if category == CmdCategory.STDIN_FILTER_DEFAULT:
                        if is_edge_case:
                            content = FuzzHelper.get_evil_string()
                        else:
                            prefix = FuzzHelper.get_string(20, 50)
                            suffix = FuzzHelper.get_string(20, 50)
                            sensitive_part = self._get_sensitive_string()
                            content = f"{prefix}\n{sensitive_part}\n{suffix}"

                    elif category == CmdCategory.STDIN_FILTER_PROJECT_CONFIG:
                        # Generate content that matches the custom pattern
                        token = FuzzHelper.get_string(29, 29, chars=string.ascii_letters + string.digits + '_-')
                        content = f"My special key is PROJECT_TOKEN={token}"

                        # Generate config.yaml
                        if is_edge_case:
                            # Malformed YAML for robustness testing
                            config_content = FuzzHelper.get_evil_string()
                        else:
                            # Valid YAML to add a new pattern
                            config_content = """
patterns:
  - name: "project_token"
    regex: 'PROJECT_TOKEN=([a-zA-Z0-9-_]{29})'
    replacement: "***PROJECT_FILTERED***"
file_blocks:
  - "*.private"
"""
                        mount_files['config.yaml'] = config_content

                    elif category == CmdCategory.STDIN_FILTER_JSON_HOOK:
                        # Valid JSON hook
                        if is_edge_case:
                            prompt_content = FuzzHelper.get_evil_string()
                        else:
                            prompt_content = f"My prompt contains a secret: {self._get_sensitive_string()}"
                        
                        hook_data = {
                            "hookType": "UserPromptSubmit",
                            "input": { "prompt": prompt_content }
                        }
                        # Use evil string as content for one edge case
                        if is_edge_case and random.random() > 0.5:
                             content = FuzzHelper.get_evil_string()
                        else:
                             content = json.dumps(hook_data)

                    # Using an environment variable is a robust way to pass arbitrary
                    # string data to a shell command, avoiding complex escaping.
                    env_vars = {'FUZZ_INPUT': content}
                    command = 'echo "$FUZZ_INPUT" | cc-filter'

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files,
                        env_vars=env_vars
                    ))
                except Exception:
                    # Skip generating this test case if any error occurs
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CCFilterAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))