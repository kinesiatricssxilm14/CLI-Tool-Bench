import os
import sys
import re
import random
from enum import Enum
from datetime import date, timedelta

# Add the parent directory of the script's location to the Python path
# This is necessary to import the BaseRepoAdapter and DiffTestEngine modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command patterns of the 'lsq' CLI tool.
    Each enum value is a generic template representing a class of commands to be tested.
    This covers printing content, appending text/stdin, and searching.
    """
    PRINT_JOURNAL_DATE = "lsq -d <dir> -c -s <date>"
    PRINT_JOURNAL_DAYS_AGO = "lsq -d <dir> -c -n <N>"
    PRINT_PAGE = "lsq -d <dir> -c -p <page>"
    APPEND_TEXT_TO_PAGE = "lsq -d <dir> -a <text> -p <page> && lsq -d <dir> -c -p <page>"
    APPEND_TEXT_TO_JOURNAL = "lsq -d <dir> -a <text> -s <date> && lsq -d <dir> -c -s <date>"
    APPEND_TEXT_WITH_INDENT = "lsq -d <dir> -a <text> -p <page> -i <level> && lsq -d <dir> -c -p <page>"
    APPEND_STDIN_TO_PAGE = "cat <file> | lsq -d <dir> -A -p <page> && lsq -d <dir> -c -p <page>"
    SEARCH_FILENAME = "lsq -d <dir> -f <string>"
    SEARCH_REGEX = "lsq -d <dir> -r <regex>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class LsqAdapter(BaseRepoAdapter):
    @staticmethod
    def _shell_quote(s: str) -> str:
        """Safely quotes a string for shell command arguments."""
        return "'{}'".format(s.replace("'", "'\\''"))

    @property
    def base_image(self) -> str:
        """Specifies the Docker base image suitable for the Go toolchain."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool according to framework rules."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/jrswab/lsq.git && cd lsq && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent version of the tool according to framework rules."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        test_dir = "/test_data/notes"
        prep_script = f"mkdir -p {test_dir}/journals {test_dir}/pages"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i % 4 == 0) # Generate some edge cases
                    mount_files = {}
                    cmd_base = f"lsq -d {test_dir}"
                    cmd = ""

                    if category in [CmdCategory.PRINT_JOURNAL_DATE, CmdCategory.APPEND_TEXT_TO_JOURNAL]:
                        rand_date = date(2024, 1, 1) + timedelta(days=random.randint(0, 364))
                        date_str_flag = rand_date.strftime("%Y-%m-%d")
                        date_str_file = rand_date.strftime("%Y_%m_%d")
                        journal_filename = f"notes/journals/{date_str_file}.md"
                        mount_files[journal_filename] = f"Content for {date_str_flag}\n"

                        if is_edge_case:
                            date_str_flag = FuzzHelper.get_evil_string()

                        if category == CmdCategory.PRINT_JOURNAL_DATE:
                            cmd = f"{cmd_base} -c -s {self._shell_quote(date_str_flag)}"
                        else: # APPEND_TEXT_TO_JOURNAL
                            text = FuzzHelper.get_evil_string() if is_edge_case else "appended text"
                            cmd_part1 = f"{cmd_base} -a {self._shell_quote(text)} -s {self._shell_quote(date_str_flag)}"
                            cmd_part2 = f"{cmd_base} -c -s {self._shell_quote(date_str_flag)}"
                            cmd = f"{cmd_part1} && {cmd_part2}"

                    elif category == CmdCategory.PRINT_JOURNAL_DAYS_AGO:
                        # This test is non-deterministic based on execution time, skipping for stable results.
                        continue

                    elif category in [CmdCategory.PRINT_PAGE, CmdCategory.APPEND_TEXT_TO_PAGE, CmdCategory.APPEND_TEXT_WITH_INDENT, CmdCategory.APPEND_STDIN_TO_PAGE]:
                        page_name = f"page_{i}.md"
                        page_path = f"notes/pages/{page_name}"
                        mount_files[page_path] = f"Initial content for {page_name}\n"
                        
                        fuzzed_page_name = page_name
                        if is_edge_case:
                            evil_name = FuzzHelper.get_evil_string().replace('/','').replace('\\','')
                            # Ensure filename is not empty for the command to be valid
                            fuzzed_page_name = evil_name if evil_name else "non_empty_evil_name.md"

                        if category == CmdCategory.PRINT_PAGE:
                            cmd = f"{cmd_base} -c -p {self._shell_quote(fuzzed_page_name)}"
                        
                        elif category == CmdCategory.APPEND_TEXT_TO_PAGE:
                            text = FuzzHelper.get_evil_string() if is_edge_case else "new line of text"
                            cmd_part1 = f"{cmd_base} -a {self._shell_quote(text)} -p {self._shell_quote(fuzzed_page_name)}"
                            cmd_part2 = f"{cmd_base} -c -p {self._shell_quote(fuzzed_page_name)}"
                            cmd = f"{cmd_part1} && {cmd_part2}"

                        elif category == CmdCategory.APPEND_TEXT_WITH_INDENT:
                            text = FuzzHelper.get_evil_string() if is_edge_case else "indented item"
                            level = str(FuzzHelper.get_int(1, 5))
                            if is_edge_case:
                                evil_level = FuzzHelper.get_evil_string()
                                # An empty string is a valid test case for a flag expecting an int
                                level = evil_level
                            
                            cmd_part1 = f"{cmd_base} -a {self._shell_quote(text)} -p {self._shell_quote(fuzzed_page_name)} -i {self._shell_quote(level)}"
                            cmd_part2 = f"{cmd_base} -c -p {self._shell_quote(fuzzed_page_name)}"
                            cmd = f"{cmd_part1} && {cmd_part2}"

                        elif category == CmdCategory.APPEND_STDIN_TO_PAGE:
                            stdin_file = f"stdin_{i}.txt"
                            stdin_content = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(20, 100)
                            mount_files[stdin_file] = stdin_content
                            
                            cmd_part1 = f"cat /test_data/{stdin_file} | {cmd_base} -A -p {self._shell_quote(fuzzed_page_name)}"
                            cmd_part2 = f"{cmd_base} -c -p {self._shell_quote(fuzzed_page_name)}"
                            cmd = f"{cmd_part1} && {cmd_part2}"

                    elif category in [CmdCategory.SEARCH_FILENAME, CmdCategory.SEARCH_REGEX]:
                        search_terms = ["apple", "banana", "cherry"]
                        for term in search_terms:
                            mount_files[f"notes/pages/{term}_{i}.md"] = f"content for {term}"
                        
                        fuzzed_term = random.choice(search_terms)
                        if is_edge_case:
                            fuzzed_term = FuzzHelper.get_evil_string()

                        if category == CmdCategory.SEARCH_FILENAME:
                            cmd = f"{cmd_base} -f {self._shell_quote(fuzzed_term)}"
                        else: # SEARCH_REGEX
                            # For regex, we create a valid pattern from the term, even if it's an evil string
                            regex_term = f".*{re.escape(fuzzed_term)}.*"
                            cmd = f"{cmd_base} -r {self._shell_quote(regex_term)}"
                    
                    if not cmd:
                        continue

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=mount_files
                    ))
                except Exception:
                    # If any error occurs during case generation, skip it to ensure robustness.
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = LsqAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))