import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    # inspect command variations
    INSPECT_LS = "debx inspect <package.deb>"
    INSPECT_JSON = "debx inspect --format=json <package.deb>"
    INSPECT_CSV = "debx inspect --format=csv <package.deb>"
    INSPECT_FIND = "debx inspect --format=find <package.deb>"

    # unpack command variations
    UNPACK_BASIC = "debx unpack <package.deb>"
    UNPACK_DIR = "debx unpack <package.deb> -d <dir>"
    UNPACK_KEEP_ARCHIVES = "debx unpack <package.deb> --keep-archives"
    UNPACK_DIR_KEEP_ARCHIVES = "debx unpack <package.deb> -d <dir> --keep-archives"

    # pack command variations
    PACK_BASIC = "debx pack --control <file>:/control --data <file>:/path/file -o <output.deb>"
    PACK_MODIFIERS = "debx pack --control <file>:/control --data <file>:/path/file:mode=<mode> -o <output.deb>"
    PACK_MULTIPLE = "debx pack --control <file>:/control --data <f1>:/p1 --data <f2>:/p2 -o <output.deb>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class DebxAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitize volatile output like timestamps, mtime values, and md5 hashes.
        """
        # Replace date/time strings like "06 May 15:30" with a placeholder
        sanitized = re.sub(r'\d{1,2} \w{3} \d{2}:\d{2}', '[TIMESTAMP]', raw_stdout)
        # Replace JSON mtime values like '"mtime": 1234567890' with a fixed value
        sanitized = re.sub(r'"mtime":\s*\d+', '"mtime": 0', sanitized)
        # Replace JSON md5 hash values
        sanitized = re.sub(r'"md5":\s*"[a-f0-9]{32}"', '"md5": "[MD5_HASH]"', sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/mosquito/debx.git && cd debx && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _sanitize_file_content(self, content: str) -> str:
        """Removes null bytes from strings to prevent file writing errors in the framework."""
        return content.replace('\x00', '')

    def _generate_control_file_content(self, is_edge_case: bool) -> str:
        """Helper to generate content for the 'control' file."""
        if is_edge_case:
            return self._sanitize_file_content(FuzzHelper.get_evil_string())

        package = FuzzHelper.get_string(5, 15, "abcdefghijklmnopqrstuvwxyz-")
        version = f"{FuzzHelper.get_int(0, 10)}.{FuzzHelper.get_int(0, 20)}.{FuzzHelper.get_int(0, 99)}"
        maintainer = f"{FuzzHelper.get_string(5,10)} <{FuzzHelper.get_email()}>"
        description = FuzzHelper.get_string(20, 50)
        return (
            f"Package: {package}\n"
            f"Version: {version}\n"
            f"Architecture: all\n"
            f"Maintainer: {maintainer}\n"
            f"Description: {description}\n"
        )

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        # This script creates a valid .deb file to be used by inspect and unpack commands.
        prep_script_for_deb = (
            "mkdir -p /test_data/prep_data && "
            "echo 'Package: prep-pkg\nVersion: 1.0\nArchitecture: all\nMaintainer: test\nDescription: test' > /test_data/prep_data/control && "
            "echo 'hello world' > /test_data/prep_data/datafile && "
            "debx pack --control /test_data/prep_data/control:/control --data /test_data/prep_data/datafile:/usr/bin/app -o /test_data/test.deb"
        )

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # First case of each category is an edge case
                    cmd = ""
                    mount_files = {}
                    prep_script = None

                    # --- Pack Commands ---
                    if category.name.startswith("PACK"):
                        output_deb = f"/test_data/output_{category.name}_{i}.deb"
                        control_filename = f"control_{category.name}_{i}"
                        control_content = self._generate_control_file_content(is_edge_case)
                        mount_files[control_filename] = control_content

                        if category == CmdCategory.PACK_BASIC:
                            data_filename = f"data_{i}.txt"
                            data_content = self._sanitize_file_content(FuzzHelper.get_evil_string()) if is_edge_case else FuzzHelper.get_string(10, 100)
                            mount_files[data_filename] = data_content
                            dest_path = FuzzHelper.get_filepath(absolute=True) if is_edge_case else f"/usr/share/doc/pkg_{i}/file.txt"
                            cmd = f"debx pack --control /test_data/{control_filename}:/control --data /test_data/{data_filename}:{dest_path} -o {output_deb}"

                        elif category == CmdCategory.PACK_MODIFIERS:
                            data_filename = f"data_{i}.bin"
                            data_content = self._sanitize_file_content(FuzzHelper.get_evil_string()) if is_edge_case else "valid_binary_content"
                            mount_files[data_filename] = data_content
                            dest_path = f"/usr/bin/app_{i}"
                            if is_edge_case:
                                mode = random.choice([FuzzHelper.get_evil_string(), "999", "-1", "abc", "07778"])
                                uid = random.choice([FuzzHelper.get_evil_string(), str(FuzzHelper.get_int(-100, -1)), str(FuzzHelper.get_int(100000, 999999))])
                                gid = random.choice([FuzzHelper.get_evil_string(), str(FuzzHelper.get_int(-100, -1)), str(FuzzHelper.get_int(100000, 999999))])
                                # Sanitize values to prevent breaking the shell command itself
                                mode = str(mode).replace("'", "").replace("`", "")
                                uid = str(uid).replace("'", "").replace("`", "")
                                gid = str(gid).replace("'", "").replace("`", "")
                            else:
                                mode = "0755"
                                uid = str(FuzzHelper.get_int(0, 1000))
                                gid = str(FuzzHelper.get_int(0, 1000))
                            cmd = f"debx pack --control /test_data/{control_filename}:/control --data /test_data/{data_filename}:{dest_path}:mode={mode},uid={uid},gid={gid} -o {output_deb}"

                        elif category == CmdCategory.PACK_MULTIPLE:
                            data_filename1 = f"data_{i}_1.txt"
                            data_filename2 = f"data_{i}_2.log"
                            mount_files[data_filename1] = FuzzHelper.get_string(10, 50)
                            mount_files[data_filename2] = self._sanitize_file_content(FuzzHelper.get_evil_string()) if is_edge_case else FuzzHelper.get_csv_string(5, 3)
                            dest_path1 = f"/etc/app_{i}/conf.txt"
                            dest_path2 = f"/var/log/app_{i}.log"
                            cmd = f"debx pack --control /test_data/{control_filename}:/control --data /test_data/{data_filename1}:{dest_path1} --data /test_data/{data_filename2}:{dest_path2} -o {output_deb}"

                    # --- Inspect and Unpack Commands ---
                    else:
                        deb_file_path = "/test_data/test.deb"
                        if is_edge_case:
                            corrupted_deb_name = f"corrupt_{i}.deb"
                            mount_files[corrupted_deb_name] = self._sanitize_file_content(FuzzHelper.get_evil_string())
                            deb_file_path = f"/test_data/{corrupted_deb_name}"
                        else:
                            prep_script = prep_script_for_deb

                        if category == CmdCategory.INSPECT_LS:
                            cmd = f"debx inspect {deb_file_path}"
                        elif category == CmdCategory.INSPECT_JSON:
                            fmt = "json" if not is_edge_case else FuzzHelper.get_string(1, 10).replace("'", "")
                            cmd = f"debx inspect --format={fmt} {deb_file_path}"
                        elif category == CmdCategory.INSPECT_CSV:
                            cmd = f"debx inspect --format=csv {deb_file_path}"
                        elif category == CmdCategory.INSPECT_FIND:
                            cmd = f"debx inspect --format=find {deb_file_path}"
                        elif category == CmdCategory.UNPACK_BASIC:
                            cmd = f"debx unpack {deb_file_path}"
                        elif category == CmdCategory.UNPACK_DIR:
                            out_dir = "/test_data/unpack_dir" if not is_edge_case else FuzzHelper.get_filepath(absolute=False).replace("'", "")
                            cmd = f"debx unpack {deb_file_path} -d {out_dir}"
                        elif category == CmdCategory.UNPACK_KEEP_ARCHIVES:
                            cmd = f"debx unpack {deb_file_path} --keep-archives"
                        elif category == CmdCategory.UNPACK_DIR_KEEP_ARCHIVES:
                            out_dir = "/test_data/unpack_dir_keep"
                            cmd = f"debx unpack {deb_file_path} -d {out_dir} --keep-archives"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"      ⚠️  Skipping test case generation for category {category.name} due to error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = DebxAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))