import os
import sys
import re
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing from BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command combinations of esupgrade.
    The value is the generic command structure template.
    """
    BASIC = "esupgrade <file>"
    BASELINE_NEWLY = "esupgrade --baseline newly-available <file>"
    JQUERY = "esupgrade --jquery <file>"
    JQUERY_BASELINE_NEWLY = "esupgrade --baseline newly-available --jquery <file>"

CASES_PER_CATEGORY = 50

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class EsupgradeAdapter(BaseRepoAdapter):
    """
    Adapter for the esupgrade CLI tool.
    """

    @property
    def base_image(self) -> str:
        """
        esupgrade is a Node.js tool. We use a node base image which includes
        node, npm, and git, as required by the installation rules.
        """
        return "node:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the oracle version of esupgrade from its git repository.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/codingjoe/esupgrade.git && cd esupgrade && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Copies the local agent code into the container and installs it.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases for esupgrade, covering different modes
        like writing to files, checking files, and printing to stdout.
        """
        cases = []

        # Self-contained, valid JS code snippets for standard transformations
        STANDARD_TRANSFORMATIONS = [
            "var x = 1; var y = 2; y = 3;",
            "const name = 'world'; const greeting = 'Hello ' + name + '!';",
            "const items = [1,2,3]; for (let i = 0; i < items.length; i++) { const item = items[i]; console.log(item); }",
            "const obj1 = {a:1}; const obj2 = {b:2}; const obj = Object.assign({}, obj1, obj2);",
            "const arr1 = [1]; const arr2 = [2]; const combined = arr1.concat(arr2);",
            "const result = Math.pow(2, 3);",
            "const myFunc = () => { return 42; };",
            "['a', 'b'].map(function(item) { return item; });",
            "function Person(name) { this.name = name; } Person.prototype.greet = function() { return 'Hello ' + this.name; };",
            "const x = null; const value = x !== null && x !== undefined ? x : 'default';",
            "const found = [1, 2, 3].indexOf(2) !== -1;",
            "const result = 'hello world'.substr(0, 5);",
            "const isPrefix = 'hello world'.indexOf('hello') === 0;",
            "function fn() { const args = Array.from(arguments); console.log(args); }",
            "function fn(x) { if (x === undefined) x = 10; return x; }",
        ]

        # Self-contained, valid JS code snippets for jQuery transformations
        JQUERY_TRANSFORMATIONS = [
            "const el = $('.foo');",
            "const el = $('#bar');",
            "const el = document.createElement('div'); $(el).addClass('a b');",
            "const el = document.createElement('div'); $(el).removeClass('a');",
            "const el = document.createElement('p'); const text = $(el).text();",
            "const el = document.createElement('p'); $(el).text('new text');",
            "const parent = document.createElement('div'); const child = document.createElement('span'); $(parent).append(child);",
            "const el = document.createElement('button'); const handler = () => {}; $(el).on('click', handler);",
            "$(document).ready(function() { console.log('ready'); });",
            "const el = document.createElement('div'); const children = $(el).children();",
            "const el = document.createElement('div'); $(el).css('color', 'red');",
            "$.each([1, 2, 3], function(i, val) { console.log(val); });"
        ]

        FILE_EXTENSIONS = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    ext = random.choice(FILE_EXTENSIONS)
                    file_name = f"test_file_{category.name.lower()}_{i}{ext}"

                    if category in [CmdCategory.JQUERY, CmdCategory.JQUERY_BASELINE_NEWLY]:
                        snippets = JQUERY_TRANSFORMATIONS
                    else:
                        snippets = STANDARD_TRANSFORMATIONS

                    roll = random.random()
                    content = ""
                    if roll < 0.1:
                        content = ""
                    elif roll < 0.2:
                        content = FuzzHelper.get_evil_string()
                    elif roll < 0.4:
                        evil_str = FuzzHelper.get_evil_string().replace("'", "\\'").replace("\n", "\\n").replace("`", "\\`")
                        content = f"const evil = `{evil_str}`;"
                    else:
                        content = random.choice(snippets)

                    cmd_parts = ["esupgrade"]
                    if category in [CmdCategory.BASELINE_NEWLY, CmdCategory.JQUERY_BASELINE_NEWLY]:
                        cmd_parts.append("--baseline newly-available")
                    if category in [CmdCategory.JQUERY, CmdCategory.JQUERY_BASELINE_NEWLY]:
                        cmd_parts.append("--jquery")

                    mode_roll = random.random()
                    mode_flag = ""
                    mode_desc = "[stdout]"
                    if mode_roll < 0.5:  # 50% chance to write (triggers fs_diff)
                        mode_flag = "--write"
                        mode_desc = "[--write]"
                    elif mode_roll < 0.8:  # 30% chance to check (triggers specific exit code)
                        mode_flag = "--check"
                        mode_desc = "[--check]"
                    # 20% chance for default (prints to stdout)

                    if mode_flag:
                        cmd_parts.append(mode_flag)
                    
                    cmd_parts.append(f"/test_data/{file_name}")
                    cmd = " ".join(cmd_parts)

                    test_category = f"{category.value} {mode_desc}"

                    cases.append(TestCase(
                        command=cmd,
                        category=test_category,
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name}: {e}")

        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = EsupgradeAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))