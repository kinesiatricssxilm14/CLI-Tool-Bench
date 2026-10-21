#!/usr/bin/env python3
"""Strip credentials and internal host paths out of agent trajectory files.

mini-swe-agent dumps its whole runtime config into every ``*.traj.json``, which
includes the LLM ``api_key`` and the absolute host path of the Docker bind mount.
Run this over a results directory before packaging it for public release.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REDACTED = "<REDACTED>"

# Keys whose values are credentials and must never be published.
SECRET_FIELDS = {"api_key", "api_base_key", "auth_token", "access_token"}

# Absolute host paths leak internal infrastructure and usernames.
HOST_PATH_RE = re.compile(r"(/data00/home/[^/\s\"]+|/home/[^/\s\"]+|/Users/[^/\s\"]+)")


def scrub(obj):
    """Recursively redact secret fields; returns (obj, n_redactions)."""
    count = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in SECRET_FIELDS and isinstance(value, str) and value and value != REDACTED:
                obj[key] = REDACTED
                count += 1
            else:
                _, n = scrub(value)
                count += n
    elif isinstance(obj, list):
        for item in obj:
            _, n = scrub(item)
            count += n
    return obj, count


def scrub_host_paths(obj):
    """Recursively replace absolute host paths inside string values."""
    count = 0
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                new = HOST_PATH_RE.sub("<HOST_PATH>", value)
                if new != value:
                    obj[key] = new
                    count += 1
            else:
                _, n = scrub_host_paths(value)
                count += n
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str):
                new = HOST_PATH_RE.sub("<HOST_PATH>", item)
                if new != item:
                    obj[i] = new
                    count += 1
            else:
                _, n = scrub_host_paths(item)
                count += n
    return obj, count


def sanitize_file(path: Path, dry_run: bool) -> tuple[int, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  skip (unparsable): {path} — {exc}", file=sys.stderr)
        return 0, 0

    data, secrets = scrub(data)
    data, paths = scrub_host_paths(data)

    if (secrets or paths) and not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return secrets, paths


def sanitize_text(path: Path, dry_run: bool) -> int:
    """Redact host paths in a plain-text log; returns the number of substitutions."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"  skip (unreadable): {path} — {exc}", file=sys.stderr)
        return 0

    new, count = HOST_PATH_RE.subn("<HOST_PATH>", text)
    if count and not dry_run:
        path.write_text(new, encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="results directory to sanitize in place")
    parser.add_argument("--pattern", default="*.traj.json", help="glob for trajectory files")
    parser.add_argument(
        "--text-pattern",
        action="append",
        default=["*.log"],
        help="glob for plain-text files that only need host-path redaction",
    )
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    if not args.root.is_dir():
        parser.error(f"{args.root} is not a directory")

    files = sorted(args.root.rglob(args.pattern))
    print(f"Scanning {len(files)} trajectory file(s) under {args.root}")

    total_secrets = total_paths = touched = 0
    for path in files:
        secrets, paths = sanitize_file(path, args.dry_run)
        if secrets or paths:
            touched += 1
            total_secrets += secrets
            total_paths += paths

    for pattern in args.text_pattern:
        for path in sorted(args.root.rglob(pattern)):
            count = sanitize_text(path, args.dry_run)
            if count:
                touched += 1
                total_paths += count

    verb = "would redact" if args.dry_run else "redacted"
    print(f"{verb} {total_secrets} credential(s) and {total_paths} host path(s) across {touched} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
