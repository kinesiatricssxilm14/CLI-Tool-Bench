import os
import sys
import re
import json
import random
import base64
from enum import Enum

# Add parent directories to sys.path to import framework modules
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for the core, non-interactive commands of the ccv tool.
    The TUI-related commands are excluded as they are not suitable for
    black-box differential testing.
    """
    SCAN = "ccv --scan"
    SUMMARY = "ccv --summary <file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CCVAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Clones from GitHub and installs the oracle version."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/swyxio/claude-compaction-viewer.git && cd claude-compaction-viewer && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the local agent code."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile output from the ccv tool.
        """
        # 1. First, remove ANSI color codes to get clean text.
        sanitized = super().sanitize_stdout(raw_stdout)

        # 2. Sanitize volatile parts of the --scan output table.
        # The tool displays /root as '~' and paths can be long or truncated.
        # This regex handles the path starting with '~' followed by our mock structure.
        sanitized = re.sub(r'~/\.claude/projects/[^\s]+', '[PROJECT_PATH]', sanitized)
        
        # 3. Replace truncated session UUIDs (e.g., 'a272d8b9…')
        sanitized = re.sub(r'\b[a-f0-9]{8}…', '[SESSION_ID]', sanitized)
        
        # 4. Replace duration strings (e.g., '4.1h', '1min', '30s')
        sanitized = re.sub(r'\b\d+(\.\d+)?(h|min|s)\b', '[DURATION]', sanitized)

        # 5. Sanitize fuzzed file paths that might appear in error messages for the --summary command
        sanitized = re.sub(r'/test_data/fuzz_summary_\d+\.jsonl', '[FUZZ_FILE_PATH]', sanitized)

        return sanitized

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The first case for each category is an edge case
                    is_edge_case = (i == 0)

                    if category == CmdCategory.SCAN:
                        # The --scan command depends on the file system state.
                        # We use prep_script to create mock project directories and files.
                        num_projects = FuzzHelper.get_int(1, 2)
                        script_lines = ["rm -rf /root/.claude", "mkdir -p /root/.claude/projects"]
                        
                        for p_idx in range(num_projects):
                            proj_name = f"proj_{p_idx}_{FuzzHelper.get_string(5, 10)}"
                            proj_path = f"/root/.claude/projects/{proj_name}"
                            script_lines.append(f"mkdir -p {proj_path}")
                            
                            num_sessions = FuzzHelper.get_int(0, 2)
                            for s_idx in range(num_sessions):
                                session_name = f"sess_{s_idx}.jsonl"
                                session_path = f"{proj_path}/{session_name}"
                                
                                if is_edge_case and s_idx == 0:
                                    # Edge cases: malformed content, empty files, non-json
                                    choice = random.randint(1, 3)
                                    if choice == 1: content = FuzzHelper.get_evil_string()
                                    elif choice == 2: content = ""
                                    else: content = self._generate_jsonl_content(is_malformed=True)
                                else:
                                    # Normal cases: valid jsonl with or without compactions
                                    has_compaction = random.choice([True, False])
                                    content = self._generate_jsonl_content(include_compaction=has_compaction)
                                
                                # Use base64 to safely echo content with special characters into the file
                                b64_content = base64.b64encode(content.encode('utf-8', 'replace')).decode('ascii')
                                script_lines.append(f"echo '{b64_content}' | base64 -d > {session_path}")

                        prep_script = " && ".join(script_lines)
                        
                        cases.append(TestCase(
                            command="ccv --scan",
                            category=category.value,
                            prep_script=prep_script
                        ))

                    elif category == CmdCategory.SUMMARY:
                        # The --summary command takes a file as input.
                        # We use mount_files to provide the content.
                        file_name = f"fuzz_summary_{i}.jsonl"
                        
                        if is_edge_case:
                            # Edge cases: malformed, empty, non-json
                            choice = random.randint(1, 3)
                            if choice == 1: content = FuzzHelper.get_evil_string()
                            elif choice == 2: content = ""
                            else: content = self._generate_jsonl_content(include_compaction=True, is_malformed=True)
                        else:
                            # Normal cases: must have compactions for summary to be meaningful,
                            # but also test files without them to ensure graceful handling.
                            has_compaction = (i % 2 == 0) # 50% of normal cases have compaction
                            content = self._generate_jsonl_content(include_compaction=has_compaction)

                        cases.append(TestCase(
                            command=f"ccv --summary /test_data/{file_name}",
                            category=category.value,
                            mount_files={file_name: content}
                        ))
                except Exception:
                    # Skip generating this specific test case on failure, but don't crash
                    continue
        return cases

    def _generate_jsonl_content(self, num_lines=10, include_compaction=False, is_malformed=False) -> str:
        """Helper to generate content for .jsonl session files."""
        lines = []
        for _ in range(FuzzHelper.get_int(2, num_lines)):
            msg_type = random.choice(['user', 'assistant', 'progress', 'system', 'file-history-snapshot'])
            line_obj = {
                "type": msg_type,
                "content": FuzzHelper.get_string(10, 50),
                "id": FuzzHelper.get_string(8, 8)
            }
            if msg_type == 'system':
                line_obj['subtype'] = FuzzHelper.get_string(5,10)
            lines.append(json.dumps(line_obj))

        if include_compaction:
            compaction_boundary = {
                "type": "system",
                "subtype": "compact_boundary",
                "compactMetadata": {
                    "trigger": random.choice(["auto", "manual"]),
                    "precompactionTokenCount": FuzzHelper.get_int(1000, 50000)
                }
            }
            compaction_summary = {
                "type": "user",
                "isCompactSummary": True,
                "content": f"This is a fuzzed summary: {FuzzHelper.get_string(50, 100)}"
            }
            if random.random() < 0.1: # Occasionally inject evil string into metadata
                compaction_boundary['compactMetadata']['trigger'] = FuzzHelper.get_evil_string()

            insert_pos = random.randint(0, len(lines)) if lines else 0
            lines.insert(insert_pos, json.dumps(compaction_boundary))
            lines.insert(insert_pos + 1, json.dumps(compaction_summary))

        content = "\n".join(lines)

        if is_malformed and content:
            # Corrupt the content in some way to create invalid JSONL
            pos_to_corrupt = random.randint(0, len(content) - 1)
            corrupted_char = random.choice(['"', '{', '}', ':', '\n', '\0', '\\'])
            content = content[:pos_to_corrupt] + corrupted_char + content[pos_to_corrupt + 1:]

        return content


# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CCVAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))