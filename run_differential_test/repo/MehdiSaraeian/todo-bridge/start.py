import os
import sys
import re
import json
import random
from enum import Enum

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    # CSV Conversion
    CSV_TO_STDOUT = "todo-bridge <input.csv>"
    CSV_TO_FILE = "todo-bridge <input.csv> <output.json>"
    CSV_TO_FILE_WITH_INDENT = "todo-bridge <input.csv> <output.json> --indent <N>"
    CSV_MERGE = "todo-bridge <input.csv> --merge <backup.json> <output.json>"
    CSV_MERGE_WITH_INDENT = "todo-bridge <input.csv> --merge <backup.json> <output.json> --indent <N>"

    # Markdown Conversion
    MD_TO_STDOUT = "todo-bridge <input.md>"
    MD_TO_FILE = "todo-bridge <input.md> <output.json>"
    MD_TO_FILE_WITH_INDENT = "todo-bridge <input.md> <output.json> --indent <N>"
    MD_MERGE = "todo-bridge <input.md> --merge <backup.json> <output.json>"
    MD_MERGE_WITH_INDENT = "todo-bridge <input.md> --merge <backup.json> <output.json> --indent <N>"

    # Todo.txt Conversion
    TXT_TO_STDOUT = "todo-bridge <input.txt>"
    TXT_TO_FILE = "todo-bridge <input.txt> <output.json>"
    TXT_TO_FILE_WITH_INDENT = "todo-bridge <input.txt> <output.json> --indent <N>"
    TXT_MERGE = "todo-bridge <input.txt> --merge <backup.json> <output.json>"
    TXT_MERGE_WITH_INDENT = "todo-bridge <input.txt> --merge <backup.json> <output.json> --indent <N>"


# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class TodoBridgeAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/MehdiSaraeian/todo-bridge.git && cd todo-bridge && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        # Use os.system for simplicity as per the original structure
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes the JSON output by removing volatile data like timestamps and
        normalizing randomly generated IDs to ensure deterministic output for comparison.
        """
        # 1. Remove volatile timestamp fields using regex
        sanitized = re.sub(r'"(lastUpdate|timestamp|created|modified|remindAt)":\s*\d+,?', '', raw_stdout)
        sanitized = re.sub(r',\s*}', '}', sanitized)
        sanitized = re.sub(r'{\s*,', '{', sanitized)

        try:
            # 2. Parse the string into a Python dictionary
            data = json.loads(sanitized)

            # 3. Normalize IDs
            id_mappers = {
                "task": {}, "project": {}, "tag": {}, "note": {},
                "taskRepeatCfg": {}, "simpleCounter": {}
            }

            def get_canonical_id(id_str, entity_type):
                if id_str not in id_mappers[entity_type]:
                    id_mappers[entity_type][id_str] = f"normalized_{entity_type}_{len(id_mappers[entity_type])}"
                return id_mappers[entity_type][id_str]

            # First pass: Collect all IDs from entity lists
            if isinstance(data, dict) and "data" in data:
                for entity_type, entities_data in data.get("data", {}).items():
                    if entity_type in id_mappers and isinstance(entities_data, dict) and "ids" in entities_data:
                        for entity_id in entities_data.get("ids", []):
                            get_canonical_id(entity_id, entity_type)

            # Second pass: Recursively replace IDs and sort ID lists
            def normalize_recursive(obj):
                if isinstance(obj, dict):
                    new_dict = {}
                    for k, v in obj.items():
                        new_val = v
                        if k in ["projectId", "parentId"] and v:
                            entity_type = "project" if k == "projectId" else "task"
                            if v in id_mappers.get(entity_type, {}):
                                new_val = get_canonical_id(v, entity_type)
                        elif k == "id" and v:
                            for entity_type in id_mappers:
                                if v in id_mappers[entity_type]:
                                    new_val = get_canonical_id(v, entity_type)
                                    break
                        elif k in ["tagIds", "subTaskIds", "attachmentIds"] and isinstance(v, list):
                            entity_type = "tag" if k == "tagIds" else "task"
                            new_val = sorted([get_canonical_id(item, entity_type) for item in v if item in id_mappers.get(entity_type, {})])
                        else:
                            new_val = normalize_recursive(v)
                        new_dict[k] = new_val
                    return new_dict
                elif isinstance(obj, list):
                    return [normalize_recursive(item) for item in obj]
                return obj

            normalized_data = normalize_recursive(data)
            final_output = json.dumps(normalized_data, sort_keys=True, indent=2)

        except (json.JSONDecodeError, TypeError, AttributeError):
            final_output = sanitized

        return super().sanitize_stdout(final_output)

    # =====================================================================
    # 3. Standardized Test Case Content Generators
    # =====================================================================

    def _generate_csv_content(self) -> str:
        headers = "title,notes,project,tags,isDone,timeEstimate,dueDay,subtasks"
        rows = []
        for _ in range(random.randint(2, 5)):
            row = [
                FuzzHelper.get_string(5, 20),  # title
                FuzzHelper.get_string(10, 50), # notes
                FuzzHelper.get_string(5, 10),  # project
                ",".join([FuzzHelper.get_string(4, 8) for _ in range(random.randint(0, 2))]), # tags
                random.choice(["true", "false", "1", "0"]), # isDone
                f"{FuzzHelper.get_int(1, 5)}h {FuzzHelper.get_int(1, 59)}m", # timeEstimate
                "2024-01-01", # dueDay
                "|".join([FuzzHelper.get_string(5, 15) for _ in range(random.randint(0, 2))]) # subtasks
            ]
            rows.append(",".join(f'"{item}"' for item in row))
        return headers + "\n" + "\n".join(rows)

    def _generate_md_content(self) -> str:
        lines = [f"# {FuzzHelper.get_string(5, 10)}"]
        for _ in range(random.randint(2, 5)):
            indent = "  " * random.randint(0, 2)
            status = random.choice(["[x]", "[ ]"])
            task = FuzzHelper.get_string(10, 30)
            tags = f" #{FuzzHelper.get_string(4, 8)}" if random.random() > 0.5 else ""
            time = f" ({FuzzHelper.get_int(1,5)}h)" if random.random() > 0.5 else ""
            lines.append(f"{indent}- {status} {task}{tags}{time}")
        return "\n".join(lines)

    def _generate_todotxt_content(self) -> str:
        lines = []
        for _ in range(random.randint(2, 5)):
            prio = f"({chr(ord('A') + random.randint(0, 3))}) " if random.random() > 0.5 else ""
            done = "x 2024-01-10 " if random.random() > 0.5 else ""
            date = "2024-01-01 "
            task = FuzzHelper.get_string(10, 40)
            proj = f" +{FuzzHelper.get_string(5,10)}"
            ctx = f" @{FuzzHelper.get_string(5,10)}"
            due = f" due:2024-12-31" if random.random() > 0.5 else ""
            time = f" t:{FuzzHelper.get_int(10, 50)}m" if random.random() > 0.5 else ""
            lines.append(f"{prio}{done}{date}{task}{proj}{ctx}{due}{time}")
        return "\n".join(lines)

    def _get_base_backup_json(self) -> str:
        # A minimal, valid Super Productivity backup file structure.
        return json.dumps({
            "data": {
                "task": {"ids": [], "entities": {}}, "project": {"ids": [], "entities": {}},
                "tag": {"ids": [], "entities": {}}, "timeTracking": {}, "globalConfig": {},
                "boards": {}, "reminders": [], "planner": {}, "simpleCounter": {},
                "note": {"ids": [], "entities": {}}, "taskRepeatCfg": {"ids": [], "entities": {}},
                "pluginUserData": [], "pluginMetadata": [], "issueProvider": {}, "metric": {},
                "improvement": {}, "obstruction": {}, "archiveYoung": {}, "archiveOld": {}
            },
            "crossModelVersion": 4.2, "lastUpdate": 1700000000000, "timestamp": 1700000000000
        })

    def generate_test_cases(self) -> list:
        cases = []
        CASES_PER_CATEGORY = 50

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    mount_files = {}
                    cmd_parts = ["todo-bridge"]

                    # Determine input file type and content generator
                    content_generator = None
                    if "CSV" in category.name:
                        input_file_name = f"input_{i}.csv"
                        content_generator = self._generate_csv_content
                    elif "MD" in category.name:
                        input_file_name = f"input_{i}.md"
                        content_generator = self._generate_md_content
                    elif "TXT" in category.name:
                        input_file_name = f"input_{i}.txt"
                        content_generator = self._generate_todotxt_content
                    else:
                        continue

                    # --- Case Generation Strategy ---
                    # i = 0: Empty input file
                    # i = 1: Malformed/evil input file content
                    # i = 2: Malformed arguments (e.g., bad indent, bad merge file)
                    # i = 3, 4: Normal valid fuzzed input

                    # 1. Generate input file content
                    if i == 0:
                        mount_files[input_file_name] = ""
                    elif i == 1:
                        mount_files[input_file_name] = FuzzHelper.get_evil_string()
                    else:
                        mount_files[input_file_name] = content_generator()
                    
                    cmd_parts.append(f"/test_data/{input_file_name}")

                    # 2. Handle output file and options
                    output_file_name = f"output_{i}.json"
                    backup_file_name = f"backup_{i}.json"

                    if "MERGE" in category.name:
                        cmd_parts.extend(["--merge", f"/test_data/{backup_file_name}", f"/test_data/{output_file_name}"])
                        if i == 2: # Malformed backup file for this edge case
                            mount_files[backup_file_name] = FuzzHelper.get_evil_string()
                        else:
                            mount_files[backup_file_name] = self._get_base_backup_json()
                    elif "TO_FILE" in category.name:
                        cmd_parts.append(f"/test_data/{output_file_name}")

                    if "INDENT" in category.name:
                        cmd_parts.append("--indent")
                        if i == 2: # Malformed indent value for this edge case
                            indent_val = random.choice(["-1", "abc", FuzzHelper.get_string(3, 5)])
                        else:
                            indent_val = str(FuzzHelper.get_int(0, 8))
                        cmd_parts.append(indent_val)

                    cases.append(TestCase(
                        command=" ".join(cmd_parts),
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Skip generating this test case if any error occurs, ensuring robustness.
                    continue
        return cases


if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = TodoBridgeAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))