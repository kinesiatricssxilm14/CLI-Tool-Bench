.PHONY: all build install clean test

BINARY_NAME := mkbrr
VERSION := 1.0.0
GO_FILES := $(shell find . -name '*.go' -not -path './vendor/*')

all: build

build:
	@echo "Building $(BINARY_NAME)..."
	@go build -o $(BINARY_NAME) ./cmd/mkbrr

install:
	@echo "Installing $(BINARY_NAME)..."
	@go install ./...

test:
	@echo "Running tests..."
	@go test ./...

clean:
	@echo "Cleaning..."
	@rm -f $(BINARY_NAME)
	@rm -rf dist/

release: clean
	@echo "Building releases..."
	@mkdir -p dist
	GOOS=linux GOARCH=amd64 go build -o dist/$(BINARY_NAME)-linux-amd64 ./cmd/mkbrr
	GOOS=darwin GOARCH=amd64 go build -o dist/$(BINARY_NAME)-darwin-amd64 ./cmd/mkbrr
	GOOS=windows GOARCH=amd64 go build -o dist/$(BINARY_NAME)-windows-amd64.exe ./cmd/mkbrr

fmt:
	@echo "Formatting code..."
	@gofmt -w -s $(GO_FILES)

vet:
	@echo "Vetting code..."
	@go vet ./...

lint:
	@if command -v golangci-lint >/dev/null; then \
		echo "Running linter..."; \
		golangci-lint run; \
	else \
		echo "golangci-lint not installed, skipping"; \
	fi

check: vet lint

help:
	@echo "Available targets:"
	@echo "  build    - Build the binary"
	@echo "  install  - Install the binary"
	@echo "  test     - Run tests"
	@echo "  clean    - Remove build artifacts"
	@echo "  release  - Build releases for multiple platforms"
	@echo "  fmt      - Format Go code"
	@echo "  vet      - Run go vet"
	@echo "  lint     - Run linter (if installed)"
	@echo "  check    - Run vet and lint"
	@echo "  help     - Show this help"