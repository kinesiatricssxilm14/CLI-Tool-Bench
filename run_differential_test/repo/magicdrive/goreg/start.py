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

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the types of commands to be tested for the 'goreg' tool.
    The value of each enum member is a generic string template of the command.
    """
    BASIC = "goreg <file-name.go>"
    WRITE = "goreg --write <file-name.go>"
    LOCAL = "goreg --local <local_module> <file-name.go>"
    ORGANIZATION = "goreg --organization <org_path> <file-name.go>"
    LOCAL_AND_ORG = "goreg --local <local_module> --organization <org_path> <file-name.go>"
    ORDER = "goreg --order <group_order> <file-name.go>"
    MINIMIZE_GROUP = "goreg --minimize-group <file-name.go>"
    SORT_INCLUDE_ALIAS = "goreg --sort-include-alias <file-name.go>"
    REMOVE_IMPORT_COMMENT = "goreg --remove-import-comment <file-name.go>"
    ALL_FORMAT_FLAGS = "goreg --minimize-group --sort-include-alias --remove-import-comment <file-name.go>"
    COMPLEX_COMBO = "goreg --write --local <local_module> --organization <org_path> --order <group_order> <file-name.go>"
    CONFIG_FILE = "goreg <file-name.go> # with goreg.toml"
    CONFIG_FILE_OVERRIDE = "goreg --local <local_module> <file-name.go> # with goreg.toml"
    ENV_VAR_DISABLE_CONFIG = "goreg <file-name.go> # with GOREG_NOT_USE_CONFIGFILE"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GoregAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes stdout by removing volatile information like file paths.
        """
        sanitized = re.sub(r'/test_data/[^:\s]+', '<file>', raw_stdout)
        sanitized = re.sub(r':\s*\d+:\d+:', ':<line>:<col>:', sanitized)
        return super().sanitize_stdout(sanitized)

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/magicdrive/goreg.git && cd goreg && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _generate_go_source(self, is_edge_case: bool) -> str:
        """Helper to generate Go source file content for testing."""
        if is_edge_case:
            return FuzzHelper.get_evil_string() if random.random() > 0.5 else ""

        std_imports = ['"fmt"', '"os"', '"net/http"', '"math/rand"', '"io/ioutil"']
        third_party_imports = ['"github.com/gin-gonic/gin"', '"github.com/spf13/cobra"', '"gopkg.in/yaml.v2"']
        org_imports = ['"github.com/myorg/utils"', '"github.com/myorg/models"']
        local_imports = ['"myproject/module/api"', '"myproject/module/db"']

        all_imports = std_imports + third_party_imports + org_imports + local_imports
        random.shuffle(all_imports)

        if random.random() > 0.5:
            all_imports.insert(1, 'u "github.com/myorg/utils" // utility package')
        if random.random() > 0.5:
            all_imports.insert(3, '_ "github.com/lib/pq" // postgres driver')

        import_block = "\n\t".join(all_imports)

        return f"""package main

import (
\t{import_block}
)

func main() {{
\tfmt.Println("hello world")
}}
"""

    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0)
                    file_name = f"fuzz_test_{category.name}_{i}.go"
                    file_content = self._generate_go_source(is_edge_case)
                    mount_files = {file_name: file_content}
                    env_vars = {}
                    cmd_parts = ["goreg"]

                    if category in [CmdCategory.WRITE, CmdCategory.COMPLEX_COMBO]:
                        cmd_parts.append("--write")

                    if category in [CmdCategory.LOCAL, CmdCategory.LOCAL_AND_ORG, CmdCategory.COMPLEX_COMBO, CmdCategory.CONFIG_FILE_OVERRIDE]:
                        local_val = FuzzHelper.get_evil_string() if is_edge_case else "myproject/module"
                        cmd_parts.extend(["--local", local_val])

                    if category in [CmdCategory.ORGANIZATION, CmdCategory.LOCAL_AND_ORG, CmdCategory.COMPLEX_COMBO]:
                        org_val = FuzzHelper.get_evil_string() if is_edge_case else "github.com/myorg"
                        cmd_parts.extend(["--organization", org_val])

                    if category in [CmdCategory.ORDER, CmdCategory.COMPLEX_COMBO]:
                        if is_edge_case:
                            order_val = FuzzHelper.get_evil_string()
                        else:
                            order_parts = ["std", "thirdparty", "organization", "local"]
                            random.shuffle(order_parts)
                            order_val = ",".join(order_parts)
                        cmd_parts.extend(["--order", order_val])

                    if category in [CmdCategory.MINIMIZE_GROUP, CmdCategory.ALL_FORMAT_FLAGS]:
                        cmd_parts.append("--minimize-group")

                    if category in [CmdCategory.SORT_INCLUDE_ALIAS, CmdCategory.ALL_FORMAT_FLAGS]:
                        cmd_parts.append("--sort-include-alias")

                    if category in [CmdCategory.REMOVE_IMPORT_COMMENT, CmdCategory.ALL_FORMAT_FLAGS]:
                        cmd_parts.append("--remove-import-comment")

                    if category in [CmdCategory.CONFIG_FILE, CmdCategory.CONFIG_FILE_OVERRIDE]:
                        config_content = """
[import]
local_module = "myproject/module"
organization_module = "github.com/myorg"
order = "local,organization,thirdparty,std"
[format]
minimize_group = true
sort_include_alias = true
remove_import_comment = true
"""
                        mount_files["goreg.toml"] = config_content

                    if category == CmdCategory.ENV_VAR_DISABLE_CONFIG:
                        env_vars["GOREG_NOT_USE_CONFIGFILE"] = "1"
                        mount_files["goreg.toml"] = '[import]\norganization_module = "github.com/should_be_ignored"'

                    cmd_parts.append(f"/test_data/{file_name}")

                    command = " ".join(shlex.quote(str(p)) for p in cmd_parts)
                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files,
                        env_vars=env_vars
                    ))
                except Exception:
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GoregAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))