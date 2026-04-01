import os
import sys
import re
from enum import Enum

# Add the root directory of the framework to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Defines the command categories for the jmux CLI tool.
    The value of each enum member is a generic command structure template.
    """
    GENERATE = "jmux generate --root <directory>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class JmuxAdapter(BaseRepoAdapter):
    """
    Adapter for the jmux repository.
    """

    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the target tool.
        jmux requires Python 3.10+.
        """
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle (baseline) version of the tool in the container."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/jaunruh/jmux.git && cd jmux && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent (local version) of the tool in the container."""
        container.exec_run("mkdir -p /repo")
        # The os.system call is executed on the host machine to copy files into the container
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile information from the tool's stdout.
        """
        # Sanitize absolute paths that might be generated in error messages
        sanitized = re.sub(r"'/test_data/[^']+'", "'<TEST_DATA_PATH>'", raw_stdout)
        # Sanitize the known output path from the tool's logs
        sanitized = re.sub(r'src/jmux/generated/__init__\.py', '<GENERATED_FILE>', sanitized)
        return super().sanitize_stdout(sanitized)

    def _generate_model_content(self, num_models: int) -> str:
        """
        Helper to generate Python code with StreamableBaseModel subclasses.
        """
        imports = """
from typing import Annotated, Optional, List
from jmux import StreamableBaseModel, Streamed
from enum import Enum
"""
        content = imports
        for i in range(num_models):
            class_name = f"FuzzModel_{i}_{FuzzHelper.get_string(5, 10, 'abcdefghijklmnopqrstuvwxyz')}"
            
            enum_name = f"FuzzEnum_{i}"
            enum_val1 = FuzzHelper.get_string(4, 8, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            enum_val2 = FuzzHelper.get_string(4, 8, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            content += f"""
class {enum_name}(Enum):
    {enum_val1} = "{enum_val1.lower()}"
    {enum_val2} = "{enum_val2.lower()}"
"""
            content += f"\nclass {class_name}(StreamableBaseModel):\n"
            num_fields = FuzzHelper.get_int(1, 5)
            for j in range(num_fields):
                field_name = f"field_{j}_{FuzzHelper.get_string(3, 7, 'abcdefghijklmnopqrstuvwxyz_')}"
                field_type_choice = FuzzHelper.get_int(1, 7)
                
                if field_type_choice == 1:
                    content += f"    {field_name}: str\n"
                elif field_type_choice == 2:
                    content += f"    {field_name}: int\n"
                elif field_type_choice == 3:
                    content += f"    {field_name}: bool\n"
                elif field_type_choice == 4:
                    content += f"    {field_name}: List[str]\n"
                elif field_type_choice == 5:
                    content += f"    {field_name}: Annotated[str, Streamed]\n"
                elif field_type_choice == 6:
                    content += f"    {field_name}: Optional[float]\n"
                else:
                    content += f"    {field_name}: {enum_name}\n"
        return content

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for the jmux CLI.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        env = {"PYTHONDONTWRITEBYTECODE": "1"}
        category = CmdCategory.GENERATE.value

        # Case 0: Edge case - evil string as argument. This tests argument parsing.
        try:
            root_dir_arg = FuzzHelper.get_evil_string()
            cases.append(TestCase(
                command=f"jmux generate --root {root_dir_arg}",
                category=category,
                env_vars=env
            ))
        except Exception as e:
            print(f"Warning: Failed to generate case 0: {e}")

        # Case 1: Edge case - evil content in file.
        try:
            root_dir_name = "evil_content_root"
            file_path = f"{root_dir_name}/malicious_model.py"
            file_content = FuzzHelper.get_evil_string()
            cases.append(TestCase(
                command=f"cd /test_data/{root_dir_name} && jmux generate --root .",
                category=category,
                mount_files={file_path: file_content},
                env_vars=env
            ))
        except Exception as e:
            print(f"Warning: Failed to generate case 1: {e}")

        # Case 2: Edge case - empty directory.
        try:
            root_dir_name = "empty_root"
            cases.append(TestCase(
                command=f"cd /test_data/{root_dir_name} && jmux generate --root .",
                category=category,
                mount_files={f"{root_dir_name}/.placeholder": ""}, # Trick to create the dir
                env_vars=env
            ))
        except Exception as e:
            print(f"Warning: Failed to generate case 2: {e}")

        # Fill remaining cases with normal, valid ones.
        while len(cases) < CASES_PER_CATEGORY:
            i = len(cases)
            try:
                root_dir_name = f"project_root_{i}"
                mount_files = {}
                num_files = FuzzHelper.get_int(1, 2)
                for j in range(num_files):
                    sub_dir = "models" if num_files > 1 else ""
                    file_path = os.path.join(root_dir_name, sub_dir, f"models_{j}.py")
                    num_models = FuzzHelper.get_int(1, 2)
                    file_content = self._generate_model_content(num_models)
                    mount_files[file_path] = file_content
                
                cases.append(TestCase(
                    command=f"cd /test_data/{root_dir_name} && jmux generate --root .",
                    category=category,
                    mount_files=mount_files,
                    env_vars=env
                ))
            except Exception as e:
                print(f"Warning: Failed to generate normal case {i}: {e}")
                break # Avoid infinite loop if generation always fails

        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = JmuxAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))