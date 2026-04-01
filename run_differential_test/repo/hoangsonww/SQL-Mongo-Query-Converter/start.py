import os
import sys
import re
import random
import string
import json
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
    Enumerates the core command structures for sql-mongo-converter.
    """
    SQL2MONGO_QUERY = "sql-mongo-converter sql2mongo --query \"<SQL>\""
    SQL2MONGO_FILE = "sql-mongo-converter sql2mongo --file <file>"
    MONGO2SQL_QUERY = "sql-mongo-converter mongo2sql --query '<MONGO_JSON>'"
    MONGO2SQL_FILE = "sql-mongo-converter mongo2sql --file <file>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class SQLMongoConverterAdapter(BaseRepoAdapter):
    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Python environment."""
        return "python:latest"

    def install_oracle(self, container) -> None:
        """
        Installs the baseline (oracle) version of the tool from GitHub.
        """
        full_name = "hoangsonww/SQL-Mongo-Query-Converter"
        repo_name = "SQL-Mongo-Query-Converter"
        cmd = f"mkdir -p /repo && cd /repo && git clone https://github.com/{full_name}.git && cd {repo_name} && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        """
        Installs the local (agent) version of the tool into the container.
        """
        container.exec_run("mkdir -p /repo")
        os.system(f"docker cp {local_agent_path} {container.id}:/repo/repo_to_be_tested")
        cmd = "cd /repo/repo_to_be_tested && pip install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def sanitize_stdout(self, raw_stdout: str) -> str:
        """
        Sanitizes volatile information from the CLI output, like line/column numbers in errors.
        """
        # Sanitize line/column numbers from parsing errors to prevent noise
        # from minor parser differences. e.g., "SQLParsingError: Unexpected token at line 1, column 8: ..."
        sanitized = re.sub(r'at line \d+, column \d+', 'at line X, column Y', raw_stdout)
        return super().sanitize_stdout(sanitized)

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        """
        Generates a list of test cases, mixing normal and edge/malicious inputs.
        """
        cases = []
        VALID_CHARS = string.ascii_letters + "_"

        def _generate_sql_query() -> str:
            """Helper to generate a variety of valid SQL queries."""
            table = FuzzHelper.get_string(5, 15, VALID_CHARS)
            col1 = FuzzHelper.get_string(5, 15, VALID_CHARS)
            col2 = FuzzHelper.get_string(5, 15, VALID_CHARS)
            val1 = FuzzHelper.get_string(5, 10).replace("'", "''") # Escape single quotes for SQL
            num1 = FuzzHelper.get_int(1, 1000)

            queries = [
                f"SELECT {col1}, {col2} FROM {table} WHERE {col1} > {num1}",
                f"SELECT * FROM {table} WHERE {col1} = '{val1}' AND {col2} IS NOT NULL",
                f"SELECT * FROM {table} WHERE {col1} LIKE '%{val1}%'",
                f"SELECT * FROM {table} WHERE {col2} BETWEEN {num1} AND {num1 + 100}",
                f"SELECT * FROM {table} WHERE {col1} IN ('{val1}', '{FuzzHelper.get_string(5,10).replace("'", "''")}')",
                f"SELECT COUNT(*) FROM {table} GROUP BY {col1} HAVING COUNT(*) > {FuzzHelper.get_int(1, 10)}",
                f"INSERT INTO {table} ({col1}, {col2}) VALUES ('{val1}', {num1})",
                f"UPDATE {table} SET {col1} = '{val1}' WHERE {col2} < {num1}",
                f"DELETE FROM {table} WHERE {col1} = '{val1}'",
                f"CREATE TABLE {table} ({col1} VARCHAR(255), {col2} INT)",
                f"DROP TABLE {table}",
                f"CREATE INDEX idx_{col1} ON {table} ({col1} ASC)",
                f"DROP INDEX idx_{col1} ON {table}",
                f"SELECT t1.{col1}, t2.{col2} FROM {table} t1 INNER JOIN {FuzzHelper.get_string(5, 15, VALID_CHARS)} t2 ON t1.id = t2.id"
            ]
            return random.choice(queries)

        def _generate_mongo_query() -> str:
            """Helper to generate a variety of valid MongoDB query JSON strings."""
            collection = FuzzHelper.get_string(5, 15, VALID_CHARS)
            field1 = FuzzHelper.get_string(5, 15, VALID_CHARS)
            field2 = FuzzHelper.get_string(5, 15, VALID_CHARS)
            val1 = FuzzHelper.get_string(5, 10)
            num1 = FuzzHelper.get_int(1, 1000)

            queries = [
                {"collection": collection, "find": {field1: {"$gt": num1}}},
                {"collection": collection, "find": {field1: val1, field2: {"$ne": None}}, "projection": {field1: 1}},
                {"collection": collection, "find": {"$or": [{field1: {"$lt": num1}}, {field2: "active"}]}, "sort": [[field1, -1]], "limit": 10},
                {"collection": collection, "operation": "insertOne", "document": {field1: val1, field2: num1}},
                {"collection": collection, "operation": "insertMany", "documents": [{field1: val1}, {field1: FuzzHelper.get_string(5,10)}]},
                {"collection": collection, "operation": "updateMany", "filter": {field1: val1}, "update": {"$set": {field2: num1 + 1}}},
                {"collection": collection, "operation": "deleteMany", "filter": {field2: {"$lt": num1}}},
            ]
            return json.dumps(random.choice(queries))

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    is_edge_case = (i == 0) # Ensure at least one edge case per category
                    cmd = ""
                    mount_files = {}
                    
                    use_file_input = category in [CmdCategory.SQL2MONGO_FILE, CmdCategory.MONGO2SQL_FILE]
                    file_name = f"fuzz_input_{i}.txt" if use_file_input else ""

                    if category in [CmdCategory.SQL2MONGO_QUERY, CmdCategory.SQL2MONGO_FILE]:
                        content = _generate_sql_query() if not is_edge_case else FuzzHelper.get_evil_string()

                        if use_file_input:
                            mount_files[file_name] = content
                            cmd = f"sql-mongo-converter sql2mongo --file /test_data/{file_name}"
                        else:
                            # Use double quotes for SQL query, escaping any internal double quotes.
                            escaped_content = content.replace('"', '\\"')
                            cmd = f'sql-mongo-converter sql2mongo --query "{escaped_content}"'

                    elif category in [CmdCategory.MONGO2SQL_QUERY, CmdCategory.MONGO2SQL_FILE]:
                        content = _generate_mongo_query() if not is_edge_case else FuzzHelper.get_evil_string()

                        if use_file_input:
                            mount_files[file_name] = content
                            cmd = f"sql-mongo-converter mongo2sql --file /test_data/{file_name}"
                        else:
                            # Use single quotes for JSON, escaping any internal single quotes.
                            # This is the most robust way to pass arbitrary strings (including JSON) via shell.
                            escaped_content = content.replace("'", "'\\''")
                            cmd = f"sql-mongo-converter mongo2sql --query '{escaped_content}'"
                    
                    cases.append(TestCase(
                        command=cmd,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception:
                    # Skip generating this test case if any error occurs
                    continue
        return cases

# =====================================================================
# 4. Main Entry Point
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = SQLMongoConverterAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))