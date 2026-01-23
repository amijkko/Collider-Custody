.PHONY: build clean copy-wasm

# Output directory for WASM files
OUTPUT_DIR = ../frontend/public/wasm

# Build WASM module
build:
	@echo "Building TSS WASM module..."
	@mkdir -p $(OUTPUT_DIR)
	GOOS=js GOARCH=wasm go build -tags=tss -o $(OUTPUT_DIR)/tss.wasm main.go
	@echo "Copying wasm_exec.js..."
	cp "$$(go env GOROOT)/misc/wasm/wasm_exec.js" $(OUTPUT_DIR)/
	@echo "Build complete: $(OUTPUT_DIR)/tss.wasm"

# Copy WASM runtime
copy-wasm-exec:
	@mkdir -p $(OUTPUT_DIR)
	cp "$$(go env GOROOT)/misc/wasm/wasm_exec.js" $(OUTPUT_DIR)/

# Clean build artifacts
clean:
	rm -f $(OUTPUT_DIR)/tss.wasm
	rm -f $(OUTPUT_DIR)/wasm_exec.js

# Download dependencies
deps:
	go mod download
	go mod tidy
