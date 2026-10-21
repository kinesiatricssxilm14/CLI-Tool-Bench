package cli

import (
	"flag"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"mkbrr/internal/torrent"
)

type InspectFlags struct {
	torrentFile string
	verbose     bool
}

func runInspect(args []string) error {
	flags := &InspectFlags{}

	fs := flag.NewFlagSet("inspect", flag.ContinueOnError)
	fs.BoolVar(&flags.verbose, "v", false, "Show all metadata fields")
	fs.BoolVar(&flags.verbose, "verbose", false, "Show all metadata fields")

	fs.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: mkbrr inspect <torrent_file> [options]\n\n")
		fs.PrintDefaults()
	}

	if err := fs.Parse(args); err != nil {
		return err
	}

	if fs.NArg() < 1 {
		return fmt.Errorf("missing torrent file argument")
	}
	flags.torrentFile = fs.Arg(0)

	return executeInspect(flags)
}

func executeInspect(flags *InspectFlags) error {
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

	// Get info hash
	hash, err := t.Info.InfoHashHex()
	if err != nil {
		return fmt.Errorf("failed to calculate info hash: %w", err)
	}

	// Calculate size
	size := t.Info.TotalLength()
	sizeStr := formatBytes(size)

	// Get magnet link
	magnet, err := t.MagnetLink()
	if err != nil {
		return fmt.Errorf("failed to generate magnet link: %w", err)
	}

	// Get tracker
	tracker := t.Announce
	if tracker == "" && len(t.AnnounceList) > 0 && len(t.AnnounceList[0]) > 0 {
		tracker = t.AnnounceList[0][0]
	}

	// Print torrent info
	fmt.Println("Torrent info:")
	fmt.Printf("  Name:         %s\n", t.Info.Name)
	fmt.Printf("  Hash:         %s\n", hash)
	fmt.Printf("  Size:         %s\n", sizeStr)
	fmt.Printf("  Piece length: %s\n", formatBytes(t.Info.PieceLength))
	fmt.Printf("  Pieces:       %d\n", t.Info.NumPieces())
	fmt.Printf("  Magnet:       %s\n", magnet)
	fmt.Printf("  Tracker:      %s\n", tracker)
	fmt.Printf("  Private:      %s\n", formatBool(t.IsPrivate()))

	if flags.verbose {
		fmt.Println("Additional metadata:")

		if t.Comment != "" {
			fmt.Printf("  Comment:      %s\n", t.Comment)
		}

		if t.CreatedBy != "" {
			fmt.Printf("  Created by:   %s\n", t.CreatedBy)
		}

		if t.CreationDate != 0 {
			fmt.Printf("  Created:      %d\n", t.CreationDate)
		}

		if t.Info.Source != "" {
			fmt.Printf("  Source:       %s\n", t.Info.Source)
		}

		if t.Info.Entropy != "" {
			fmt.Printf("  Entropy:      %s\n", t.Info.Entropy)
		}

		// Show all trackers
		allTrackers := t.AllTrackers()
		if len(allTrackers) > 1 {
			fmt.Println("  Trackers:")
			for i, tracker := range allTrackers {
				fmt.Printf("    [%d] %s\n", i+1, tracker)
			}
		}

		// Show file list for multi-file torrents
		if len(t.Info.Files) > 0 {
			fmt.Println("  Files:")
			for _, file := range t.Info.Files {
				path := strings.Join(file.Path, "/")
				fmt.Printf("    %s (%s)\n", path, formatBytes(file.Length))
			}
		}
	}

	return nil
}

func formatBytes(bytes int64) string {
	const (
		KB = 1024
		MB = 1024 * KB
		GB = 1024 * MB
		TB = 1024 * GB
	)

	switch {
	case bytes >= TB:
		return fmt.Sprintf("%.2f TiB", float64(bytes)/TB)
	case bytes >= GB:
		return fmt.Sprintf("%.2f GiB", float64(bytes)/GB)
	case bytes >= MB:
		return fmt.Sprintf("%.2f MiB", float64(bytes)/MB)
	case bytes >= KB:
		return fmt.Sprintf("%.2f KiB", float64(bytes)/KB)
	default:
		return fmt.Sprintf("%d B", bytes)
	}
}

func formatBool(b bool) string {
	if b {
		return "yes"
	}
	return "no"
}

func encodeTrackerURL(tracker string) string {
	return url.QueryEscape(tracker)
}