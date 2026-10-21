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
    LIST = "md-tree list <file>"
    LIST_JSON = "md-tree list <file> --format json"
    EXTRACT = "md-tree extract <file> \"<heading>\""
    EXTRACT_OUTPUT = "md-tree extract <file> \"<heading>\" --output <dir>"
    EXTRACT_ALL = "md-tree extract-all <file> <level>"
    EXTRACT_ALL_OUTPUT = "md-tree extract-all <file> <level> --output <dir>"
    TREE = "md-tree tree <file>"
    SEARCH = "md-tree search <file> \"<selector>\""
    STATS = "md-tree stats <file>"
    CHECK_LINKS = "md-tree check-links <file>"
    CHECK_LINKS_RECURSIVE = "md-tree check-links <file> --recursive"
    TOC = "md-tree toc <file>"
    TOC_MAX_LEVEL = "md-tree toc <file> --max-level <level>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Node.js environment."""
        return "node:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (Oracle) version of the tool from GitHub."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ksylvan/markdown-tree-parser.git && cd markdown-tree-parser && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the development (Agent) version of the tool from local source."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Sanitizes volatile parts of the stdout for consistent diffing."""
        # Sanitize absolute file paths which may differ
        sanitized = re.sub(r'/repo/repo_to_be_tested/?', '<WORKDIR>/', raw_stdout)
        sanitized = re.sub(r'/repo/markdown-tree-parser/?', '<WORKDIR>/', sanitized)
        sanitized = re.sub(r'/test_data/?', '<WORKDIR>/', sanitized)
        # Sanitize node internal file paths
        sanitized = re.sub(r'file:///.*/repo/repo_to_be_tested/', 'file:///<WORKDIR>/', sanitized)
        sanitized = re.sub(r'file:///.*/repo/markdown-tree-parser/', 'file:///<WORKDIR>/', sanitized)
        # Sanitize AST line/column position info, e.g., (1:1-3:4) or [1:1]
        sanitized = re.sub(r'\s*[\(\[]\d+:\d+(-\d+:\d+)?[\)\]]', '', sanitized)
        # Sanitize timing information, e.g., "(123ms)"
        sanitized = re.sub(r'\(\d+ms\)', '(TIMING)', sanitized)
        # Sanitize version numbers which might differ
        sanitized = re.sub(r'@kayvan/markdown-tree-parser/\d+\.\d+\.\d+', '@kayvan/markdown-tree-parser/VERSION', sanitized)
        # Call parent sanitizer to remove ANSI color codes
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50

        def generate_markdown_content(is_edge: bool, num_headings=5):
            """Helper to generate markdown content for tests."""
            if is_edge:
                return FuzzHelper.get_evil_string(), []
            
            headings = [f"Section Heading {j}" for j in range(1, num_headings + 1)]
            content = f"# {headings[0]}\n"
            content += FuzzHelper.get_string(50, 150) + "\n\n"
            content += f"## {headings[1]}\n"
            content += "```js\nconsole.log('hello world');\n```\n\n"
            content += f"### {headings[2]}\n"
            content += f"A link to [GitHub](https://github.com) and a local [link](./other.md).\n\n"
            content += f"## {headings[3]}\n"
            content += FuzzHelper.get_string(50, 150) + "\n\n"
            content += f"## {headings[4]}\n"
            content += "* list item 1\n* list item 2\n"
            return content, headings

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # First case is always an edge case
                    file_name = f"fuzz_test_{category.name}_{i}.md"
                    
                    content, headings = generate_markdown_content(is_edge_case)

                    cmd = ""
                    prep_script = ""
                    mount_files = {file_name: content}
                    input_file_path = f"/test_data/{file_name}"

                    if category == CmdCategory.LIST:
                        cmd = f"md-tree list {input_file_path}"
                    
                    elif category == CmdCategory.LIST_JSON:
                        cmd = f"md-tree list {input_file_path} --format json"

                    elif category == CmdCategory.EXTRACT:
                        if is_edge_case:
                            heading_to_find = f'"{FuzzHelper.get_evil_string()}"'
                        else:
                            heading_to_find = f'"{random.choice(headings) if headings else "NonExistent"}"'
                        cmd = f"md-tree extract {input_file_path} {heading_to_find}"

                    elif category == CmdCategory.EXTRACT_OUTPUT:
                        output_dir = "/test_data/output"
                        prep_script = f"mkdir -p {output_dir}"
                        if is_edge_case:
                            heading_to_find = f'"{FuzzHelper.get_evil_string()}"'
                        else:
                            heading_to_find = f'"{random.choice(headings) if headings else "NonExistent"}"'
                        cmd = f"md-tree extract {input_file_path} {heading_to_find} --output {output_dir}"

                    elif category == CmdCategory.EXTRACT_ALL:
                        level = FuzzHelper.get_int(1, 4)
                        level_arg = FuzzHelper.get_evil_string() if is_edge_case else level
                        cmd = f"md-tree extract-all {input_file_path} {level_arg}"

                    elif category == CmdCategory.EXTRACT_ALL_OUTPUT:
                        output_dir = "/test_data/output"
                        prep_script = f"mkdir -p {output_dir}"
                        level = FuzzHelper.get_int(1, 4)
                        level_arg = FuzzHelper.get_evil_string() if is_edge_case else level
                        cmd = f"md-tree extract-all {input_file_path} {level_arg} --output {output_dir}"

                    elif category == CmdCategory.TREE:
                        cmd = f"md-tree tree {input_file_path}"

                    elif category == CmdCategory.SEARCH:
                        if is_edge_case:
                            selector = f'"{FuzzHelper.get_evil_string()}"'
                        else:
                            selector = random.choice(['"heading[depth=2]"', '"link"', '"code"', '"paragraph"'])
                        cmd = f"md-tree search {input_file_path} {selector}"

                    elif category == CmdCategory.STATS:
                        cmd = f"md-tree stats {input_file_path}"

                    elif category == CmdCategory.CHECK_LINKS:
                        mount_files["other.md"] = "# Other File\nThis is another file."
                        cmd = f"md-tree check-links {input_file_path}"

                    elif category == CmdCategory.CHECK_LINKS_RECURSIVE:
                        mount_files["other.md"] = "# Other File\nThis is another file."
                        cmd = f"md-tree check-links {input_file_path} --recursive"

                    elif category == CmdCategory.TOC:
                        cmd = f"md-tree toc {input_file_path}"

                    elif category == CmdCategory.TOC_MAX_LEVEL:
                        level = FuzzHelper.get_int(1, 6)
                        level_arg = FuzzHelper.get_evil_string() if is_edge_case else level
                        cmd = f"md-tree toc {input_file_path} --max-level {level_arg}"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=mount_files
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
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))