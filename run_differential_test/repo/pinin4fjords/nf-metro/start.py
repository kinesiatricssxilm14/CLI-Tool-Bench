import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    VALIDATE = "nf-metro validate <file>"
    INFO = "nf-metro info <file>"
    CONVERT = "nf-metro convert <file>"
    CONVERT_WITH_TITLE = "nf-metro convert <file> --title <text>"
    RENDER_BASIC = "nf-metro render <file>"
    RENDER_THEME = "nf-metro render <file> --theme <theme>"
    RENDER_DIMENSIONS = "nf-metro render <file> --width <N> --height <N>"
    RENDER_SPACING = "nf-metro render <file> --x-spacing <F> --y-spacing <F>"
    RENDER_ANIMATE_DEBUG = "nf-metro render <file> --animate --debug"
    RENDER_LINE_ORDER = "nf-metro render <file> --line-order <strategy>"
    RENDER_WITH_LOGO = "nf-metro render <file> --logo <path>"
    RENDER_FROM_NEXTFLOW = "nf-metro render <file> --from-nextflow --title <text>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class NfMetroAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        # Sanitize file paths and line numbers in Python tracebacks
        sanitized = re.sub(r'File ".*?"', 'File "..."', raw_stdout)
        sanitized = re.sub(r', line \d+', ', line ...', sanitized)
        # Sanitize memory addresses
        sanitized = re.sub(r' at 0x[0-9a-fA-F]+', '', sanitized)
        sanitized = re.sub(r'<.+? object at 0x[0-9a-fA-F]+>', '<... object>', sanitized)
        # The default sanitizer removes ANSI codes
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        cmd = (
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/pinin4fjords/nf-metro.git && "
            "cd nf-metro && pip install ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Test Case Generation Logic
    # =====================================================================
    def _generate_nfmetro_mmd_content(self, is_evil: bool) -> str:
        """Helper to generate nf-metro compatible .mmd file content."""
        if is_evil:
            roll = random.random()
            if roll < 0.5:
                # Completely invalid content
                return FuzzHelper.get_evil_string()
            else:
                # Structurally malformed .mmd
                line_id = FuzzHelper.get_string(1, 10, "a_").replace(" ", "")
                line_name = FuzzHelper.get_evil_string()
                color = FuzzHelper.get_string(3, 7)
                return f"""
                graph {FuzzHelper.get_string(2,3)}
                %%metro line: {line_id} | {line_name} | #{color}
                {FuzzHelper.get_string(5,10)} -->|{line_id}| {FuzzHelper.get_string(5,10)}
                subgraph {FuzzHelper.get_evil_string()}
                """
        else:
            # Syntactically valid .mmd for nf-metro
            line_id = FuzzHelper.get_string(5, 10, "abcdef_")
            line_name = FuzzHelper.get_string(10, 30)
            color = f"#{random.randint(0, 0xFFFFFF):06x}"
            node1 = FuzzHelper.get_string(5, 10, "abcdef_")
            node2 = FuzzHelper.get_string(5, 10, "abcdef_")
            return f"""
            graph LR
            %%metro title: {FuzzHelper.get_string(10, 20)}
            %%metro line: {line_id} | {line_name} | {color}
            subgraph section_1 [Section One]
                {node1}[Node 1] -->|{line_id}| {node2}[Node 2]
            end
            """

    def _generate_nextflow_mmd_content(self, is_evil: bool) -> str:
        """Helper to generate a simplified Nextflow DAG-style .mmd file."""
        if is_evil:
            return FuzzHelper.get_evil_string()
        else:
            # A plausible, simple Nextflow DAG mermaid graph
            process1 = FuzzHelper.get_string(5, 10, "abcdef_")
            process2 = FuzzHelper.get_string(5, 10, "abcdef_")
            process3 = FuzzHelper.get_string(5, 10, "abcdef_")
            return f"""
            graph TD
                {process1} --> {process2}
                {process2} --> {process3}
            """

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        
        # Minimal valid 1x1 PNG content
        MINIMAL_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    mount_files = {}
                    cmd = ""

                    # Select the correct content generator based on the command
                    if category in [CmdCategory.CONVERT, CmdCategory.CONVERT_WITH_TITLE, CmdCategory.RENDER_FROM_NEXTFLOW]:
                        file_name = f"input_nextflow_{category.name}_{i}.mmd"
                        mmd_content = self._generate_nextflow_mmd_content(is_evil=is_edge_case)
                    else:
                        file_name = f"input_nfmetro_{category.name}_{i}.mmd"
                        mmd_content = self._generate_nfmetro_mmd_content(is_evil=is_edge_case)
                    
                    input_path = f"/test_data/{file_name}"
                    mount_files[file_name] = mmd_content

                    if category == CmdCategory.VALIDATE:
                        cmd = f"nf-metro validate {input_path}"
                    
                    elif category == CmdCategory.INFO:
                        cmd = f"nf-metro info {input_path}"

                    elif category == CmdCategory.CONVERT:
                        cmd = f"nf-metro convert {input_path}"

                    elif category == CmdCategory.CONVERT_WITH_TITLE:
                        title = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(5, 20)
                        cmd = f"nf-metro convert {input_path} --title \"{title.replace('\"', '')}\""

                    elif category == CmdCategory.RENDER_BASIC:
                        cmd = f"nf-metro render {input_path}"

                    elif category == CmdCategory.RENDER_THEME:
                        theme = FuzzHelper.get_string(3, 8) if is_edge_case else random.choice(['nfcore', 'light'])
                        cmd = f"nf-metro render {input_path} --theme {theme}"

                    elif category == CmdCategory.RENDER_DIMENSIONS:
                        width = FuzzHelper.get_int(-100, 0) if is_edge_case else FuzzHelper.get_int(100, 2000)
                        height = FuzzHelper.get_string(3, 5) if is_edge_case else FuzzHelper.get_int(100, 2000)
                        cmd = f"nf-metro render {input_path} --width {width} --height {height}"

                    elif category == CmdCategory.RENDER_SPACING:
                        x_spacing = FuzzHelper.get_float(-10.0, 0.0) if is_edge_case else FuzzHelper.get_float(10.0, 100.0)
                        y_spacing = FuzzHelper.get_string(3, 5) if is_edge_case else FuzzHelper.get_float(10.0, 100.0)
                        cmd = f"nf-metro render {input_path} --x-spacing {x_spacing} --y-spacing {y_spacing}"

                    elif category == CmdCategory.RENDER_ANIMATE_DEBUG:
                        cmd = f"nf-metro render {input_path} --animate --debug"

                    elif category == CmdCategory.RENDER_LINE_ORDER:
                        strategy = FuzzHelper.get_string(3, 8) if is_edge_case else random.choice(['definition', 'span'])
                        cmd = f"nf-metro render {input_path} --line-order {strategy}"

                    elif category == CmdCategory.RENDER_WITH_LOGO:
                        logo_name = "logo.png"
                        logo_path = f"/test_data/{logo_name}"
                        logo_content = FuzzHelper.get_evil_string() if is_edge_case else MINIMAL_PNG.decode('latin-1')
                        mount_files[logo_name] = logo_content
                        cmd = f"nf-metro render {input_path} --logo {logo_path}"

                    elif category == CmdCategory.RENDER_FROM_NEXTFLOW:
                        title = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(5, 20)
                        cmd = f"nf-metro render {input_path} --from-nextflow --title \"{title.replace('\"', '')}\""

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate a test case for {category.name}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = NfMetroAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))