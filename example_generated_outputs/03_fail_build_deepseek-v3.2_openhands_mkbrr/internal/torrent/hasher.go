package torrent

import (
	"crypto/sha1"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type HashResult struct {
	Pieces []byte
	Error  error
}

type Hasher struct {
	pieceLength int64
	numWorkers  int
	progress    func(current, total int)
}

func NewHasher(pieceLength int64, numWorkers int, progress func(current, total int)) *Hasher {
	if numWorkers <= 0 {
		numWorkers = runtime.NumCPU()
	}
	if numWorkers > 32 {
		numWorkers = 32
	}
	return &Hasher{
		pieceLength: pieceLength,
		numWorkers:  numWorkers,
		progress:    progress,
	}
}

func (h *Hasher) HashFile(path string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	info, err := file.Stat()
	if err != nil {
		return nil, err
	}

	totalLength := info.Size()
	numPieces := int((totalLength + h.pieceLength - 1) / h.pieceLength)
	pieces := make([]byte, 0, numPieces*20)

	var currentPiece []byte
	var pieceOffset int64

	buf := make([]byte, h.pieceLength)
	for {
		n, err := file.Read(buf)
		if err != nil && err != io.EOF {
			return nil, err
		}

		if n > 0 {
			currentPiece = append(currentPiece, buf[:n]...)
			pieceOffset += int64(n)
		}

		if int64(len(currentPiece)) == h.pieceLength || (err == io.EOF && len(currentPiece) > 0) {
			hash := sha1.Sum(currentPiece)
			pieces = append(pieces, hash[:]...)

			if h.progress != nil {
				pieceNum := len(pieces) / 20
				h.progress(pieceNum, numPieces)
			}

			currentPiece = nil
		}

		if err == io.EOF {
			break
		}
	}

	return pieces, nil
}

func (h *Hasher) HashFiles(files []*File) ([]byte, error) {
	if len(files) == 0 {
		return nil, fmt.Errorf("no files to hash")
	}

	// Single file optimization
	if len(files) == 1 && files[0].Length > 0 {
		path := strings.Join(files[0].Path, "/")
		return h.HashFile(path)
	}

	// Multi-file hashing with workers
	totalPieces := h.estimateTotalPieces(files)
	pieces := make([]byte, 0, totalPieces*20)

	fileQueue := make(chan *File, len(files))
	resultChan := make(chan *hashJobResult, h.numWorkers)

	// Send files to queue
	for _, file := range files {
		fileQueue <- file
	}
	close(fileQueue)

	// Start workers
	var wg sync.WaitGroup
	var completedPieces atomic.Int32

	for i := 0; i < h.numWorkers; i++ {
		wg.Add(1)
		go h.hashWorker(fileQueue, resultChan, &wg, &completedPieces, totalPieces)
	}

	// Close result channel when all workers are done
	go func() {
		wg.Wait()
		close(resultChan)
	}()

	// Collect results
	for result := range resultChan {
		if result.err != nil {
			return nil, result.err
		}
		pieces = append(pieces, result.pieceHash...)
	}

	return pieces, nil
}

func (h *Hasher) estimateTotalPieces(files []*File) int {
	var totalLength int64
	for _, file := range files {
		totalLength += file.Length
	}
	return int((totalLength + h.pieceLength - 1) / h.pieceLength)
}

type hashJobResult struct {
	pieceHash []byte
	err       error
}

func (h *Hasher) hashWorker(files <-chan *File, results chan<- *hashJobResult, wg *sync.WaitGroup, completed *atomic.Int32, totalPieces int) {
	defer wg.Done()

	for file := range files {
		path := strings.Join(file.Path, "/")
		f, err := os.Open(path)
		if err != nil {
			results <- &hashJobResult{err: err}
			return
		}

		var offset int64
		buf := make([]byte, h.pieceLength)

		for offset < file.Length {
			toRead := h.pieceLength
			if offset+toRead > file.Length {
				toRead = file.Length - offset
			}

			n, err := io.ReadFull(f, buf[:toRead])
			if err != nil && err != io.EOF && err != io.ErrUnexpectedEOF {
				results <- &hashJobResult{err: err}
				f.Close()
				return
			}

			if n > 0 {
				hash := sha1.Sum(buf[:n])
				results <- &hashJobResult{pieceHash: hash[:]}

				curr := completed.Add(1)
				if h.progress != nil {
					h.progress(int(curr), totalPieces)
				}
			}

			offset += int64(n)
			if err == io.EOF {
				break
			}
		}

		f.Close()
	}
}

type CheckResult struct {
	ValidPieces   int
	InvalidPieces int
	TotalPieces   int
	Duration      time.Duration
}

func (h *Hasher) CheckFile(torrent *Torrent, contentPath string) (*CheckResult, error) {
	start := time.Now()

	// Get expected pieces from torrent
	expectedPieces := torrent.Info.Pieces
	if len(expectedPieces)%20 != 0 {
		return nil, fmt.Errorf("invalid pieces length")
	}

	// Hash the file
	actualPieces, err := h.HashFile(contentPath)
	if err != nil {
		return nil, err
	}

	// Compare pieces
	valid := 0
	invalid := 0
	total := len(expectedPieces) / 20

	for i := 0; i < total; i++ {
		expectedStart := i * 20
		expectedEnd := expectedStart + 20
		actualStart := i * 20
		actualEnd := actualStart + 20

		if actualEnd > len(actualPieces) {
			invalid++
			continue
		}

		if string(expectedPieces[expectedStart:expectedEnd]) == string(actualPieces[actualStart:actualEnd]) {
			valid++
		} else {
			invalid++
		}
	}

	duration := time.Since(start)

	return &CheckResult{
		ValidPieces:   valid,
		InvalidPieces: invalid,
		TotalPieces:   total,
		Duration:      duration,
	}, nil
}

func BuildFileList(path string, includePatterns, excludePatterns []string) ([]*File, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, err
	}

	var files []*File

	if info.IsDir() {
		err = filepath.Walk(path, func(filePath string, fileInfo os.FileInfo, err error) error {
			if err != nil {
				return err
			}

			if fileInfo.IsDir() {
				return nil
			}

			relPath, err := filepath.Rel(path, filePath)
			if err != nil {
				return err
			}

			// Check exclude patterns
			if matchesPatterns(relPath, excludePatterns) {
				return nil
			}

			// Check include patterns
			if len(includePatterns) > 0 && !matchesPatterns(relPath, includePatterns) {
				return nil
			}

			// Split path into components
			pathComponents := strings.Split(relPath, string(filepath.Separator))

			files = append(files, &File{
				Length: fileInfo.Size(),
				Path:   pathComponents,
			})

			return nil
		})
		if err != nil {
			return nil, err
		}
	} else {
		// Single file
		baseName := filepath.Base(path)
		files = append(files, &File{
			Length: info.Size(),
			Path:   []string{baseName},
		})
	}

	return files, nil
}

func matchesPatterns(path string, patterns []string) bool {
	if len(patterns) == 0 {
		return false
	}

	for _, pattern := range patterns {
		pattern = strings.TrimSpace(pattern)
		if pattern == "" {
			continue
		}

		matched, err := filepath.Match(pattern, path)
		if err == nil && matched {
			return true
		}

		// Also check against just the filename
		filename := filepath.Base(path)
		matched, err = filepath.Match(pattern, filename)
		if err == nil && matched {
			return true
		}
	}

	return false
}