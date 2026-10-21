import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# This allows importing BaseRepoAdapter and DiffTestEngine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures, exhaust all combinations)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core command structures and argument combinations for 'nub'.
    Each enum value is a generic template string representing a class of commands.
    """
    # Basic operations
    BASIC_FILE = "nub <file>"
    
    # Core options, one by one
    SHAPE = "nub <file> --shape <W:H>"
    LIMIT = "nub <file> --limit <N>"
    RANGE = "nub <file> --range <S:E>"
    GREP = "nub <file> --grep <PATTERN>"
    DEDUPLICATE = "nub <file> --deduplicate"
    PROFILE = "nub <file> --profile"
    TYPE = "nub <file> --type <FORMAT>"
    NO_LINE_NUMBERS = "nub <file> --no-line-numbers"
    
    # Key combinations
    SHAPE_AND_GREP = "nub <file> --shape <W:H> --grep <PATTERN>"
    LIMIT_AND_RANGE = "nub <file> --limit <N> --range <S:E>"
    DEDUPLICATE_AND_NO_LINE_NUMBERS = "nub <file> --deduplicate --no-line-numbers"
    
    # Complex combination
    SHAPE_RANGE_GREP = "nub <file> --shape <W:H> --range <S:E> --grep <PATTERN>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class NubAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """Installs the oracle version of the tool in the container, following strict rules."""
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/horiacristescu/nub.git && cd nub && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """Installs the agent version of the tool in the container, following strict rules."""
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """Custom stdout sanitization to remove volatile elements like file sizes."""
        # Sanitize volatile file size markers like '[2.3 KB]' or '[1MB]'
        # which can appear in directory listings or profile outputs.
        sanitized = re.sub(r'\[\s*\d+\.?\d*\s*[kKmMgGtT]?B\s*\]', '[SIZE]', raw_stdout)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator (Integrate normal & edge tests)
    # =====================================================================
    def _get_random_content(self, is_edge_case: bool, i: int) -> tuple[str, str]:
        """Helper to generate varied file content for testing different format strategies."""
        if is_edge_case:
            # Generate problematic or empty content for edge case testing
            if i % 2 == 0:
                return "", ".txt"
            return FuzzHelper.get_evil_string(), ".txt"

        rand_choice = random.randint(0, 2)
        if rand_choice == 0:  # Python-like content
            content = f"""
import os
import sys

class MyClass:
    # {FuzzHelper.get_string(10, 30)}
    def __init__(self, name):
        self.name = name
        print(f"Hello, {{self.name}}")

    def do_work(self, value: int) -> int:
        # A simple calculation
        # {FuzzHelper.get_string(20, 40)}
        result = (value * 2) + 10
        return result

def main():
    # {FuzzHelper.get_string(10, 20)}
    instance = MyClass("{FuzzHelper.get_string(3, 8)}")
    instance.do_work({FuzzHelper.get_int(1, 100)})
"""
            return content, ".py"
        elif rand_choice == 1:  # Markdown-like content
            content = f"""
# {FuzzHelper.get_string(5, 15)}

This is a test document for nub.

## Section 1: {FuzzHelper.get_string(10, 20)}
* Item 1: {FuzzHelper.get_string(5, 10)}
* Item 2: {FuzzHelper.get_string(5, 10)}

```python
def hello():
    print("hello from a code block")
```

### Subsection 1.1
{FuzzHelper.get_string(50, 80)}
"""
            return content, ".md"
        else:  # Plain text / CSV
            return FuzzHelper.get_csv_string(rows=20, cols=5), ".txt"

    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # Make first case in each category an edge case
                    content, extension = self._get_random_content(is_edge_case, i)
                    file_name = f"fuzz_test_{category.name}_{i}{extension}"
                    file_path = f"/test_data/{file_name}"
                    
                    cmd_parts = ["nub", file_path]

                    if category == CmdCategory.BASIC_FILE:
                        pass
                    
                    elif category == CmdCategory.SHAPE:
                        if is_edge_case:
                            shape_val = f"{FuzzHelper.get_int(-5, 5)}:{FuzzHelper.get_string(1, 3, 'abc')}"
                        else:
                            shape_val = f"{FuzzHelper.get_int(10, 200)}:{FuzzHelper.get_int(10, 100)}"
                        cmd_parts.extend(["--shape", shape_val])

                    elif category == CmdCategory.LIMIT:
                        if is_edge_case:
                            limit_val = FuzzHelper.get_evil_string()
                            # Quote evil strings to ensure they are passed as a single argument
                            cmd_parts.extend(["--limit", f'"{limit_val}"'])
                        else:
                            limit_val = str(FuzzHelper.get_int(100, 5000))
                            cmd_parts.extend(["--limit", limit_val])

                    elif category == CmdCategory.RANGE:
                        if is_edge_case:
                            s = FuzzHelper.get_int(-10, 50)
                            e = FuzzHelper.get_int(-10, 50)
                            range_val = f"{s}:{e}"
                        else:
                            s = FuzzHelper.get_int(1, 20)
                            e = FuzzHelper.get_int(s, 50)
                            range_val = f"{s}:{e}"
                        cmd_parts.extend(["--range", range_val])

                    elif category == CmdCategory.GREP:
                        if is_edge_case:
                            grep_pattern = FuzzHelper.get_evil_string()
                            # Quote evil strings to prevent shell interpretation
                            cmd_parts.extend(["--grep", f'"{grep_pattern}"'])
                        else:
                            word_to_grep = content.split()
                            grep_pattern = word_to_grep[len(word_to_grep)//2] if word_to_grep else "test"
                            cmd_parts.extend(["--grep", grep_pattern])

                    elif category == CmdCategory.DEDUPLICATE:
                        cmd_parts.append("--deduplicate")

                    elif category == CmdCategory.PROFILE:
                        cmd_parts.append("--profile")

                    elif category == CmdCategory.TYPE:
                        if is_edge_case:
                            type_val = FuzzHelper.get_string(3, 10)
                        else:
                            type_val = random.choice(["python", "markdown", "text", "mindmap"])
                        cmd_parts.extend(["--type", type_val])

                    elif category == CmdCategory.NO_LINE_NUMBERS:
                        cmd_parts.append("--no-line-numbers")

                    elif category == CmdCategory.SHAPE_AND_GREP:
                        shape_val = f"{FuzzHelper.get_int(50, 150)}:{FuzzHelper.get_int(20, 80)}"
                        grep_pattern = FuzzHelper.get_string(3, 8)
                        cmd_parts.extend(["--shape", shape_val, "--grep", grep_pattern])

                    elif category == CmdCategory.LIMIT_AND_RANGE:
                        limit_val = str(FuzzHelper.get_int(500, 2000))
                        s = FuzzHelper.get_int(1, 10)
                        e = FuzzHelper.get_int(s + 5, 20)
                        range_val = f"{s}:{e}"
                        cmd_parts.extend(["--limit", limit_val, "--range", range_val])

                    elif category == CmdCategory.DEDUPLICATE_AND_NO_LINE_NUMBERS:
                        cmd_parts.extend(["--deduplicate", "--no-line-numbers"])

                    elif category == CmdCategory.SHAPE_RANGE_GREP:
                        shape_val = f"{FuzzHelper.get_int(80, 120)}:{FuzzHelper.get_int(10, 40)}"
                        s = FuzzHelper.get_int(1, 5)
                        e = FuzzHelper.get_int(s + 10, 30)
                        range_val = f"{s}:{e}"
                        grep_pattern = FuzzHelper.get_string(4, 7)
                        cmd_parts.extend(["--shape", shape_val, "--range", range_val, "--grep", grep_pattern])

                    command = " ".join(cmd_parts)
                    
                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception:
                    # If a single test case generation fails, skip it and continue
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = NubAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))