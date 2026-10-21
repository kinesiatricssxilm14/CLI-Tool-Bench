import os
import sys
import re
import random
from enum import Enum

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
    Enumerates the different command-line argument combinations for mp4analyzer.
    The value of each enum is a generic template representing the command structure.
    """
    BASIC = "mp4analyzer <file>"
    DETAILED = "mp4analyzer -d <file>"
    SUMMARY = "mp4analyzer -s <file>"
    EXPAND = "mp4analyzer -e <file>"
    DETAILED_EXPAND = "mp4analyzer -d -e <file>"
    OUTPUT_JSON = "mp4analyzer -o json <file>"
    OUTPUT_JSON_DETAILED = "mp4analyzer -o json -d <file>"
    JSON_PATH = "mp4analyzer -j <path> <file>"
    JSON_PATH_DETAILED_EXPAND = "mp4analyzer -j <path> -d -e <file>"
    NO_COLOR = "mp4analyzer --no-color <file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MP4AnalyzerAdapter(BaseRepoAdapter):
    # A minimal, valid MP4 file content (ftyp box).
    # This ensures the tool has a valid file to parse for non-edge-case tests.
    # The bytes are decoded using 'latin-1' to store them as a string,
    # which can represent any byte value.
    _MINIMAL_MP4_CONTENT = b'\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2avc1mp41'.decode('latin-1')

    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Removes volatile information from the tool's output."""
        # Sanitize file paths
        sanitized = re.sub(r"File: .*?\.mp4", "File: <file>", raw_stdout)
        # Sanitize usage message for consistency
        sanitized = re.sub(r"usage: mp4analyzer", "usage: <tool>", sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/andrewx-bu/mp4analyzer.git && cd mp4analyzer && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def generate_test_cases(self) -> list[TestCase]:
        test_cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The first case of each category is an edge case
                    is_edge_case = (i == 0)
                    file_name = f"test_{category.name.lower()}_{i}.mp4"
                    content_str = ""

                    if is_edge_case:
                        # For edge cases, use an empty file or a problematic string as content
                        content_str = random.choice(["", FuzzHelper.get_evil_string()])
                    else:
                        # For normal cases, use a minimal but valid MP4 file content
                        # to ensure the tool's main logic can be executed.
                        content_str = self._MINIMAL_MP4_CONTENT

                    mount_files = {file_name: content_str}
                    
                    # Build the command using the category's template
                    cmd_template = category.value
                    cmd = cmd_template.replace("<file>", f"/test_data/{file_name}")

                    if "<path>" in cmd_template:
                        json_path = ""
                        if is_edge_case:
                            # Fuzz the output path for edge cases
                            json_path = FuzzHelper.get_evil_string()
                        else:
                            json_path = f"/test_data/output_{category.name.lower()}_{i}.json"
                        # Use quotes to handle paths with spaces or special characters
                        cmd = cmd.replace("<path>", f"'{json_path}'")
                    
                    # For non-edge cases with multiple options, shuffle them to test order-insensitivity
                    if not is_edge_case and ' ' in category.value.split('<file>')[0].strip():
                        parts = cmd.split()
                        tool_name = parts[0]
                        file_arg = parts[-1]
                        options = parts[1:-1]
                        random.shuffle(options)
                        cmd = " ".join([tool_name] + options + [file_arg])

                    test_cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    # This ensures that if one test case generation fails, the whole process doesn't stop.
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")
        return test_cases

# =====================================================================
# 3. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MP4AnalyzerAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))