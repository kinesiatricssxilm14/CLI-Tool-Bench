"""CSV parser for todo-bridge."""
import csv
from typing import Any, Dict, List

from ..utils import parse_time_csv


def _parse_bool(value: str) -> bool:
    """Parse isDone values: 'true', '1', 'false', '0'."""
    return value.strip().lower() in ("true", "1")


def parse_csv(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a CSV file and return a list of task spec dicts.

    Expected columns: title, notes, project, tags, isDone, timeEstimate, dueDay, subtasks

    Each returned dict has:
      title, notes, project_name, tag_names, is_done, time_estimate, due_day,
      subtask_titles (list of str)
    """
    tasks = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("title", "").strip()
            if not title:
                continue

            notes = row.get("notes", "").strip()
            project_name = row.get("project", "").strip() or None
            tags_raw = row.get("tags", "").strip()
            tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
            is_done = _parse_bool(row.get("isDone", "false"))
            time_str = row.get("timeEstimate", "").strip()
            time_estimate = parse_time_csv(time_str)
            due_day = row.get("dueDay", "").strip() or None

            subtasks_raw = row.get("subtasks", "").strip()
            subtask_titles = [s.strip() for s in subtasks_raw.split("|") if s.strip()] if subtasks_raw else []

            tasks.append({
                "title": title,
                "notes": notes,
                "project_name": project_name,
                "tag_names": tag_names,
                "is_done": is_done,
                "time_estimate": time_estimate,
                "due_day": due_day,
                "subtask_titles": subtask_titles,
            })
    return tasks
