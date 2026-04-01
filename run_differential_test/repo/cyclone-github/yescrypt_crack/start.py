import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of the 'final_differential_test' directory to the Python path.
# This allows importing modules from the framework (BaseRepoAdapter, DiffTestEngine).
# The structure is assumed to be: final_differential_test/repo/[Author]/[Repo]/start.py
# So, ../../.. points to final_differential_test/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# ======================================================================================
# 1. Command Category Enumeration
#
# Define the core functional command combinations to be tested.
# The value of each enum member is a generic string template representing the command structure.
# This covers all primary options: -h, -w, -o, -t, -s, and stdin piping for wordlists.
# ======================================================================================
class CmdCategory(Enum):
    # Wordlist from file (-w)
    H_W = "yescrypt_crack -h <hash_file> -w <wordlist_file>"
    H_W_O = "yescrypt_crack -h <hash_file> -w <wordlist_file> -o <output_file>"
    H_W_T = "yescrypt_crack -h <hash_file> -w <wordlist_file> -t <threads>"
    H_W_S = "yescrypt_crack -h <hash_file> -w <wordlist_file> -s <seconds>"
    H_W_O_T_S = "yescrypt_crack -h <hash_file> -w <wordlist_file> -o <output_file> -t <threads> -s <seconds>"

    # Wordlist from stdin (cat ... |)
    H_STDIN = "cat <wordlist_file> | yescrypt_crack -h <hash_file>"
    H_STDIN_O = "cat <wordlist_file> | yescrypt_crack -h <hash_file> -o <output_file>"
    H_STDIN_T = "cat <wordlist_file> | yescrypt_crack -h <hash_file> -t <threads>"
    H_STDIN_S = "cat <wordlist_file> | yescrypt_crack -h <hash_file> -s <seconds>"
    H_STDIN_O_T_S = "cat <wordlist_file> | yescrypt_crack -h <hash_file> -o <output_file> -t <threads> -s <seconds>"

# ======================================================================================
# 2. Repository Adapter Implementation
#
# This class adapts the testing framework to the specific `yescrypt_crack` tool.
# It defines how to set up the Docker environment, install the tool, and sanitize its output.
# ======================================================================================
class YescryptCrackAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool from its GitHub repository."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/cyclone-github/yescrypt_crack.git && cd yescrypt_crack && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the development (agent) version of the tool from local source code."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Removes volatile and non-deterministic parts from the tool's output for stable comparison."""
        # Remove version and date line
        sanitized = re.sub(r"Cyclone's Yescrypt Cracker v.*", "[VERSION_INFO]", raw_stdout)
        # Remove timestamps (e.g., 2025/03/06 17:56:12)
        sanitized = re.sub(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", "[TIMESTAMP]", sanitized)
        # Remove file paths which are dynamically generated
        sanitized = re.sub(r"Hash file:\s+.*", "Hash file: [HASH_FILE]", sanitized)
        sanitized = re.sub(r"Wordlist:\s+.*", "Wordlist: [WORDLIST_FILE]", sanitized)
        # Remove variable counts
        sanitized = re.sub(r"Total Hashes:\s+\d+", "Total Hashes: [N]", sanitized)
        sanitized = re.sub(r"CPU Threads:\s+\d+", "CPU Threads: [N]", sanitized)
        sanitized = re.sub(r"Cracked: \d+/\d+", "Cracked: [N]/[M]", sanitized)
        # Remove performance metrics
        sanitized = re.sub(r"\d+\.?\d*\s?h/s", "[SPEED] h/s", sanitized)
        sanitized = re.sub(r"\d{2}h:\d{2}m:\d{2}s", "[ELAPSED_TIME]", sanitized)
        # Remove potential environment-specific errors
        sanitized = re.sub(r"Failed to clear screen:.*\n?", "", sanitized)
        
        return super().sanitize_stdout(sanitized)

    # ======================================================================================
    # 3. Standardized Test Case Generator
    #
    # Generates a comprehensive suite of test cases, blending normal functional tests
    # with robustness tests using malicious and boundary-value inputs.
    # ======================================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        
        # Use a static, known hash and password for predictable cracking results.
        correct_password = "cyclone123"
        correct_hash_line = "$y$j9T$z7lNWyBfW4ZruGHCsFzDz/$Sz1GtrDDnsf0KfUE8mQHNJqGyG32TDWC287DdU97dz.:cyclone123"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                # Make the first case an edge case, the rest normal.
                is_edge_case = (i == 0)

                hash_file = f"hash_{category.name}_{i}.txt"
                wordlist_file = f"wordlist_{category.name}_{i}.txt"
                output_file = f"output_{category.name}_{i}.txt"
                
                mount_files = {}

                try:
                    if is_edge_case:
                        # Generate malicious/boundary content for files and arguments
                        hash_content = FuzzHelper.get_evil_string()
                        wordlist_content = FuzzHelper.get_evil_string()
                        threads_val = FuzzHelper.get_evil_string()
                        seconds_val = FuzzHelper.get_evil_string()
                    else:
                        # Generate valid content for files and arguments
                        hash_content = correct_hash_line.split(':')[0]
                        # Create a wordlist with the correct password and some noise
                        words = [FuzzHelper.get_string(4, 10) for _ in range(20)]
                        words.insert(random.randint(0, len(words)), correct_password)
                        wordlist_content = "\n".join(words)
                        threads_val = str(FuzzHelper.get_int(1, 4))
                        seconds_val = str(FuzzHelper.get_int(1, 5))

                    mount_files[hash_file] = hash_content
                    mount_files[wordlist_file] = wordlist_content

                    # Build the command string based on the category
                    base_cmd = "yescrypt_crack"
                    
                    args = [f"-h /test_data/{hash_file}"]
                    
                    if "_O" in category.name:
                        args.append(f"-o /test_data/{output_file}")
                    if "_T" in category.name:
                        args.append(f"-t '{threads_val}'")
                    if "_S" in category.name:
                        args.append(f"-s '{seconds_val}'")
                    
                    random.shuffle(args)

                    if "STDIN" in category.name:
                        cmd_suffix = ' '.join(args)
                        command = f"cat /test_data/{wordlist_file} | {base_cmd} {cmd_suffix}"
                    else:
                        args.insert(0, f"-w /test_data/{wordlist_file}")
                        command = f"{base_cmd} {' '.join(args)}"

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files,
                    ))
                except Exception:
                    # Skip generating this test case if any error occurs (e.g., from FuzzHelper)
                    continue
        return cases

# ======================================================================================
# 4. Main Execution Block
#
# Entry point for the script. It instantiates the adapter and the test engine,
# then starts the differential testing process.
# ======================================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = YescryptCrackAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))