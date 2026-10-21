"""Markdown parser for todo-bridge."""
import re
from typing import Any, Dict, List, Optional

from ..utils import parse_time_md


def _parse_task_line(text: str) -> Dict[str, Any]:
    """
    Parse the content part of a task list item.
    Returns dict with title, tag_names, time_estimate.
    """
    time_estimate = 0
    time_match = re.search(r'\((\d+h(?:\s*\d+m)?|\d+m)\)\s*$', text)
    if time_match:
        time_estimate = parse_time_md(time_match.group(0))
        text = text[:time_match.start()].strip()

    tags_found = re.findall(r'#(\S+)', text)
    title = re.sub(r'\s*#\S+', '', text).strip()

    return {
        "title": title,
        "tag_names": tags_found,
        "time_estimate": time_estimate,
    }


def parse_md(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a Markdown file and return a nested list of top-level task dicts.

    H1 headers (# Title) define projects. Task list items (- [ ] or - [x])
    are tasks. Indentation creates parent-child (subtask) relationships.
    """
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    current_project: Optional[str] = None
    # Stack entries: (indent, task_dict)
    indent_stack: List[tuple] = []
    # Result: top-level task dicts
    top_tasks: List[Dict[str, Any]] = []

    for line in lines:
        stripped = line.rstrip("\n")

        # H1 header → project
        header_match = re.match(r'^#\s+(.+)$', stripped)
        if header_match:
            current_project = header_match.group(1).strip()
            indent_stack = []
            continue

        # Task list item
        task_match = re.match(r'^(\s*)- \[([ x])\]\s+(.+)$', stripped)
        if task_match:
            indent = len(task_match.group(1))
            is_done = task_match.group(2) == "x"
            content = task_match.group(3)

            parsed = _parse_task_line(content)
            task = {
                "title": parsed["title"],
                "is_done": is_done,
                "project_name": current_project,
                "tag_names": parsed["tag_names"],
                "time_estimate": parsed["time_estimate"],
                "subtasks": [],
            }

            # Pop all stack entries with indent >= current
            while indent_stack and indent_stack[-1][0] >= indent:
                indent_stack.pop()

            if indent_stack:
                # This is a subtask of the current top of stack
                indent_stack[-1][1]["subtasks"].append(task)
            else:
                top_tasks.append(task)

            indent_stack.append((indent, task))

    return top_tasks
