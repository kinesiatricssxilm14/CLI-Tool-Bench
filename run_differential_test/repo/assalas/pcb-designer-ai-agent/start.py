import os
import sys
import re
import random
import shlex
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
    Enumerates the core functional commands of the pcbai tool.
    The value of each enum member is a generic template string representing the command structure.
    """
    FOOTPRINT_SMD_RC = "pcbai footprint --type smd_rc --name <name> --body-l <f> --body-w <f> --pad-l <f> --pad-w <f> --gap <f> --out <path>"
    FOOTPRINT_SOIC = "pcbai footprint --type soic --name <name> --pins <int> --pitch <f> --body-l <f> --body-w <f> --pad-l <f> --pad-w <f> --row-offset <f> --out <path>"
    FOOTPRINT_QFN = "pcbai footprint --type qfn --name <name> --pins <int> --pitch <f> --body-l <f> --body-w <f> --pad-l <f> --pad-w <f> --ep-l <f> --ep-w <f> --out <path>"
    FOOTPRINT_QFP = "pcbai footprint --type qfp --name <name> --pins <int> --pitch <f> --body-l <f> --body-w <f> --pad-l <f> --pad-w <f> --gullwing-ext <f> --out <path>"
    BOM_BASIC = "pcbai bom <description>"
    BOM_WITH_OUT = "pcbai bom <description> --out <path>"
    SYNTHESIZE_BASIC = "pcbai synthesize <description>"
    SYNTHESIZE_WITH_OUT = "pcbai synthesize <description> --out <path>"
    EXTRACT_PACKAGE = "pcbai extract-package <pdf_file> --out <path>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class PcbaiAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Sanitizes stdout by removing volatile file paths."""
        sanitized = re.sub(r"at .*?\.kicad_mod", "at [FILEPATH].kicad_mod", raw_stdout)
        sanitized = re.sub(r"at .*?\.kicad_sch", "at [FILEPATH].kicad_sch", sanitized)
        sanitized = re.sub(r"at .*?\.txt", "at [FILEPATH].txt", sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/assalas/pcb-designer-ai-agent.git && cd pcb-designer-ai-agent && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    cmd = ""
                    mount_files = {}
                    
                    output_dir = "/test_data/output_dir"
                    output_file = "/test_data/output.txt"

                    if category.name.startswith("FOOTPRINT"):
                        base_cmd = f"pcbai footprint --out {output_dir}"
                        
                        if is_edge_case:
                            name = shlex.quote(FuzzHelper.get_evil_string())
                            body_l = FuzzHelper.get_float(-5.0, 0.0)
                            body_w = FuzzHelper.get_float(-5.0, 0.0)
                            pad_l = FuzzHelper.get_float(-2.0, 0.0)
                            pad_w = FuzzHelper.get_float(-2.0, 0.0)
                            pins = FuzzHelper.get_int(-10, 1)
                            pitch = FuzzHelper.get_float(-1.0, 0.0)
                        else:
                            name = FuzzHelper.get_string(5, 20)
                            body_l = FuzzHelper.get_float(0.5, 10.0)
                            body_w = FuzzHelper.get_float(0.5, 5.0)
                            pad_l = FuzzHelper.get_float(0.2, 2.0)
                            pad_w = FuzzHelper.get_float(0.2, 2.0)
                            pins = FuzzHelper.get_int(4, 20) * 2  # Even numbers are common for pins
                            pitch = FuzzHelper.get_float(0.4, 2.54)

                        if category == CmdCategory.FOOTPRINT_SMD_RC:
                            gap = FuzzHelper.get_float(-1.0, 0.0) if is_edge_case else FuzzHelper.get_float(0.1, 2.0)
                            cmd = f"{base_cmd} --type smd_rc --name {name} --body-l {body_l} --body-w {body_w} --pad-l {pad_l} --pad-w {pad_w} --gap {gap}"
                        
                        elif category == CmdCategory.FOOTPRINT_SOIC:
                            row_offset = FuzzHelper.get_float(-5.0, 0.0) if is_edge_case else FuzzHelper.get_float(1.0, 5.0)
                            cmd = f"{base_cmd} --type soic --name {name} --pins {pins} --pitch {pitch} --body-l {body_l} --body-w {body_w} --pad-l {pad_l} --pad-w {pad_w} --row-offset {row_offset}"

                        elif category == CmdCategory.FOOTPRINT_QFN:
                            ep_l = FuzzHelper.get_float(-5.0, 0.0) if is_edge_case else FuzzHelper.get_float(1.0, 5.0)
                            ep_w = FuzzHelper.get_float(-5.0, 0.0) if is_edge_case else FuzzHelper.get_float(1.0, 5.0)
                            cmd = f"{base_cmd} --type qfn --name {name} --pins {pins} --pitch {pitch} --body-l {body_l} --body-w {body_w} --pad-l {pad_l} --pad-w {pad_w} --ep-l {ep_l} --ep-w {ep_w}"

                        elif category == CmdCategory.FOOTPRINT_QFP:
                            gullwing_ext = FuzzHelper.get_float(-2.0, 0.0) if is_edge_case else FuzzHelper.get_float(0.1, 1.0)
                            cmd = f"{base_cmd} --type qfp --name {name} --pins {pins} --pitch {pitch} --body-l {body_l} --body-w {body_w} --pad-l {pad_l} --pad-w {pad_w} --gullwing-ext {gullwing_ext}"

                    elif category.name.startswith("BOM") or category.name.startswith("SYNTHESIZE"):
                        description = shlex.quote(FuzzHelper.get_evil_string() if is_edge_case else "a simple board with one 555 timer and a few resistors")
                        sub_cmd = "bom" if "BOM" in category.name else "synthesize"
                        
                        if "WITH_OUT" in category.name:
                            out_path = shlex.quote(FuzzHelper.get_evil_string()) if is_edge_case else output_file
                            cmd = f"pcbai {sub_cmd} {description} --out {out_path}"
                        else:
                            cmd = f"pcbai {sub_cmd} {description}"

                    elif category == CmdCategory.EXTRACT_PACKAGE:
                        pdf_filename = "fuzz_doc.pdf"
                        pdf_path = f"/test_data/{pdf_filename}"
                        if is_edge_case:
                            content = FuzzHelper.get_evil_string()
                            out_path = shlex.quote(FuzzHelper.get_evil_string())
                        else:
                            content = "This is a dummy file pretending to be a PDF for testing purposes."
                            out_path = output_file
                        
                        mount_files[pdf_filename] = content
                        cmd = f"pcbai extract-package {pdf_path} --out {out_path}"

                    if cmd:
                        cases.append(TestCase(
                            command=cmd,
                            category=category.value,
                            mount_files=mount_files
                        ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} (i={i}): {e}")
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = PcbaiAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))