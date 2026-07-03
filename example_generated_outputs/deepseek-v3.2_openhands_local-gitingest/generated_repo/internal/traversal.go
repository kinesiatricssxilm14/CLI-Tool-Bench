package internal

import (
	"fmt"
	"io/fs"
	"path/filepath"
	"strings"
)

type FileInfo struct {
	Path    string
	RelPath string
	IsDir   bool
	Size    int64
}

type TraversalConfig struct {
	RootDir      string
	RepoRoot     string
	ExcludeExts  []string
	ExcludeDirs  []string
	DefaultExclusions []string
	Verbose      bool
	SizeLimit    bool
	MaxSize      int64
	GitIgnore    *GitIgnore
}

func TraverseDirectory(config *TraversalConfig) ([]FileInfo, []string, error) {
	var files []FileInfo
	var excluded []string
	
	// Default exclusions
	defaultExclusions := []string{".git", "node_modules", ".DS_Store"}
	if len(config.DefaultExclusions) > 0 {
		defaultExclusions = config.DefaultExclusions
	}
	
	// Combine all directory exclusions
	allDirExclusions := append(defaultExclusions, config.ExcludeDirs...)
	
	err := filepath.WalkDir(config.RootDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		
		relToRoot, err := filepath.Rel(config.RootDir, path)
		if err != nil {
			return err
		}
		
		// Skip root directory of traversal
		if relToRoot == "." {
			return nil
		}
		
		// Compute path relative to repo root for display
		relToRepo := relToRoot
		if config.RootDir != config.RepoRoot {
			relToRepoRoot, err := filepath.Rel(config.RepoRoot, path)
			if err == nil {
				relToRepo = relToRepoRoot
			}
		}
		
		// Check gitignore patterns
		if config.GitIgnore != nil {
			ignore, _ := config.GitIgnore.ShouldIgnore(path, d.IsDir())
			if ignore {
				if config.Verbose {
					excluded = append(excluded, fmt.Sprintf("Excluded by .gitignore: %s", relToRepo))
				}
				if d.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}
		}
		
		// Check directory exclusions
		for _, exclDir := range allDirExclusions {
			if shouldExcludeDirectory(relToRepo, exclDir) {
				if config.Verbose && d.IsDir() {
					excluded = append(excluded, fmt.Sprintf("Excluded by default: %s", relToRepo))
				}
				if d.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}
		}
		
		// Check file extension exclusions
		if !d.IsDir() {
			ext := strings.ToLower(filepath.Ext(path))
			for _, exclExt := range config.ExcludeExts {
				exclExt = strings.TrimSpace(exclExt)
				if exclExt != "" {
					if !strings.HasPrefix(exclExt, ".") {
						exclExt = "." + exclExt
					}
					if ext == strings.ToLower(exclExt) {
						if config.Verbose {
							excluded = append(excluded, fmt.Sprintf("Excluded by extension: %s", relToRepo))
						}
						return nil
					}
				}
			}
		}
		
		info, err := d.Info()
		if err != nil {
			return err
		}
		
		files = append(files, FileInfo{
			Path:    path,
			RelPath: relToRepo, // Store relative to repo root for display
			IsDir:   d.IsDir(),
			Size:    info.Size(),
		})
		
		return nil
	})
	
	return files, excluded, err
}

func shouldExcludeDirectory(path, pattern string) bool {
	// Simple pattern matching for now
	path = strings.ToLower(path)
	pattern = strings.ToLower(pattern)
	
	// Handle wildcards
	if strings.Contains(pattern, "*") {
		// For directory patterns with wildcards, check if any path component matches
		pathParts := strings.Split(path, string(filepath.Separator))
		for _, part := range pathParts {
			// Simple wildcard matching: check if pattern (with * replaced with .*) matches part
			// For now, just check if part contains the non-wildcard parts
			patternParts := strings.Split(pattern, "*")
			matches := true
			for _, p := range patternParts {
				if p != "" && !strings.Contains(part, p) {
					matches = false
					break
				}
			}
			if matches {
				return true
			}
		}
		return false
	}
	
	// For exact directory name matching
	// Check if any path component exactly matches the pattern
	pathParts := strings.Split(path, string(filepath.Separator))
	for _, part := range pathParts {
		if part == pattern {
			return true
		}
	}
	
	// Check if path starts with pattern followed by path separator
	// This handles patterns like "dir" matching "dir/subdir"
	if strings.HasPrefix(path, pattern+string(filepath.Separator)) {
		return true
	}
	
	return false
}