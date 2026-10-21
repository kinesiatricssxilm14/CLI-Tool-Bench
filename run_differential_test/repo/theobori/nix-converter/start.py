import os
import sys
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    # --- Conversion TO Nix ---
    JSON_TO_NIX = "nix-converter -filename <file> -language json"
    YAML_TO_NIX = "nix-converter -filename <file> -language yaml"
    TOML_TO_NIX = "nix-converter -filename <file> -language toml"

    # --- Conversion TO Nix with Modifiers ---
    JSON_TO_NIX_UNSAFE = "nix-converter -filename <file> -language json -unsafe-keys"
    YAML_TO_NIX_SORT = "nix-converter -filename <file> -language yaml -sort-iterators <type>"
    TOML_TO_NIX_UNSAFE_SORT = "nix-converter -filename <file> -language toml -unsafe-keys -sort-iterators <type>"

    # --- Conversion FROM Nix ---
    NIX_TO_JSON = "nix-converter -from-nix -filename <file> -language json"
    NIX_TO_YAML = "nix-converter -from-nix -filename <file> -language yaml"
    NIX_TO_TOML = "nix-converter -from-nix -filename <file> -language toml"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/theobori/nix-converter.git && cd nix-converter && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Helper methods for generating valid content
    # =====================================================================
    def _get_nix_content(self) -> str:
        """Generates a valid Nix expression string with fuzzed data."""
        return f"""
        {{
          id = "{FuzzHelper.get_string(8, 12)}";
          users = [
            {{
              name = "{FuzzHelper.get_string(5, 15)}";
              age = {FuzzHelper.get_int(18, 65)};
              "pets" = [ {{ type = "cat"; name = "Luna"; }} ];
            }}
          ];
          settings = {{
            theme = "dark";
            notifications = {random.choice(['true', 'false'])};
          }};
          meta = {{
            created = "{FuzzHelper.get_string(10,10)}";
          }};
        }}
        """

    def _get_yaml_content(self) -> str:
        """Generates a valid YAML string with fuzzed data, including anchors."""
        return f"""
        definitions:
          steps:
            - step: &build-test
                name: {FuzzHelper.get_string(10, 20)}
                script:
                  - mvn package
        pipelines:
          branches:
            {FuzzHelper.get_string(5, 10)}:
              - step: *build-test
        """

    def _get_toml_content(self) -> str:
        """Generates a valid TOML string with fuzzed data."""
        return f"""
        title = "{FuzzHelper.get_string(10, 20)}"
        [owner]
        name = "{FuzzHelper.get_string(10, 20)}"

        [database]
        server = "{FuzzHelper.get_ip()}"
        ports = [ {FuzzHelper.get_int(1000, 2000)}, {FuzzHelper.get_int(2001, 3000)} ]
        enabled = {random.choice(['true', 'false'])}
        """

    # =====================================================================
    # 4. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        SORT_ITERATOR_OPTIONS = ["all", "list", "hashmap", "list,hashmap"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make the first case of each category an edge case
                    is_edge_case = (i == 0)

                    content = ""
                    file_ext = ".txt"
                    content_func = None

                    # Determine input format and content generator based on category
                    if "JSON_TO" in category.name:
                        file_ext, content_func = ".json", FuzzHelper.get_json_string
                    elif "YAML_TO" in category.name:
                        file_ext, content_func = ".yaml", self._get_yaml_content
                    elif "TOML_TO" in category.name:
                        file_ext, content_func = ".toml", self._get_toml_content
                    elif "NIX_TO" in category.name:
                        file_ext, content_func = ".nix", self._get_nix_content

                    # Generate content for the input file
                    if is_edge_case:
                        content = FuzzHelper.get_evil_string()
                    elif content_func:
                        # Call content function with appropriate args if needed
                        if content_func == FuzzHelper.get_json_string:
                            content = content_func(num_keys=random.randint(2, 5))
                        else:
                            content = content_func()
                    
                    file_name = f"fuzz_{category.name.lower()}_{i}{file_ext}"
                    
                    # Assemble the command string
                    cmd_parts = ["nix-converter"]
                    
                    if "NIX_TO" in category.name:
                        cmd_parts.append("-from-nix")

                    cmd_parts.extend(["-filename", f"/test_data/{file_name}"])

                    lang = "json" # Default language
                    if "YAML" in category.name: lang = "yaml"
                    elif "TOML" in category.name: lang = "toml"
                    cmd_parts.extend(["-language", lang])

                    if "UNSAFE" in category.name:
                        cmd_parts.append("-unsafe-keys")

                    if "SORT" in category.name:
                        if is_edge_case:
                            sort_val = "invalid_sort_option"
                        else:
                            sort_val = random.choice(SORT_ITERATOR_OPTIONS)
                        cmd_parts.extend(["-sort-iterators", sort_val])

                    command = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} index {i}: {e}")
                    continue
        return cases


if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))