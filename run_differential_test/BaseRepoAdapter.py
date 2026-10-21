import random
import string
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict


class FuzzHelper:
    """ Fuzzing data generator"""

    @staticmethod
    def get_string(min_len=5, max_len=20, chars=string.ascii_letters + string.digits):
        return ''.join(random.choice(chars) for _ in range(random.randint(min_len, max_len)))

    @staticmethod
    def get_int(min_val=-1000, max_val=10000):
        return random.randint(min_val, max_val)

    @staticmethod
    def get_float(min_val=-100.0, max_val=100.0, decimals=2):
        return round(random.uniform(min_val, max_val), decimals)

    @staticmethod
    def get_boolean_str():
        return random.choice(["true", "false", "1", "0", "True", "False"])

    @staticmethod
    def get_domain():
        parts = [FuzzHelper.get_string(3, 8, string.ascii_lowercase) for _ in range(random.randint(2, 4))]
        return ".".join(parts) + random.choice([".com", ".net", ".org", ".io"])

    @staticmethod
    def get_ip(v6=False):
        if v6:
            return ":".join(f"{random.randint(0, 65535):x}" for _ in range(8))
        return ".".join(str(random.randint(0, 255)) for _ in range(4))

    @staticmethod
    def get_url():
        scheme = random.choice(["http", "https", "ftp"])
        return f"{scheme}://{FuzzHelper.get_domain()}/{FuzzHelper.get_string(5, 10)}"

    @staticmethod
    def get_email():
        return f"{FuzzHelper.get_string(5, 10, string.ascii_lowercase)}@{FuzzHelper.get_domain()}"

    @staticmethod
    def get_filepath(ext=".txt", absolute=True):
        path = "/" if absolute else ""
        dirs = [FuzzHelper.get_string(4, 8, string.ascii_lowercase) for _ in range(random.randint(1, 3))]
        filename = FuzzHelper.get_string(5, 10) + ext
        return path + "/".join(dirs) + "/" + filename

    @staticmethod
    def get_json_string(num_keys=5):
        data = {FuzzHelper.get_string(5, 10): FuzzHelper.get_string(10, 20) for _ in range(num_keys)}
        data["id"] = FuzzHelper.get_int(1, 1000)
        data["active"] = random.choice([True, False])
        return json.dumps(data)

    @staticmethod
    def get_csv_string(rows=10, cols=3):
        lines = [",".join(FuzzHelper.get_string(4, 8) for _ in range(cols))]
        for _ in range(rows):
            lines.append(",".join(FuzzHelper.get_string(5, 15) for _ in range(cols)))
        return "\n".join(lines)

    @staticmethod
    def get_subdomains_content(min_lines=10, max_lines=100):
        return "\n".join(FuzzHelper.get_domain() for _ in range(random.randint(min_lines, max_lines)))

    @staticmethod
    def get_evil_string():
        evil_chars = [
            "", " ", "\n", "\r\n", "\t", "\x00",
            "../../etc/passwd",
            "'; DROP TABLE users; --", "`reboot`",
            "A" * 100,
            "中文测试🚀",
            "-1", "9999999999999999999999999999"
        ]
        return random.choice(evil_chars)


@dataclass
class TestCase:
    command: str
    category: str = "UNKNOWN"
    prep_script: str = ""
    mount_files: Dict[str, str] = field(default_factory=dict)
    env_vars: Dict[str, str] = field(default_factory=dict)


class BaseRepoAdapter(ABC):
    @property
    @abstractmethod
    def base_image(self) -> str:
        pass

    @property
    def repo_root_dir(self) -> str:
        return "/repo"

    @property
    def work_repo_dir_name(self) -> str:
        return "repo_to_be_tested"

    @property
    def work_repo_dir(self) -> str:
        return f"{self.repo_root_dir.rstrip('/')}/{self.work_repo_dir_name}"

    @property
    def snapshot_root_dir(self) -> str:
        return "/baseline_snapshots"

    @property
    def snapshot_repo_dir(self) -> str:
        return f"{self.snapshot_root_dir.rstrip('/')}/{self.work_repo_dir_name}"

    @property
    def test_data_dir(self) -> str:
        return "/test_data"

    @property
    def workspace_diff_ignore_dir_names(self) -> List[str]:
        return [
            ".git",
            ".hg",
            ".svn",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".nox",
            ".venv",
            "venv",
            "env",
            "node_modules",
            "dist",
            "build",
            "target",
            "coverage",
            ".coverage",
            ".next",
            ".nuxt",
            ".parcel-cache",
        ]

    @property
    def ignore_patterns(self) -> List[str]:
        """
        兼容保留。当前 DiffTestEngine 不依赖全容器 diff。
        """
        return [
            r"^/tmp(/|$)",
            r"^/var/tmp(/|$)",
            r"^/usr/tmp(/|$)",
            r"^/var/log(/|$)",
            r"^/var/run(/|$)",
            r"^/run(/|$)",
            r"^/var/spool(/|$)",
            r"^/var/backups(/|$)",
            r"^/var/lib/apt(/|$)",
            r"^/var/lib/dpkg(/|$)",
            r"^/var/cache(/|$)",
            r"^/etc/ld\.so\.cache$",
            r"^/proc(/|$)",
            r"^/sys(/|$)",
            r"^/dev(/|$)",
            r"^/usr/local/lib(/|$)",
            r".*/__pycache__(/|$)",
            r".*\.py[cod]$",
            r"^/go(/|$)",
            r"^/root/\.cache/go-build(/|$)",
            r"^/root/\.npm(/|$)",
            r"^/root/\.yarn(/|$)",
            r"^/root/\.cargo(/|$)",
            r"^/root/\.rustup(/|$)",
            r"^/root/\.cache(/|$)",
            r"^/root/\.config(/|$)",
            r"^/root/\.local(/|$)",
            r"^/root/\.wget-hsts$",
            r"^/root/\.bash_history$",
            r"/\.[^/]+"
        ]

    def sanitize_stdout(self, raw_stdout: str) -> str:
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', raw_stdout)

    @abstractmethod
    def install_oracle(self, container) -> None:
        pass

    @abstractmethod
    def install_agent(self, container, local_agent_path: str) -> None:
        pass

    @abstractmethod
    def generate_test_cases(self) -> List[TestCase]:
        pass
