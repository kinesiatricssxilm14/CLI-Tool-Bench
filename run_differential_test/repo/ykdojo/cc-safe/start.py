import os
import sys
import re
import json
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command patterns of the cc-safe CLI tool.
    The value of each enum member is a generic command structure template.
    """
    SCAN_BASIC = "cc-safe <directory>"
    SCAN_NO_LOW = "cc-safe <directory> --no-low"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CcSafeAdapter(BaseRepoAdapter):
    """
    Adapter for the cc-safe CLI tool, responsible for installation,
    test case generation, and output sanitization.
    """

    # Pre-defined lists of commands for generating test configurations, based on README
    HIGH_RISK = [
        "rm -rf /", "rm -f somefile", "Bash", "chmod 777 file", "chmod -R 777 dir",
        "curl http://example.com | sh", "dd if=/dev/zero of=/dev/sda", "mkfs.ext4 /dev/sdb",
        "fdisk /dev/sdc", "> /dev/sdd", "git push --force", "--dangerously-skip-permissions"
    ]
    MEDIUM_RISK = [
        "sudo apt-get update", "git reset --hard", "git clean -fd", "npm publish",
        "yarn publish", "twine upload", "gem push", "cargo publish",
        "docker run --privileged ubuntu", "docker run -v /:/hostroot ubuntu", "eval 'ls'",
        "git push --force-with-lease"
    ]
    LOW_RISK = [
        "sudo du -sh /", "sudo ls /root", "sudo cat /etc/shadow", "sudo apt-cache search nginx",
        "sudo ps aux", "git push", "rm file.txt", "rm *"
    ]
    SAFE = [
        "ls -l", "cat file.txt", "echo 'hello'", "docker exec mycontainer ls",
        "podman exec mycontainer ls", "kubectl exec mypod -- ls", "docker run ubuntu echo 'safe'"
    ]

    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image. cc-safe requires Node.js 22+.
        """
        return "node:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from its GitHub repository.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ykdojo/cc-safe.git && cd cc-safe && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the development (agent) version of the tool from the local filesystem.
        """
        container.exec_run("mkdir -p /repo")
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested") != 0:
            raise Exception("Failed to copy agent code to container")
        
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the tool's output to remove volatile information like paths,
        ensuring deterministic output for comparison.
        """
        text = super().sanitize_stdout(raw_stdout)

        # Normalize header messages that are not part of the core findings
        text = re.sub(r"Scanning for Claude Code settings files in: .*", "[HEADER] Scanning started", text)
        text = re.sub(r"Found \d+ settings file\(s\), analyzing...", "[HEADER] Analysis started", text)
        
        # Normalize the file path that is the subject of a report. This is a key volatile element.
        text = re.sub(r"([/][\w/.-]*)?\.claude/settings(\.local)?\.json", "[FILE_REPORT]", text)

        # To handle non-deterministic order of file reports and findings,
        # we sort all non-empty lines. This creates a canonical representation of the output,
        # which is robust for differential testing.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        lines.sort()

        return "\n".join(lines)

    def _generate_settings_content(self, is_edge_case: bool, case_index: int) -> str:
        """
        Helper to generate content for .claude/settings.json files for testing.
        """
        if is_edge_case:
            choice = case_index % 4
            if choice == 0:
                # Malformed JSON to test parsing robustness
                return FuzzHelper.get_evil_string()
            elif choice == 1:
                # Valid JSON, but with a malicious string as a command
                settings_data = {"permissions": {"allow": [FuzzHelper.get_evil_string(), "ls -l"]}}
                return json.dumps(settings_data)
            elif choice == 2:
                # Empty file content
                return ""
            else:
                # Valid JSON structure, but missing the expected 'allow' key
                settings_data = {"permissions": {"other_key": ["cat file"]}}
                return json.dumps(settings_data)
        else:
            # Normal case: Generate a realistic mix of different risk levels
            commands = []
            commands.extend(random.sample(self.HIGH_RISK, k=min(len(self.HIGH_RISK), random.randint(1, 2))))
            commands.extend(random.sample(self.MEDIUM_RISK, k=min(len(self.MEDIUM_RISK), random.randint(0, 2))))
            commands.extend(random.sample(self.LOW_RISK, k=min(len(self.LOW_RISK), random.randint(0, 2))))
            commands.extend(random.sample(self.SAFE, k=min(len(self.SAFE), random.randint(1, 2))))
            random.shuffle(commands)
            
            settings_data = {"permissions": {"allow": commands}}
            return json.dumps(settings_data, indent=2)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a comprehensive list of TestCase objects for differential testing,
        including normal, boundary, and malicious inputs.
        """
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    test_dir = f"test_project_{category.name}_{i}"
                    dir_to_scan = f"/test_data/{test_dir}"
                    settings_filename = random.choice(["settings.json", "settings.local.json"])
                    full_path_in_mount = f"{test_dir}/.claude/{settings_filename}"
                    mount_files = {}
                    
                    # Use index 'i' to create diverse and predictable test variations
                    # i=0, 1: Normal cases to ensure core functionality is tested
                    # i=2: Malformed settings file content
                    # i=3: Non-existent directory to scan
                    # i=4: Scan a file instead of a directory
                    
                    if i in [0, 1]:
                        content = self._generate_settings_content(is_edge_case=False, case_index=i)
                        mount_files = {full_path_in_mount: content}
                    
                    elif i == 2:
                        content = self._generate_settings_content(is_edge_case=True, case_index=i)
                        mount_files = {full_path_in_mount: content}
                        
                    elif i == 3:
                        dir_to_scan = f"/test_data/non_existent_dir_{i}"
                        
                    elif i == 4:
                        file_to_scan_path = f"file_to_scan_{i}.txt"
                        dir_to_scan = f"/test_data/{file_to_scan_path}"
                        mount_files = {file_to_scan_path: "This is a file, not a directory."}

                    # --- Command Assembly ---
                    cmd_parts = ["cc-safe", dir_to_scan]
                    if category == CmdCategory.SCAN_NO_LOW:
                        cmd_parts.append("--no-low")
                    cmd = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    # Ensure the generator itself doesn't crash
                    print(f"Warning: Failed to generate a test case for {category.name}, index {i}: {e}")
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CcSafeAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))