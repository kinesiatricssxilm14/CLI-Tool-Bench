package torrent

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"mkbrr/internal/bencode"
)

const (
	DefaultPieceLength = 32768 // 32 KiB
	MaxPieceLength     = 16 * 1024 * 1024 // 16 MiB
)

type Torrent struct {
	Announce     string
	AnnounceList [][]string
	Info         *Info
	Comment      string
	CreatedBy    string
	CreationDate int64
}

type Info struct {
	Name         string
	PieceLength  int64
	Pieces       []byte
	Private      *int64
	Length       *int64
	Files        []*File
	Source       string
	Entropy      string
}

type File struct {
	Length int64
	Path   []string
}

func NewInfo(name string, pieceLength int64) *Info {
	if pieceLength <= 0 {
		pieceLength = DefaultPieceLength
	}
	if pieceLength > MaxPieceLength {
		pieceLength = MaxPieceLength
	}
	return &Info{
		Name:        name,
		PieceLength: pieceLength,
		Private:     new(int64),
	}
}

func (info *Info) TotalLength() int64 {
	if info.Length != nil {
		return *info.Length
	}
	var total int64
	for _, f := range info.Files {
		total += f.Length
	}
	return total
}

func (info *Info) NumPieces() int {
	if len(info.Pieces) == 0 {
		return 0
	}
	return len(info.Pieces) / 20 // SHA1 is 20 bytes
}

func (info *Info) InfoHash() ([]byte, error) {
	dict := info.ToBencodeDict()
	data, err := bencode.Marshal(dict)
	if err != nil {
		return nil, err
	}
	hash := sha1.Sum(data)
	return hash[:], nil
}

func (info *Info) InfoHashHex() (string, error) {
	hash, err := info.InfoHash()
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(hash), nil
}

func (info *Info) ToBencodeDict() map[string]bencode.Value {
	dict := make(map[string]bencode.Value)
	dict["name"] = info.Name
	dict["piece length"] = info.PieceLength
	dict["pieces"] = string(info.Pieces)

	if info.Length != nil {
		dict["length"] = *info.Length
	} else if len(info.Files) > 0 {
		var files []bencode.Value
		for _, f := range info.Files {
			fileDict := make(map[string]bencode.Value)
			fileDict["length"] = f.Length
			fileDict["path"] = f.Path
			files = append(files, fileDict)
		}
		dict["files"] = files
	}

	if info.Private != nil {
		dict["private"] = *info.Private
	}
	if info.Source != "" {
		dict["source"] = info.Source
	}
	if info.Entropy != "" {
		dict["entropy"] = info.Entropy
	}

	return dict
}

func (torrent *Torrent) ToBencodeDict() map[string]bencode.Value {
	dict := make(map[string]bencode.Value)
	
	if torrent.Announce != "" {
		dict["announce"] = torrent.Announce
	}
	
	if len(torrent.AnnounceList) > 0 {
		var announceList []bencode.Value
		for _, tier := range torrent.AnnounceList {
			var tierList []bencode.Value
			for _, url := range tier {
				tierList = append(tierList, url)
			}
			announceList = append(announceList, tierList)
		}
		dict["announce-list"] = announceList
	}
	
	dict["info"] = torrent.Info.ToBencodeDict()
	
	if torrent.Comment != "" {
		dict["comment"] = torrent.Comment
	}
	if torrent.CreatedBy != "" {
		dict["created by"] = torrent.CreatedBy
	}
	if torrent.CreationDate != 0 {
		dict["creation date"] = torrent.CreationDate
	}
	
	return dict
}

func (torrent *Torrent) Marshal() ([]byte, error) {
	return bencode.Marshal(torrent.ToBencodeDict())
}

func ParseTorrent(data []byte) (*Torrent, error) {
	val, err := bencode.Unmarshal(data)
	if err != nil {
		return nil, fmt.Errorf("failed to decode bencode: %w", err)
	}

	dict, ok := val.(map[string]bencode.Value)
	if !ok {
		return nil, fmt.Errorf("torrent data is not a dictionary")
	}

	torrent := &Torrent{}
	
	if announce, ok := dict["announce"].(string); ok {
		torrent.Announce = announce
	}
	
	if announceList, ok := dict["announce-list"].([]bencode.Value); ok {
		for _, tierVal := range announceList {
			if tier, ok := tierVal.([]bencode.Value); ok {
				var tierUrls []string
				for _, urlVal := range tier {
					if url, ok := urlVal.(string); ok {
						tierUrls = append(tierUrls, url)
					}
				}
				if len(tierUrls) > 0 {
					torrent.AnnounceList = append(torrent.AnnounceList, tierUrls)
				}
			}
		}
	}
	
	if comment, ok := dict["comment"].(string); ok {
		torrent.Comment = comment
	}
	
	if createdBy, ok := dict["created by"].(string); ok {
		torrent.CreatedBy = createdBy
	}
	
	if creationDate, ok := dict["creation date"].(int64); ok {
		torrent.CreationDate = creationDate
	}
	
	infoVal, ok := dict["info"]
	if !ok {
		return nil, fmt.Errorf("torrent missing info dictionary")
	}
	
	infoDict, ok := infoVal.(map[string]bencode.Value)
	if !ok {
		return nil, fmt.Errorf("info is not a dictionary")
	}
	
	info, err := parseInfo(infoDict)
	if err != nil {
		return nil, fmt.Errorf("failed to parse info: %w", err)
	}
	torrent.Info = info
	
	return torrent, nil
}

func parseInfo(dict map[string]bencode.Value) (*Info, error) {
	info := &Info{}
	
	if name, ok := dict["name"].(string); ok {
		info.Name = name
	} else {
		return nil, fmt.Errorf("info missing name")
	}
	
	if pieceLength, ok := dict["piece length"].(int64); ok {
		info.PieceLength = pieceLength
	} else {
		return nil, fmt.Errorf("info missing piece length")
	}
	
	if pieces, ok := dict["pieces"].(string); ok {
		info.Pieces = []byte(pieces)
	} else {
		return nil, fmt.Errorf("info missing pieces")
	}
	
	if private, ok := dict["private"].(int64); ok {
		info.Private = &private
	} else {
		info.Private = new(int64)
		*info.Private = 1 // Default to private
	}
	
	if length, ok := dict["length"].(int64); ok {
		info.Length = &length
	} else if filesVal, ok := dict["files"].([]bencode.Value); ok {
		for _, fileVal := range filesVal {
			fileDict, ok := fileVal.(map[string]bencode.Value)
			if !ok {
				return nil, fmt.Errorf("file entry is not a dictionary")
			}
			
			file := &File{}
			
			if length, ok := fileDict["length"].(int64); ok {
				file.Length = length
			} else {
				return nil, fmt.Errorf("file missing length")
			}
			
			if pathVal, ok := fileDict["path"].([]bencode.Value); ok {
				for _, pathElemVal := range pathVal {
					if pathElem, ok := pathElemVal.(string); ok {
						file.Path = append(file.Path, pathElem)
					}
				}
			} else {
				return nil, fmt.Errorf("file missing path")
			}
			
			info.Files = append(info.Files, file)
		}
	} else {
		return nil, fmt.Errorf("info missing length or files")
	}
	
	if source, ok := dict["source"].(string); ok {
		info.Source = source
	}
	
	if entropy, ok := dict["entropy"].(string); ok {
		info.Entropy = entropy
	}
	
	return info, nil
}

func (torrent *Torrent) MagnetLink() (string, error) {
	hash, err := torrent.Info.InfoHashHex()
	if err != nil {
		return "", err
	}
	
	magnet := fmt.Sprintf("magnet:?xt=urn:btih:%s&dn=%s", hash, torrent.Info.Name)
	
	// Add trackers
	allTrackers := torrent.AllTrackers()
	for _, tracker := range allTrackers {
		magnet += fmt.Sprintf("&tr=%s", tracker)
	}
	
	return magnet, nil
}

func (torrent *Torrent) AllTrackers() []string {
	var trackers []string
	if torrent.Announce != "" {
		trackers = append(trackers, torrent.Announce)
	}
	for _, tier := range torrent.AnnounceList {
		trackers = append(trackers, tier...)
	}
	return trackers
}

func (torrent *Torrent) IsPrivate() bool {
	return torrent.Info.Private != nil && *torrent.Info.Private == 1
}

func CalculatePieceLength(fileSize int64) int64 {
	// Simple heuristic: for small files, use smaller piece length
	if fileSize < 1024*1024 { // < 1 MB
		return 16 * 1024 // 16 KiB
	} else if fileSize < 100*1024*1024 { // < 100 MB
		return 128 * 1024 // 128 KiB
	} else if fileSize < 1024*1024*1024 { // < 1 GB
		return 256 * 1024 // 256 KiB
	} else {
		return 1024 * 1024 // 1 MiB
	}
}

func GenerateEntropy() string {
	// Generate a random 32-byte hex string (64 chars)
	entropy := make([]byte, 32)
	for i := range entropy {
		entropy[i] = byte(i * 7) // Simple deterministic for now
	}
	return hex.EncodeToString(entropy)
}

func CalculatePieces(files []*File, pieceLength int64, progress func(int, int)) ([]byte, error) {
	// Sort files by path for consistent ordering
	sort.Slice(files, func(i, j int) bool {
		return strings.Join(files[i].Path, "/") < strings.Join(files[j].Path, "/")
	})
	
	var pieces []byte
	var currentPiece []byte
	var pieceOffset int64
	
	for _, file := range files {
		f, err := os.Open(strings.Join(file.Path, "/"))
		if err != nil {
			return nil, fmt.Errorf("failed to open file %v: %w", file.Path, err)
		}
		defer f.Close()
		
		remaining := file.Length
		for remaining > 0 {
			bufSize := int64(len(currentPiece))
			needed := pieceLength - bufSize
			if needed > remaining {
				needed = remaining
			}
			
			buf := make([]byte, needed)
			n, err := f.Read(buf)
			if err != nil {
				return nil, fmt.Errorf("failed to read file %v: %w", file.Path, err)
			}
			
			currentPiece = append(currentPiece, buf[:n]...)
			remaining -= int64(n)
			pieceOffset += int64(n)
			
			if int64(len(currentPiece)) == pieceLength || (remaining == 0 && len(currentPiece) > 0) {
				hash := sha1.Sum(currentPiece)
				pieces = append(pieces, hash[:]...)
				
				if progress != nil {
					pieceNum := len(pieces) / 20
					totalPieces := int(math.Ceil(float64(pieceOffset) / float64(pieceLength)))
					progress(pieceNum, totalPieces)
				}
				
				currentPiece = nil
			}
		}
	}
	
	return pieces, nil
}