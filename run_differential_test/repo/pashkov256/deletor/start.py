import os
import sys
import re
import random
from enum import Enum
from typing import List, Dict

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

class CmdCategory(Enum):
    """
    Enum for different command categories of the 'deletor' CLI tool.
    The value of each enum member is a generic command structure template.
    We focus on the scriptable '-cli' mode and always use '-skip-confirm'.
    """
    EXTENSIONS = "deletor -cli -d <dir> -e <exts> -skip-confirm"
    MIN_SIZE = "deletor -cli -d <dir> --min-size <size> -skip-confirm"
    MAX_SIZE = "deletor -cli -d <dir> --max-size <size> -skip-confirm"
    MIN_MAX_SIZE = "deletor -cli -d <dir> --min-size <min> --max-size <max> -skip-confirm"
    OLDER_THAN = "deletor -cli -d <dir> --older <duration> -skip-confirm"
    NEWER_THAN = "deletor -cli -d <dir> --newer <duration> -skip-confirm"
    EXCLUDE = "deletor -cli -d <dir> --exclude <paths> -skip-confirm"
    SUBDIRS = "deletor -cli -d <dir> -subdirs -skip-confirm"
    PRUNE_EMPTY = "deletor -cli -d <dir> -prune-empty -skip-confirm"
    COMPLEX_EXT_SIZE_SUBDIRS = "deletor -cli -d <dir> -e <exts> --min-size <size> -subdirs -skip-confirm"
    COMPLEX_TIME_EXCLUDE_SUBDIRS = "deletor -cli -d <dir> --older <duration> --exclude <paths> -subdirs -skip-confirm"


class DeletorAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/pashkov256/deletor.git && cd deletor && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def generate_test_cases(self) -> List[TestCase]:
        cases: List[TestCase] = []
        TEST_DIR = "/test_data"

        mount_files: Dict[str, str] = {
            "file_a.txt": "This is a text file.",
            "file_b.log": "This is a log file." * 100,  # ~2KB
            "archive.zip": "Z" * 1024 * 10,  # 10KB
            "image.jpg": "J" * 1024 * 50,  # 50KB
            "subdir/sub_file.dat": "This is a file in a subdirectory.",
            "old_file.tmp": "This file is old.",
            "new_file.tmp": "This file is new.",
            "exclude_dir/secret.txt": "This file should be excluded.",
            "another_dir/another_file.txt": "Another file."
        }

        prep_script = f"""
        mkdir -p {TEST_DIR}/subdir
        mkdir -p {TEST_DIR}/exclude_dir
        mkdir -p {TEST_DIR}/another_dir
        mkdir -p {TEST_DIR}/empty_dir_to_prune
        touch -m -d '5 days ago' {TEST_DIR}/old_file.tmp
        touch -m -d '5 minutes ago' {TEST_DIR}/new_file.tmp
        """

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    command = ""

                    if category == CmdCategory.EXTENSIONS:
                        exts = "invalid-ext" if is_edge_case else random.choice(['txt', 'log,zip', 'dat', 'tmp'])
                        command = f"deletor -cli -d {TEST_DIR} -e {exts} -skip-confirm"

                    elif category == CmdCategory.MIN_SIZE:
                        size = "not-a-size" if is_edge_case else random.choice(['1kb', '5kb', '20kb'])
                        command = f"deletor -cli -d {TEST_DIR} --min-size {size} -skip-confirm"

                    elif category == CmdCategory.MAX_SIZE:
                        size = "-10kb" if is_edge_case else random.choice(['1kb', '20kb', '60kb'])
                        command = f"deletor -cli -d {TEST_DIR} --max-size {size} -skip-confirm"

                    elif category == CmdCategory.MIN_MAX_SIZE:
                        min_s, max_s = ('20kb', '5kb') if is_edge_case else ('5kb', '20kb')
                        command = f"deletor -cli -d {TEST_DIR} --min-size {min_s} --max-size {max_s} -skip-confirm"

                    elif category == CmdCategory.OLDER_THAN:
                        duration = "not-a-duration" if is_edge_case else '2day'
                        command = f"deletor -cli -d {TEST_DIR} --older {duration} -skip-confirm"

                    elif category == CmdCategory.NEWER_THAN:
                        duration = FuzzHelper.get_evil_string() if is_edge_case else '1hour'
                        command = f"deletor -cli -d {TEST_DIR} --newer {duration} -skip-confirm"

                    elif category == CmdCategory.EXCLUDE:
                        path = FuzzHelper.get_evil_string() if is_edge_case else random.choice(['exclude_dir', '*.tmp', 'file_a.txt'])
                        command = f"deletor -cli -d {TEST_DIR} --exclude {path} -skip-confirm"

                    elif category == CmdCategory.SUBDIRS:
                        # This command has no specific value to fuzz, so we just run it
                        command = f"deletor -cli -d {TEST_DIR} -subdirs -skip-confirm"

                    elif category == CmdCategory.PRUNE_EMPTY:
                        # To test prune, we first need to delete something to make a dir empty
                        # This command will delete sub_file.dat, leaving 'subdir' empty, which should be pruned.
                        command = f"deletor -cli -d {TEST_DIR} -e dat -subdirs -prune-empty -skip-confirm"

                    elif category == CmdCategory.COMPLEX_EXT_SIZE_SUBDIRS:
                        exts = "txt,dat"
                        size = "not-a-size" if is_edge_case else '10b'
                        command = f"deletor -cli -d {TEST_DIR} -e {exts} --min-size {size} -subdirs -skip-confirm"

                    elif category == CmdCategory.COMPLEX_TIME_EXCLUDE_SUBDIRS:
                        duration = '1day'
                        path = FuzzHelper.get_evil_string() if is_edge_case else 'secret.txt'
                        command = f"deletor -cli -d {TEST_DIR} --older {duration} --exclude {path} -subdirs -skip-confirm"

                    if command:
                        cases.append(TestCase(
                            command=command,
                            category=category.value,
                            prep_script=prep_script,
                            mount_files=mount_files.copy()
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")

        return cases


if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = DeletorAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))