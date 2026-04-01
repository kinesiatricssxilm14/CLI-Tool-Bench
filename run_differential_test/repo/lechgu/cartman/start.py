import os
import sys
import re
from enum import Enum
import random
import string
import shlex

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command structures of the 'cartman' CLI tool.
    The value of each enum member is a generic command template string.
    """
    # 'init' command variations
    INIT_BASIC = "cartman init"
    INIT_FORCE = "cartman init --force"
    INIT_WITH_NAME = "cartman init --name <name>"
    INIT_WITH_VALIDITY = "cartman init --validity-days <days>"
    INIT_FULL = "cartman init --force --name <name> --validity-days <days>"

    # 'issue' command variations (requires 'init' as a prerequisite)
    ISSUE_WITH_DNS = "cartman issue --name <name> --dns <dns>"
    ISSUE_WITH_IP = "cartman issue --name <name> --ip <ip>"
    ISSUE_WITH_DNS_IP = "cartman issue --name <name> --dns <dns> --ip <ip>"
    ISSUE_MULTIPLE_DNS = "cartman issue --name <name> --dns <dns1> --dns <dns2>"
    ISSUE_MULTIPLE_IP = "cartman issue --name <name> --ip <ip1> --ip <ip2>"
    ISSUE_WITH_VALIDITY = "cartman issue --name <name> --dns <dns> --validity-days <days>"
    ISSUE_WITH_FORCE = "cartman issue --name <name> --dns <dns> --force"
    ISSUE_FULL = "cartman issue --name <name> --dns <dns> --ip <ip> --validity-days <days> --force"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class CartmanAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool in the container."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/lechgu/cartman.git && cd cartman && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent (version to be tested) in the container."""
        container.exec_run("mkdir -p /repo")
        # Use os.system for simplicity as it's a one-off command.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the tool's output by removing volatile information like timestamps
        and cryptographic values from the certificate details.
        """
        sanitized = super().sanitize_stdout(raw_stdout)
        
        # Remove validity dates which are always different
        sanitized = re.sub(r"Not Before: .*", "Not Before: [REDACTED]", sanitized)
        sanitized = re.sub(r"Not After\s*: .*", "Not After : [REDACTED]", sanitized)
        
        # Remove serial number, which is a large, volatile hex string
        sanitized = re.sub(r"Serial Number:\s*\n\s*([0-9a-fA-F:\s]+)", "Serial Number: [REDACTED]", sanitized, re.MULTILINE)
        
        # Remove the public key modulus, which is a large block of hex
        sanitized = re.sub(r"Modulus:\s*\n\s*([0-9a-fA-F:\s\n]+?)(?=Exponent:)", "Modulus: [REDACTED]\n", sanitized, re.DOTALL)
        
        # Remove the signature value, another large block of hex at the end
        sanitized = re.sub(r"Signature Algorithm: [^\n]+(?:\n\s+[0-9a-fA-F:\s]+)+", "Signature Algorithm: [REDACTED]", sanitized)

        return sanitized

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make 1 out of 5 cases an edge case for robustness testing
                    is_edge_case = (i == 0)
                    
                    # Generate a safe name for certificate files/directories
                    safe_name = f"cert_{FuzzHelper.get_string(5, 8, chars=string.ascii_lowercase)}"
                    
                    cmd = ""
                    prep_script = ""
                    args = []

                    # --- 'init' command test cases ---
                    if category.name.startswith("INIT"):
                        prep_script = "rm -rf .cartman"
                        
                        if category in [CmdCategory.INIT_FORCE, CmdCategory.INIT_FULL]:
                            args.append("--force")

                        if category in [CmdCategory.INIT_WITH_NAME, CmdCategory.INIT_FULL]:
                            name_val = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(5, 15)
                            args.append(f"--name {shlex.quote(name_val)}")

                        if category in [CmdCategory.INIT_WITH_VALIDITY, CmdCategory.INIT_FULL]:
                            days_val = random.choice(["abc", -1, 999999]) if is_edge_case else FuzzHelper.get_int(1, 8000)
                            args.append(f"--validity-days {days_val}")
                        
                        command_part = f"cartman init {' '.join(args)}"
                        # After running init, verify the root cert was created and is valid
                        verification_part = "if [ -f .cartman/cert.pem ]; then openssl x509 -in .cartman/cert.pem -text -noout; fi"
                        cmd = f"{command_part} && {verification_part}"

                    # --- 'issue' command test cases ---
                    elif category.name.startswith("ISSUE"):
                        # Prerequisite: clean up previous runs and initialize a new CA
                        prep_script = f"rm -rf .cartman {safe_name} && cartman init"
                        # The --name flag is required for 'issue'
                        args.append(f"--name {shlex.quote(safe_name)}")

                        if category in [CmdCategory.ISSUE_WITH_FORCE, CmdCategory.ISSUE_FULL]:
                            args.append("--force")
                        
                        if category in [CmdCategory.ISSUE_WITH_VALIDITY, CmdCategory.ISSUE_FULL]:
                            days_val = random.choice(["xyz", -1, 0]) if is_edge_case else FuzzHelper.get_int(1, 1000)
                            args.append(f"--validity-days {days_val}")

                        # Generate DNS arguments
                        dns_count = 0
                        if category in [CmdCategory.ISSUE_WITH_DNS, CmdCategory.ISSUE_WITH_DNS_IP, CmdCategory.ISSUE_WITH_VALIDITY, CmdCategory.ISSUE_WITH_FORCE, CmdCategory.ISSUE_FULL]:
                            dns_count = 1
                        elif category == CmdCategory.ISSUE_MULTIPLE_DNS:
                            dns_count = random.randint(2, 3)
                        
                        for _ in range(dns_count):
                            dns_val = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_domain()
                            args.append(f"--dns {shlex.quote(dns_val)}")

                        # Generate IP arguments
                        ip_count = 0
                        if category in [CmdCategory.ISSUE_WITH_IP, CmdCategory.ISSUE_WITH_DNS_IP, CmdCategory.ISSUE_FULL]:
                            ip_count = 1
                        elif category == CmdCategory.ISSUE_MULTIPLE_IP:
                            ip_count = random.randint(2, 3)

                        for _ in range(ip_count):
                            ip_val = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_ip()
                            args.append(f"--ip {shlex.quote(ip_val)}")

                        command_part = f"cartman issue {' '.join(args)}"
                        # After running issue, verify the leaf cert was created and is valid
                        verification_part = f"if [ -f {safe_name}/cert.pem ]; then openssl x509 -in {safe_name}/cert.pem -text -noout; fi"
                        cmd = f"{command_part} && {verification_part}"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            prep_script=prep_script
                        ))
                except Exception as e:
                    # Failsafe to prevent a single broken generator from stopping the whole process
                    print(f"Skipping test case generation for {category.name} due to error: {e}", file=sys.stderr)
                    continue
        return cases

# =====================================================================
# 4. Main Execution Block
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = CartmanAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))