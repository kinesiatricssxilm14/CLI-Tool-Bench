# sec-scanner

A security scanner CLI tool for analyzing `.claude/settings.json` files.

## Installation

```bash
npm install && npm install -g .
```

## Usage

```bash
# Basic scan
sec-scanner <directory>

# Scan without low severity findings
sec-scanner <directory> --no-low
```

## Description

The tool recursively scans a given directory for specific JSON settings files (`.claude/settings.json` and `.claude/settings.local.json`). It analyzes an array of approved commands within these files (specifically under `permissions.allow`) and flags dangerous patterns that could pose a security risk. The tool categorizes findings by severity (HIGH, MEDIUM, LOW) and can filter out low-severity findings with the `--no-low` option.

## Examples

```bash
# Scan a project directory
sec-scanner /path/to/project

# Scan without low severity findings
sec-scanner /path/to/project --no-low
```

## Output Format

The tool outputs findings in a structured format:
- Summary line with counts of findings by severity
- `[FILE_REPORT]` marker
- Header lines
- Individual findings with severity, pattern name, and the original command

## Exit Codes

- `0`: Success
- `1`: Error (e.g., directory not found, parsing error)