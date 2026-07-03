# mp4analyzer

A CLI tool for analyzing MP4 files. It can parse and display the box structure of an MP4 file, show a concise summary, and output the analysis in a structured JSON format.

## Installation

```bash
pip install .
```

## Usage

### Basic Analysis
```bash
mp4analyzer <file>
```

### Detailed Analysis
```bash
mp4analyzer -d <file>
```

### Summary View
```bash
mp4analyzer -s <file>
```

### JSON Output
```bash
mp4analyzer -o json <file>
```

### Save JSON to Path
```bash
mp4analyzer -j <path> <file>
```

### Options
- `-d`, `--detailed`: Show detailed properties for each box
- `-s`, `--summary`: Show concise summary
- `-e`, `--expand`: Expand arrays and large data structures
- `-o FORMAT`: Output format (json)
- `-j PATH`: Save JSON output to specified path
- `--no-color`: Disable colored output
