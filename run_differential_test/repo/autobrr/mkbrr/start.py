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
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    # Create
    CREATE_BASIC = "mkbrr create <path> -t <url>"
    CREATE_PUBLIC = "mkbrr create <path> -t <url> --private <bool>"
    CREATE_COMMENT = "mkbrr create <path> -t <url> -c <string>"
    CREATE_SOURCE = "mkbrr create <path> -t <url> -s <string>"
    CREATE_ENTROPY = "mkbrr create <path> -t <url> -e"
    CREATE_WORKERS = "mkbrr create <path> -t <url> --workers <N>"
    CREATE_EXCLUDE = "mkbrr create <path> -t <url> --exclude <patterns>"
    CREATE_INCLUDE = "mkbrr create <path> -t <url> --include <patterns>"
    CREATE_COMBO = "mkbrr create <path> -t <url> -c <string> -s <string> --private <bool>"

    # Inspect
    INSPECT_BASIC = "mkbrr inspect <torrent_file>"
    INSPECT_VERBOSE = "mkbrr inspect <torrent_file> -v"

    # Check
    CHECK_BASIC = "mkbrr check <torrent_file> <content_path>"
    CHECK_WORKERS = "mkbrr check <torrent_file> <content_path> --workers <N>"

    # Modify
    MODIFY_TRACKER = "mkbrr modify <torrent_file> -t <url>"
    MODIFY_MULTI_TRACKER = "mkbrr modify <torrent_file> -t <url1> -t <url2>"
    MODIFY_PUBLIC = "mkbrr modify <torrent_file> --private <bool>"
    MODIFY_COMMENT = "mkbrr modify <torrent_file> -c <string>"
    MODIFY_SOURCE = "mkbrr modify <torrent_file> -s <string>"
    MODIFY_ENTROPY = "mkbrr modify <torrent_file> -e"
    MODIFY_DRY_RUN = "mkbrr modify <torrent_file> -t <url> -n"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MkbrrAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        sanitized = super().sanitize_stdout(raw_stdout)
        
        # Remove volatile progress bars and speed indicators
        sanitized = re.sub(r'^(Hashing|Verifying) pieces\.\.\..*$', '', sanitized, flags=re.MULTILINE)
        
        # Normalize output path messages, removing volatile elapsed time
        sanitized = re.sub(r'Wrote \S+\.torrent \(elapsed .*?\)', 'Wrote <sanitized>.torrent', sanitized)
        sanitized = re.sub(r'Modified torrent written to \S+\.torrent', 'Modified torrent written to <sanitized>.torrent', sanitized)

        # Remove season pack warnings, as our input is random and may trigger them
        sanitized = re.sub(r'Warning: Possible incomplete season pack detected.*?(?=\n\n|\Z)', '', sanitized, flags=re.DOTALL)

        # Sanitize volatile fields from 'inspect' output
        sanitized = re.sub(r'^Creator: .*$', 'Creator: <sanitized>', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'^Creation Date: .*$', 'Creation Date: <sanitized>', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'^Total Size: .*$', 'Total Size: <sanitized>', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'^Piece Size: .*$', 'Piece Size: <sanitized>', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'^Pieces: \d+', 'Pieces: <sanitized>', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'^Info Hash: .*$', 'Info Hash: <sanitized>', sanitized, flags=re.MULTILINE)
        
        # Remove blank lines to make diffs cleaner
        sanitized = '\n'.join(line for line in sanitized.splitlines() if line.strip())

        return sanitized

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/autobrr/mkbrr.git && cd mkbrr && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list:
        cases = []
        CASES_PER_CATEGORY = 50
        case_counter = 0

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    cmd = ""
                    prep_script = ""
                    mount_files = {}
                    case_counter += 1

                    # --- Setup for CREATE commands ---
                    if category.name.startswith("CREATE"):
                        source_filename = f"source_{case_counter}.dat"
                        if is_edge_case:
                            source_content = FuzzHelper.get_evil_string()
                        else:
                            source_content = FuzzHelper.get_string(100, 500)
                        mount_files[source_filename] = source_content
                        
                        input_path = f"/test_data/{source_filename}"
                        output_path = f"/test_data/output_{case_counter}.torrent"
                        
                        tracker = "invalid-url-format" if is_edge_case else FuzzHelper.get_url()
                        base_cmd = f"mkbrr create {input_path} -t {tracker} -o {output_path} --no-date --no-creator --skip-prefix"

                        if category == CmdCategory.CREATE_BASIC:
                            cmd = base_cmd
                        elif category == CmdCategory.CREATE_PUBLIC:
                            private_val = "not-a-bool" if is_edge_case else random.choice(["true", "false"])
                            cmd = f"{base_cmd} --private={private_val}"
                        elif category == CmdCategory.CREATE_COMMENT:
                            comment_raw = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(10, 50)
                            comment = comment_raw.replace('"', '\\"')
                            cmd = f"{base_cmd} -c \"{comment}\""
                        elif category == CmdCategory.CREATE_SOURCE:
                            source_raw = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(5, 20)
                            source = source_raw.replace('"', '\\"')
                            cmd = f"{base_cmd} -s \"{source}\""
                        elif category == CmdCategory.CREATE_ENTROPY:
                            cmd = f"{base_cmd} -e"
                        elif category == CmdCategory.CREATE_WORKERS:
                            workers = random.choice(["-1", "not_a_number", "0"]) if is_edge_case else FuzzHelper.get_int(1, 8)
                            cmd = f"{base_cmd} --workers {workers}"
                        elif category == CmdCategory.CREATE_EXCLUDE:
                            pattern_raw = FuzzHelper.get_evil_string() if is_edge_case else "*.log,*.tmp"
                            pattern = pattern_raw.replace('"', '\\"')
                            cmd = f"{base_cmd} --exclude \"{pattern}\""
                        elif category == CmdCategory.CREATE_INCLUDE:
                            pattern_raw = FuzzHelper.get_evil_string() if is_edge_case else "*.dat"
                            pattern = pattern_raw.replace('"', '\\"')
                            cmd = f"{base_cmd} --include \"{pattern}\""
                        elif category == CmdCategory.CREATE_COMBO:
                            comment_raw = FuzzHelper.get_string(10, 50)
                            comment = comment_raw.replace('"', '\\"')
                            source_raw = FuzzHelper.get_string(5, 20)
                            source = source_raw.replace('"', '\\"')
                            private_val = random.choice(["true", "false"])
                            cmd = f"{base_cmd} -c \"{comment}\" -s \"{source}\" --private={private_val}"

                    # --- Setup for commands needing a torrent file ---
                    else:
                        source_filename = f"source_{case_counter}.dat"
                        torrent_filename = f"test_{case_counter}.torrent"
                        
                        mount_files[source_filename] = FuzzHelper.get_string(100, 500)
                        # Prep script should always be valid to ensure the test artifact is created
                        prep_script = f"mkbrr create /test_data/{source_filename} -t http://tracker.test/ann -o /test_data/{torrent_filename} --no-date --no-creator --skip-prefix"
                        
                        torrent_path = f"/test_data/{torrent_filename}"
                        
                        if category == CmdCategory.INSPECT_BASIC:
                            cmd = f"mkbrr inspect {torrent_path}"
                        elif category == CmdCategory.INSPECT_VERBOSE:
                            cmd = f"mkbrr inspect {torrent_path} -v"
                        
                        elif category == CmdCategory.CHECK_BASIC:
                            cmd = f"mkbrr check {torrent_path} /test_data/{source_filename}"
                        elif category == CmdCategory.CHECK_WORKERS:
                            workers = random.choice(["-1", "not_a_number", "0"]) if is_edge_case else FuzzHelper.get_int(1, 8)
                            cmd = f"mkbrr check {torrent_path} /test_data/{source_filename} --workers {workers}"

                        elif category.name.startswith("MODIFY"):
                            output_name = f"modified_{case_counter}"
                            base_cmd = f"mkbrr modify {torrent_path} --output-dir /test_data -o {output_name} --no-date --no-creator --skip-prefix"

                            if category == CmdCategory.MODIFY_TRACKER:
                                tracker = "invalid-url-format" if is_edge_case else FuzzHelper.get_url()
                                cmd = f"{base_cmd} -t {tracker}"
                            elif category == CmdCategory.MODIFY_MULTI_TRACKER:
                                tracker1 = FuzzHelper.get_url()
                                tracker2 = "invalid-url-format" if is_edge_case else FuzzHelper.get_url()
                                cmd = f"{base_cmd} -t {tracker1} -t {tracker2}"
                            elif category == CmdCategory.MODIFY_PUBLIC:
                                private_val = "not-a-bool" if is_edge_case else random.choice(["true", "false"])
                                cmd = f"{base_cmd} --private={private_val}"
                            elif category == CmdCategory.MODIFY_COMMENT:
                                comment_raw = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(10, 50)
                                comment = comment_raw.replace('"', '\\"')
                                cmd = f"{base_cmd} -c \"{comment}\""
                            elif category == CmdCategory.MODIFY_SOURCE:
                                source_raw = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(5, 20)
                                source = source_raw.replace('"', '\\"')
                                cmd = f"{base_cmd} -s \"{source}\""
                            elif category == CmdCategory.MODIFY_ENTROPY:
                                cmd = f"{base_cmd} -e"
                            elif category == CmdCategory.MODIFY_DRY_RUN:
                                tracker = FuzzHelper.get_url()
                                cmd = f"{base_cmd} -t {tracker} -n"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            prep_script=prep_script,
                            mount_files=mount_files
                        ))
                except Exception as e:
                    print(f"Warning: Could not generate test case for {category.name} index {i}: {e}")
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MkbrrAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))