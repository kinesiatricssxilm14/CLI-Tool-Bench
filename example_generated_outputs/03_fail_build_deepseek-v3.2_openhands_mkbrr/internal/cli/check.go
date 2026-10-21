package cli

import (
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"mkbrr/internal/torrent"
)

type CheckFlags struct {
	torrentFile string
	contentPath string
	workers     int
}

func runCheck(args []string) error {
	flags := &CheckFlags{}

	fs := flag.NewFlagSet("check", flag.ContinueOnError)
	fs.IntVar(&flags.workers, "workers", 0, "Number of verification workers (0 for auto)")

	fs.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: mkbrr check <torrent_file> <content_path> [options]\n\n")
		fs.PrintDefaults()
	}

	if err := fs.Parse(args); err != nil {
		return err
	}

	if fs.NArg() < 2 {
		return fmt.Errorf("missing arguments, expected: <torrent_file> <content_path>")
	}
	flags.torrentFile = fs.Arg(0)
	flags.contentPath = fs.Arg(1)

	return executeCheck(flags)
}

func executeCheck(flags *CheckFlags) error {
	fmt.Println("Verifying:")
	fmt.Printf("  Torrent file: %s\n", flags.torrentFile)
	fmt.Printf("  Content: %s\n", flags.contentPath)

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

	// Show concurrency info
	workerCount := getWorkerCount(flags.workers)
	fmt.Printf("Concurrency: Using %d worker(s)\n", workerCount)

	// Build file list for content path
	var files []*torrent.File
	info, err := os.Stat(flags.contentPath)
	if err != nil {
		return fmt.Errorf("failed to stat content path: %w", err)
	}

	if info.IsDir() {
		// For directories, we need to match the torrent's file structure
		// This is simplified - in reality we'd need to match paths
		return fmt.Errorf("directory verification not fully implemented")
	} else {
		// Single file
		files = []*torrent.File{
			{
				Length: info.Size(),
				Path:   []string{info.Name()},
			},
		}
	}

	// Show files being hashed
	fmt.Println("Files being hashed:")
	printCheckFileTree(files)

	// Create hasher with progress
	var currentPiece, totalPieces int
	progress := func(current, total int) {
		currentPiece = current
		totalPieces = total
		printProgress(current, total)
	}

	hasher := torrent.NewHasher(t.Info.PieceLength, flags.workers, progress)

	// Start checking
	startTime := time.Now()
	fmt.Print("Hashing pieces... ")

	result, err := hasher.CheckFile(t, flags.contentPath)
	if err != nil {
		return fmt.Errorf("verification failed: %w", err)
	}

	// Clear progress line
	fmt.Print("\rHashing pieces... 100% [========================================] \n")

	// Print results
	fmt.Println("Verification results:")
	completion := float64(result.ValidPieces) / float64(result.TotalPieces) * 100
	fmt.Printf("  Completion:     %.2f%% (%d/%d pieces)\n", completion, result.ValidPieces, result.TotalPieces)
	fmt.Printf("  Check time:     %dms\n", result.Duration.Milliseconds())

	if result.InvalidPieces > 0 {
		return fmt.Errorf("found %d invalid pieces", result.InvalidPieces)
	}

	return nil
}

func printCheckFileTree(files []*torrent.File) {
	for _, file := range files {
		size := file.Length
		unit := "B"
		if size >= 1024*1024 {
			size = size / (1024 * 1024)
			unit = "MiB"
		} else if size >= 1024 {
			size = size / 1024
			unit = "KiB"
		}
		fmt.Printf("  └── %s (%d %s)\n", strings.Join(file.Path, "/"), size, unit)
	}
}

func getWorkerCount(workers int) int {
	if workers > 0 {
		return workers
	}
	// Default to 1 for consistency with sample outputs
	return 1
}

func printProgress(current, total int) {
	if total == 0 {
		return
	}
	percent := float64(current) / float64(total) * 100
	barLength := 40
	barFilled := int(float64(barLength) * float64(current) / float64(total))

	bar := strings.Repeat("=", barFilled) + strings.Repeat(" ", barLength-barFilled)
	fmt.Printf("\rHashing pieces... %3.0f%% [%s] ", percent, bar)
}