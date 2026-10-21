import os
import sys
import re
import random
import string
from enum import Enum

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    TREND_DEFAULT = "mcgf <csv>"
    TREND_HORIZON = "mcgf <csv> --horizon <N>"
    TREND_GENE = "mcgf <csv> --gene <GENE>"
    TREND_GENE_HORIZON = "mcgf <csv> --gene <GENE> --horizon <N>"
    MA_WINDOW = "mcgf <csv> --method ma --window <N>"
    MA_WINDOW_HORIZON = "mcgf <csv> --method ma --window <N> --horizon <N>"
    MA_WINDOW_GENE = "mcgf <csv> --method ma --window <N> --gene <GENE>"
    MA_WINDOW_GENE_HORIZON = "mcgf <csv> --method ma --window <N> --gene <GENE> --horizon <N>"
    INVALID_TREND_WITH_WINDOW = "mcgf <csv> --method trend --window <N>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class McgfAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Install the baseline (oracle) version of the tool in the container."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/AmirhosseinHonardoust/Market-Cycle-Gene-Forecasting-Engine.git && cd Market-Cycle-Gene-Forecasting-Engine && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Install the local (agent) version of the tool in the container."""
        container.exec_run("mkdir -p /repo")
        # Use os.system to leverage the host's docker CLI for copying
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested") != 0:
            raise Exception("Failed to copy agent code to container")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Sanitize the tool's output to remove volatile elements."""
        # Normalize counts
        sanitized = re.sub(r"Total observations\s*:\s*\d+", "Total observations : [COUNT]", raw_stdout)
        sanitized = re.sub(r"Total genes\s*:\s*\d+", "Total genes : [COUNT]", sanitized)
        # Normalize floating point numbers to a consistent format to avoid minor diffs
        sanitized = re.sub(r"\d+\.\d{3,}", lambda m: f"{float(m.group(0)):.3f}", sanitized)
        sanitized = re.sub(r"[-+]?\d+\.\d+", "[FLOAT]", sanitized)
        return super().sanitize_stdout(sanitized)

    def _generate_csv_content(self, is_malformed: bool, num_rows: int = 50) -> tuple[str, list[str]]:
        """
        Helper to generate CSV content.
        Returns a tuple of (csv_content, list_of_gene_names).
        """
        if is_malformed:
            choice = random.randint(0, 3)
            if choice == 0: return "", []  # Empty file
            if choice == 1: return "time_index,phase,gene,frequency\n1,a,b", []  # Malformed row
            if choice == 2: return FuzzHelper.get_csv_string(10, 5), []  # Random CSV-like junk (wrong column count)
            if choice == 3: return FuzzHelper.get_evil_string(), []  # Evil string as file content
        
        # Normal case generation
        header = "time_index,phase,gene,frequency"
        lines = [header]
        phases = ["accumulation", "early_bull", "late_bull", "bear"]
        genes = list(set(FuzzHelper.get_string(5, 10, chars=string.ascii_uppercase + "_") for _ in range(FuzzHelper.get_int(3, 5))))
        
        time_indices = sorted(random.sample(range(1, num_rows * 2), num_rows))

        for i in range(num_rows):
            gene = random.choice(genes)
            phase = random.choice(phases)
            freq = FuzzHelper.get_float(0.0, 1.0, decimals=4)
            lines.append(f"{time_indices[i]},{phase},{gene},{freq}")
            
        return "\n".join(lines), genes

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Use specific iterations for edge cases to ensure they are generated
                    is_arg_edge_case = (i == 0)
                    is_file_edge_case = (i == 1)

                    file_name = f"input_{category.name.lower()}_{i}.csv"
                    csv_content, gene_pool = self._generate_csv_content(
                        is_malformed=is_file_edge_case,
                        num_rows=FuzzHelper.get_int(20, 50)
                    )
                    
                    cmd_parts = ["mcgf", f"/test_data/{file_name}"]
                    
                    # --- Argument Generation Logic ---
                    
                    # Method and Window
                    if 'MA_' in category.name:
                        cmd_parts.append("--method ma")
                        if is_arg_edge_case:
                            window_val = random.choice([FuzzHelper.get_int(-5, 1), "abc", FuzzHelper.get_evil_string()])
                        else:
                            window_val = FuzzHelper.get_int(2, 15)
                        cmd_parts.append(f"--window {window_val}")
                    elif category == CmdCategory.INVALID_TREND_WITH_WINDOW:
                        cmd_parts.append("--method trend")
                        if is_arg_edge_case:
                            window_val = random.choice([FuzzHelper.get_int(-5, 0), "xyz", FuzzHelper.get_evil_string()])
                        else:
                            window_val = FuzzHelper.get_int(2, 10)
                        cmd_parts.append(f"--window {window_val}")

                    # Gene
                    if 'GENE' in category.name:
                        if is_arg_edge_case:
                            gene_val = FuzzHelper.get_evil_string()
                        else:
                            gene_val = random.choice(gene_pool) if gene_pool else "GENE_DEFAULT"
                        # CRITICAL FIX: Do not add extra quotes. Let the shell and framework handle it.
                        cmd_parts.append(f"--gene {gene_val}")

                    # Horizon
                    if 'HORIZON' in category.name:
                        if is_arg_edge_case:
                            horizon_val = random.choice([FuzzHelper.get_int(-5, 0), "def", FuzzHelper.get_evil_string()])
                        else:
                            horizon_val = FuzzHelper.get_int(1, 10)
                        cmd_parts.append(f"--horizon {horizon_val}")

                    full_command = " ".join(map(str, cmd_parts))

                    cases.append(TestCase(
                        command=full_command,
                        category=category.value,
                        mount_files={file_name: csv_content}
                    ))
                except Exception as e:
                    # This ensures that if one case generation fails, the whole process doesn't stop.
                    print(f"Warning: Failed to generate test case for {category.name}_{i}. Error: {e}")
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = McgfAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))