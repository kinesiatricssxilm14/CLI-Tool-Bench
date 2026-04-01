import os
import sys
import re
from enum import Enum
import random
import string

# Add the parent directory of the script's location to the Python path
# to be able to import BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command structures to be tested for the tview tool.
    The value of each enum member is a generic string template of the command.
    """
    BASIC = "tview <path>"
    WITH_DEPTH = "tview <path> --depth <N>"
    WITH_IGNORE = "tview <path> --ignore <patterns>"
    WITH_SIZE = "tview <path> --size"
    NO_COLOR = "tview <path> --color=false"
    HIDE_ICONS = "tview <path> --icons"
    SORT_BY_NAME_ASC = "tview <path> --sort name:asc"
    SORT_BY_NAME_DESC = "tview <path> --sort name:desc"
    SORT_BY_SIZE_ASC = "tview <path> --sort size:asc"
    SORT_BY_SIZE_DESC = "tview <path> --sort size:desc"
    DEPTH_AND_SIZE = "tview <path> --depth <N> --size"
    SIZE_AND_SORT = "tview <path> --size --sort size:desc"
    DEPTH_AND_IGNORE = "tview <path> --depth <N> --ignore <patterns>"
    ALL_FEATURES = "tview <path> --depth <N> --size --sort name:asc --ignore <patterns>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the Go-based tool.
        """
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/sameer240704/tview.git && cd tview && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent version of the tool from the local file system.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the command output to remove noise.
        The default implementation removes ANSI color codes, which is sufficient for tview.
        """
        return super().sanitize_stdout(raw_stdout)

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        TEST_ROOT_DIR = "/test_data"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The last case in each category is an edge case
                    is_edge_case = (i == CASES_PER_CATEGORY - 1)

                    # --- 1. Generate a stable file system structure ---
                    mount_files = {
                        "dir1/file1.txt": FuzzHelper.get_string(10, 50),
                        "dir1/sub1/file2.log": FuzzHelper.get_string(20, 100),
                        "dir2/file3.tmp": FuzzHelper.get_string(0, 30),
                        "toplevel.md": "This is a test file."
                    }
                    if is_edge_case:
                        # Add a file with potentially problematic content, avoiding null bytes
                        mount_files["evil.txt"] = FuzzHelper.get_evil_string().replace('\x00', '')

                    # --- 2. Build the command ---
                    path_arg = TEST_ROOT_DIR
                    if is_edge_case and random.random() > 0.5:
                        path_arg = random.choice(["/non_existent_dir", FuzzHelper.get_filepath(absolute=True)])
                    
                    args = []

                    # --- 3. Add flags based on category ---
                    if category in [CmdCategory.WITH_DEPTH, CmdCategory.DEPTH_AND_SIZE, CmdCategory.DEPTH_AND_IGNORE, CmdCategory.ALL_FEATURES]:
                        if not is_edge_case:
                            depth = FuzzHelper.get_int(-1, 5)
                        else:
                            # Use an evil string or a large number for edge case
                            depth = random.choice([FuzzHelper.get_evil_string().split()[0] if FuzzHelper.get_evil_string().split() else "bad", str(FuzzHelper.get_int(100, 200))])
                        args.append(f"--depth {depth}")

                    if category in [CmdCategory.WITH_IGNORE, CmdCategory.DEPTH_AND_IGNORE, CmdCategory.ALL_FEATURES]:
                        if not is_edge_case:
                            ignore_pattern = random.choice(["*.tmp", "dir1", "sub1"])
                        else:
                            # Use an evil string, ensuring it's quoted and internal quotes are escaped
                            ignore_pattern = FuzzHelper.get_evil_string().replace('"', '\\"')
                        args.append(f'--ignore="{ignore_pattern}"')

                    if category in [CmdCategory.WITH_SIZE, CmdCategory.DEPTH_AND_SIZE, CmdCategory.SIZE_AND_SORT, CmdCategory.ALL_FEATURES]:
                        args.append("--size")

                    if category == CmdCategory.NO_COLOR:
                        # Per README example: tview --color=false
                        value = 'false' if not is_edge_case else FuzzHelper.get_boolean_str()
                        args.append(f"--color={value}")

                    if category == CmdCategory.HIDE_ICONS:
                        # Per help: --icons hides icons. It's a presence flag.
                        args.append("--icons")

                    sort_map = {
                        CmdCategory.SORT_BY_NAME_ASC: "name:asc",
                        CmdCategory.SORT_BY_NAME_DESC: "name:desc",
                        CmdCategory.SORT_BY_SIZE_ASC: "size:asc",
                        CmdCategory.SORT_BY_SIZE_DESC: "size:desc",
                        CmdCategory.SIZE_AND_SORT: "size:desc",
                        CmdCategory.ALL_FEATURES: "name:asc"
                    }
                    if category in sort_map:
                        sort_val = sort_map[category] if not is_edge_case else FuzzHelper.get_evil_string()
                        args.append(f"--sort '{sort_val}'") # Quote to handle spaces in evil strings
                    
                    random.shuffle(args)
                    command = f"tview {path_arg} {' '.join(args)}"

                    cases.append(TestCase(
                        command=command.strip(),
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Skipped generating a test case for {category.name} due to error: {e}")
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))