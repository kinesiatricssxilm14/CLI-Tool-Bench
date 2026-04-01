import os
import sys
import re
import json
import random
from enum import Enum

# Add parent directories to sys.path to import framework modules
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """Defines the command structures to be tested."""
    # Using --convert option
    CONVERT_DEFAULT = "postwright --convert <file>"
    CONVERT_WITH_OUTPUT = "postwright --convert <file> --output <dir>"
    CONVERT_WITH_FORMAT_TS = "postwright --convert <file> --format ts"
    CONVERT_WITH_OUTPUT_AND_FORMAT_TS = "postwright --convert <file> --output <dir> --format ts"

    # Using 'convert' subcommand
    SUBCOMMAND_CONVERT_DEFAULT = "postwright convert <file>"
    SUBCOMMAND_CONVERT_WITH_OUTPUT = "postwright convert <file> --output <dir>"
    SUBCOMMAND_CONVERT_WITH_FORMAT_TS = "postwright convert <file> --format ts"
    
    # Using short flags
    SHORT_FLAGS_DEFAULT = "postwright -c <file>"
    SHORT_FLAGS_OUTPUT_FORMAT_TS = "postwright -c <file> -o <dir> -f ts"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class PostwrightAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Node.js environment."""
        return "node:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/bhadmus/postwright.git && cd postwright && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        # Use os.system as it's simple and part of the original spec
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Sanitize tool-specific output to ensure consistent diffs."""
        # Sanitize absolute paths which can differ between containers/runs
        sanitized = re.sub(r'to\s+([/\w.-]+)', 'to <PATH>', raw_stdout)
        sanitized = re.sub(r'directory\s+"([/\w.-]+)"', 'directory "<PATH>"', sanitized)
        sanitized = re.sub(r"open\s+'([/\w.-]+)'", "open '<PATH>'", sanitized)
        # Sanitize specific known paths
        sanitized = re.sub(r'/repo/repo_to_be_tested', '<WORKDIR>', sanitized)
        sanitized = re.sub(r'/repo/postwright', '<WORKDIR_ORACLE>', sanitized)
        # Remove ANSI color codes
        return super().sanitize_stdout(sanitized)

    def _generate_postman_collection_content(self, is_edge_case: bool) -> str:
        """Helper to generate valid or malformed Postman collection JSON content."""
        if is_edge_case:
            # Return various forms of invalid or problematic content
            return random.choice([
                "",  # Empty file
                "{}", # Empty JSON
                FuzzHelper.get_evil_string(), # Malicious/junk string
                FuzzHelper.get_csv_string(), # Wrong format
                "this is not a json"
            ])
        
        # Generate a structurally valid collection
        try:
            collection = {
                "info": {
                    "_postman_id": FuzzHelper.get_string(10, 36),
                    "name": FuzzHelper.get_string(5, 20),
                    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
                },
                "item": []
            }
            # Keep item count reasonable to avoid overly large files
            for _ in range(random.randint(1, 3)):
                item = {
                    "name": FuzzHelper.get_string(5, 20),
                    "request": {
                        "method": random.choice(["GET", "POST", "PUT", "DELETE"]),
                        "header": [],
                        "url": {
                            "raw": FuzzHelper.get_url(),
                            "host": [FuzzHelper.get_domain()]
                        }
                    },
                    "response": []
                }
                collection["item"].append(item)
            return json.dumps(collection, indent=2)
        except Exception:
            # Fallback for any errors during generation
            return json.dumps({"info": {"name": "fallback_collection"}, "item": []})

    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == CASES_PER_CATEGORY - 1)
                
                try:
                    # --- 1. Input File Generation ---
                    collection_filename = f"collection_{category.name.lower()}_{i}.json"
                    collection_content = self._generate_postman_collection_content(is_edge_case)
                    
                    # --- 2. Argument Fuzzing ---
                    collection_path_arg = f"/test_data/{collection_filename}"
                    output_dir_basename = f"output_{category.name.lower()}_{i}"
                    format_arg = "ts" if "ts" in category.value else "js"

                    if is_edge_case:
                        collection_path_arg = random.choice([collection_path_arg, FuzzHelper.get_evil_string()])
                        output_dir_basename = random.choice([".", FuzzHelper.get_evil_string().replace("/", "_")])
                        format_arg = random.choice(["ts", "js", "txt", "", FuzzHelper.get_string(1, 4)])

                    # --- 3. Command Assembly ---
                    command = category.value
                    command = command.replace("<file>", collection_path_arg)
                    command = command.replace("<dir>", f"/test_data/{output_dir_basename}")
                    
                    if " ts" in category.value:
                        command = command.replace(" ts", f" {format_arg}")

                    # --- 4. Prep Script & Mounts ---
                    prep_script = ""
                    # FIX: Base the decision on the template, not the fuzzed command.
                    if ("--output" in category.value or "-o" in category.value) and output_dir_basename != ".":
                        # Create the output directory. For edge cases, this tests shell's ability to handle weird names.
                        # The framework's runner will escape this safely.
                        prep_script = f"mkdir -p /test_data/{output_dir_basename}"

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files={collection_filename: collection_content},
                        prep_script=prep_script
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
    adapter = PostwrightAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))