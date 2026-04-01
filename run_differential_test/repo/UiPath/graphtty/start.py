import os
import sys
import re
from enum import Enum
import random
import json
import string

# Add the parent directory to the path to import framework modules
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command structures of graphtty.
    """
    BASIC = "graphtty <file>"
    THEME = "graphtty <file> --theme <theme>"
    ASCII = "graphtty <file> --ascii"
    NO_TYPES = "graphtty <file> --no-types"
    WIDTH = "graphtty <file> --width <N>"
    MAX_DEPTH = "graphtty <file> --max-depth <N>"
    MAX_BREADTH = "graphtty <file> --max-breadth <N>"
    
    # Key Combinations
    THEME_ASCII = "graphtty <file> --theme <theme> --ascii"
    THEME_NO_TYPES = "graphtty <file> --theme <theme> --no-types"
    ASCII_NO_TYPES = "graphtty <file> --ascii --no-types"
    WIDTH_DEPTH_BREADTH = "graphtty <file> --width <N> --max-depth <N> --max-breadth <N>"
    
    # Standalone command
    LIST_THEMES = "graphtty --list-themes"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class GraphttyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/UiPath/graphtty.git && cd graphtty && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []
        CASES_PER_CATEGORY = 50
        VALID_THEMES = [
            'default', 'monokai', 'ocean', 'forest', 'dracula', 
            'solarized', 'nord', 'catppuccin', 'gruvbox', 'tokyo-night'
        ]

        def _generate_graph_content(is_edge: bool, case_index: int) -> str:
            """Generates content for the graph JSON file."""
            if not is_edge:
                # Generate a structurally valid graph JSON
                num_nodes = FuzzHelper.get_int(2, 10)
                nodes = []
                node_ids = []
                for j in range(num_nodes):
                    node_id = f"id_{j}_{FuzzHelper.get_string(3, 5)}"
                    node_ids.append(node_id)
                    node = {
                        "id": node_id,
                        "name": FuzzHelper.get_string(5, 20),
                        "type": FuzzHelper.get_string(4, 10)
                    }
                    if random.random() < 0.3:
                        node["description"] = FuzzHelper.get_string(10, 40)
                    nodes.append(node)

                edges = []
                if num_nodes > 1:
                    num_edges = FuzzHelper.get_int(1, num_nodes)
                    for _ in range(num_edges):
                        source, target = random.sample(node_ids, 2)
                        edge = {"source": source, "target": target}
                        if random.random() < 0.5:
                            edge["label"] = FuzzHelper.get_string(3, 10)
                        edges.append(edge)
                
                return json.dumps({"nodes": nodes, "edges": edges}, indent=2)
            else:
                # Generate edge case content
                roll = case_index % 5
                if roll == 0:
                    return FuzzHelper.get_evil_string()
                elif roll == 1:
                    return ""
                elif roll == 2:
                    return random.choice(['{}', '{"nodes": []}', '{"edges": []}', '{"nodes": null, "edges": null}'])
                elif roll == 3:
                    # Dangling edge
                    return json.dumps({
                        "nodes": [{"id": "a", "name": "Node A"}],
                        "edges": [{"source": "a", "target": "non_existent_node"}]
                    })
                else:
                    # Malformed JSON
                    return '{"nodes": [{"id": "a"}], "edges":'

        total_case_index = 0
        for category in CmdCategory:
            if category == CmdCategory.LIST_THEMES:
                cases.append(TestCase(
                    command="graphtty --list-themes",
                    category=category.value
                ))
                continue

            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # Designate the first case in each category as an edge case
                    file_name = f"graph_{category.name.lower()}_{i}.json"
                    
                    content = _generate_graph_content(is_edge_case, total_case_index)
                    mount_files = {file_name: content}
                    
                    cmd_parts = [f"graphtty /test_data/{file_name}"]
                    
                    if category in [CmdCategory.THEME, CmdCategory.THEME_ASCII, CmdCategory.THEME_NO_TYPES]:
                        theme = FuzzHelper.get_string(5, 10) if is_edge_case else random.choice(VALID_THEMES)
                        cmd_parts.append(f"--theme {theme}")

                    if category in [CmdCategory.ASCII, CmdCategory.THEME_ASCII, CmdCategory.ASCII_NO_TYPES]:
                        cmd_parts.append("--ascii")

                    if category in [CmdCategory.NO_TYPES, CmdCategory.THEME_NO_TYPES, CmdCategory.ASCII_NO_TYPES]:
                        cmd_parts.append("--no-types")

                    # --- Refactored and fixed argument generation ---
                    if category in [CmdCategory.WIDTH, CmdCategory.WIDTH_DEPTH_BREADTH]:
                        if is_edge_case:
                            width = FuzzHelper.get_int(-100, 0) if random.random() > 0.5 else FuzzHelper.get_string(2, 4)
                        else:
                            width = FuzzHelper.get_int(20, 200)
                        cmd_parts.append(f"--width {width}")

                    if category in [CmdCategory.MAX_DEPTH, CmdCategory.WIDTH_DEPTH_BREADTH]:
                        if is_edge_case:
                            depth = FuzzHelper.get_int(-10, 0) if random.random() > 0.5 else FuzzHelper.get_string(2, 4)
                        else:
                            depth = FuzzHelper.get_int(1, 20)
                        cmd_parts.append(f"--max-depth {depth}")

                    if category in [CmdCategory.MAX_BREADTH, CmdCategory.WIDTH_DEPTH_BREADTH]:
                        if is_edge_case:
                            breadth = FuzzHelper.get_int(-10, 0) if random.random() > 0.5 else FuzzHelper.get_string(2, 4)
                        else:
                            breadth = FuzzHelper.get_int(1, 20)
                        cmd_parts.append(f"--max-breadth {breadth}")
                    
                    main_cmd = cmd_parts[0]
                    optional_args = cmd_parts[1:]
                    random.shuffle(optional_args)
                    final_cmd = f"{main_cmd} {' '.join(optional_args)}"

                    cases.append(TestCase(
                        command=final_cmd.strip(),
                        category=category.value,
                        mount_files=mount_files
                    ))
                    total_case_index += 1
                except Exception as e:
                    print(f"Warning: Failed to generate test case for category {category.name}: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = GraphttyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))