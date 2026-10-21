import os
import sys
import re
from enum import Enum
import random
import string

# Add parent directory to path to import framework modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    VALIDATE = "sophone validate <number>"
    FORMAT = "sophone format <number>"
    E164 = "sophone e164 <number>"
    INTERNATIONAL = "sophone international <number>"
    OPERATOR = "sophone operator <number>"
    WALLET = "sophone wallet <number>"
    INFO = "sophone info <number>"
    WALLETINFO = "sophone walletinfo <number>"
    OPERATORS = "sophone operators"
    WALLETS = "sophone wallets"
    BATCH = "sophone batch <file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Node.js environment."""
        return "node:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/omartood/sophone.git && cd sophone && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the stdout to remove non-deterministic parts like input values,
        file paths, and counts, which cause noise in differential testing.
        """
        # First, remove ANSI color codes using the parent method.
        sanitized = super().sanitize_stdout(raw_stdout)

        # Normalize the "Processing..." line from the batch command.
        # e.g., "Processing 4 numbers from numbers.txt:" -> "Processing numbers from file:"
        sanitized = re.sub(r"Processing \d+ numbers from .*", "Processing numbers from file:", sanitized)

        # Normalize the "Summary..." line from the batch command.
        # e.g., "Summary: 2 valid, 2 invalid" -> "Summary: [counts]"
        sanitized = re.sub(r"Summary: \d+ valid, \d+ invalid", "Summary: [counts]", sanitized)

        # Normalize individual result lines in batch output to remove the non-deterministic input part.
        # e.g., "✓ 0611234567 → ..." -> "✓ [input] → ..."
        # e.g., "✗ invalid → ..." -> "✗ [input] → ..."
        sanitized = re.sub(r"(✓|✗) .*? →", r"\1 [input] →", sanitized)

        # Normalize error messages that include the invalid input.
        # e.g., '"invalid-number" contains no valid digits' -> '"[input]" contains no valid digits'
        sanitized = re.sub(r'".*?" contains no valid digits', '"[input]" contains no valid digits', sanitized)
        # e.g., '"123" is too short (3 digits)' -> '"[input]" is too short'
        sanitized = re.sub(r'".*?" is too short \(.*? digits\)', '"[input]" is too short', sanitized)
        # e.g., 'Invalid prefix for "0111234567"' -> 'Invalid prefix for "[input]"'
        sanitized = re.sub(r'Invalid prefix for ".*?"', 'Invalid prefix for "[input]"', sanitized)

        return sanitized

    def _shell_quote(self, s: str) -> str:
        """
        Safely quote a string for shell consumption by wrapping it in single quotes
        and escaping any internal single quotes. This is crucial for passing
        arbitrary strings (including evil strings) as a single command-line argument.
        """
        return "'" + s.replace("'", "'\\''") + "'"

    def _generate_somali_phone_number(self, valid=True) -> str:
        """Generates a Somali phone number in various formats."""
        if not valid:
            return FuzzHelper.get_string(5, 15)

        prefixes = ['61', '77', '62', '65', '66', '63', '64', '68', '69', '71']
        prefix = random.choice(prefixes)
        rest = ''.join(random.choices(string.digits, k=7))
        number_core = f"{prefix}{rest}"

        format_choice = random.randint(1, 5)
        if format_choice == 1:
            return f"0{number_core}"
        elif format_choice == 2:
            return f"+252{number_core}"
        elif format_choice == 3:
            return f"252{number_core}"
        elif format_choice == 4:
            return f"+252 {prefix} {rest[:3]} {rest[3:]}"
        else:
            return number_core

    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        for category in CmdCategory:
            # For commands with no arguments, one test case is sufficient
            if category in [CmdCategory.OPERATORS, CmdCategory.WALLETS]:
                cases.append(TestCase(
                    command=category.value,
                    category=category.value
                ))
                continue

            for i in range(CASES_PER_CATEGORY):
                try:
                    # Use first case for edge/invalid inputs, others for valid inputs
                    is_edge_case = (i == 0)

                    if category == CmdCategory.BATCH:
                        file_name = f"batch_test_{i}.txt"
                        content = ""
                        if is_edge_case:
                            # Test with an empty file or a file containing an evil string
                            content = FuzzHelper.get_evil_string() if random.random() > 0.5 else ""
                        else:
                            # Generate a file with a mix of valid and invalid phone numbers
                            num_lines = random.randint(5, 15)
                            lines = [self._generate_somali_phone_number(valid=random.random() > 0.2) for _ in range(num_lines)]
                            content = "\n".join(lines)

                        cmd = f"sophone batch /test_data/{file_name}"
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files={file_name: content}
                        ))
                    else:  # All other commands that take a <number> argument
                        phone_number = ""
                        if is_edge_case:
                            # Use various forms of invalid or malicious input
                            choice = random.random()
                            if choice < 0.4:
                                phone_number = FuzzHelper.get_evil_string()
                            elif choice < 0.7:
                                phone_number = str(FuzzHelper.get_int(-1000, 1000))
                            else:
                                phone_number = FuzzHelper.get_string(1, 30)
                        else:
                            phone_number = self._generate_somali_phone_number()

                        # Safely quote the argument to handle spaces and special characters
                        phone_number_arg = self._shell_quote(phone_number)
                        sub_command = category.value.split(" ")[1]
                        cmd = f"sophone {sub_command} {phone_number_arg}"

                        cases.append(TestCase(
                            command=cmd,
                            category=category.value
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate a test case for {category.name}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 3. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))