import os
import sys
import re
from enum import Enum
import random

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the different command-line argument combinations for the outlier-detect tool.
    The value of each enum member is a generic template string representing the command structure.
    """
    INPUT_ONLY = "outlier-detect --input <file>"
    INPUT_THRESHOLD = "outlier-detect --input <file> --threshold <float>"
    INPUT_OUTPUT = "outlier-detect --input <file> --output <file>"
    INPUT_VERBOSE = "outlier-detect --input <file> --verbose"
    INPUT_THRESHOLD_OUTPUT = "outlier-detect --input <file> --threshold <float> --output <file>"
    INPUT_THRESHOLD_VERBOSE = "outlier-detect --input <file> --threshold <float> --verbose"
    INPUT_OUTPUT_VERBOSE = "outlier-detect --input <file> --output <file> --verbose"
    INPUT_THRESHOLD_OUTPUT_VERBOSE = "outlier-detect --input <file> --threshold <float> --output <file> --verbose"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class OutlierDetectAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Clones the repository and installs the oracle version using pip."""
        cmd = (
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/Riley702/outlier-detection-tool.git && "
            "cd outlier-detection-tool && "
            "pip install ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies the local agent code into the container and installs it."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The first case of each category is an edge case, the rest are normal.
                    is_edge_case = (i == 0)

                    input_file_name = f"input_{category.name}_{i}.csv"
                    content = self._generate_csv_content(is_edge_case)

                    # Base command parts
                    cmd_parts = ["outlier-detect", f"--input /test_data/{input_file_name}"]
                    
                    optional_args = {}

                    if "THRESHOLD" in category.name:
                        if is_edge_case:
                            evil_val = FuzzHelper.get_evil_string()
                            threshold = evil_val.split()[0] if evil_val.strip() else "-1"
                        else:
                            threshold = FuzzHelper.get_float(0.01, 4.0, 2)
                        optional_args["--threshold"] = str(threshold)

                    if "OUTPUT" in category.name:
                        if is_edge_case:
                            evil_val = FuzzHelper.get_evil_string()
                            output_path = evil_val.replace(" ", "/")
                            if not output_path:
                                output_path = "/dev/null"
                        else:
                            output_file_name = f"output_{category.name}_{i}.csv"
                            output_path = f"/test_data/{output_file_name}"
                        optional_args["--output"] = output_path

                    if "VERBOSE" in category.name:
                        optional_args["--verbose"] = None

                    shuffled_items = list(optional_args.items())
                    random.shuffle(shuffled_items)
                    
                    for key, value in shuffled_items:
                        cmd_parts.append(key)
                        if value is not None:
                            cmd_parts.append(value)

                    command = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files={input_file_name: content}
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} index {i}. Error: {e}")
                    continue
        return cases

    def _generate_csv_content(self, is_edge_case: bool) -> str:
        """Helper to generate CSV content for normal and edge cases."""
        if is_edge_case:
            # Randomly select a type of malformed/edge case file
            edge_type = random.randint(0, 3)
            if edge_type == 0:  # Empty file
                return ""
            elif edge_type == 1:  # Header only
                return "x,y"
            elif edge_type == 2:  # Malformed CSV with non-numeric and evil strings
                return "x,y\n1,a\n" + FuzzHelper.get_evil_string() + "\n3,4"
            else:  # Wrong header or column count
                return "a,b,c\n1,2,3\n4,5,6"
        else:  # Normal case
            rows = FuzzHelper.get_int(10, 50)
            csv_lines = ["x,y"]
            for _ in range(rows):
                # Generate some potential outliers with a 5% chance
                if random.random() < 0.05:
                    x = FuzzHelper.get_int(5000, 10000) * random.choice([-1, 1])
                    y = FuzzHelper.get_int(5000, 10000) * random.choice([-1, 1])
                else:
                    x = FuzzHelper.get_int(-500, 500)
                    y = FuzzHelper.get_int(-500, 500)
                csv_lines.append(f"{x},{y}")
            return "\n".join(csv_lines)


if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = OutlierDetectAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))