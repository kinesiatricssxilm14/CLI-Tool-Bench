import re
import uuid
import time


def gen_id() -> str:
    """Generate a 21-character hex ID."""
    return uuid.uuid4().hex[:21]


def now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.time() * 1000)


def parse_time_csv(s: str) -> int:
    """Parse CSV time string like '2h 27m' or '1h 23m' into milliseconds."""
    if not s or not s.strip():
        return 0
    s = s.strip()
    total_minutes = 0
    hour_match = re.search(r'(\d+)\s*h', s)
    min_match = re.search(r'(\d+)\s*m', s)
    if hour_match:
        total_minutes += int(hour_match.group(1)) * 60
    if min_match:
        total_minutes += int(min_match.group(1))
    return total_minutes * 60 * 1000


def parse_time_md(s: str) -> int:
    """Parse Markdown time string like '(1h)' or '(30m)' or '(1h 30m)' into ms."""
    if not s or not s.strip():
        return 0
    s = s.strip().strip('()')
    total_minutes = 0
    hour_match = re.search(r'(\d+)\s*h', s)
    min_match = re.search(r'(\d+)\s*m', s)
    if hour_match:
        total_minutes += int(hour_match.group(1)) * 60
    if min_match:
        total_minutes += int(min_match.group(1))
    return total_minutes * 60 * 1000


def parse_time_txt(s: str) -> int:
    """Parse Todo.txt time string like '41m' or '2h' or '1h30m' into ms."""
    if not s or not s.strip():
        return 0
    s = s.strip()
    total_minutes = 0
    hour_match = re.search(r'(\d+)\s*h', s)
    min_match = re.search(r'(\d+)\s*m', s)
    if hour_match:
        total_minutes += int(hour_match.group(1)) * 60
    if min_match:
        total_minutes += int(min_match.group(1))
    return total_minutes * 60 * 1000


def is_date(s: str) -> bool:
    """Check if string looks like a date YYYY-MM-DD."""
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', s))
