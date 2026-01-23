#!/bin/bash
# Build script for TSS WASM module
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/../frontend/public/wasm"

echo "Building TSS WASM module..."

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Check if Go is installed
if command -v go &> /dev/null; then
    echo "Using local Go installation..."
    cd "$SCRIPT_DIR"

    # Download dependencies
    go mod tidy

    # Build WASM
    GOOS=js GOARCH=wasm go build -tags=tss -o "$OUTPUT_DIR/tss.wasm" main.go

    # Copy wasm_exec.js
    cp "$(go env GOROOT)/misc/wasm/wasm_exec.js" "$OUTPUT_DIR/"
else
    echo "Go not found, using Docker..."

    # Build using Docker
    cd "$SCRIPT_DIR"

    # Build the image
    docker build --target builder -t tss-wasm-builder .

    # Extract the built files
    CONTAINER_ID=$(docker create tss-wasm-builder)
    docker cp "$CONTAINER_ID:/build/tss.wasm" "$OUTPUT_DIR/"
    docker cp "$CONTAINER_ID:/build/wasm_exec.js" "$OUTPUT_DIR/"
    docker rm "$CONTAINER_ID"
fi

echo "Build complete!"
echo "Output files:"
ls -la "$OUTPUT_DIR"
