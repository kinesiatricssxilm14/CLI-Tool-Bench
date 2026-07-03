package internal

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type OutputGenerator struct {
	config *TraversalConfig
	files  []FileInfo
}

func NewOutputGenerator(config *TraversalConfig, files []FileInfo) *OutputGenerator {
	return &OutputGenerator{
		config: config,
		files:  files,
	}
}

func (og *OutputGenerator) GenerateTree() string {
	// Build tree structure
	type TreeNode struct {
		name     string
		isDir    bool
		children map[string]*TreeNode
		files    []string
	}
	
	root := &TreeNode{
		name:     filepath.Base(og.config.RepoRoot),
		isDir:    true,
		children: make(map[string]*TreeNode),
		files:    []string{},
	}
	
	// Helper function to get or create node
	getOrCreateNode := func(path string, isDir bool) *TreeNode {
		parts := strings.Split(path, string(filepath.Separator))
		current := root
		
		for i, part := range parts {
			if i == len(parts)-1 && !isDir {
				// This is a file, add to current directory's files
				current.files = append(current.files, part)
				sort.Strings(current.files)
				return nil
			}
			
			if part == "" {
				continue
			}
			
			if _, exists := current.children[part]; !exists {
				current.children[part] = &TreeNode{
					name:     part,
					isDir:    true,
					children: make(map[string]*TreeNode),
					files:    []string{},
				}
			}
			current = current.children[part]
		}
		return current
	}
	
	// Process all files and directories
	for _, file := range og.files {
		if file.RelPath == "" {
			continue
		}
		getOrCreateNode(file.RelPath, file.IsDir)
	}
	
	// Sort children names for consistent output
	var sortedChildren []string
	for name := range root.children {
		sortedChildren = append(sortedChildren, name)
	}
	sort.Strings(sortedChildren)
	
	// Build output recursively
	var lines []string
	var traverse func(node *TreeNode, indent int)
	
	traverse = func(node *TreeNode, indent int) {
		indentStr := strings.Repeat("    ", indent)
		if indent == 0 {
			lines = append(lines, node.name+"/")
		} else {
			lines = append(lines, indentStr+node.name+"/")
		}
		
		// Get all entries (files and directories) at this level
		var entries []string
		entryMap := make(map[string]string) // name -> type: "file" or "dir"
		
		for _, fileName := range node.files {
			entries = append(entries, fileName)
			entryMap[fileName] = "file"
		}
		
		for dirName := range node.children {
			entries = append(entries, dirName)
			entryMap[dirName] = "dir"
		}
		
		// Sort entries alphabetically
		sort.Strings(entries)
		
		// Process entries
		for _, entry := range entries {
			if entryMap[entry] == "file" {
				if indent == 0 {
					// Files at root level have no indentation
					lines = append(lines, entry)
				} else {
					lines = append(lines, indentStr+"    "+entry)
				}
			} else {
				// It's a directory, traverse it
				traverse(node.children[entry], indent+1)
			}
		}
	}
	
	traverse(root, 0)
	return strings.Join(lines, "\n")
}

func (og *OutputGenerator) GenerateOutput(outputPath string) error {
	file, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer file.Close()
	
	writer := bufio.NewWriter(file)
	
	// Write directory tree
	tree := og.GenerateTree()
	writer.WriteString(tree)
	writer.WriteString("\n\n")
	
	// Write file contents
	for _, fileInfo := range og.files {
		if !fileInfo.IsDir {
			// Skip if it's the output file itself
			if fileInfo.RelPath == outputPath || fileInfo.Path == outputPath {
				continue
			}
			
			content, err := og.readFileContent(fileInfo)
			if err != nil {
				return err
			}
			
			writer.WriteString(strings.Repeat("=", 48))
			writer.WriteString(fmt.Sprintf("\nFile: %s\n", fileInfo.RelPath))
			writer.WriteString(strings.Repeat("=", 48))
			writer.WriteString("\n")
			writer.WriteString(content)
			writer.WriteString("\n\n")
		}
	}
	
	return writer.Flush()
}

func (og *OutputGenerator) readFileContent(fileInfo FileInfo) (string, error) {
	// Always check size limit (default is 1000 bytes)
	if fileInfo.Size > og.config.MaxSize {
		return og.readTruncatedFile(fileInfo.Path, og.config.MaxSize)
	}
	
	// Read entire file
	content, err := os.ReadFile(fileInfo.Path)
	if err != nil {
		return "", err
	}
	
	// Check if file is binary
	if isBinary(content) {
		return string(content), nil
	}
	
	return string(content), nil
}

func (og *OutputGenerator) readTruncatedFile(path string, maxSize int64) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	
	// Read up to maxSize bytes
	reader := io.LimitReader(file, maxSize)
	content, err := io.ReadAll(reader)
	if err != nil {
		return "", err
	}
	
	// Add truncation indicator
	result := string(content)
	if len(result) == int(maxSize) {
		result += "\n...[TRUNCATED]"
	}
	
	return result, nil
}

func isBinary(content []byte) bool {
	// Simple heuristic: check for null bytes
	for _, b := range content {
		if b == 0 {
			return true
		}
	}
	return false
}