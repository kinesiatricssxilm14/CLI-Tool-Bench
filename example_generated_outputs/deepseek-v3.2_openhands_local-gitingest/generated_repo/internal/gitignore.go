package internal

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
)

type GitIgnore struct {
	patterns []string
	rootDir  string
}

func NewGitIgnore(rootDir string) (*GitIgnore, error) {
	gi := &GitIgnore{
		rootDir: rootDir,
	}
	
	// Look for .gitignore file
	gitignorePath := filepath.Join(rootDir, ".gitignore")
	if _, err := os.Stat(gitignorePath); os.IsNotExist(err) {
		// No .gitignore file, return empty patterns
		return gi, nil
	}
	
	file, err := os.Open(gitignorePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		
		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		
		gi.patterns = append(gi.patterns, line)
	}
	
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	
	return gi, nil
}

func (gi *GitIgnore) ShouldIgnore(path string, isDir bool) (bool, string) {
	relPath, err := filepath.Rel(gi.rootDir, path)
	if err != nil {
		return false, ""
	}
	
	// Convert to forward slashes for consistent matching
	relPath = filepath.ToSlash(relPath)
	
	// DEBUG: Check if this is .gitignore file
	if strings.HasSuffix(relPath, ".gitignore") {
		// Don't exclude .gitignore file itself
		return false, ""
	}
	
	for _, pattern := range gi.patterns {
		pattern = filepath.ToSlash(pattern)
		if matchesGitIgnorePattern(relPath, pattern, isDir) {
			return true, pattern
		}
	}
	
	return false, ""
}

func matchesGitIgnorePattern(path, pattern string, isDir bool) bool {
	// Handle directory-only patterns
	if strings.HasSuffix(pattern, "/") {
		if !isDir {
			return false
		}
		pattern = strings.TrimSuffix(pattern, "/")
	}
	
	// Handle patterns starting with /
	if strings.HasPrefix(pattern, "/") {
		pattern = strings.TrimPrefix(pattern, "/")
		return matchesPattern(path, pattern)
	}
	
	// Handle patterns with wildcards
	if strings.Contains(pattern, "/") {
		// Pattern contains directory separators
		return matchesPattern(path, pattern)
	}
	
	// Simple filename pattern
	// Check if any component matches
	parts := strings.Split(path, "/")
	for _, part := range parts {
		if matchesPattern(part, pattern) {
			return true
		}
	}
	
	return false
}

func matchesPattern(path, pattern string) bool {
	// Convert pattern to regex-like pattern
	patternParts := strings.Split(pattern, "*")
	
	// Simple substring matching for now
	// In a full implementation, we would use regexp
	if strings.Contains(pattern, "*") {
		// Check if path matches the pattern
		// Simple implementation: check if path contains all non-wildcard parts
		for _, part := range patternParts {
			if part != "" && !strings.Contains(path, part) {
				return false
			}
		}
		return true
	}
	
	// Exact match for non-wildcard patterns
	return path == pattern
}