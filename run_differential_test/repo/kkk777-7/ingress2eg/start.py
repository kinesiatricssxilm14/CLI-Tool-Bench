import os
import sys
import re
import random
import string
from enum import Enum
from textwrap import dedent

# Add the parent directory of 'final_differential_test' to the Python path
# to allow importing BaseRepoAdapter and DiffTestEngine.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enumerates the core functional command patterns of ingress2eg.
    The value of each enum member is a generic template of the command.
    """
    PRINT_FILE_YAML = "print --input-file <file> --output yaml"
    PRINT_FILE_JSON = "print --input-file <file> --output json"
    PRINT_FILE_CLASS = "print --input-file <file> --ingress-nginx-ingress-class <class>"
    PRINT_FILE_EMITTER = "print --input-file <file> --emitter <emitter>"
    PRINT_FILE_ALL_OPTS = "print --input-file <file> --output json --ingress-nginx-ingress-class <class> --emitter <emitter>"
    PRINT_FILE_WITH_NS = "print --input-file <file> --namespace <namespace>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class Ingress2egAdapter(BaseRepoAdapter):
    """
    Adapter for the ingress2eg CLI tool.
    """

    @property
    def base_image(self) -> str:
        """
        Specifies the Docker base image suitable for the Go application.
        """
        return "golang:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/kkk777-7/ingress2eg.git && cd ingress2eg && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle installation failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the development (agent) version of the tool from the local filesystem.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent installation failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Removes informational log lines from stdout to focus diffing on the generated manifests.
        The tool prints lines like 'parsed ...' and 'converted ...' to stdout along with the YAML/JSON.
        """
        # Remove lines starting with 'parsed' or 'converted'
        sanitized = re.sub(r"^(parsed|converted).*\n?", "", raw_stdout, flags=re.MULTILINE)
        return super().sanitize_stdout(sanitized)

    @staticmethod
    def _generate_ingress_yaml(is_edge_case: bool, ingress_class: str = "nginx") -> str:
        """
        Helper method to generate Ingress YAML content for testing.
        """
        if is_edge_case and random.random() < 0.2:
            return FuzzHelper.get_evil_string()
        if is_edge_case and random.random() < 0.3:
            return "" # Empty file

        # Use valid characters for Kubernetes resource names
        name = FuzzHelper.get_string(10, 15, string.ascii_lowercase + string.digits)
        namespace = FuzzHelper.get_string(10, 15, string.ascii_lowercase + string.digits)
        host = FuzzHelper.get_domain()
        service_name = FuzzHelper.get_string(10, 15, string.ascii_lowercase + string.digits)
        port = FuzzHelper.get_int(1, 65535)

        # Inject evil strings for edge cases into specific fields, otherwise use valid-like data
        cookie_name = FuzzHelper.get_evil_string() if is_edge_case else FuzzHelper.get_string(5, 10)
        cors_origin = FuzzHelper.get_evil_string() if is_edge_case else "*"
        limit_rps = FuzzHelper.get_evil_string() if is_edge_case else str(FuzzHelper.get_int(1, 100))
        rewrite_target = FuzzHelper.get_evil_string() if is_edge_case else "/"

        template_choice = random.choice(['affinity_cors', 'limit_rewrite'])

        if template_choice == 'affinity_cors':
            return dedent(f"""
            apiVersion: networking.k8s.io/v1
            kind: Ingress
            metadata:
              name: {name}
              namespace: {namespace}
              annotations:
                nginx.ingress.kubernetes.io/affinity: "cookie"
                nginx.ingress.kubernetes.io/session-cookie-name: "{cookie_name}"
                nginx.ingress.kubernetes.io/enable-cors: "true"
                nginx.ingress.kubernetes.io/cors-allow-origin: "{cors_origin}"
            spec:
              ingressClassName: {ingress_class}
              rules:
              - host: {host}
                http:
                  paths:
                  - path: /
                    pathType: Prefix
                    backend:
                      service:
                        name: {service_name}
                        port:
                          number: {port}
            """)
        else: # limit_rewrite
            return dedent(f"""
            apiVersion: networking.k8s.io/v1
            kind: Ingress
            metadata:
              name: {name}
              namespace: {namespace}
              annotations:
                nginx.ingress.kubernetes.io/limit-rps: "{limit_rps}"
                nginx.ingress.kubernetes.io/rewrite-target: "{rewrite_target}"
            spec:
              ingressClassName: {ingress_class}
              rules:
              - host: {host}
                http:
                  paths:
                  - path: /app
                    pathType: Prefix
                    backend:
                      service:
                        name: {service_name}
                        port:
                          number: {port}
            """)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of TestCase objects for differential testing.
        """
        cases = []
        CASES_PER_CATEGORY = 50
        TOOL_NAME = "ingress2eg"

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Make the first case of each category an edge case
                    is_edge_case = (i == 0)
                    file_name = f"ingress_{category.name.lower()}_{i}.yaml"
                    cmd = ""
                    content = ""
                    
                    ingress_class_for_yaml = "nginx"

                    if category == CmdCategory.PRINT_FILE_YAML:
                        content = self._generate_ingress_yaml(is_edge_case)
                        cmd = f"{TOOL_NAME} print --input-file /test_data/{file_name} --output yaml"

                    elif category == CmdCategory.PRINT_FILE_JSON:
                        content = self._generate_ingress_yaml(is_edge_case)
                        cmd = f"{TOOL_NAME} print --input-file /test_data/{file_name} --output json"

                    elif category == CmdCategory.PRINT_FILE_CLASS:
                        if is_edge_case:
                            class_val = FuzzHelper.get_evil_string()
                        else:
                            class_val = FuzzHelper.get_string(5, 15, string.ascii_lowercase + string.digits + "-")
                        
                        ingress_class_for_yaml = class_val if not is_edge_case else "nginx"
                        content = self._generate_ingress_yaml(is_edge_case, ingress_class=ingress_class_for_yaml)
                        cmd = f"{TOOL_NAME} print --input-file /test_data/{file_name} --ingress-nginx-ingress-class '{class_val}'"

                    elif category == CmdCategory.PRINT_FILE_EMITTER:
                        if is_edge_case:
                            emitter_val = FuzzHelper.get_evil_string()
                        else:
                            emitter_val = random.choice(["envoy-gateway", "standard"])
                        content = self._generate_ingress_yaml(is_edge_case)
                        cmd = f"{TOOL_NAME} print --input-file /test_data/{file_name} --emitter '{emitter_val}'"

                    elif category == CmdCategory.PRINT_FILE_ALL_OPTS:
                        if is_edge_case:
                            class_val = FuzzHelper.get_evil_string()
                            emitter_val = FuzzHelper.get_evil_string()
                        else:
                            class_val = FuzzHelper.get_string(5, 15, string.ascii_lowercase + string.digits + "-")
                            emitter_val = random.choice(["envoy-gateway", "standard"])
                        
                        ingress_class_for_yaml = class_val if not is_edge_case else "nginx"
                        content = self._generate_ingress_yaml(is_edge_case, ingress_class=ingress_class_for_yaml)
                        cmd = f"{TOOL_NAME} print --input-file /test_data/{file_name} --output json --ingress-nginx-ingress-class '{class_val}' --emitter '{emitter_val}'"

                    elif category == CmdCategory.PRINT_FILE_WITH_NS:
                        if is_edge_case:
                            ns_val = FuzzHelper.get_evil_string()
                        else:
                            ns_val = FuzzHelper.get_string(5, 15, string.ascii_lowercase + string.digits + "-")
                        content = self._generate_ingress_yaml(is_edge_case)
                        cmd = f"{TOOL_NAME} print --input-file /test_data/{file_name} --namespace '{ns_val}'"

                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files={file_name: content}
                    ))
                except Exception as e:
                    print(f"Warning: Failed to generate test case for {category.name} index {i}. Error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = Ingress2egAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))