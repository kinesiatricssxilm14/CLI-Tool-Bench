import os
import sys
import re
import random
from enum import Enum

sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

class CmdCategory(Enum):
    FROM_CONFIG = "browserslist-to-es-version"
    FROM_ARGUMENT = "browserslist-to-es-version \"<query>\""

class BrowserslistAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Node.js environment."""
        return "node:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/rstackjs/browserslist-to-es-version.git && cd browserslist-to-es-version && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def generate_test_cases(self) -> list:
        test_cases = []
        browsers = ["Chrome", "Firefox", "Safari", "Edge", "ie", "Opera", "Samsung"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0)
                
                try:
                    if category == CmdCategory.FROM_CONFIG:
                        content = ""
                        if is_edge_case:
                            content = FuzzHelper.get_evil_string()
                        else:
                            num_lines = random.randint(1, 4)
                            lines = []
                            for _ in range(num_lines):
                                browser = random.choice(browsers)
                                version = FuzzHelper.get_int(50, 120)
                                operator = random.choice([">", ">=", "<", "<="])
                                lines.append(f"{browser} {operator} {version}")
                            content = "\n".join(lines)
                        
                        # The tool must be run in the directory containing the config file.
                        # The framework mounts files into /test_data.
                        command = "cd /test_data && browserslist-to-es-version"
                        mount_files = {".browserslistrc": content}
                        
                        test_cases.append(TestCase(
                            command=command,
                            category=category.value,
                            mount_files=mount_files
                        ))

                    elif category == CmdCategory.FROM_ARGUMENT:
                        query = ""
                        if is_edge_case:
                            query = FuzzHelper.get_evil_string()
                        else:
                            num_parts = random.randint(1, 3)
                            parts = []
                            for _ in range(num_parts):
                                browser = random.choice(browsers)
                                version = FuzzHelper.get_int(50, 120)
                                operator = random.choice([">", ">=", "<", "<="])
                                parts.append(f"{browser} {operator} {version}")
                            query = ", ".join(parts)
                        
                        # Escape double quotes within the query to prevent breaking the command string
                        safe_query = query.replace('"', '\\"')
                        command = f'browserslist-to-es-version "{safe_query}"'

                        test_cases.append(TestCase(
                            command=command,
                            category=category.value
                        ))
                except Exception as e:
                    # Skip case generation if any error occurs
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")
                    continue
        return test_cases

if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = BrowserslistAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))