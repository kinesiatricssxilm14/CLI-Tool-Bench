import os
import sys
import re
import random
from enum import Enum

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the types of commands to be tested for compute-wer.
    The value of each enum member is a generic string template of the command.
    """
    # Basic file comparison
    FILE_BASIC = "compute-wer <ref_file> <hyp_file>"
    # Core options
    FILE_CHAR = "compute-wer --char <ref_file> <hyp_file>"
    FILE_CASE_SENSITIVE = "compute-wer --case-sensitive <ref_file> <hyp_file>"
    FILE_REMOVE_TAG = "compute-wer --remove-tag <ref_file> <hyp_file>"
    FILE_ALIGN_HYP = "compute-wer --align-to-hyp <ref_file> <hyp_file>"
    # Options with arguments
    FILE_IGNORE = "compute-wer --ignore-file <ignore_file> <ref_file> <hyp_file>"
    FILE_MAX_WER = "compute-wer --max-wer <float> <ref_file> <hyp_file>"
    FILE_SORT_UTT = "compute-wer --sort utt <ref_file> <hyp_file>"
    FILE_SORT_WER = "compute-wer --sort wer <ref_file> <hyp_file>"
    # Combinations of options
    FILE_CHAR_CASE_SENSITIVE = "compute-wer --char --case-sensitive <ref_file> <hyp_file>"
    FILE_REMOVE_TAG_IGNORE = "compute-wer --remove-tag --ignore-file <ignore_file> <ref_file> <hyp_file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class ComputeWerAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Specifies the Docker base image suitable for the Python tool."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the command output to remove volatile data like percentages,
        which can have minor floating-point differences.
        """
        # Sanitize floating point percentages like "50.00 %" to "[PERCENTAGE]%"
        sanitized = re.sub(r"\d+\.\d{2}\s*%", "[PERCENTAGE]%", raw_stdout)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/pengzhendong/compute-wer.git && cd compute-wer && pip install ."
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
    def _generate_wer_file_content(self, num_lines: int, with_tags: bool, with_case_diff: bool) -> tuple[str, str]:
        """Helper to generate plausible content for reference and hypothesis files."""
        ref_lines = []
        hyp_lines = []
        base_words = ["hello", "world", "this", "is", "a", "test", "for", "speech", "recognition", "systems"]

        for i in range(num_lines):
            utt_id = f"utt_{i+1}"
            
            ref_text_list = random.sample(base_words, k=random.randint(2, len(base_words)-1))
            if with_case_diff:
                ref_text_list = [w.upper() if random.random() > 0.5 else w.lower() for w in ref_text_list]
            ref_text = " ".join(ref_text_list)

            hyp_text_list = list(ref_text_list)
            if random.random() > 0.2 and len(hyp_text_list) > 0:
                action = random.choice(["sub", "del", "ins"])
                pos = random.randint(0, len(hyp_text_list) - 1)
                if action == "sub" and len(hyp_text_list) > 0:
                    hyp_text_list[pos] = random.choice(base_words)
                elif action == "del" and len(hyp_text_list) > 0:
                    hyp_text_list.pop(pos)
                elif action == "ins":
                    hyp_text_list.insert(pos, random.choice(base_words))
            
            if with_case_diff:
                 hyp_text_list = [w.lower() for w in hyp_text_list]

            hyp_text = " ".join(hyp_text_list)

            if with_tags:
                ref_text = f"<noise> {ref_text} </noise>"
                hyp_text = f"{hyp_text} <hesitation>"

            ref_lines.append(f"{utt_id} {ref_text}")
            hyp_lines.append(f"{utt_id} {hyp_text}")
        
        return "\n".join(ref_lines), "\n".join(hyp_lines)

    def generate_test_cases(self) -> list[TestCase]:
        """Generates a list of TestCase objects for differential testing."""
        cases = []
        
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == CASES_PER_CATEGORY - 1)
                    
                    mount_files = {}
                    command = category.value
                    
                    # --- File Content Generation ---
                    ref_file = f"ref_{category.name}_{i}.txt"
                    hyp_file = f"hyp_{category.name}_{i}.txt"
                    
                    if is_edge_case:
                        # Alternate between empty files and files with evil strings
                        if i % 2 == 0:
                            ref_content, hyp_content = "", ""
                        else:
                            ref_content = f"utt1 {FuzzHelper.get_evil_string()}"
                            hyp_content = f"utt1 {FuzzHelper.get_evil_string()}"
                    else:
                        with_tags = "remove-tag" in command
                        with_case_diff = "case-sensitive" in command
                        ref_content, hyp_content = self._generate_wer_file_content(
                            num_lines=random.randint(2, 5),
                            with_tags=with_tags,
                            with_case_diff=with_case_diff
                        )
                    
                    mount_files[ref_file] = ref_content
                    mount_files[hyp_file] = hyp_content
                    command = command.replace("<ref_file>", f"/test_data/{ref_file}")
                    command = command.replace("<hyp_file>", f"/test_data/{hyp_file}")

                    # --- Handle options with arguments ---
                    if "<ignore_file>" in command:
                        ignore_file = f"ignore_{category.name}_{i}.txt"
                        if is_edge_case:
                            ignore_content = FuzzHelper.get_evil_string()
                        else:
                            ignore_content = "a\nis\nthe\nworld"
                        mount_files[ignore_file] = ignore_content
                        command = command.replace("<ignore_file>", f"/test_data/{ignore_file}")

                    if "<float>" in command:
                        if is_edge_case:
                            # FIX: Provide a more targeted invalid input for a float parameter.
                            # FuzzHelper.get_evil_string() is too broad and can cause unpredictable errors.
                            # A non-numeric string is a better test for type validation.
                            max_wer_val = FuzzHelper.get_string(5, 10, chars=string.ascii_letters)
                        else:
                            max_wer_val = str(FuzzHelper.get_float(0.0, 1.0))
                        command = command.replace("<float>", max_wer_val)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = ComputeWerAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))