import os
import sys
import re
import json
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# The magic bytes for a SQLite 3 database file.
SQLITE_HEADER = b'SQLite format 3\x00'
CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line argument combinations for sqlite-scanner.
    The value of each enum member is a generic string template representing the command structure.
    """
    # Plain text output variants
    SCAN_PATHS = "sqlite-scanner <paths...>"
    SCAN_PATHS_WITH_SIZE = "sqlite-scanner --size <paths...>"
    SCAN_PATHS_WITH_WORKERS = "sqlite-scanner --workers <N> <paths...>"
    SCAN_PATHS_WITH_SIZE_WORKERS = "sqlite-scanner --size --workers <N> <paths...>"

    # JSON output variants
    SCAN_JSON = "sqlite-scanner --json <paths...>"
    SCAN_JSON_WITH_SIZE = "sqlite-scanner --json --size <paths...>"
    SCAN_JSON_WITH_WORKERS = "sqlite-scanner --json --workers <N> <paths...>"
    SCAN_JSON_WITH_SIZE_WORKERS = "sqlite-scanner --json --size --workers <N> <paths...>"

    # JSONL output variants
    SCAN_JSONL = "sqlite-scanner --jsonl <paths...>"
    SCAN_JSONL_WITH_SIZE = "sqlite-scanner --jsonl --size <paths...>"
    SCAN_JSONL_WITH_WORKERS = "sqlite-scanner --jsonl --workers <N> <paths...>"
    SCAN_JSONL_WITH_SIZE_WORKERS = "sqlite-scanner --jsonl --size --workers <N> <paths...>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class SqliteScannerAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image suitable for the Go tool."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Clones the official repository and installs the oracle version of the tool."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/simonw/sqlite-scanner.git && cd sqlite-scanner && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies the local agent code into the container and installs it."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Normalizes the tool's output to ensure stable comparisons.
        The tool's parallel nature means output order is not guaranteed. This method
        sorts the output lines (for text/JSONL) or the entries in the JSON object
        to create a canonical representation.
        """
        clean_stdout = super().sanitize_stdout(raw_stdout)
        stripped_output = clean_stdout.strip()

        # Attempt to parse as a single JSON object (for --json mode)
        if stripped_output.startswith('{') and stripped_output.endswith('}'):
            try:
                data = json.loads(stripped_output)
                if 'entries' in data and isinstance(data['entries'], list):
                    # Sort entries by 'path' to ensure order doesn't cause diffs
                    data['entries'] = sorted(data['entries'], key=lambda x: x.get('path', ''))
                    return json.dumps(data, sort_keys=True, indent=2)
            except json.JSONDecodeError:
                # If parsing fails, fall through to treat as line-based text
                pass

        # Treat as line-delimited output (for plain text or --jsonl mode)
        lines = [line for line in stripped_output.split('\n') if line.strip()]
        lines.sort()
        return '\n'.join(lines)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        # Use latin-1 to safely decode any byte sequence into a string for file content
        sqlite_header_str = SQLITE_HEADER.decode('latin-1')

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == CASES_PER_CATEGORY - 1) # Last case in each category is an edge case

                    # --- Test Data and Environment Setup ---
                    test_dir_name = f"case_{category.name.lower()}_{i}"
                    prep_script = f"mkdir -p /test_data/{test_dir_name}/subdir"
                    mount_files = {}

                    if is_edge_case:
                        # Generate malicious/boundary file content. All content must be string.
                        mount_files[f"{test_dir_name}/valid.db"] = sqlite_header_str + FuzzHelper.get_evil_string()
                        mount_files[f"{test_dir_name}/not_a_db.txt"] = FuzzHelper.get_evil_string()
                        mount_files[f"{test_dir_name}/empty.file"] = ""
                        mount_files[f"{test_dir_name}/subdir/just_header.db"] = sqlite_header_str
                        corrupted_header = (SQLITE_HEADER[:8] + b'\x01\x02' + SQLITE_HEADER[10:]).decode('latin-1')
                        mount_files[f"{test_dir_name}/subdir/corrupted.db"] = corrupted_header
                    else:
                        # Generate normal file content. All content must be string.
                        mount_files[f"{test_dir_name}/valid.db"] = sqlite_header_str + FuzzHelper.get_string(100, 200)
                        mount_files[f"{test_dir_name}/not_a_db.txt"] = FuzzHelper.get_string(50, 100)
                        mount_files[f"{test_dir_name}/empty.file"] = ""
                        mount_files[f"{test_dir_name}/subdir/another_valid.db"] = sqlite_header_str + FuzzHelper.get_string(10, 20)
                        mount_files[f"{test_dir_name}/subdir/random.bin"] = FuzzHelper.get_string(16, 64)

                    # --- Command Assembly ---
                    base_cmd = "sqlite-scanner"
                    args = []
                    
                    # Add flags based on the category
                    if "jsonl" in category.name.lower():
                        args.append("--jsonl")
                    elif "json" in category.name.lower():
                        args.append("--json")
                    
                    if "size" in category.name.lower():
                        args.append("--size")

                    if "workers" in category.name.lower():
                        if is_edge_case:
                            evil_str = FuzzHelper.get_evil_string()
                            worker_val = evil_str.split()[0] if evil_str.strip() else str(FuzzHelper.get_int(-10, 0))
                        else:
                            worker_val = FuzzHelper.get_int(1, 8) # Use a reasonable number of workers
                        args.append(f"--workers {worker_val}")
                    
                    random.shuffle(args)
                    flags_str = ' '.join(args)
                    
                    command: str
                    # For some normal cases, test scanning the current directory
                    if not is_edge_case and i % 2 == 1:
                        command = f"cd /test_data/{test_dir_name} && {base_cmd} {flags_str}"
                    else:
                        path_arg = f"/test_data/{test_dir_name}"
                        # For some edge cases, add a non-existent path
                        if is_edge_case:
                            path_arg += f" /test_data/non_existent_{i}"
                        command = f"{base_cmd} {flags_str} {path_arg}"
                    
                    # Clean up potential double spaces
                    command = ' '.join(command.split())

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate a test case for category {category.name}: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = SqliteScannerAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))