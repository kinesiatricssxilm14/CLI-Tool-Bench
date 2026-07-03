"""Todo.txt parser for todo-bridge."""
import re
from typing import Any, Dict, List, Optional

from ..utils import is_date, parse_time_txt


def _parse_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single todo.txt line.

    Format: [x] [completion_date] [creation_date] title [+project] [@context] [key:value]
    OR:     [(A)] [creation_date] title [+project] [@context] [key:value]

    Note: If a priority marker (A)-(Z) is the first token, the 'x' completion
    marker is NOT subsequently processed. This matches the expected behavior
    where '(D) x ...' results in the task title starting with 'x'.
    """
    line = line.strip()
    if not line:
        return None

    tokens = line.split()
    if not tokens:
        return None

    i = 0
    is_done = False
    priority: Optional[str] = None
    completion_date: Optional[str] = None
    creation_date: Optional[str] = None

    # Check first token: completion marker 'x' OR priority '(A)'
    if tokens[i] == "x":
        is_done = True
        i += 1
        # Check for completion date
        if i < len(tokens) and is_date(tokens[i]):
            completion_date = tokens[i]
            i += 1
            # Check for creation date
            if i < len(tokens) and is_date(tokens[i]):
                creation_date = tokens[i]
                i += 1
    elif re.match(r'^\([A-Z]\)$', tokens[i]):
        priority = tokens[i][1]  # Extract single letter
        i += 1
        # After priority, optionally a creation date
        if i < len(tokens) and is_date(tokens[i]):
            creation_date = tokens[i]
            i += 1
    else:
        # May start with a creation date
        if is_date(tokens[i]):
            creation_date = tokens[i]
            i += 1

    # Process remaining tokens for title, projects, contexts, metadata
    title_parts = []
    projects = []
    contexts = []
    metadata: Dict[str, str] = {}

    for token in tokens[i:]:
        if token.startswith("+") and len(token) > 1:
            projects.append(token[1:])
        elif token.startswith("@") and len(token) > 1:
            contexts.append(token[1:])
        elif ":" in token and not token.startswith(":") and not token.endswith(":"):
            key, _, value = token.partition(":")
            if key and value:
                metadata[key] = value
        else:
            title_parts.append(token)

    title = " ".join(title_parts).strip()
    if not title:
        return None

    # Parse time estimate from 't' metadata key
    time_estimate = 0
    if "t" in metadata:
        time_estimate = parse_time_txt(metadata["t"])

    # Parse due date
    due_day = metadata.get("due") or None

    # Build tag names: contexts + priority tag
    tag_names = list(contexts)
    if priority:
        tag_names.append(f"Priority {priority}")

    return {
        "title": title,
        "is_done": is_done,
        "project_name": projects[0] if projects else None,
        "extra_projects": projects[1:],
        "tag_names": tag_names,
        "time_estimate": time_estimate,
        "due_day": due_day,
        "creation_date": creation_date,
        "completion_date": completion_date,
    }


def parse_txt(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a todo.txt file and return a list of task spec dicts.

    Each returned dict has:
      title, is_done, project_name, tag_names, time_estimate, due_day
    """
    tasks = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            parsed = _parse_line(line)
            if parsed:
                tasks.append(parsed)
    return tasks
