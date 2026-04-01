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
    Enumerates the types of commands to be tested for gotmplfmt.
    The tool reads from stdin, so commands include redirection.
    """
    BASIC = "gotmplfmt < <file>"
    WIDTH = "gotmplfmt -w <N> < <file>"
    TOKENS = "gotmplfmt -t < <file>"
    WIDTH_AND_TOKENS = "gotmplfmt -w <N> -t < <file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GotmplfmtAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image for the testing environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle (baseline) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/miekg/gotmplfmt.git && cd gotmplfmt && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent (local) version of the tool into the container."""
        container.exec_run("mkdir -p /repo")
        # The user running the script must have docker permissions.
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested") != 0:
            raise Exception("Failed to copy agent code to container")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases covering different command categories.
        """
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    file_name = f"fuzz_test_{category.name}_{i}.tmpl"
                    # The first case of each category is an edge case
                    is_edge_case = (i == 0)

                    content = ""
                    if is_edge_case:
                        # For edge cases, use an evil string or an empty file
                        content = random.choice([FuzzHelper.get_evil_string(), ""])
                    else:
                        # For normal cases, generate a syntactically plausible Go template
                        # to ensure the core formatting logic is tested.
                        content = f"""
<html><head>
<title>{{{{.Title}}}}</title></head>
<body>
<h1>{FuzzHelper.get_string(5, 15)}</h1>
{{{{if .ShowSection}}}}
  <p>This is a section.</p>
  <ul>{{{{range .Items}}}}
    <li>{{{{.Name}}}} - {FuzzHelper.get_string(5, 15)}</li>{{{{end}}}}
  </ul>
{{{{else}}}}
  <p>Section is hidden for {{{{.User}}}}.</p>
{{{{end}}}}
<footer>{FuzzHelper.get_string(10, 20)}</footer>
</body></html>
{{{{define "test"}}}}<div>{{{{.}}}}{{{{end}}}}
"""

                    cmd = ""
                    # Assemble commands based on enum type
                    if category == CmdCategory.BASIC:
                        cmd = f"gotmplfmt < /test_data/{file_name}"

                    elif category == CmdCategory.WIDTH:
                        if is_edge_case:
                            # Use invalid width values that are still single arguments
                            evil_widths = ["-1", "0", "not_a_number", "999999999999999999999"]
                            width_val = random.choice(evil_widths)
                        else:
                            # Normal, valid width
                            width_val = FuzzHelper.get_int(20, 200)
                        cmd = f"gotmplfmt -w {width_val} < /test_data/{file_name}"

                    elif category == CmdCategory.TOKENS:
                        cmd = f"gotmplfmt -t < /test_data/{file_name}"

                    elif category == CmdCategory.WIDTH_AND_TOKENS:
                        if is_edge_case:
                            evil_widths = ["-10", "abc", "0"]
                            width_val = random.choice(evil_widths)
                        else:
                            width_val = FuzzHelper.get_int(20, 200)
                        
                        # Test different argument orders
                        args = [f"-w {width_val}", "-t"]
                        random.shuffle(args)
                        cmd = f"gotmplfmt {' '.join(args)} < /test_data/{file_name}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    # Don't let test case generation crash the whole process
                    print(f"Warning: Failed to generate a test case for {category.name}: {e}")
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GotmplfmtAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))