import os
import sys
import re
from enum import Enum
import random
import string

# Add parent directory to path to import framework modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# Static valid GitLab CI YAML templates for generating normal test cases
YAML_TEMPLATE_1 = """
stages:
  - build
  - test
  - deploy

build-job:
  stage: build
  script:
    - echo "Building..."
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'

test-job:
  stage: test
  script:
    - echo "Testing..."
  rules:
    - if: '$CI_PIPELINE_SOURCE == "push"'

deploy-job:
  stage: deploy
  script:
    - echo "Deploying..."
  rules:
    - if: '$CI_COMMIT_TAG =~ /^v[0-9]+\\.[0-9]+\\.[0-9]+$/'
"""

YAML_TEMPLATE_2 = """
# Using anchors
.job_template: &job_definition
  image: ruby:2.6
  services:
    - postgres
  rules:
    - if: '$RUN_JOB == "true"'

test1:
  <<: *job_definition
  script:
    - bundle exec rspec

test2:
  <<: *job_definition
  script:
    - bundle exec rubocop
"""

VALID_YAML_TEMPLATES = [YAML_TEMPLATE_1, YAML_TEMPLATE_2]
CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum
# =====================================================================
class CmdCategory(Enum):
    SIMULATE_NO_VARS = "gitlab-pipeline-simulator <yaml>"
    SIMULATE_ONE_VAR = "gitlab-pipeline-simulator <yaml> <var=val>"
    SIMULATE_MULTI_VARS = "gitlab-pipeline-simulator <yaml> <var1=val1> <var2=val2>"
    SHOW_SCRIPTS_ONE_VAR = "gitlab-pipeline-simulator -show-scripts <yaml> <var=val>"
    EXPAND_ONLY = "gitlab-pipeline-simulator -expand-only <yaml>"
    # HELP = "gitlab-pipeline-simulator -h"
    EDGE_CASES = "Edge cases with invalid inputs"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/sanchezpaco/gitlab-pipeline-simulator.git && cd gitlab-pipeline-simulator && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        # Correctly copy the local repo directory into the container's /repo directory
        os.system(f"docker cp {local_agent_path} {container.id}:/repo")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def generate_test_cases(self) -> list:
        cases = []

        def create_vars(num_vars: int) -> list:
            """Helper to generate a list of 'key=value' strings for the CLI."""
            variables = []
            predefined_vars = {
                "CI_COMMIT_BRANCH": random.choice(["main", "develop", f"feat/{FuzzHelper.get_string(5, 10, 'a-z-')}"]),
                "CI_PIPELINE_SOURCE": random.choice(["push", "web", "schedule", "api"]),
                "CI_COMMIT_TAG": f"v1.{FuzzHelper.get_int(0,9)}.{FuzzHelper.get_int(0,20)}",
                "RUN_JOB": FuzzHelper.get_boolean_str(),
                "CUSTOM_VAR": FuzzHelper.get_string(5, 10)
            }
            keys_to_use = random.sample(list(predefined_vars.keys()), min(num_vars, len(predefined_vars)))
            for key in keys_to_use:
                val = predefined_vars[key].split(' ')[0]  # Avoid spaces in values for simplicity
                variables.append(f"{key}={val}")
            return variables

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    command = ""
                    mount_files = {}
                    
                    # if category == CmdCategory.HELP:
                    #     if i == 0: command = "gitlab-pipeline-simulator -h"
                    #     elif i == 1: command = "gitlab-pipeline-simulator --help"
                    #     else: continue
                    #     cases.append(TestCase(command=command, category=category.value))
                    #     continue

                    # Default setup for cases that need a YAML file
                    file_name = f"test_{category.name.lower()}_{i}.yml"
                    yaml_path = f"/test_data/{file_name}"
                    yaml_content = random.choice(VALID_YAML_TEMPLATES)
                    mount_files = {file_name: yaml_content}
                    variables = []
                    flags = ""
                    
                    # --- Category-specific logic ---
                    if category == CmdCategory.SIMULATE_NO_VARS:
                        variables = []
                    elif category == CmdCategory.SIMULATE_ONE_VAR:
                        variables = create_vars(1)
                    elif category == CmdCategory.SIMULATE_MULTI_VARS:
                        variables = create_vars(random.randint(2, 4))
                    elif category == CmdCategory.SHOW_SCRIPTS_ONE_VAR:
                        flags = "-show-scripts"
                        variables = create_vars(1)
                    elif category == CmdCategory.EXPAND_ONLY:
                        flags = "-expand-only"
                    elif category == CmdCategory.EDGE_CASES:
                        if i == 0: # Non-existent YAML file
                            yaml_path = "/test_data/non_existent_file.yml"
                            mount_files = {}
                        elif i == 1: # Malformed YAML content
                            yaml_content = "job1:\n  script: echo 1\n\tbad-indent: true"
                            mount_files = {file_name: yaml_content}
                        elif i == 2: # Empty YAML file
                            mount_files = {file_name: ""}
                        elif i == 3: # Malformed variable argument (not key=value)
                            variables = [FuzzHelper.get_string(10, 15, chars=string.ascii_letters)]
                        elif i == 4: # Evil string in variable value, properly quoted for shell
                            evil_val = FuzzHelper.get_evil_string()
                            # Escape single quotes within the value to form a valid shell string
                            safe_evil_val = evil_val.replace("'", "'\\''")
                            variables = [f"EVIL_VAR='{safe_evil_val}'"]
                    
                    # Assemble the command: gitlab-pipeline-simulator [options] <path-to-yaml> [var=value...]
                    cmd_parts = ["gitlab-pipeline-simulator"]
                    if flags: cmd_parts.append(flags)
                    cmd_parts.append(yaml_path)
                    if variables: cmd_parts.extend(variables)
                    command = " ".join(cmd_parts)

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))

                except Exception as e:
                    # This ensures that if one case generation fails, the whole process doesn't stop.
                    print(f"Skipping test case generation for category {category.name} index {i} due to error: {e}")
                    continue
        return cases

# =====================================================================
# 3. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))