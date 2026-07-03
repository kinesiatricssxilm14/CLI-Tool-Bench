package cli

import (
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"mkbrr/internal/torrent"
)

const (
	appName    = "mkbrr"
	appVersion = "1.0.0"
)

func Execute() error {
	if len(os.Args) < 2 {
		return printUsage()
	}

	command := os.Args[1]
	switch command {
	case "create":
		return runCreate(os.Args[2:])
	case "inspect":
		return runInspect(os.Args[2:])
	case "check":
		return runCheck(os.Args[2:])
	case "modify":
		return runModify(os.Args[2:])
	case "help", "-h", "--help":
		return printHelp()
	case "version", "-v", "--version":
		return printVersion()
	default:
		return fmt.Errorf("unknown command: %s\n\n%s", command, getUsage())
	}
}

func printUsage() error {
	fmt.Print(getUsage())
	return nil
}

func getUsage() string {
	return `mkbrr - Torrent creation and manipulation tool

Usage:
  mkbrr <command> [options]

Commands:
  create    Create a new torrent file
  inspect   Display torrent metadata
  check     Verify local content against torrent
  modify    Modify existing torrent metadata

Use "mkbrr help <command>" for more information about a command.
`
}

func printHelp() error {
	if len(os.Args) > 2 {
		command := os.Args[2]
		switch command {
		case "create":
			fmt.Print(getCreateHelp())
		case "inspect":
			fmt.Print(getInspectHelp())
		case "check":
			fmt.Print(getCheckHelp())
		case "modify":
			fmt.Print(getModifyHelp())
		default:
			fmt.Printf("Unknown command: %s\n", command)
		}
		return nil
	}
	return printUsage()
}

func printVersion() error {
	fmt.Printf("%s version %s\n", appName, appVersion)
	return nil
}

func getCreateHelp() string {
	return `Create a new torrent file

Usage:
  mkbrr create <path> -t <url> [options]

Options:
  -t, --tracker <url>        Tracker announce URL (required)
  -o, --output <path>        Output torrent file path
      --no-date              Don't write creation date
      --no-creator           Don't write creator/tool name
      --skip-prefix          Don't add tracker domain prefix to filename
      --private=<bool>       Set private flag (default: true)
  -c, --comment <string>     Add comment to torrent
  -s, --source <string>      Add source tag to info dictionary
  -e, --entropy              Add random entropy field to info dictionary
      --workers <N>          Number of hashing workers (default: CPU count)
      --exclude <patterns>   Exclude files matching glob patterns (comma-separated)
      --include <patterns>   Include only files matching glob patterns (comma-separated)

Examples:
  mkbrr create /path/to/file -t http://tracker.example.com/announce
  mkbrr create /path/to/dir -t http://tracker.example.com/announce -o my.torrent
`
}

func getInspectHelp() string {
	return `Display torrent metadata

Usage:
  mkbrr inspect <torrent_file> [options]

Options:
  -v, --verbose    Show all metadata fields

Examples:
  mkbrr inspect file.torrent
  mkbrr inspect file.torrent -v
`
}

func getCheckHelp() string {
	return `Verify local content against torrent

Usage:
  mkbrr check <torrent_file> <content_path> [options]

Options:
  --workers <N>    Number of verification workers (default: CPU count)

Examples:
  mkbrr check file.torrent /path/to/content
`
}

func getModifyHelp() string {
	return `Modify existing torrent metadata

Usage:
  mkbrr modify <torrent_file> [options]

Options:
  -t, --tracker <url>        Set tracker URL (can be specified multiple times)
  -c, --comment <string>     Set or remove comment (empty string removes)
  -s, --source <string>      Set or remove source tag (empty string removes)
  -e, --entropy              Add or replace entropy field
      --private=<bool>       Set private flag
      --output-dir <path>    Directory for modified torrent
  -o, --output <name>        Base name for modified torrent
      --no-date              Don't write creation date
      --no-creator           Don't write creator/tool name
      --skip-prefix          Don't add tracker domain prefix to filename
  -n, --dry-run              Show what would be modified without writing

Examples:
  mkbrr modify old.torrent -t http://new.tracker.com -o new.torrent
  mkbrr modify file.torrent -c "Updated comment" --private=false
`
}