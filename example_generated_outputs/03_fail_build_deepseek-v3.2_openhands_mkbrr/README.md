# mkbrr

A command-line tool for creating, inspecting, verifying, and modifying torrent files.

## Installation

```bash
go install .
```

Or using the Makefile:

```bash
make install
```

## Usage

### Create a torrent

```bash
mkbrr create <path> -t <tracker_url> [options]
```

Options:
- `-t, --tracker <url>`: Tracker announce URL (required)
- `-o, --output <path>`: Output torrent file path
- `--no-date`: Don't write creation date
- `--no-creator`: Don't write creator/tool name
- `--skip-prefix`: Don't add tracker domain prefix to filename
- `--private=<bool>`: Set private flag (default: true)
- `-c, --comment <string>`: Add comment to torrent
- `-s, --source <string>`: Add source tag to info dictionary
- `-e, --entropy`: Add random entropy field to info dictionary
- `--workers <N>`: Number of hashing workers (default: CPU count)
- `--exclude <patterns>`: Exclude files matching glob patterns (comma-separated)
- `--include <patterns>`: Include only files matching glob patterns (comma-separated)

### Inspect a torrent

```bash
mkbrr inspect <torrent_file> [options]
```

Options:
- `-v, --verbose`: Show all metadata fields

### Check content against torrent

```bash
mkbrr check <torrent_file> <content_path> [options]
```

Options:
- `--workers <N>`: Number of verification workers (default: CPU count)

### Modify a torrent

```bash
mkbrr modify <torrent_file> [options]
```

Options:
- `-t, --tracker <url>`: Set tracker URL (can be specified multiple times)
- `-c, --comment <string>`: Set or remove comment (empty string removes)
- `6-s, --source <string>`: Set or remove source tag (empty string removes)
- `-e, --entropy`: Add or replace entropy field
- `--private=<bool>`: Set private flag
- `--output-dir <path>`: Directory for modified torrent
- `-o, --output <name>`: Base name for modified torrent
- `--no-date`: Don't write creation date
- `--no-creator`: Don't write creator/tool name
- `--skip-prefix`: Don't add tracker domain prefix to filename
- `-n, --dry-run`: Show what would be modified without writing

## Examples

Create a torrent from a file:
```bash
mkbrr create /path/to/file.dat -t http://tracker.example.com/announce -o myfile.torrent
```

Create a torrent with comment and source:
```bash
mkbrr create /path/to/dir -t http://tracker.example.com/announce -c "My release" -s "MKBRR"
```

Inspect a torrent:
```bash
mkbrr inspect file.torrent
mkbrr inspect file.torrent -v
```

Check if files match a torrent:
```bash
mkbrr check file.torrent /path/to/content
```

Modify a torrent's tracker:
```bash
mkbrr modify old.torrent -t http://new.tracker.com/announce -o new.torrent
```

## Development

Build the project:
```bash
make build
```

Run tests:
```bash
make test
```

Format code:
```bash
make fmt
```

## License

[MIT](LICENSE)