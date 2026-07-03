package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	
	"local-gitingest/internal"
)

type Config struct {
	TargetDir    string
	OutputFile   string
	ExcludeExts  []string
	ExcludeDirs  []string
	SizeLimit    bool
	MaxSize      int64
	Verbose      bool
}

func main() {
	config := parseFlags()
	
	// Validate target directory
	if config.TargetDir == "" {
		config.TargetDir = "."
	}
	
	absPath, err := filepath.Abs(config.TargetDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error resolving path: %v\n", err)
		os.Exit(1)
	}
	

	
	// Parse .gitignore
	gitIgnore, err := internal.NewGitIgnore(absPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading .gitignore: %v\n", err)
		os.Exit(1)
	}
	
	// Find repository root (where .git directory is)
	repoRoot := findGitRoot(absPath)
	if repoRoot == "" {
		fmt.Fprintf(os.Stderr, "Error: %s is not in a git repository\n", absPath)
		os.Exit(1)
	}
	
	// Create traversal config
	traversalConfig := &internal.TraversalConfig{
		RootDir:     absPath,
		RepoRoot:    repoRoot,
		ExcludeExts: config.ExcludeExts,
		ExcludeDirs: config.ExcludeDirs,
		Verbose:     config.Verbose,
		SizeLimit:   config.SizeLimit,
		MaxSize:     config.MaxSize,
		GitIgnore:   gitIgnore,
	}
	
	// Traverse directory
	files, excluded, err := internal.TraverseDirectory(traversalConfig)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error traversing directory: %v\n", err)
		os.Exit(1)
	}
	
	// Print verbose exclusions
	if config.Verbose {
		for _, excl := range excluded {
			fmt.Println(excl)
		}
	}
	
	// Generate output
	outputGen := internal.NewOutputGenerator(traversalConfig, files)
	outputPath := filepath.Join(absPath, config.OutputFile)
	
	err = outputGen.GenerateOutput(outputPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error generating output: %v\n", err)
		os.Exit(1)
	}
	
	fmt.Printf("Successfully generated output to %s\n", config.OutputFile)
	os.Exit(0)
}

func parseFlags() *Config {
	config := &Config{
		OutputFile: "output.txt",
		MaxSize:    1000, // Default 1000 bytes based on sample output
	}
	
	var excludeExts string
	var excludeDirs string
	
	flag.StringVar(&config.TargetDir, "d", "", "Target subdirectory to process")
	flag.StringVar(&config.OutputFile, "o", config.OutputFile, "Output filename")
	flag.StringVar(&excludeExts, "exclude", "", "Comma-separated list of file extensions to exclude")
	flag.StringVar(&excludeDirs, "exclude-dir", "", "Comma-separated list of directories to exclude")
	flag.BoolVar(&config.SizeLimit, "size-limit", false, "Enable file size limit")
	flag.Int64Var(&config.MaxSize, "max-size", config.MaxSize, "Maximum file size in bytes")
	flag.BoolVar(&config.Verbose, "v", false, "Verbose mode")
	
	flag.Parse()
	
	// Handle positional argument for target directory
	if flag.NArg() > 0 && config.TargetDir == "" {
		config.TargetDir = flag.Arg(0)
	}
	
	// Parse comma-separated lists
	if excludeExts != "" {
		config.ExcludeExts = parseCommaList(excludeExts)
	}
	
	if excludeDirs != "" {
		config.ExcludeDirs = parseCommaList(excludeDirs)
	}
	
	// If size-limit flag is not set, we still apply default limit
	// but the flag controls whether to show it as enabled
	if !config.SizeLimit {
		// Still apply default limit but don't treat it as "enabled"
		// The output will still truncate at MaxSize
	}
	
	return config
}

func parseCommaList(input string) []string {
	var result []string
	parts := strings.Split(input, ",")
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func isGitRepository(path string) bool {
	gitDir := filepath.Join(path, ".git")
	info, err := os.Stat(gitDir)
	if err != nil {
		return false
	}
	return info.IsDir()
}

func findGitRoot(startPath string) string {
	current := startPath
	for {
		gitDir := filepath.Join(current, ".git")
		if info, err := os.Stat(gitDir); err == nil && info.IsDir() {
			return current
		}
		
		parent := filepath.Dir(current)
		if parent == current {
			// Reached root directory
			break
		}
		current = parent
	}
	return ""
}