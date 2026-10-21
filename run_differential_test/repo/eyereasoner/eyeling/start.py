import os
import sys
import re
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are option strings, not full templates)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for eyeling CLI command categories.
    The value is the options string for the command. The file argument is handled separately.
    """
    # Basic reasoning
    BASIC = ""
    # Different output modes/formats
    AST = "--ast"
    PROOF_COMMENTS = "--proof-comments"
    STRINGS = "--strings"
    STREAM = "--stream"
    # Behavior modifiers
    DETERMINISTIC_SKOLEM = "--deterministic-skolem"
    ENFORCE_HTTPS = "--enforce-https"
    SUPER_RESTRICTED = "--super-restricted"
    # Key combinations
    PROOF_STRINGS = "--proof-comments --strings"
    STREAM_STRINGS = "--stream --strings"
    DETERMINISTIC_PROOF = "--deterministic-skolem --proof-comments"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class EyelingAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Node.js environment."""
        # eyeling requires Node.js >= 18
        return "node:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the stdout to remove non-deterministic parts.
        - Normalizes non-deterministic blank node identifiers (e.g., _:b0, _:b1_1).
        """
        # Replace blank node identifiers like '_:b0', '_:b1_1' with a stable placeholder.
        sanitized = re.sub(r'_:[a-zA-Z0-9_]+', '_:sanitized_blank_node', raw_stdout)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Clones and installs the oracle version of eyeling from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/eyereasoner/eyeling.git && cd eyeling && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the local agent version of eyeling."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        def _generate_n3_content(is_edge_case: bool) -> str:
            """Helper to generate N3 file content."""
            if is_edge_case:
                # 50% chance of a malicious string, 50% chance of empty content
                return FuzzHelper.get_evil_string() if FuzzHelper.get_int(0, 1) == 0 else ""
            
            # Generate plausible N3 content for normal cases
            lines = [
                f"@prefix ex: <http://{FuzzHelper.get_domain()}/>.",
                f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>."
            ]
            # Add some facts
            for _ in range(FuzzHelper.get_int(2, 5)):
                subj = f"ex:{FuzzHelper.get_string(min_len=3, max_len=10)}"
                pred = f"ex:{FuzzHelper.get_string(min_len=3, max_len=10)}"
                obj = f"ex:{FuzzHelper.get_string(min_len=3, max_len=10)}"
                lines.append(f"{subj} {pred} {obj} .")
            
            # Add a simple forward-chaining rule
            lines.append("{ ?s ?p ?o . } => { ?s a ex:Processed . }.")
            
            # Add a query to test the log:query mode
            lines.append("{ ?s a ex:Processed . } log:query { ?s a ex:QueryResult . }.")
            
            return "\n".join(lines)

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    file_name = f"fuzz_test_{category.name}_{i}.n3"
                    
                    # 20% probability for boundary/malicious cases
                    is_edge_case = (i % 5 == 4)
                    
                    content = _generate_n3_content(is_edge_case)
                    
                    options = category.value
                    file_path = f"/test_data/{file_name}"
                    
                    # Robustly build the full command
                    command_parts = ["eyeling"]
                    if options:
                        command_parts.append(options)
                    command_parts.append(file_path)
                    full_command = " ".join(command_parts)

                    # Reconstruct the generic category template for reporting
                    category_template = f"{options} <file.n3>".strip()

                    cases.append(TestCase(
                        command=full_command,
                        category=category_template, # Pass the generic structure template
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate a test case for category {category.name}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = EyelingAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))