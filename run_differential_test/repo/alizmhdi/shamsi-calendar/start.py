import os
import sys
import re
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
    Enumerates the core command structures and flag combinations for the 'shamsi-calendar' tool.
    The value of each enum member is a generic string template of the command.
    """
    BASIC = "shamsi-calendar"
    MONTH_ONLY = "shamsi-calendar --month <M>"
    YEAR_ONLY = "shamsi-calendar --year <Y>"
    MONTH_AND_YEAR = "shamsi-calendar --month <M> --year <Y>"
    THREE_MONTHS = "shamsi-calendar --three"
    FULL_YEAR = "shamsi-calendar --full-year"
    THREE_MONTHS_WITH_DATE = "shamsi-calendar --three --month <M> --year <Y>"
    REDUNDANT_FULL_YEAR_WITH_YEAR = "shamsi-calendar --full-year --year <Y>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ShamsiCalendarAdapter(BaseRepoAdapter):
    """
    Adapter for the 'shamsi-calendar' CLI tool.
    """
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image suitable for the Go application."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool by cloning from GitHub
        and installing from source, as per framework rules.
        """
        # Rule 1: Standardized Go installation command.
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/alizmhdi/shamsi-calendar.git && cd shamsi-calendar && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Copies the local agent code into the container and installs it from source.
        """
        # Rule 1: Standardized agent installation procedure.
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases, including normal and edge/malicious inputs.
        """
        cases = []
        # Rule 6: Set a small number of cases per category.
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Rule 8: Ensure at least some cases are valid.
                    # i=0 is the edge case, the rest are normal.
                    is_edge_case = (i == 0)
                    cmd = ""
                    prep_script = ""

                    # For commands that depend on the current system time, we set a fixed
                    # date in the container to ensure deterministic output.
                    if category in [CmdCategory.BASIC, CmdCategory.MONTH_ONLY, CmdCategory.THREE_MONTHS, CmdCategory.FULL_YEAR]:
                        fuzz_year = FuzzHelper.get_int(1380, 1420)
                        fuzz_month = FuzzHelper.get_int(1, 12)
                        fuzz_day = FuzzHelper.get_int(1, 28)  # Use 28 to be valid for all months
                        # Use a robust date format for `date -s`
                        prep_script = f'date -s "{fuzz_year}-{fuzz_month:02d}-{fuzz_day:02d} 12:00:00"'

                    # --- Command Assembly ---
                    if category == CmdCategory.BASIC:
                        cmd = "shamsi-calendar"
                    
                    elif category == CmdCategory.MONTH_ONLY:
                        month_val = random.choice([FuzzHelper.get_evil_string(), str(FuzzHelper.get_int(-10, 0)), str(FuzzHelper.get_int(13, 50))]) if is_edge_case else FuzzHelper.get_int(1, 12)
                        cmd = f"shamsi-calendar --month {month_val}"

                    elif category == CmdCategory.YEAR_ONLY:
                        year_val = random.choice([FuzzHelper.get_evil_string(), str(FuzzHelper.get_int(-100, 100))]) if is_edge_case else FuzzHelper.get_int(1350, 1450)
                        cmd = f"shamsi-calendar --year {year_val}"

                    elif category == CmdCategory.MONTH_AND_YEAR:
                        if is_edge_case:
                            month_val = random.choice([FuzzHelper.get_evil_string(), str(FuzzHelper.get_int(-10, 0))])
                            year_val = random.choice([FuzzHelper.get_evil_string(), str(FuzzHelper.get_int(-100, 100))])
                        else:
                            month_val = FuzzHelper.get_int(1, 12)
                            year_val = FuzzHelper.get_int(1350, 1450)
                        args = [f"--month {month_val}", f"--year {year_val}"]
                        random.shuffle(args)
                        cmd = f"shamsi-calendar {' '.join(args)}"

                    elif category == CmdCategory.THREE_MONTHS:
                        cmd = "shamsi-calendar --three"

                    elif category == CmdCategory.FULL_YEAR:
                        cmd = "shamsi-calendar --full-year"

                    elif category == CmdCategory.THREE_MONTHS_WITH_DATE:
                        if is_edge_case:
                            month_val = FuzzHelper.get_int(13, 50)
                            year_val = FuzzHelper.get_int(-100, 100)
                        else:
                            month_val = FuzzHelper.get_int(1, 12)
                            year_val = FuzzHelper.get_int(1350, 1450)
                        args = ["--three", f"--month {month_val}", f"--year {year_val}"]
                        random.shuffle(args)
                        cmd = f"shamsi-calendar {' '.join(args)}"

                    elif category == CmdCategory.REDUNDANT_FULL_YEAR_WITH_YEAR:
                        if is_edge_case:
                            # Rule 4: FuzzHelper.get_evil_string() takes no arguments
                            year_val = FuzzHelper.get_evil_string()
                        else:
                            year_val = FuzzHelper.get_int(1350, 1450)
                        args = ["--full-year", f"--year {year_val}"]
                        random.shuffle(args)
                        cmd = f"shamsi-calendar {' '.join(args)}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files={},
                        env_vars={}
                    ))
                except Exception as e:
                    # Rule 8: Do not let test case generation fail.
                    print(f"Warning: Failed to generate a test case for {category.name}. Error: {e}")
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    # Rule 3: Standardized main entry point.
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ShamsiCalendarAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))