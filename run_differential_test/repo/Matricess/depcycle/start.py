import os
import sys
import re
from enum import Enum
import random
import string

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the command-line argument combinations for depcycle.
    The value of each enum is the generic structure of the command.
    """
    BASIC = "depcycle <project_path>"
    OUTPUT = "depcycle <project_path> --output <file>"
    FORMAT_SVG = "depcycle <project_path> --format svg"
    FORMAT_HTML = "depcycle <project_path> --format html"
    OUTPUT_FORMAT = "depcycle <project_path> --output <file> --format <format>"
    EXCLUDE = "depcycle <project_path> --exclude <pattern>"
    MULTIPLE_EXCLUDE = "depcycle <project_path> --exclude <p1> --exclude <p2>"
    NO_THIRD_PARTY = "depcycle <project_path> --no-third-party"
    NO_STDLIB = "depcycle <project_path> --no-stdlib"
    NO_THIRD_PARTY_NO_STDLIB = "depcycle <project_path> --no-third-party --no-stdlib"
    INCLUDE_ALL = "depcycle <project_path> --include-all"
    COMPLEX_COMBO = "depcycle <project_path> --output <file> --format svg --no-stdlib --exclude <pattern>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class DepCycleAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle version of depcycle from GitHub, strictly following the rules."""
        # Install prerequisites (git for cloning, graphviz for rendering) first.
        # Then, run the mandated installation command.
        cmd = "apt-get update && apt-get install -y git graphviz && " \
              "mkdir -p /repo && cd /repo && git clone https://github.com/Matricess/depcycle.git && cd depcycle && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies the local agent code and installs it, strictly following the rules."""
        # Install prerequisites (graphviz for rendering) first.
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "apt-get update && apt-get install -y graphviz && " \
              "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Removes volatile information like file paths from the output."""
        sanitized = re.sub(r"Analyzing project: .*", "Analyzing project: <PROJECT_PATH>", raw_stdout)
        sanitized = re.sub(r"Visualization saved to: .*", "Visualization saved to: <OUTPUT_PATH>", sanitized)
        # Remove Graphviz version info if present
        sanitized = re.sub(r"graphviz version .*", "", sanitized, flags=re.IGNORECASE)
        return super().sanitize_stdout(sanitized)

    def _generate_project_files(self, project_name: str, is_edge_case: bool) -> dict:
        """Helper to generate a dictionary of files for a dummy Python project."""
        files = {}
        base_path = project_name + "/"

        if is_edge_case:
            # Generate malformed or problematic project files
            files[base_path + "main.py"] = "import non_existent_module"
            files[base_path + "empty.py"] = ""
            # Invalid syntax that will cause AST parsing to fail
            files[base_path + "corrupt.py"] = "import a from b c"
            files[base_path + "binary_content.py"] = b'\x80\x02\x03'.decode('utf-8', errors='replace')
        else:
            # Generate a well-formed project with various import types and a cycle
            files[base_path + "app/main.py"] = "import os\nimport requests\nfrom app.services import logic\n\nlogic.run()"
            files[base_path + "app/services/logic.py"] = "from app.models import user\n\ndef run():\n    print('running')"
            files[base_path + "app/models/user.py"] = "import datetime\nfrom app.services import logic # Circular dependency"
            files[base_path + "app/tests/test_logic.py"] = "from app.services import logic"
            files[base_path + "venv/dummy.py"] = "# This should be ignored by default"
        return files

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # First case in each category is an edge case
                    project_name = f"project_{category.name}_{i}"
                    project_path_in_container = f"/test_data/{project_name}"

                    mount_files = self._generate_project_files(project_name, is_edge_case)
                    cmd = ""

                    if category == CmdCategory.BASIC:
                        cmd = f"depcycle {project_path_in_container}"

                    elif category == CmdCategory.OUTPUT:
                        output_file = "/test_data/out-!@#$.tmp" if is_edge_case else f"/test_data/out_{i}.png"
                        cmd = f"depcycle {project_path_in_container} --output {output_file}"

                    elif category == CmdCategory.FORMAT_SVG:
                        cmd = f"depcycle {project_path_in_container} --output /test_data/out.svg --format svg"

                    elif category == CmdCategory.FORMAT_HTML:
                        cmd = f"depcycle {project_path_in_container} --output /test_data/out.html --format html"

                    elif category == CmdCategory.OUTPUT_FORMAT:
                        fmt = random.choice(["svg", "html", "png"])
                        if is_edge_case:
                            fmt = FuzzHelper.get_string(3, 5)  # Invalid format
                        output_file = f"/test_data/output_{i}.{fmt if fmt in ['svg', 'html', 'png'] else 'txt'}"
                        cmd = f"depcycle {project_path_in_container} --output {output_file} --format {fmt}"

                    elif category == CmdCategory.EXCLUDE:
                        pattern = "*/**/.." if is_edge_case else "app/tests/*"
                        cmd = f"depcycle {project_path_in_container} --exclude \"{pattern}\""

                    elif category == CmdCategory.MULTIPLE_EXCLUDE:
                        p1 = "venv/*"
                        p2 = "app/models/user.py"
                        if is_edge_case:
                            p1 = FuzzHelper.get_string(1, 5) # Potentially invalid pattern
                        cmd = f"depcycle {project_path_in_container} --exclude \"{p1}\" --exclude \"{p2}\""

                    elif category == CmdCategory.NO_THIRD_PARTY:
                        cmd = f"depcycle {project_path_in_container} --no-third-party"

                    elif category == CmdCategory.NO_STDLIB:
                        cmd = f"depcycle {project_path_in_container} --no-stdlib"

                    elif category == CmdCategory.NO_THIRD_PARTY_NO_STDLIB:
                        cmd = f"depcycle {project_path_in_container} --no-third-party --no-stdlib"

                    elif category == CmdCategory.INCLUDE_ALL:
                        cmd = f"depcycle {project_path_in_container} --include-all"

                    elif category == CmdCategory.COMPLEX_COMBO:
                        output_file = f"/test_data/complex_{i}.svg"
                        pattern = "app/models/*"
                        if is_edge_case:
                            pattern = FuzzHelper.get_string(1, 10, chars="*[]?")
                        cmd = f"depcycle {project_path_in_container} --output {output_file} --format svg --no-stdlib --exclude \"{pattern}\""

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files=mount_files
                        ))
                except Exception:
                    # Ensure test case generation does not crash
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = DepCycleAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))