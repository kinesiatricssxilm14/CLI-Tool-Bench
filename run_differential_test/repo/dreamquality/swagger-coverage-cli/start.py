import os
import sys
import re
import random
import json
from enum import Enum

# Add the parent directory to the path to import framework modules
sys.path.append(os.path.abspath("../../.."))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    POSTMAN_SINGLE_API = "swagger-coverage-cli <apiFile> <collectionFile>"
    POSTMAN_MULTI_API = "swagger-coverage-cli \"<apiFile1>,<apiFile2>\" <collectionFile>"
    POSTMAN_STRICT_QUERY = "swagger-coverage-cli <apiFile> <collectionFile> --strict-query"
    POSTMAN_STRICT_BODY = "swagger-coverage-cli <apiFile> <collectionFile> --strict-body"
    POSTMAN_STRICT_BOTH = "swagger-coverage-cli <apiFile> <collectionFile> --strict-query --strict-body"
    NEWMAN_SINGLE_API = "swagger-coverage-cli <apiFile> <reportFile> --newman"
    DISABLE_VALIDATION = "swagger-coverage-cli <apiFile> <collectionFile> --disable-spec-validation"
    CUSTOM_OUTPUT = "swagger-coverage-cli <apiFile> <collectionFile> --output <file>"
    # EDGE_CASES = "Edge cases with invalid inputs"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class MyAdapter(BaseRepoAdapter):

    def __init__(self):
        super().__init__()
        # Define API types and their corresponding file generators
        self.api_definitions = {
            'rest': {'file': 'api.yaml', 'gen': self._get_openapi_content},
            'grpc': {'file': 'api.proto', 'gen': self._get_proto_content},
            'graphql': {'file': 'api.graphql', 'gen': self._get_graphql_content},
            'csv': {'file': 'api.csv', 'gen': self._get_csv_api_content}
        }

    @property
    def base_image(self) -> str:
        # Per README, Node.js 12+ is required.
        return "node:latest"

    def install_oracle(self, container) -> None:
        # Rule 1: Strict installation command for JavaScript/NodeJs
        cmd = (
            "mkdir -p /repo && cd /repo && "
            "git clone https://github.com/dreamquality/swagger-coverage-cli.git && "
            "cd swagger-coverage-cli && "
            "npm install && npm install -g ."
        )
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        # Rule 1: Strict installation command for JavaScript/NodeJs
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && npm install && npm install -g ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        # Sanitize volatile parts of the output for stable diffing
        sanitized = re.sub(r"Coverage: \d+\.\d+%", "Coverage: [COVERAGE]%", raw_stdout)
        sanitized = re.sub(r"Total operations in spec\(s\): \d+", "Total operations in spec(s): [COUNT]", sanitized)
        sanitized = re.sub(r"Matched operations in Postman: \d+", "Matched operations in Postman: [COUNT]", sanitized)
        sanitized = re.sub(r"Matched operations in Postman/Newman: \d+", "Matched operations in Postman/Newman: [COUNT]", sanitized)
        sanitized = re.sub(r"HTML report saved to: .*", "HTML report saved to: [REPORT_FILE]", sanitized)
        sanitized = re.sub(r"APIs analyzed: .*", "APIs analyzed: [API_LIST]", sanitized)
        sanitized = re.sub(r"Error processing file .*", "Error processing file [FILE_PATH]", sanitized)
        sanitized = re.sub(r"Path to file is not specified for .*", "Path to file is not specified for [FILE]", sanitized)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list:
        test_cases = []
        CASES_PER_CATEGORY = 50 # Rule 6

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    tc = self._generate_case_for_category(category, i)
                    if tc:
                        test_cases.append(tc)
                except Exception as e:
                    # Rule 8: Don't let generation failures crash the whole process
                    print(f"WARNING: Failed to generate test case for {category.name} (i={i}): {e}")
        
        return test_cases

    def _generate_case_for_category(self, category: CmdCategory, iteration: int) -> TestCase:
        """Generates a single, logical test case for a given category."""
        mount_files = {}
        cmd_parts = ["swagger-coverage-cli"]
        api_types = list(self.api_definitions.keys())

        if category == CmdCategory.POSTMAN_SINGLE_API:
            chosen_type = api_types[iteration % len(api_types)]
            api_def = self.api_definitions[chosen_type]
            api_file_name = api_def['file']
            
            mount_files = {
                api_file_name: api_def['gen'](),
                "collection.json": self._get_postman_collection_content(api_types=[chosen_type])
            }
            cmd_parts.extend([f"/test_data/{api_file_name}", "/test_data/collection.json"])

        elif category == CmdCategory.POSTMAN_MULTI_API:
            type1_key = api_types[iteration % len(api_types)]
            type2_key = api_types[(iteration + 1) % len(api_types)]
            if type1_key == type2_key: type2_key = api_types[(iteration + 2) % len(api_types)]

            api1_def, api2_def = self.api_definitions[type1_key], self.api_definitions[type2_key]
            api1_filename, api2_filename = api1_def['file'], api2_def['file']
            if api1_filename == api2_filename:
                name, ext = os.path.splitext(api2_filename)
                api2_filename = f"{name}2{ext}"

            mount_files = {
                api1_filename: api1_def['gen'](),
                api2_filename: api2_def['gen'](),
                "collection.json": self._get_postman_collection_content(api_types=[type1_key, type2_key])
            }
            api1_path, api2_path = f"/test_data/{api1_filename}", f"/test_data/{api2_filename}"
            cmd_parts.extend([f'"{api1_path},{api2_path}"', "/test_data/collection.json"])

        elif category in [CmdCategory.POSTMAN_STRICT_QUERY, CmdCategory.POSTMAN_STRICT_BODY, CmdCategory.POSTMAN_STRICT_BOTH]:
            mismatch = (iteration % 2 == 1)
            mount_files = {
                "strict_api.yaml": self._get_strict_openapi_spec(),
                "strict_collection.json": self._get_strict_postman_collection(mismatch_query=mismatch, mismatch_body=mismatch)
            }
            cmd_parts.extend(["/test_data/strict_api.yaml", "/test_data/strict_collection.json"])
            if category in [CmdCategory.POSTMAN_STRICT_QUERY, CmdCategory.POSTMAN_STRICT_BOTH]: cmd_parts.append("--strict-query")
            if category in [CmdCategory.POSTMAN_STRICT_BODY, CmdCategory.POSTMAN_STRICT_BOTH]: cmd_parts.append("--strict-body")

        elif category == CmdCategory.NEWMAN_SINGLE_API:
            chosen_type = api_types[iteration % len(api_types)]
            api_def = self.api_definitions[chosen_type]
            api_file_name = api_def['file']
            
            mount_files = {
                api_file_name: api_def['gen'](),
                "newman.json": self._get_newman_report_content(api_type=chosen_type)
            }
            cmd_parts.extend([f"/test_data/{api_file_name}", "/test_data/newman.json", "--newman"])

        elif category == CmdCategory.DISABLE_VALIDATION:
            mount_files = {
                "broken.yaml": self._get_broken_openapi_spec(),
                "collection.json": self._get_postman_collection_content(api_types=['rest'])
            }
            cmd_parts.extend(["/test_data/broken.yaml", "/test_data/collection.json", "--disable-spec-validation"])

        elif category == CmdCategory.CUSTOM_OUTPUT:
            output_filename = f"report_{iteration}.html"
            if iteration == 4: output_filename = "'my custom report.html'"
            mount_files = {
                "api.yaml": self._get_openapi_content(),
                "collection.json": self._get_postman_collection_content(api_types=['rest'])
            }
            cmd_parts.extend(["/test_data/api.yaml", "/test_data/collection.json", "--output", output_filename])

        elif category == CmdCategory.EDGE_CASES:
            if iteration == 0: # Non-existent file
                cmd_parts.extend(["/test_data/nonexistent.yaml", "/test_data/collection.json"])
                mount_files = {"collection.json": self._get_postman_collection_content(api_types=[])}
            elif iteration == 1: # Empty file
                mount_files = {"empty.yaml": "", "collection.json": self._get_postman_collection_content(api_types=[])}
                cmd_parts.extend(["/test_data/empty.yaml", "/test_data/collection.json"])
            elif iteration == 2: # Malformed JSON collection
                mount_files = {"api.yaml": self._get_openapi_content(), "collection.json": '{"info": "missing stuff"'}
                cmd_parts.extend(["/test_data/api.yaml", "/test_data/collection.json"])
            elif iteration == 3: # No arguments
                pass 
            else:
                pass

        command = " ".join(cmd_parts)
        return TestCase(command=command, category=category.value, mount_files=mount_files)

    # --- Helper Methods for Content Generation (Logical & Protocol-Aware) ---

    def _get_openapi_content(self):
        return """
openapi: 3.0.0
info:
  title: Fuzz REST API
  version: 1.0.0
paths:
  /items:
    get:
      summary: Get all items
      responses:
        '200':
          description: A list of items.
"""

    def _get_proto_content(self):
        return """
syntax = "proto3";
package fuzz_service;
service FuzzService { rpc DoThing (ThingRequest) returns (ThingReply); }
message ThingRequest { string data = 1; }
message ThingReply { string result = 1; }
"""

    def _get_graphql_content(self):
        return """
type Query { fuzzQuery(id: ID!): String }
"""

    def _get_csv_api_content(self):
        return 'METHOD,URI,NAME,STATUS CODE,BODY,TAGS\nGET,/fuzz/items,getItems,200,"{}","fuzz"'

    def _get_postman_collection_content(self, api_types: list):
        item_parts = []
        if 'rest' in api_types:
            item_parts.append("""
            {"name": "Get Items (REST)","request": {"method": "GET", "url": {"raw": "http://localhost/items"}},"event": [{"listen": "test", "script": {"exec": ["pm.response.to.have.status(200);"]}}]}""")
        if 'grpc' in api_types:
            item_parts.append("""
            {"name": "DoThing (gRPC)","request": {"method": "POST","header": [{"key": "Content-Type", "value": "application/grpc"}],"body": {"mode": "raw", "raw": "{\\"data\\": \\"fuzz\\"}"},"url": {"raw": "http://localhost/fuzz_service.FuzzService/DoThing"}},"event": [{"listen": "test", "script": {"exec": ["pm.response.to.have.status(200);"]}}]}""")
        if 'graphql' in api_types:
            item_parts.append("""
            {"name": "FuzzQuery (GraphQL)","request": {"method": "POST","header": [{"key": "Content-Type", "value": "application/json"}],"body": {"mode": "raw", "raw": "{\\"query\\": \\"query { fuzzQuery(id: \\\\\\"1\\\\\\") }\\"}"},"url": {"raw": "http://localhost/graphql"}},"event": [{"listen": "test", "script": {"exec": ["pm.response.to.have.status(200);"]}}]}""")
        if 'csv' in api_types:
            item_parts.append("""
            {"name": "Get Items (CSV)","request": {"method": "GET", "url": {"raw": "http://localhost/fuzz/items"}},"event": [{"listen": "test", "script": {"exec": ["pm.response.to.have.status(200);"]}}]}""")
        
        items_json = ",".join(item_parts)
        return f'{{"info": {{"name": "Fuzz Collection", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}},"item": [{items_json}]}}'

    def _get_newman_report_content(self, api_type: str):
        execution = ""
        if api_type == 'rest':
            execution = '{"item": {"name": "Get Items"},"request": {"method": "GET", "url": {"path": ["items"]}},"response": {"code": 200, "status": "OK"}}'
        elif api_type == 'grpc':
            execution = '{"item": {"name": "DoThing"},"request": {"method": "POST", "url": {"path": ["fuzz_service.FuzzService", "DoThing"]}},"response": {"code": 200, "status": "OK"}}'
        elif api_type == 'graphql':
            execution = '{"item": {"name": "FuzzQuery"},"request": {"method": "POST", "url": {"path": ["graphql"]}},"response": {"code": 200, "status": "OK"}}'
        elif api_type == 'csv':
            execution = '{"item": {"name": "getItems"},"request": {"method": "GET", "url": {"path": ["fuzz", "items"]}},"response": {"code": 200, "status": "OK"}}'
        
        return f'{{"collection": {{"info": {{"name": "Fuzz Collection"}}}},"run": {{"stats": {{"requests": {{"total": 1}}, "assertions": {{"total": 1}}}},"executions": [{execution}]}}}}'

    def _get_broken_openapi_spec(self):
        return '{"openapi": "3.0.0", "info": {"title": "Broken Spec"}, "paths": {}, "components": {"schemas": {"User": {"$ref": "#/components/schemas/NonExistent"}}}}'

    def _get_strict_openapi_spec(self):
        return """
openapi: 3.0.0
info:
  title: Strict API
  version: 1.0.0
paths:
  /search:
    get:
      parameters:
      - name: q
        in: query
        required: true
        schema: {type: string}
      responses: {'200': {description: OK}}
  /submit:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties: {id: {type: integer}}
              required: [id]
      responses: {'200': {description: OK}}
"""

    def _get_strict_postman_collection(self, mismatch_query=False, mismatch_body=False):
        query_part = "" if mismatch_query else "?q=test"
        body_part = '{\\"id\\": \\"not-an-int\\"}' if mismatch_body else '{\\"id\\": 123}'
        return f"""
{{
  "info": {{"name": "Strict Collection", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}},
  "item": [
    {{"name": "Strict Search","request": {{"method": "GET", "url": {{"raw": "http://localhost/search{query_part}"}}}},"event": [{{"listen": "test", "script": {{"exec": ["pm.response.to.have.status(200);"]}}}}]}},
    {{"name": "Strict Submit","request": {{"method": "POST","header": [{{"key": "Content-Type", "value": "application/json"}}],"body": {{"mode": "raw", "raw": "{body_part}"}},"url": {{"raw": "http://localhost/submit"}}}},"event": [{{"listen": "test", "script": {{"exec": ["pm.response.to.have.status(200);"]}}}}]}}
  ]
}}
"""

# =====================================================================
# 4. Main Entrypoint (Do not modify)
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = MyAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))