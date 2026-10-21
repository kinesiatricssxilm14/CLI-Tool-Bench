import os
import sys
import random
import re
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
    Enumerates the command categories for local-gitingest.
    The value of each enum is the generic command structure template.
    """
    BASIC = "local-gitingest"
    TARGET_SUBDIR_POS = "local-gitingest <target-subdirectory>"
    TARGET_SUBDIR_FLAG = "local-gitingest -d <directory>"
    EXCLUDE_EXT = "local-gitingest -exclude <extensions>"
    EXCLUDE_DIR = "local-gitingest -exclude-dir <dir1> -exclude-dir <dir2>"
    OUTPUT_FILE = "local-gitingest -o <filename>"
    SIZE_LIMIT = "local-gitingest -size-limit -max-size <bytes>"
    VERBOSE = "local-gitingest -v"
    COMPLEX_1 = "local-gitingest -d <directory> -exclude <extensions>"
    COMPLEX_2 = "local-gitingest -size-limit -max-size <bytes> -exclude-dir <dir>"
    ALL_FILTERS = "local-gitingest -d <directory> -exclude-dir <dir> -exclude <extensions> -size-limit -max-size <bytes>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class LocalGitingestAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/bigwhite/local-gitingest.git && cd local-gitingest && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _generate_repo_files(self, is_edge_case: bool) -> dict:
        """Helper to generate a random repository file structure and content."""
        files = {}
        # Define a structured set of dirs and exts for predictable testing
        dirs = ["src/app", "docs/guide", "tests", "assets/images", ""]
        exts = ["go", "md", "txt", "json", "log", "tmp", "jpg", "png"]

        # Generate a set of normal files
        for _ in range(random.randint(8, 12)):
            dir_path = random.choice(dirs)
            ext = random.choice(exts)
            fname = FuzzHelper.get_string(5, 10, chars="abcdef")
            file_path = os.path.join(dir_path, f"{fname}.{ext}") if dir_path else f"{fname}.{ext}"
            
            if is_edge_case and random.random() < 0.3:
                content = FuzzHelper.get_evil_string()
            else:
                content = FuzzHelper.get_string(50, 500)
            files[file_path] = content

        # Add specific files to test size limits
        files["src/large_file.go"] = "A" * 60000 # Above default limit
        files["src/small_file.go"] = "B" * 100   # Below default limit

        # Add a .gitignore file to test its exclusion logic
        files[".gitignore"] = "*.log\n/assets/\n*.tmp\n"
            
        return files

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        
        # This script is crucial: the tool must be run in a git repo.
        prep_script = (
            "mkdir -p /repo_root && "
            "([ -d /test_data ] && cp -r /test_data/. /repo_root/ 2>/dev/null || true) && "
            "cd /repo_root && "
            "git init --quiet && "
            "git config --global user.email 'test@example.com' && "
            "git config --global user.name 'Test User' && "
            "git add . && "
            "git commit -m 'fuzz test' --quiet --no-gpg-sign"
        )

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    
                    repo_files = self._generate_repo_files(is_edge_case)
                    
                    # Dirs and exts that are known to exist in our generated files
                    fuzz_dirs = ["src", "docs", "tests", "assets", "nonexistent_dir"]
                    fuzz_exts = ["go", "md", "log", "jpg", "dat"]

                    args = []

                    if category == CmdCategory.BASIC:
                        pass

                    elif category in [CmdCategory.TARGET_SUBDIR_POS, CmdCategory.TARGET_SUBDIR_FLAG]:
                        target_dir = random.choice(fuzz_dirs)
                        if is_edge_case:
                            target_dir = FuzzHelper.get_evil_string()
                        
                        if category == CmdCategory.TARGET_SUBDIR_FLAG:
                            args.append(f"-d '{target_dir}'")
                        else:
                            args.append(f"'{target_dir}'")

                    elif category == CmdCategory.EXCLUDE_EXT:
                        if is_edge_case:
                            ext_list = FuzzHelper.get_evil_string()
                        else:
                            selected_exts = random.sample(fuzz_exts, k=random.randint(1, 3))
                            ext_list = ",".join(f".{ext}" for ext in selected_exts)
                        args.append(f"-exclude '{ext_list}'")

                    elif category == CmdCategory.EXCLUDE_DIR:
                        dir1 = random.choice(fuzz_dirs)
                        dir2 = FuzzHelper.get_string(5,10)
                        if is_edge_case:
                            dir1 = FuzzHelper.get_evil_string()
                        
                        args.append(f"-exclude-dir='{dir1}'")
                        if not is_edge_case:
                            args.append(f"-exclude-dir='{dir2}'")

                    elif category == CmdCategory.OUTPUT_FILE:
                        if is_edge_case:
                            output_filename = FuzzHelper.get_evil_string().replace("/", "_").replace("'", "")
                        else:
                            output_filename = f"fuzz_out_{i}.txt"
                        args.append(f"-o '{output_filename}'")

                    elif category == CmdCategory.SIZE_LIMIT:
                        args.append("-size-limit")
                        if is_edge_case:
                            if random.random() > 0.5:
                                max_size = FuzzHelper.get_int(-100, 0)
                            else:
                                max_size = f"'{FuzzHelper.get_evil_string()}'"
                        else:
                            max_size = random.choice([1024, 51200, 51201, 65536])
                        args.append(f"-max-size={max_size}")

                    elif category == CmdCategory.VERBOSE:
                        args.append(random.choice(["-v", "-verbose"]))

                    elif category == CmdCategory.COMPLEX_1:
                        target_dir = random.choice(fuzz_dirs[:-1])
                        ext_list = ",".join(f".{ext}" for ext in random.sample(fuzz_exts, k=2))
                        args.append(f"-d '{target_dir}'")
                        args.append(f"-exclude '{ext_list}'")

                    elif category == CmdCategory.COMPLEX_2:
                        max_size = FuzzHelper.get_int(1024, 65536)
                        excl_dir = random.choice(fuzz_dirs[:-1])
                        args.append("-size-limit")
                        args.append(f"-max-size={max_size}")
                        args.append(f"-exclude-dir='{excl_dir}'")

                    elif category == CmdCategory.ALL_FILTERS:
                        args.append(f"-d '{random.choice(fuzz_dirs[:-1])}'")
                        args.append(f"-exclude-dir='{random.choice(fuzz_dirs[:-1])}'")
                        args.append(f"-exclude '{','.join(f'.{ext}' for ext in random.sample(fuzz_exts, k=2))}'")
                        args.append("-size-limit")
                        args.append(f"-max-size={FuzzHelper.get_int(1024, 65536)}")

                    random.shuffle(args)
                    args_str = " ".join(map(str, args))
                    
                    command = f"cd /repo_root && local-gitingest {args_str}"

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=repo_files
                    ))
                except Exception:
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = LocalGitingestAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))