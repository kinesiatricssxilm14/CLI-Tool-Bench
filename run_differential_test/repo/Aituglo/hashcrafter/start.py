import os
import sys
import re
from enum import Enum
import random
import hashlib
import string

# Add parent directory to path to import framework modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine

CASES_PER_CATEGORY = 50

# =====================================================================
# 1. Command Type Enum (Values are generic command structures)
# =====================================================================
class CmdCategory(Enum):
    """
    Enum for different command-line argument combinations for hashcrafter.
    The value is the generic command structure template.
    """
    BASE = "hashcrafter -i <file> <hash>"
    WITH_TYPE = "hashcrafter -i <file> -t <type> <hash>"
    WITH_SEPARATORS = "hashcrafter -i <file> -s <seps> <hash>"
    ALL_FLAGS = "hashcrafter -i <file> -t <type> -s <seps> -v <hash>"

# =====================================================================
# 2. Repository Adapter Implementation
# =====================================================================
class HashCrafterAdapter(BaseRepoAdapter):
    
    SUPPORTED_HASH_TYPES = [
        "md5", "sha1", "sha224", "sha256", "sha384", "sha512",
        "sha3-224", "sha3-256", "sha3-384", "sha3-512",
        "blake2b-256", "blake2b-384", "blake2b-512"
    ]
    
    HASH_LENGTHS = {
        "md5": 32, "sha1": 40, "sha224": 56, "sha3-224": 56,
        "sha256": 64, "sha3-256": 64, "blake2b-256": 64,
        "sha384": 96, "blake2b-384": 96,
        "sha512": 128, "sha3-512": 128, "blake2b-512": 128
    }

    @property
    def base_image(self) -> str:
        """Return the Docker base image for the Go environment."""
        return "golang:latest"

    def install_oracle(self, container) -> None:
        cmd = "mkdir -p /repo && cd /repo && git clone https://github.com/Aituglo/hashcrafter.git && cd hashcrafter && go install ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def install_agent(self, container, local_agent_path: str) -> None:
        container.exec_run("mkdir -p /repo")
        # The rule explicitly requires this os.system call.
        if os.system(f"docker cp {local_agent_path} {container.id}:/repo") != 0:
            raise Exception("Failed to copy agent code to container")
        cmd = "cd /repo/repo_to_be_tested && go install -buildvcs=false ."
        if container.exec_run(f"sh -c '{cmd}'").exit_code != 0:
            raise Exception("Agent Installation Failed")

    def _get_hash(self, text: str, hash_type: str) -> str:
        """Helper to generate a hash for a given string and algorithm."""
        data = text.encode('utf-8')
        hash_type = hash_type.lower()
        try:
            if hash_type.startswith("blake2b"):
                size_map = {"blake2b-256": 32, "blake2b-384": 48, "blake2b-512": 64}
                digest_size = size_map.get(hash_type)
                if digest_size is None:
                    raise ValueError(f"Unsupported blake2b size for {hash_type}")
                return hashlib.blake2b(data, digest_size=digest_size).hexdigest()
            
            if hash_type == "sha3-224": return hashlib.sha3_224(data).hexdigest()
            if hash_type == "sha3-256": return hashlib.sha3_256(data).hexdigest()
            if hash_type == "sha3-384": return hashlib.sha3_384(data).hexdigest()
            if hash_type == "sha3-512": return hashlib.sha3_512(data).hexdigest()

            hasher = hashlib.new(hash_type)
            hasher.update(data)
            return hasher.hexdigest()
        except ValueError:
            # This path should not be hit with valid hash types, but is a safeguard.
            raise ValueError(f"Unsupported hash type for test generation: {hash_type}")

    # =====================================================================
    # 3. Standardized Test Case Generator
    # =====================================================================
    def generate_test_cases(self) -> list[TestCase]:
        cases = []

        for category in CmdCategory:
            for i in range(CASES_PER_CATEGORY):
                try:
                    # Determine the effective hash type for this test case
                    if category in [CmdCategory.WITH_TYPE, CmdCategory.ALL_FLAGS]:
                        effective_hash_type = random.choice(self.SUPPORTED_HASH_TYPES)
                    else:
                        effective_hash_type = "sha256" # Tool's default

                    file_name = f"input_{category.name.lower()}_{i}.txt"
                    target_hash = ""
                    input_content = ""
                    separators_arg = ""
                    type_arg = effective_hash_type
                    
                    # Define test case properties based on index `i`
                    # i=0: simple solvable case
                    # i=1: simple unsolvable case
                    # i=2: edge case with evil file content
                    # i=3: edge case with evil arguments
                    # i=4: random solvable/unsolvable case
                    
                    if i == 0: # Simple, solvable case
                        words = [FuzzHelper.get_string(3, 6) for _ in range(random.randint(2, 3))]
                        separator = random.choice(["_", "-", ""])
                        plaintext_words = list(words)
                        random.shuffle(plaintext_words)
                        plaintext = separator.join(plaintext_words)
                        input_content = "\n".join(words)
                        target_hash = self._get_hash(plaintext, effective_hash_type)
                        # Ensure the correct separator is in the list
                        seps_list = {separator, "_", ".", "-"}
                        separators_arg = ",".join(seps_list)

                    elif i == 1: # Simple, unsolvable case
                        input_content = "\n".join([FuzzHelper.get_string(3, 8) for _ in range(3)])
                        hash_len = self.HASH_LENGTHS.get(effective_hash_type, 64)
                        target_hash = FuzzHelper.get_string(hash_len, hash_len, string.hexdigits.lower())
                        separators_arg = "_,-,."

                    elif i == 2: # Edge case: Evil file content
                        input_content = FuzzHelper.get_evil_string()
                        hash_len = self.HASH_LENGTHS.get(effective_hash_type, 64)
                        target_hash = FuzzHelper.get_string(hash_len, hash_len, string.hexdigits.lower())
                        separators_arg = "_,-,."

                    elif i == 3: # Edge case: Evil arguments
                        input_content = "\n".join([FuzzHelper.get_string(3, 8) for _ in range(3)])
                        hash_len = self.HASH_LENGTHS.get(effective_hash_type, 64)
                        target_hash = FuzzHelper.get_string(hash_len, hash_len, string.hexdigits.lower())
                        
                        evil_choice = random.choice(['type', 'sep', 'hash_val'])
                        if evil_choice == 'type':
                            type_arg = FuzzHelper.get_evil_string()
                        elif evil_choice == 'sep':
                            separators_arg = FuzzHelper.get_evil_string()
                        else: # 'hash_val'
                            target_hash = FuzzHelper.get_evil_string()
                    
                    else: # Random case (can be solvable or not)
                        if random.choice([True, False]): # Solvable
                            words = [FuzzHelper.get_string(3, 6) for _ in range(2)]
                            separator = random.choice(["_", "-", "."])
                            # The tool checks all permutations, so we can just join them in order
                            plaintext = separator.join(words)
                            input_content = "\n".join(words)
                            target_hash = self._get_hash(plaintext, effective_hash_type)
                            separators_arg = separator
                        else: # Unsolvable
                            input_content = "\n".join([FuzzHelper.get_string(3, 8) for _ in range(3)])
                            hash_len = self.HASH_LENGTHS.get(effective_hash_type, 64)
                            target_hash = FuzzHelper.get_string(hash_len, hash_len, string.hexdigits.lower())
                            separators_arg = "_,-,."

                    mount_files = {file_name: input_content}

                    # --- Assemble command based on category ---
                    # The examples show `[flags] [hash]`, which is more common.
                    # We will follow the example format.
                    args = [f"--input /test_data/{file_name}"]

                    if category in [CmdCategory.WITH_TYPE, CmdCategory.ALL_FLAGS]:
                        # Quoting is necessary to handle evil strings with spaces or special chars
                        args.append(f'--type "{type_arg}"')

                    if category in [CmdCategory.WITH_SEPARATORS, CmdCategory.ALL_FLAGS]:
                        # Quoting is crucial as separators can contain spaces/commas
                        args.append(f'--separators "{separators_arg}"')

                    if category == CmdCategory.ALL_FLAGS:
                        args.append("--verbose")
            
                    # Follow the example format: `hashcrafter [flags] [target_hash]`
                    command = f'hashcrafter {" ".join(args)} "{target_hash}"'

                    cases.append(TestCase(
                        command=command,
                        category=category.value,
                        mount_files=mount_files
                    ))
                except Exception as e:
                    print(f"      ⚠️  Skipping test case generation for category {category.name} due to error: {e}")
                    continue
        return cases

# =====================================================================
# 4. Main Entry
# =====================================================================
if __name__ == "__main__":
    local_repo_path = os.path.join(os.path.dirname(__file__), "repo_to_be_tested")
    adapter = HashCrafterAdapter()
    engine = DiffTestEngine(adapter=adapter, agent_local_path=local_repo_path)
    engine.run(output_json_path=os.path.join(os.path.dirname(__file__), "output.json"))