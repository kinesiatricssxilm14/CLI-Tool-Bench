import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of 'final_differential_test' to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine from the sibling directories
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    INIT = "pygha init"
    BUILD_DEFAULT = "pygha build"
    BUILD_SRC = "pygha build --src-dir <dir>"
    BUILD_OUT = "pygha build --out-dir <dir>"
    BUILD_CLEAN = "pygha build --clean"
    BUILD_SRC_OUT = "pygha build --src-dir <dir> --out-dir <dir>"
    BUILD_SRC_CLEAN = "pygha build --src-dir <dir> --clean"
    BUILD_OUT_CLEAN = "pygha build --out-dir <dir> --clean"
    BUILD_SRC_OUT_CLEAN = "pygha build --src-dir <dir> --out-dir <dir> --clean"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class PyghaAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Install the oracle version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/parneetsingh022/pygha.git && cd pygha && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Install the agent version of the tool from the local path."""
        container.exec_run("mkdir -p /repo")
        # This copies the host's 'repo_to_be_tested' directory into the container's '/repo' directory,
        # resulting in '/repo/repo_to_be_tested' inside the container.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Sanitize the stdout to remove dynamic content like paths and timestamps."""
        # Normalize paths found in output messages
        sanitized = re.sub(r"Scanning for pipelines in: \S+", "Scanning for pipelines in: <src_dir>", raw_stdout)
        sanitized = re.sub(r"Initialized pygha project in \S+", "Initialized pygha project in <dir>", sanitized)
        sanitized = re.sub(r"-> '\S+/(\w+\.yml)'", r"-> '<path>/\1'", sanitized)
        sanitized = re.sub(r"-> '(\w+\.yml)'", r"-> '<path>/\1'", sanitized)
        sanitized = re.sub(r"Deleting stale workflow: \S+", "Deleting stale workflow: <path>", sanitized)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """Generate a list of test cases for pygha."""
        cases = []

        def get_pipeline_content(job_name: str) -> str:
            """Generates a valid Python pipeline definition as a string."""
            # Ensure the job name is a valid Python identifier
            safe_job_name = re.sub(r'\W|^(?=\d)', '_', job_name)
            if not safe_job_name:
                safe_job_name = "default_job"
            return f"""
from pygha import job, default_pipeline
from pygha.steps import run, checkout

default_pipeline(on_push=["main"])

@job(name="{safe_job_name}")
def fuzz_job():
    checkout()
    run("echo 'Hello from pygha fuzz test'")
"""

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == CASES_PER_CATEGORY - 1)
                    
                    cmd_template = category.value
                    cmd = ""
                    prep_script = ""
                    mount_files = {}

                    if category == CmdCategory.INIT:
                        cmd = cmd_template
                        # Edge case: try to init in a directory that already has a .pipe folder
                        if is_edge_case:
                            prep_script = "mkdir -p .pipe && echo 'pre-existing' > .pipe/somefile.txt"
                    
                    else:  # All 'build' categories
                        # 1. Prepare pipeline content
                        if is_edge_case:
                            # Test robustness against malformed pipeline files
                            pipeline_content = FuzzHelper.get_evil_string()
                        else:
                            job_name = FuzzHelper.get_string(5, 15)
                            pipeline_content = get_pipeline_content(job_name)

                        # 2. Prepare directory names and arguments
                        if is_edge_case:
                            # Test path handling with spaces and special characters
                            src_dir_name = f"fuzz src dir {i}"
                            out_dir_name = f"fuzz out dir {i}"
                        else:
                            src_dir_name = f"fuzz_pipe_{i}"
                            out_dir_name = f"fuzz_out_{i}"
                        
                        # These paths are inside the container's /test_data mount
                        src_arg = f"/test_data/{src_dir_name}"
                        out_arg = f"/test_data/{out_dir_name}"

                        # 3. Prepare mount files based on command template
                        # The test framework will create these directories on the host before mounting.
                        if "--src-dir" in cmd_template:
                            mount_files[f"{src_dir_name}/pipeline_fuzz.py"] = pipeline_content
                        else:
                            # If no --src-dir, pygha defaults to '.pipe'
                            mount_files[".pipe/pipeline_fuzz.py"] = pipeline_content

                        # 4. Construct final command by replacing placeholders
                        cmd = cmd_template
                        if "<dir>" in cmd:
                            # Use single quotes to handle spaces in paths
                            cmd = cmd.replace("--src-dir <dir>", f"--src-dir '{src_arg}'", 1)
                            cmd = cmd.replace("--out-dir <dir>", f"--out-dir '{out_arg}'", 1)

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=mount_files
                    ))
                except Exception:
                    # If generating a specific case fails for any reason, skip it
                    # and continue with the next one to ensure the test run is not blocked.
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = PyghaAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))