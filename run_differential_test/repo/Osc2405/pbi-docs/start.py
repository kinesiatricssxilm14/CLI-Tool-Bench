import os
import sys
import re
import random
import zipfile
import io
import json
import base64
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command structures of pbi-docs.
    Each enum value is a template representing a specific usage pattern.
    """
    INPUT_BASIC = "pbi-docs --input <file>"
    INPUT_WITH_OUTPUT = "pbi-docs --input <file> --output <dir>"
    INPUT_WITH_LANG = "pbi-docs --input <file> --lang <lang>"
    INPUT_WITH_VERBOSE = "pbi-docs --input <file> --verbose"
    BATCH_BASIC = "pbi-docs --batch <pattern>"
    BATCH_WITH_OPTIONS = "pbi-docs --batch <pattern> --output <dir> --lang <lang>"
    DIFF_BASIC = "pbi-docs --diff <file1> <file2>"
    DIFF_WITH_OPTIONS = "pbi-docs --diff <file1> <file2> --output <dir> --verbose"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class PbiDocsAdapter(BaseRepoAdapter):
    """
    Adapter for the pbi-docs CLI tool.
    Handles installation, test case generation, and output sanitization.
    """

    @property
    def base_image(self) -> str:
        """Specifies the Docker base image suitable for the Python tool."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Removes volatile, non-deterministic strings from the tool's stdout.
        """
        sanitized = re.sub(r"Generated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "Generated: [TIMESTAMP]", raw_stdout)
        sanitized = re.sub(r"diff_.*\.json", "diff_output.json", sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        """Installs the baseline version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Osc2405/pbi-docs.git && cd pbi-docs && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the local agent version of the tool into the container."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _create_pbit_file_content(self, is_evil: bool, variation: int = 0) -> bytes:
        """
        Creates content for a fake .pbit file (a zip archive).
        Returns bytes, as zip files are binary.
        """
        if is_evil:
            evil_type = variation % 4
            if evil_type == 0:
                # Not a zip file at all, just random bytes or evil string
                return FuzzHelper.get_evil_string().encode('utf-8', errors='ignore')
            elif evil_type == 1:
                # Zip with evil string as schema content
                schema_content = FuzzHelper.get_evil_string()
            elif evil_type == 2:
                # Zip with malformed JSON
                schema_content = '{"key": "value", "data":'
            else:
                # Zip without the required DataModelSchema file
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr('some_other_file.txt', 'data')
                return zip_buffer.getvalue()
        else:  # Normal cases
            base_model = {
                "model": {
                    "tables": [{"name": "Sales", "columns": [{"name": "Amount", "dataType": "decimal"}]}],
                    "measures": [{"name": "Total Sales", "expression": "SUM(Sales[Amount])"}],
                    "relationships": []
                }
            }
            if variation > 0:
                base_model["model"]["measures"].append({
                    "name": f"New_Measure_{variation}",
                    "expression": "COUNT(Sales[Amount])"
                })
            schema_content = json.dumps(base_model)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('DataModelSchema', schema_content)
        return zip_buffer.getvalue()

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for all command categories.
        Uses a prep_script to create binary files from base64 encoded strings,
        working around the framework's text-only file mounting.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        DATA_DIR = "/test_data"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0)  # Make the first case of each category an edge case
                cmd = ""
                mount_files = {}
                prep_scripts = []

                try:
                    if category in [
                        CmdCategory.INPUT_BASIC, CmdCategory.INPUT_WITH_OUTPUT,
                        CmdCategory.INPUT_WITH_LANG, CmdCategory.INPUT_WITH_VERBOSE
                    ]:
                        file_name = f"fuzz_{i}.pbit"
                        file_path = f"{DATA_DIR}/{file_name}"
                        binary_content = self._create_pbit_file_content(is_edge_case, i)
                        b64_content = base64.b64encode(binary_content).decode('ascii')
                        mount_files[f"{file_name}.b64"] = b64_content
                        prep_scripts.append(f"base64 -d {DATA_DIR}/{file_name}.b64 > {file_path}")

                        if category == CmdCategory.INPUT_BASIC:
                            cmd = f"pbi-docs --input {file_path}"
                        elif category == CmdCategory.INPUT_WITH_OUTPUT:
                            output_dir = f"{DATA_DIR}/{FuzzHelper.get_string(5, 10)}" if is_edge_case else f"{DATA_DIR}/out_{i}"
                            cmd = f'pbi-docs --input {file_path} --output "{output_dir}"'
                        elif category == CmdCategory.INPUT_WITH_LANG:
                            lang = FuzzHelper.get_string(1, 5) if is_edge_case else random.choice(["en", "es"])
                            cmd = f"pbi-docs --input {file_path} --lang {lang}"
                        elif category == CmdCategory.INPUT_WITH_VERBOSE:
                            cmd = f"pbi-docs --input {file_path} --verbose"

                    elif category in [CmdCategory.BATCH_BASIC, CmdCategory.BATCH_WITH_OPTIONS]:
                        num_files = 3
                        prep_scripts.append(f"mkdir -p {DATA_DIR}/batch_dir_{i}")
                        for j in range(num_files):
                            file_name = f"batch_{i}_{j}.pbit"
                            file_path = f"{DATA_DIR}/batch_dir_{i}/{file_name}"
                            is_file_evil = is_edge_case and (j == 0)
                            binary_content = self._create_pbit_file_content(is_file_evil, i + j)
                            b64_content = base64.b64encode(binary_content).decode('ascii')
                            mount_files[f"batch_dir_{i}/{file_name}.b64"] = b64_content
                            prep_scripts.append(f"base64 -d {DATA_DIR}/batch_dir_{i}/{file_name}.b64 > {file_path}")
                        
                        pattern = f"'{DATA_DIR}/batch_dir_{i}/*.pbit'"
                        if is_edge_case:
                            pattern = f"'{FuzzHelper.get_evil_string()}'"

                        if category == CmdCategory.BATCH_BASIC:
                            cmd = f"pbi-docs --batch {pattern}"
                        else:
                            output_dir = f"{DATA_DIR}/batch_out_{i}"
                            lang = FuzzHelper.get_string(3, 3) if is_edge_case else random.choice(["en", "es"])
                            cmd = f'pbi-docs --batch {pattern} --output "{output_dir}" --lang {lang}'

                    elif category in [CmdCategory.DIFF_BASIC, CmdCategory.DIFF_WITH_OPTIONS]:
                        file1_name, file2_name = f"diff_{i}_v1.pbit", f"diff_{i}_v2.pbit"
                        file1_path, file2_path = f"{DATA_DIR}/{file1_name}", f"{DATA_DIR}/{file2_name}"

                        for fn, var in [(file1_name, 1), (file2_name, 2)]:
                            is_file_evil = is_edge_case and (var == 1)
                            binary_content = self._create_pbit_file_content(is_file_evil, var)
                            b64_content = base64.b64encode(binary_content).decode('ascii')
                            mount_files[f"{fn}.b64"] = b64_content
                            prep_scripts.append(f"base64 -d {DATA_DIR}/{fn}.b64 > {DATA_DIR}/{fn}")

                        if category == CmdCategory.DIFF_BASIC:
                            cmd = f"pbi-docs --diff {file1_path} {file2_path}"
                        else:
                            output_dir = f"{DATA_DIR}/diff_out_{i}"
                            cmd = f'pbi-docs --diff {file1_path} {file2_path} --output "{output_dir}" --verbose'

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            prep_script=" && ".join(prep_scripts),
                            mount_files=mount_files
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} index {i}: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = PbiDocsAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))