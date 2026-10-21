package cli

import (
	"crypto/rand"
	"encoding/hex"
	"flag"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"mkbrr/internal/torrent"
)

type ModifyFlags struct {
	torrentFile string
	trackers    []string
	comment     string
	source      string
	entropy     bool
	private     string
	outputDir   string
	outputName  string
	noDate      bool
	noCreator   bool
	skipPrefix  bool
	dryRun      bool
}

func runModify(args []string) error {
	flags := &ModifyFlags{}

	fs := flag.NewFlagSet("modify", flag.ContinueOnError)
	var trackers trackerList
	fs.Var(&trackers, "t", "Tracker announce URL (can be specified multiple times)")
	fs.Var(&trackers, "tracker", "Tracker announce URL (can be specified multiple times)")
	fs.StringVar(&flags.comment, "c", "", "Set or remove comment (empty string removes)")
	fs.StringVar(&flags.comment, "comment", "", "Set or remove comment (empty string removes)")
	fs.StringVar(&flags.source, "s", "", "Set or remove source tag (empty string removes)")
	fs.StringVar(&flags.source, "source", "", "Set or remove source tag (empty string removes)")
	fs.BoolVar(&flags.entropy, "e", false, "Add or replace entropy field")
	fs.BoolVar(&flags.entropy, "entropy", false, "Add or replace entropy field")
	fs.StringVar(&flags.private, "private", "", "Set private flag (true/false, empty to keep existing)")
	fs.StringVar(&flags.outputDir, "output-dir", ".", "Directory for modified torrent")
	fs.StringVar(&flags.outputName, "o", "", "Base name for modified torrent")
	fs.StringVar(&flags.outputName, "output", "", "Base name for modified torrent")
	fs.BoolVar(&flags.noDate, "no-date", false, "Don't write creation date")
	fs.BoolVar(&flags.noCreator, "no-creator", false, "Don't write creator/tool name")
	fs.BoolVar(&flags.skipPrefix, "skip-prefix", false, "Don't add tracker domain prefix to filename")
	fs.BoolVar(&flags.dryRun, "n", false, "Show what would be modified without writing")
	fs.BoolVar(&flags.dryRun, "dry-run", false, "Show what would be modified without writing")

	fs.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: mkbrr modify <torrent_file> [options]\n\n")
		fs.PrintDefaults()
	}

	if err := fs.Parse(args); err != nil {
		return err
	}

	if fs.NArg() < 1 {
		return fmt.Errorf("missing torrent file argument")
	}
	flags.torrentFile = fs.Arg(0)
	flags.trackers = trackers

	return executeModify(flags)
}

type trackerList []string

func (t *trackerList) String() string {
	return strings.Join(*t, ",")
}

func (t *trackerList) Set(value string) error {
	*t = append(*t, value)
	return nil
}

func executeModify(flags *ModifyFlags) error {
	fmt.Println("Info: Modifying 1 torrent files...")

	// Read torrent file
	data, err := os.ReadFile(flags.torrentFile)
	if err != nil {
		return fmt.Errorf("failed to read torrent file: %w", err)
	}

	// Parse torrent
	t, err := torrent.ParseTorrent(data)
	if err != nil {
		return fmt.Errorf("failed to parse torrent: %w", err)
	}

	// Apply modifications
	modified := false

	// Update trackers
	if len(flags.trackers) > 0 {
		t.Announce = flags.trackers[0]
		if len(flags.trackers) > 1 {
			t.AnnounceList = [][]string{flags.trackers}
		} else {
			t.AnnounceList = nil
		}
		modified = true
	}

	// Update comment
	if flags.comment != "" || (flags.comment == "" && t.Comment != "") {
		t.Comment = flags.comment
		modified = true
	}

	// Update source
	if flags.source != "" || (flags.source == "" && t.Info.Source != "") {
		t.Info.Source = flags.source
		modified = true
	}

	// Update entropy
	if flags.entropy {
		entropy := generateEntropy()
		t.Info.Entropy = entropy
		modified = true
	}

	// Update private flag
	if flags.private != "" {
		privateBool, err := strconv.ParseBool(flags.private)
		if err != nil {
			return fmt.Errorf("invalid private value: %w", err)
		}
		if t.Info.Private == nil {
			t.Info.Private = new(int64)
		}
		if privateBool {
			*t.Info.Private = 1
		} else {
			*t.Info.Private = 0
		}
		modified = true
	}

	// Update creation date and creator
	if !flags.noDate {
		t.CreationDate = time.Now().Unix()
		modified = true
	}

	if !flags.noCreator && t.CreatedBy == "" {
		t.CreatedBy = fmt.Sprintf("%s/%s", appName, appVersion)
		modified = true
	}

	if !modified && !flags.dryRun {
		return fmt.Errorf("no modifications specified")
	}

	if flags.dryRun {
		fmt.Printf("Info: Would modify %s\n", flags.torrentFile)
		return nil
	}

	// Determine output path
	outputPath := flags.outputName
	if outputPath == "" {
		baseName := filepath.Base(flags.torrentFile)
		ext := filepath.Ext(baseName)
		if ext != "" {
			baseName = baseName[:len(baseName)-len(ext)]
		}

		if !flags.skipPrefix && len(flags.trackers) > 0 {
			// Extract domain from first tracker URL for prefix
			if domain := extractDomain(flags.trackers[0]); domain != "" {
				baseName = domain + "_" + baseName
			}
		}
		outputPath = baseName + ".torrent"
	}

	// Prepend output directory if specified
	if flags.outputDir != "." {
		outputPath = filepath.Join(flags.outputDir, outputPath)
	}

	// Ensure output directory exists
	if err := os.MkdirAll(filepath.Dir(outputPath), 0755); err != nil {
		return fmt.Errorf("failed to create output directory: %w", err)
	}

	// Marshal and write torrent
	data, err = t.Marshal()
	if err != nil {
		return fmt.Errorf("failed to marshal torrent: %w", err)
	}

	if err := os.WriteFile(outputPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write torrent file: %w", err)
	}

	fmt.Printf("Wrote %s\n", outputPath)
	return nil
}

func generateEntropy() string {
	bytes := make([]byte, 32)
	if _, err := rand.Read(bytes); err != nil {
		// Fallback to deterministic entropy
		for i := range bytes {
			bytes[i] = byte(i * 7)
		}
	}
	return hex.EncodeToString(bytes)
}

func extractDomain(urlStr string) string {
	// Simple domain extraction
	urlStr = strings.TrimPrefix(urlStr, "http://")
	urlStr = strings.TrimPrefix(urlStr, "https://")
	urlStr = strings.TrimPrefix(urlStr, "ftp://")
	urlStr = strings.TrimPrefix(urlStr, "udp://")

	if idx := strings.Index(urlStr, "/"); idx != -1 {
		urlStr = urlStr[:idx]
	}

	// Remove port
	if idx := strings.Index(urlStr, ":"); idx != -1 {
		urlStr = urlStr[:idx]
	}

	// Take first part before dot if available
	parts := strings.Split(urlStr, ".")
	if len(parts) > 0 {
		return parts[0]
	}
	return ""
}