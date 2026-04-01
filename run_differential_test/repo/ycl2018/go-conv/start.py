import os
import sys
import re
import random
from enum import Enum
from typing import List, Dict

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command combinations for go-conv.
    The value is a generic template representing the command structure.
    """
    BASIC_CONV = "go-conv <path>"
    BASIC_CONV_STRCONV = "go-conv -strconv <path>"
    BASIC_CONV_QUIET = "go-conv -q <path>"
    BASIC_CONV_OUTPUT = "go-conv -o <file> <path>"
    DEEP_COPY = "go-conv <path> (with //go-conv:copy)"
    DEEP_COPY_STRCONV = "go-conv -strconv <path> (with //go-conv:copy)"
    DEEP_COPY_QUIET = "go-conv -q <path> (with //go-conv:copy)"
    DEEP_COPY_STRCONV_QUIET = "go-conv -strconv -q <path> (with //go-conv:copy)"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GoConvAdapter(BaseRepoAdapter):
    """
    Adapter for the go-conv CLI tool.
    Handles installation and test case generation.
    """

    GO_KEYWORDS = {
        "break", "default", "func", "interface", "select", "case", "defer", "go",
        "map", "struct", "chan", "else", "goto", "package", "switch", "const",
        "fallthrough", "if", "range", "type", "continue", "for", "import",
        "return", "var"
    }

    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """Installs the baseline (oracle) version of go-conv."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/ycl2018/go-conv.git && cd go-conv && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the local (agent) version of go-conv."""
        container.exec_run("mkdir -p /repo")
        # Use os.system for simplicity as per the original structure, assuming it's run in a trusted context.
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _sanitize_identifier(self, name: str) -> str:
        """Sanitizes a string to be a valid Go identifier."""
        if not isinstance(name, str):
            name = "invalid_type"
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        if not sanitized:
            return "DefaultName"
        if sanitized[0].isdigit():
            sanitized = '_' + sanitized
        if sanitized in self.GO_KEYWORDS:
            sanitized += '_'
        return sanitized

    def _generate_go_source(self, is_copy_mode: bool, is_edge_case: bool) -> str:
        """Generates fuzzed Go source code for go-conv to process."""
        try:
            package_name = "main"
            if is_edge_case:
                src_name = self._sanitize_identifier(FuzzHelper.get_evil_string())
                dst_name = self._sanitize_identifier(FuzzHelper.get_evil_string())
                if src_name == dst_name:
                    dst_name += "_dst"
                num_fields = FuzzHelper.get_int(0, 5)
            else:
                src_name = "Src" + FuzzHelper.get_string(5, 10, chars="abcdefghijklmnopqrstuvwxyz").capitalize()
                dst_name = "Dst" + FuzzHelper.get_string(5, 10, chars="abcdefghijklmnopqrstuvwxyz").capitalize()
                num_fields = FuzzHelper.get_int(1, 8)

            src_name = src_name or "DefaultSrc"
            dst_name = dst_name or "DefaultDst"

            go_types = ["string", "int", "int64", "float32", "bool", "[]byte", "[]string", "map[string]int"]
            src_fields, dst_fields = [], []

            for _ in range(num_fields):
                field_name = FuzzHelper.get_string(4, 8, chars="abcdefghijklmnopqrstuvwxyz").capitalize()
                field_name = self._sanitize_identifier(field_name)
                field_type = random.choice(go_types)
                
                if random.random() < 0.8: # Higher chance of common fields
                    src_fields.append(f"{field_name} {field_type}")
                    dst_fields.append(f"{field_name} {field_type}")
                else: # Create mismatched fields
                    if random.random() < 0.5:
                        src_fields.append(f"{field_name} {field_type}")
                    else:
                        dst_fields.append(f"{field_name} {field_type}")

            # Add specific fields to test strconv functionality
            if random.random() < 0.5:
                src_fields.append("ConvertibleInt string")
                dst_fields.append("ConvertibleInt int")
                src_fields.append("ConvertibleString int64")
                dst_fields.append("ConvertibleString string")

            conv_directive = "// go-conv:generate"
            if is_copy_mode:
                conv_directive += "\n// go-conv:copy"

            src_fields_str = '\n    '.join(src_fields)
            dst_fields_str = '\n    '.join(dst_fields)

            return f"""
package {package_name}

{conv_directive}
var Conv func(src *{src_name}) *{dst_name}

type {src_name} struct {{
    {src_fields_str}
}}

type {dst_name} struct {{
    {dst_fields_str}
}}
"""
        except Exception:
            # Fallback for any unexpected error during generation
            return """
package main
// go-conv:generate
var Conv func(src *Src) *Dst
type Src struct { A int }
type Dst struct { A int }
"""

    def generate_test_cases(self) -> list[TestCase]:
        """Generates a list of TestCase objects for differential testing."""
        cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                is_edge_case = (i == 0) # Make one case per category an edge case
                
                try:
                    is_copy_mode = "DEEP_COPY" in category.name
                    go_code_content = self._generate_go_source(is_copy_mode, is_edge_case)

                    mount_files = {'main.go': go_code_content}
                    # Initialize a go module to ensure the tool can process the files correctly.
                    prep_script = "cd /test_data && go mod init fuzz_module &> /dev/null"

                    cmd_parts = ["cd /test_data && go-conv"]

                    if category in [CmdCategory.BASIC_CONV_STRCONV, CmdCategory.DEEP_COPY_STRCONV, CmdCategory.DEEP_COPY_STRCONV_QUIET]:
                        cmd_parts.append("-strconv")
                    
                    if category in [CmdCategory.BASIC_CONV_QUIET, CmdCategory.DEEP_COPY_QUIET, CmdCategory.DEEP_COPY_STRCONV_QUIET]:
                        cmd_parts.append("-q")

                    if category == CmdCategory.BASIC_CONV_OUTPUT:
                        if is_edge_case:
                            # Use a potentially problematic but sanitized filename
                            fname_fuzz = FuzzHelper.get_evil_string()
                            safe_fname = re.sub(r"[^a-zA-Z0-9_.-]", "_", fname_fuzz)[:30]
                            output_filename = f"out_{safe_fname}.go" if safe_fname else "out_default.go"
                        else:
                            output_filename = f"custom_output_{i}.go"
                        cmd_parts.extend(["-o", output_filename])

                    # The path argument for go-conv to process the current directory
                    cmd_parts.append(".")
                    
                    # The command should not include `cat`. The framework's diff engine will capture file changes.
                    full_command = ' '.join(cmd_parts)

                    cases.append(TestCase(
                        command=full_command,
                        category=category.value,
                        prep_script=prep_script,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Skip test case generation if any unexpected error occurs
                    continue
        
        return cases

# =====================================================================
# 3. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GoConvAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))