import os
import sys
import re
import json
import random
from enum import Enum

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for the command categories of the react-rsc-vuln-scanner.
    The tool's primary function is to scan a directory, so there is one main command pattern.
    """
    SCAN_PATH = "scan-rsc-vuln <path>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ReactRSCVulnScannerAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """
        The tool is a Node.js script requiring Node.js 18+.
        'node:latest' is a suitable base image that includes git.
        """
        return "node:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the oracle version of the tool according to the framework's strict rules for JS projects.
        The 'node:latest' image is Debian-based and includes git, so 'apk' or 'apt-get' is not needed.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/burakeregar/react-rsc-vuln-scanner.git && cd react-rsc-vuln-scanner && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the agent version of the tool according to the framework's strict rules for JS projects.
        """
        container.exec_run("mkdir -p /repo")
        # The os.system call is part of the framework's standard procedure.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile information from the stdout, such as absolute file paths.
        The scanner's output includes the full path to the scanned directory and found projects.
        These paths are dynamically generated and must be normalized for differential testing.
        """
        # Example output lines to sanitize:
        # 📂 Scan Directory: /test_data/scan_dir_123
        # Path: /test_data/scan_dir_123/project_abc
        # This regex replaces any path starting with /test_data/ or <WORKDIR>/ with a placeholder.
        sanitized = re.sub(r'(?:/test_data|<WORKDIR>)/[^\s\n\r]*', '<path>', raw_stdout)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        # Helper to create valid package.json content
        def create_pkg_json(name, deps=None, dev_deps=None):
            pkg = {"name": name, "version": "1.0.0"}
            if deps:
                pkg["dependencies"] = deps
            if dev_deps:
                pkg["devDependencies"] = dev_deps
            return json.dumps(pkg, indent=2)

        vulnerable_deps = [
            "react-server-dom-webpack",
            "react-server-dom-parcel",
            "react-server-dom-turbopack"
        ]
        vulnerable_versions = ["19.0.0", "19.1.1", "19.2.1"]
        affected_frameworks = ["next", "waku", "@parcel/rsc", "@vitejs/plugin-rsc"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i % 4 == 0) # Generate some edge cases
                    mount_files = {}
                    cmd_path = ""

                    if category == CmdCategory.SCAN_PATH:
                        if is_edge_case:
                            # Edge/malicious cases
                            edge_case_type = random.randint(0, 3)
                            if edge_case_type == 0:
                                # Malicious/invalid path argument
                                cmd_path = FuzzHelper.get_evil_string()
                            elif edge_case_type == 1:
                                # Malformed package.json
                                scan_dir = f"scan_dir_edge_{i}"
                                mount_files[f"{scan_dir}/project_a/package.json"] = "{" + FuzzHelper.get_string(10, 50)
                                cmd_path = f"/test_data/{scan_dir}"
                            elif edge_case_type == 2:
                                # Scan a file instead of a directory
                                file_to_scan = "a_file.txt"
                                mount_files[file_to_scan] = "This is not a directory."
                                cmd_path = f"/test_data/{file_to_scan}"
                            else: # edge_case_type == 3
                                # Empty directory
                                cmd_path = f"/test_data/empty_dir_{i}"
                                # mount_files remains empty, but we need to create the dir
                                mount_files[f"empty_dir_{i}/.keep"] = ""

                        else:
                            # Normal functional tests
                            scan_dir = f"scan_dir_normal_{i}"
                            num_projects = random.randint(1, 3)
                            for j in range(num_projects):
                                project_name = f"project_{j}"
                                project_path = f"{scan_dir}/{project_name}"
                                
                                project_type = random.choice(['safe', 'vulnerable', 'framework'])

                                if project_type == 'safe':
                                    content = create_pkg_json(project_name, deps={"react": "18.2.0"})
                                elif project_type == 'vulnerable':
                                    vuln_pkg = random.choice(vulnerable_deps)
                                    vuln_ver = random.choice(vulnerable_versions)
                                    content = create_pkg_json(project_name, deps={vuln_pkg: vuln_ver})
                                else: # 'framework'
                                    framework_pkg = random.choice(affected_frameworks)
                                    content = create_pkg_json(project_name, dev_deps={framework_pkg: "15.0.0"})
                                
                                mount_files[f"{project_path}/package.json"] = content
                            
                            cmd_path = f"/test_data/{scan_dir}"

                        command = f"scan-rsc-vuln {cmd_path}"
                        cases.append(TestCase(
                            command=command,
                            category=category.value,
                            mount_files=mount_files
                        ))
                except Exception:
                    # FuzzHelper might generate invalid filenames, skip if that happens
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ReactRSCVulnScannerAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))