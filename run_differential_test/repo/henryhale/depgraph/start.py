import os
import sys
import re
from enum import Enum
import random
import string

# Add the parent directory of the script's location to the Python path
# to ensure that the BaseRepoAdapter and DiffTestEngine can be imported.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command combinations for depgraph.
    Each enum value is a generic template representing a class of commands.
    """
    BASE = "depgraph -d <dir> -l <lang>"
    WITH_FORMAT = "depgraph -d <dir> -l <lang> -f <format>"
    WITH_IGNORE = "depgraph -d <dir> -l <lang> -i <dirs>"
    WITH_REPLACE = "depgraph -d <dir> -l <lang> -r <paths>"
    WITH_OUTPUT = "depgraph -d <dir> -l <lang> -o <file>"
    FORMAT_AND_IGNORE = "depgraph -d <dir> -l <lang> -f <format> -i <dirs>"
    IGNORE_AND_REPLACE = "depgraph -d <dir> -l <lang> -i <dirs> -r <paths>"
    ALL_MODIFIERS = "depgraph -d <dir> -l <lang> -f <format> -i <dirs> -r <paths>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class DepgraphAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Clones and installs the baseline (oracle) version of the tool."""
        cmd = (
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/henryhale/depgraph.git && "
            "cd depgraph && go install ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Copies and installs the local (agent) version of the tool."""
        container.exec_run("mkdir -p /repo")
        # Use os.system for simplicity as per framework guidelines
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _create_mock_project(self, lang: str) -> dict:
        """Helper to generate a small mock project with source files."""
        files = {}
        main_content = "// main file content"
        util_content = "// util file content"

        if lang in ['js', 'ts', 'jsx', 'tsx']:
            ext = lang if len(lang) > 2 else lang[0:2] # js or ts or jsx or tsx
            files[f'project/main.{ext}'] = f"import {{ util }} from './utils/util.{ext}';\nconsole.log(util());\n{main_content}"
            files[f'project/utils/util.{ext}'] = f"export const util = () => 'hello';\n{util_content}"
        elif lang in ['c', 'cpp']:
            ext = lang
            files[f'project/main.{ext}'] = f"#include \"utils/util.h\"\nint main() {{ return 0; }}\n{main_content}"
            files[f'project/utils/util.h'] = f"// Utility header\n{util_content}"
        # The tool also supports Go files, even if not a -l option
        elif lang == 'go':
            files['project/main.go'] = f"package main\n\nimport (\n\t_ \"project/utils\"\n)\n\nfunc main() {{}}\n{main_content}"
            files['project/utils/util.go'] = f"package utils\n\nimport \"fmt\"\n\nfunc Hello() {{ fmt.Println(\"hello\") }}\n{util_content}"

        files['project/ignored_dir/ignore.js'] = "console.log('should be ignored');"
        files['project/src/demo.js'] = "console.log('demo');"
        
        return files

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        
        # According to help message, -l only supports js, ts, c, cpp.
        # Although the README mentions go, we stick to the help message for CLI flags.
        languages = ['js', 'ts', 'c', 'cpp']
        formats = ['mermaid', 'dot', 'jsoncanvas', 'json']
        # We can still generate Go source files to see how the tool handles them without a specific -l go flag.
        all_project_types = languages + ['go']

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # The last case in each category is a "fuzz" case, others are valid.
                    is_fuzz_case = (i == CASES_PER_CATEGORY - 1)

                    lang_for_project = random.choice(all_project_types)
                    mount_files = self._create_mock_project(lang_for_project)
                    
                    cmd_parts = ["depgraph"]
                    target_dir = "/test_data/project"
                    
                    # -d and -l are fundamental
                    cmd_parts.append(f"-d {target_dir}")
                    
                    if is_fuzz_case and random.random() < 0.5:
                        # Fuzz language with a random string
                        lang_arg = FuzzHelper.get_string(1, 5)
                        cmd_parts.append(f"-l '{lang_arg}'")
                    else:
                        # Use a valid language for the -l flag
                        lang_arg = random.choice(languages)
                        cmd_parts.append(f"-l {lang_arg}")

                    # Build command based on category name
                    category_name = category.name.upper()

                    if "FORMAT" in category_name:
                        format_arg = FuzzHelper.get_string(3, 8) if is_fuzz_case else random.choice(formats)
                        cmd_parts.append(f"-f {format_arg}")

                    if "IGNORE" in category_name:
                        # Fuzz with a random string, but avoid shell-breaking chars
                        ignore_arg = FuzzHelper.get_string(5, 10, chars=string.ascii_letters) if is_fuzz_case else "ignored_dir"
                        cmd_parts.append(f"-i '{ignore_arg}'")

                    if "REPLACE" in category_name:
                        if is_fuzz_case:
                            # Fuzz with a string that doesn't match the key:value format
                            replace_arg = FuzzHelper.get_string(5, 15)
                        else:
                            # Valid format
                            replace_arg = "@:src,demo:src/demo"
                        cmd_parts.append(f"-r '{replace_arg}'")

                    if "OUTPUT" in category_name:
                        if is_fuzz_case:
                            # Try to write to a potentially invalid path
                            output_file = FuzzHelper.get_filepath(ext=".out")
                        else:
                            output_file = f"/test_data/output_{i}.txt"
                        cmd_parts.append(f"-o {output_file}")
                    
                    # Randomize order of arguments for robustness
                    main_cmd = cmd_parts[0]
                    args_to_shuffle = cmd_parts[1:]
                    random.shuffle(args_to_shuffle)
                    command = f"{main_cmd} {' '.join(args_to_shuffle)}"
                    
                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Skip generating this specific test case if an error occurs
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = DepgraphAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))