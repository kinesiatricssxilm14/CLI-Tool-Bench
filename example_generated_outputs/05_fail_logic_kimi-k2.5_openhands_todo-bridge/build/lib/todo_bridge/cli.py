"""Main CLI entry point for todo-bridge."""
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .models import DataBuilder, build_empty_data
from .parsers.csv_parser import parse_csv
from .parsers.md_parser import parse_md
from .parsers.txt_parser import parse_txt


def _detect_format(filepath: str) -> str:
    """Detect input format from file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        return "csv"
    if ext == ".md":
        return "md"
    if ext == ".txt":
        return "txt"
    return "unknown"


def _json_dumps(data: Dict[str, Any], indent: int) -> str:
    """Serialize data to JSON with the given indent level.

    indent == 0 → compact with newlines (no spaces)
    indent > 0  → standard indented
    """
    if indent == 0:
        return json.dumps(data, indent=0, ensure_ascii=False)
    return json.dumps(data, indent=indent, ensure_ascii=False)


def _build_from_csv(filepath: str, builder: DataBuilder) -> int:
    """Parse CSV file and populate builder. Returns count of new tasks added."""
    tasks = parse_csv(filepath)
    new_count = 0
    for spec in tasks:
        parent_id = builder.add_task(
            title=spec["title"],
            is_done=spec["is_done"],
            notes=spec["notes"],
            project_name=spec["project_name"],
            tag_names=spec["tag_names"],
            time_estimate=spec["time_estimate"],
            due_day=spec["due_day"],
        )
        new_count += 1
        for subtask_title in spec["subtask_titles"]:
            sub_id = builder.add_task(
                title=subtask_title,
                parent_id=parent_id,
            )
            builder.add_subtask_to_parent(parent_id, sub_id)
            new_count += 1
    return new_count


def _build_from_md(filepath: str, builder: DataBuilder) -> int:
    """Parse MD file and populate builder. Returns count of new tasks added."""
    top_tasks = parse_md(filepath)
    new_count = 0

    def add_task_recursive(task_spec: Dict, parent_id: Optional[str] = None) -> str:
        nonlocal new_count
        task_id = builder.add_task(
            title=task_spec["title"],
            is_done=task_spec["is_done"],
            project_name=task_spec["project_name"] if parent_id is None else None,
            tag_names=task_spec["tag_names"],
            time_estimate=task_spec["time_estimate"],
            parent_id=parent_id,
        )
        new_count += 1
        for sub_spec in task_spec.get("subtasks", []):
            sub_id = add_task_recursive(sub_spec, parent_id=task_id)
            builder.add_subtask_to_parent(task_id, sub_id)
        return task_id

    for task_spec in top_tasks:
        add_task_recursive(task_spec)
    return new_count


def _build_from_txt(filepath: str, builder: DataBuilder) -> int:
    """Parse TXT file and populate builder. Returns count of new tasks added."""
    tasks = parse_txt(filepath)
    new_count = 0
    for spec in tasks:
        builder.add_task(
            title=spec["title"],
            is_done=spec["is_done"],
            project_name=spec["project_name"],
            tag_names=spec["tag_names"],
            time_estimate=spec["time_estimate"],
            due_day=spec["due_day"],
        )
        new_count += 1
    return new_count


def _load_backup(backup_path: str) -> Dict[str, Any]:
    """Load existing JSON backup file."""
    with open(backup_path, encoding="utf-8") as f:
        return json.load(f)


def _format_conversion_summary_brief(task_count: int, project_count: int, tag_count: int) -> str:
    """Short summary (no output file): Tasks, Projects, Tags only."""
    return (
        f"\nConversion Summary:\n"
        f"  Tasks: {task_count}\n"
        f"  Projects: {project_count}\n"
        f"  Tags: {tag_count}\n"
    )


def _format_conversion_summary_detailed(
    input_path: str,
    output_path: str,
    task_count: int,
    project_count: int,
    tag_count: int,
    completed: int,
    incomplete: int,
    projects_summary: List[Dict],
    tags_summary: List[Dict],
) -> str:
    """Detailed summary (with output file)."""
    lines = [
        f"Successfully converted {input_path} to {output_path}",
        "",
        "Conversion Summary:",
        f"  Tasks: {task_count}",
        f"  Projects: {project_count}",
        f"  Tags: {tag_count}",
        f"  Completed tasks: {completed}",
        f"  Incomplete tasks: {incomplete}",
        "",
        "Projects created:",
    ]
    for p in projects_summary:
        lines.append(f"  - {p['title']} ({p['task_count']} tasks)")
    lines.append("")
    lines.append("Tags created:")
    for t in tags_summary:
        lines.append(f"  - {t['title']} ({t['task_count']} tasks)")
    lines.append("")
    return "\n".join(lines)


def _format_merge_summary(
    input_path: str,
    backup_path: str,
    output_path: str,
    new_tasks: int,
    total_tasks: int,
    total_projects: int,
    total_tags: int,
) -> str:
    return (
        f"Successfully merged {input_path} with {backup_path} and saved to {output_path}\n"
        f"\nMerge Summary:\n"
        f"  New tasks added: {new_tasks}\n"
        f"  Total tasks: {total_tasks}\n"
        f"  Total projects: {total_projects}\n"
        f"  Total tags: {total_tags}\n"
    )


def _run_convert(
    input_path: str,
    output_path: Optional[str],
    indent: int,
    fmt: str,
) -> int:
    """Handle conversion (no merge). Returns exit code."""
    builder = DataBuilder()

    if fmt == "csv":
        _build_from_csv(input_path, builder)
    elif fmt == "md":
        _build_from_md(input_path, builder)
    elif fmt == "txt":
        _build_from_txt(input_path, builder)
    else:
        print(f"Error: Unsupported file format for '{input_path}'", file=sys.stderr)
        return 1

    json_str = _json_dumps(builder.data, indent)

    if output_path is None:
        # Print to stdout
        task_count = builder.get_task_count()
        project_count = builder.get_project_count()
        tag_count = builder.get_tag_count()
        summary = _format_conversion_summary_brief(task_count, project_count, tag_count)

        if fmt == "txt":
            # For txt: JSON first, then summary
            sys.stdout.write(json_str + "\n")
            sys.stdout.write(summary)
        else:
            # For csv/md: summary first, then JSON
            sys.stdout.write(summary)
            sys.stdout.write(json_str + "\n")
    else:
        # Write JSON to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        task_count = builder.get_task_count()
        project_count = builder.get_project_count()
        tag_count = builder.get_tag_count()
        completed = builder.get_completed_count()
        incomplete = builder.get_incomplete_count()
        projects_summary = builder.get_projects_summary()
        tags_summary = builder.get_tags_summary()

        summary = _format_conversion_summary_detailed(
            input_path=input_path,
            output_path=output_path,
            task_count=task_count,
            project_count=project_count,
            tag_count=tag_count,
            completed=completed,
            incomplete=incomplete,
            projects_summary=projects_summary,
            tags_summary=tags_summary,
        )
        sys.stdout.write(summary)

    return 0


def _run_merge(
    input_path: str,
    backup_path: str,
    output_path: str,
    indent: int,
    fmt: str,
) -> int:
    """Handle merge operation. Returns exit code."""
    # Load existing backup
    try:
        base_data = _load_backup(backup_path)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading backup file '{backup_path}': {e}", file=sys.stderr)
        return 1

    # Ensure the base data has the required structure
    if "data" not in base_data:
        base_data = build_empty_data()
    else:
        # Ensure all required keys exist in base_data
        empty = build_empty_data()
        data = base_data["data"]
        for key in empty["data"]:
            if key not in data:
                data[key] = empty["data"][key]

    builder = DataBuilder(base_data=base_data)
    tasks_before = builder.get_task_count()

    if fmt == "csv":
        new_count = _build_from_csv(input_path, builder)
    elif fmt == "md":
        new_count = _build_from_md(input_path, builder)
    elif fmt == "txt":
        new_count = _build_from_txt(input_path, builder)
    else:
        print(f"Error: Unsupported file format for '{input_path}'", file=sys.stderr)
        return 1

    json_str = _json_dumps(builder.data, indent)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)

    total_tasks = builder.get_task_count()
    total_projects = builder.get_project_count()
    total_tags = builder.get_tag_count()
    new_tasks_added = total_tasks - tasks_before

    summary = _format_merge_summary(
        input_path=input_path,
        backup_path=backup_path,
        output_path=output_path,
        new_tasks=new_tasks_added,
        total_tasks=total_tasks,
        total_projects=total_projects,
        total_tags=total_tags,
    )
    sys.stdout.write(summary)

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="todo-bridge",
        description="Convert to-do lists (CSV, Markdown, Todo.txt) to structured JSON",
    )
    parser.add_argument("input_file", help="Path to the input file (.csv, .md, .txt)")
    parser.add_argument(
        "output_file",
        nargs="?",
        default=None,
        help="Path to the output JSON file (optional)",
    )
    parser.add_argument(
        "--merge",
        metavar="BACKUP_FILE",
        default=None,
        help="Path to an existing JSON backup to merge into",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        metavar="N",
        help="JSON indentation level (default: 2; use -1 for compact)",
    )

    args = parser.parse_args()

    input_path = args.input_file
    output_path = args.output_file
    backup_path = args.merge
    indent = args.indent if args.indent >= 0 else 0

    # Validate input file exists
    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: '{input_path}'", file=sys.stderr)
        sys.exit(1)

    # Detect format
    fmt = _detect_format(input_path)
    if fmt == "unknown":
        print(
            f"Error: Unsupported file extension for '{input_path}'. "
            "Expected .csv, .md, or .txt",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate merge requirements
    if backup_path is not None and output_path is None:
        print(
            "Error: --merge requires an output file argument.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        if backup_path is not None:
            exit_code = _run_merge(
                input_path=input_path,
                backup_path=backup_path,
                output_path=output_path,
                indent=indent,
                fmt=fmt,
            )
        else:
            exit_code = _run_convert(
                input_path=input_path,
                output_path=output_path,
                indent=indent,
                fmt=fmt,
            )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
