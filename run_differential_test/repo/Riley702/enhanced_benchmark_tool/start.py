import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures, exhaust all combinations)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command structures for ebt-profile.
    """
    PROFILE_CSV = "ebt-profile --input <file>"
    PROFILE_CSV_JSON = "ebt-profile --input <file> --json"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class EbtProfileAdapter(BaseRepoAdapter):
    """
    Adapter for the enhanced_benchmark_tool.
    """
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the Python tool.
        """
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile output like floating-point numbers and memory usage
        to ensure stable diffs.
        """
        # Sanitize floating point numbers (e.g., in stats tables: 12.345, .5)
        sanitized = re.sub(r'\b\d+\.\d+\b', '[FLOAT]', raw_stdout)
        # Sanitize memory usage strings (e.g., "123.4 KB", "500 bytes")
        sanitized = re.sub(r'\d+(\.\d+)?\s*(?:KB|MB|GB|bytes)', '[MEM]', sanitized, flags=re.IGNORECASE)
        # Sanitize object memory addresses (e.g., <... at 0x...>)
        sanitized = re.sub(r'<[^>]+ at 0x[0-9a-fA-F]+>', '[OBJECT]', sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Riley702/enhanced_benchmark_tool.git && cd enhanced_benchmark_tool && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the development (agent) version of the tool from the local directory.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a comprehensive list of test cases covering normal and edge scenarios.
        """
        cases = []
        CASES_PER_CATEGORY = 50 # This will generate 2 normal + 3 edge cases per category

        for category in CmdCategory:
            # --- Normal Cases ---
            # Case 1: Standard CSV
            try:
                file_name = f"fuzz_normal_1_{category.name}.csv"
                content = FuzzHelper.get_csv_string(rows=10, cols=5)
                cmd = category.value.replace("<file>", f"/test_data/{file_name}")
                cases.append(TestCase(command=cmd, category=category.value, mount_files={file_name: content}))
            except Exception: continue

            # Case 2: Wider CSV
            try:
                file_name = f"fuzz_normal_2_{category.name}.csv"
                content = FuzzHelper.get_csv_string(rows=5, cols=10)
                cmd = category.value.replace("<file>", f"/test_data/{file_name}")
                cases.append(TestCase(command=cmd, category=category.value, mount_files={file_name: content}))
            except Exception: continue

            # --- Edge Cases ---
            # Case 3: Empty file
            try:
                file_name = f"fuzz_edge_empty_{category.name}.csv"
                content = ""
                cmd = category.value.replace("<file>", f"/test_data/{file_name}")
                cases.append(TestCase(command=cmd, category=category.value, mount_files={file_name: content}))
            except Exception: continue

            # Case 4: Malformed CSV (ragged rows)
            try:
                file_name = f"fuzz_edge_ragged_{category.name}.csv"
                lines = [",".join(FuzzHelper.get_string(4, 8) for _ in range(5))] # Header
                lines.append(",".join(FuzzHelper.get_string(5, 15) for _ in range(5))) # Good row
                lines.append(",".join(FuzzHelper.get_string(5, 15) for _ in range(3))) # Bad row (fewer columns)
                lines.append(",".join(FuzzHelper.get_string(5, 15) for _ in range(6))) # Bad row (more columns)
                content = "\n".join(lines)
                cmd = category.value.replace("<file>", f"/test_data/{file_name}")
                cases.append(TestCase(command=cmd, category=category.value, mount_files={file_name: content}))
            except Exception: continue

            # Case 5: CSV with evil strings in cells
            try:
                file_name = f"fuzz_edge_evil_cell_{category.name}.csv"
                cols = 4
                header = [FuzzHelper.get_string(4, 8) for _ in range(cols)]
                rows_data = [header]
                for _ in range(5):
                    row = [FuzzHelper.get_string(5, 10) for _ in range(cols - 1)]
                    row.insert(random.randint(0, cols - 1), FuzzHelper.get_evil_string())
                    rows_data.append(row)
                # Ensure all parts of the row are strings before joining
                content = "\n".join([",".join(map(str, r)) for r in rows_data])
                cmd = category.value.replace("<file>", f"/test_data/{file_name}")
                cases.append(TestCase(command=cmd, category=category.value, mount_files={file_name: content}))
            except Exception: continue

        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = EbtProfileAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))