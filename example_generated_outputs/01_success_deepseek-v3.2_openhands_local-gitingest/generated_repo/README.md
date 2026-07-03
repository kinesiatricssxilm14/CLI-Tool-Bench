# local-gitingest

A CLI tool written in Go that converts a local Git repository into a single text file. It generates a hierarchical representation of the project's directory structure and includes the content of text-based source files.

## Features

- Scans Git repositories and respects `.gitignore` patterns
- Generates a tree-like directory structure in the output
- Includes file contents with clear separators
- Supports various exclusion filters:
  - Default exclusions (`.git`, `node_modules`, `.DS_Store`)
  - `.gitignore` pattern matching
  - Custom file extension exclusions
  - Custom directory exclusions
- Allows specifying a target subdirectory
- Configurable file size limits with truncation
- Verbose mode to show excluded files
- Custom output filename support

## Installation

```bash
go install .
```

This will install `local-gitingest` to your `$GOPATH/bin`.

## Usage

### Basic usage
```bash
# In a git repository directory
local-gitingest
```
Generates `output.txt` with the repository structure and file contents.

### Specify target subdirectory
```bash
# Process only the 'src' directory
local-gitingest src
# or using -d flag
local-gitingest -d src
```

### Custom output file
```bash
local-gitingest -o my_output.txt
```

### Exclude file extensions
```bash
# Exclude .log and .tmp files
local-gitingest -exclude .log,.tmp
```

### Exclude directories
```bash
# Exclude tests and node_modules directories
local-gitingest -exclude-dir tests,node_modules
```

### File size limiting
```bash
# Enable size limit with 100 byte max
local-gitingest -size-limit -max-size=100
```

### Verbose mode
```bash
# Show which files are being excluded
local-gitingest -v
```

### Combined flags
```bash
# Process only src directory, exclude .go files, with verbose output
local-gitingest -d src -exclude .go -v
```

## Output Format

The output file contains:

1. A tree-like representation of the directory structure
2. A separator line (`================================================`)
3. File contents with headers:
   ```
   ================================================
   File: path/to/file.txt
   ================================================
   [file content]
   ```

Files larger than the size limit (default 1000 bytes) are truncated with `...[TRUNCATED]` indicator.

## Implementation Details

- Written in Go using only standard library packages
- No external dependencies
- Proper handling of `.gitignore` patterns
- Recursive directory traversal with configurable exclusions
- Efficient file reading with size-based truncation

## License

This project is created as a demonstration of Go CLI tool development.