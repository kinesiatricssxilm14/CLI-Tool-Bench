import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for upfile command test categories.
    Each value is a generic command structure template representing a test workflow.
    """
    ADD_AND_LIST = "upfile add <path>... && upfile list"
    PUSH_AND_LIST = "upfile push <path> && upfile list"
    PULL_AND_VERIFY = "upfile pull <filename> --yes && cat <file_to_verify>"
    SYNC_AND_VERIFY = "upfile sync <filename> --yes && cat <file_to_verify>"
    DIFF = "upfile diff <path>"
    REMOVE_AND_LIST = "upfile remove <path> && upfile list"
    DROP_AND_LIST = "upfile drop <filename> --yes && upfile list"
    RENAME_AND_LIST = "upfile rename <old> <new> && upfile list <new>"
    SHOW = "upfile show <filename>"
    STATUS = "upfile status <dir>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class UpfileAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/skewb1k/upfile.git && cd upfile && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        # The output paths like /test_data/proj1/fuzz_file.txt are deterministic
        # within the container, so no sanitization is needed for them.
        # The tool does not seem to output timestamps or memory addresses.
        return super().sanitize_stdout(raw_stdout)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        
        def _sanitize_for_filename(s: str) -> str:
            s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', s)
            s = re.sub(r'\s+', '_', s)
            return s[:50] or "sanitized_empty_name"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # Make the first case of each category an edge case
                    
                    # --- Test Setup ---
                    env_vars = {"UPFILE_DIR": f"/tmp/upfile_data_{category.name}_{i}"}
                    prep_script = "mkdir -p /test_data/proj1 /test_data/proj2"
                    mount_files = {}
                    cmd = ""

                    # --- Test Case Generation ---
                    if category == CmdCategory.ADD_AND_LIST:
                        fname = f"file_{i}.txt"
                        fpath = f"/test_data/proj1/{fname}"
                        mount_files[f"proj1/{fname}"] = FuzzHelper.get_string(10, 50)
                        
                        if is_edge_case:
                            # Try to add a non-existent file, then the real one twice
                            cmd = f"upfile add /test_data/non_existent.txt; upfile add {fpath}; upfile add {fpath}; upfile list"
                        else:
                            cmd = f"upfile add {fpath} && upfile list"

                    elif category == CmdCategory.PUSH_AND_LIST:
                        fname = f"file_{i}.txt"
                        path1 = f"/test_data/proj1/{fname}"
                        path2 = f"/test_data/proj2/{fname}"
                        mount_files[f"proj1/{fname}"] = "version1"
                        mount_files[f"proj2/{fname}"] = "version1"
                        
                        setup = f"upfile add {path1} && upfile add {path2}"
                        
                        if is_edge_case:
                            # Push an unmodified file
                            push_cmd = f"upfile push {path2}"
                        else:
                            # Modify file before pushing
                            setup += f" && echo '{FuzzHelper.get_string(5, 15)}' > {path1}"
                            push_cmd = f"upfile push {path1}"
                        
                        cmd = f"{setup} && {push_cmd} && upfile list"

                    elif category in [CmdCategory.PULL_AND_VERIFY, CmdCategory.SYNC_AND_VERIFY]:
                        base_name = f"config_{i}.json"
                        path1 = f"/test_data/proj1/{base_name}"
                        path2 = f"/test_data/proj2/{base_name}"
                        
                        content_v1 = FuzzHelper.get_json_string(3)
                        content_v2 = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_json_string(4)
                        
                        mount_files[f"proj1/{base_name}"] = content_v1
                        mount_files[f"proj2/{base_name}"] = content_v1
                        
                        # Correctly escape single quotes for the shell 'echo' command
                        escaped_content_v2 = content_v2.replace("'", "'\"'\"'")
                        setup = f"upfile add {path1} && upfile add {path2} && echo '{escaped_content_v2}' > {path1} && upfile push {path1}"
                        
                        action_cmd = "pull" if category == CmdCategory.PULL_AND_VERIFY else "sync"
                        cmd = f"{setup} && upfile {action_cmd} {base_name} --yes && cat {path2}"

                    elif category == CmdCategory.DIFF:
                        fname = f"diff_me_{i}.txt"
                        fpath = f"/test_data/proj1/{fname}"
                        mount_files[f"proj1/{fname}"] = "initial content"
                        
                        setup = f"upfile add {fpath}"
                        if is_edge_case:
                            # Diff an unmodified file
                            cmd = f"{setup} && upfile diff {fpath}"
                        else:
                            # Modify and then diff
                            modification = FuzzHelper.get_string(10, 20)
                            cmd = f"{setup} && echo '{modification}' > {fpath} && upfile diff {fpath}"

                    elif category == CmdCategory.REMOVE_AND_LIST:
                        fname = f"rem_file_{i}.txt"
                        path1 = f"/test_data/proj1/{fname}"
                        path2 = f"/test_data/proj2/{fname}"
                        mount_files[f"proj1/{fname}"] = "content"
                        mount_files[f"proj2/{fname}"] = "content"
                        
                        setup = f"upfile add {path1} && upfile add {path2}"
                        if is_edge_case:
                            # Remove a non-existent entry, then the real one twice
                            cmd = f"{setup} && upfile remove /test_data/proj1/non_existent.txt && upfile remove {path1} && upfile remove {path1} && upfile list"
                        else:
                            cmd = f"{setup} && upfile remove {path1} && upfile list"

                    elif category == CmdCategory.DROP_AND_LIST:
                        fname = f"drop_file_{i}.txt"
                        path1 = f"/test_data/proj1/{fname}"
                        mount_files[f"proj1/{fname}"] = "content"
                        
                        setup = f"upfile add {path1}"
                        if is_edge_case:
                            # Drop a non-existent file
                            non_existent_name = FuzzHelper.get_string(10, 15) + ".bak"
                            cmd = f"{setup} && upfile drop {non_existent_name} --yes && upfile list"
                        else:
                            cmd = f"{setup} && upfile drop {fname} --yes && upfile list"

                    elif category == CmdCategory.RENAME_AND_LIST:
                        old_name = f"old_name_{i}.cfg"
                        path1 = f"/test_data/proj1/{old_name}"
                        mount_files[f"proj1/{old_name}"] = "config"
                        setup = f"upfile add {path1}"

                        if is_edge_case:
                            # Use evil string for new name
                            new_name = _sanitize_for_filename(FuzzHelper.get_evil_string())
                        else:
                            new_name = f"new_name_{i}.cfg"
                        
                        cmd = f"{setup} && upfile rename {old_name} {new_name} && upfile list {new_name}"

                    elif category == CmdCategory.SHOW:
                        fname = f"show_me_{i}.yml"
                        fpath = f"/test_data/proj1/{fname}"
                        content = "key: value"
                        mount_files[f"proj1/{fname}"] = content
                        
                        setup = f"upfile add {fpath}"
                        if is_edge_case:
                            # Show a non-existent file
                            cmd = f"{setup} && upfile show non_existent_file.yml"
                        else:
                            cmd = f"{setup} && upfile show {fname}"

                    elif category == CmdCategory.STATUS:
                        fname = f"status_file_{i}.txt"
                        path1 = f"/test_data/proj1/{fname}"
                        mount_files[f"proj1/{fname}"] = "v1"
                        
                        setup = f"upfile add {path1}"
                        if is_edge_case:
                            # Check status in an empty directory where no files are tracked
                            cmd = f"{setup} && upfile status /test_data/proj2"
                        else:
                            # Modify file and check status of its directory
                            cmd = f"{setup} && echo 'v2' > {path1} && upfile status /test_data/proj1"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            prep_script=prep_script,
                            mount_files=mount_files,
                            env_vars=env_vars
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} index {i}: {e}")
                    continue
        return cases


# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = UpfileAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))