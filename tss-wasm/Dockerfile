# Dockerfile for building TSS WASM module
FROM golang:1.21-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git make

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download || true

# Copy source
COPY . .

# Tidy modules
RUN go mod tidy

# Build WASM module
RUN GOOS=js GOARCH=wasm go build -tags=tss -o tss.wasm main.go

# Copy wasm_exec.js
RUN cp "$(go env GOROOT)/misc/wasm/wasm_exec.js" .

# Output stage - just the WASM files
FROM scratch AS output
COPY --from=builder /build/tss.wasm /tss.wasm
COPY --from=builder /build/wasm_exec.js /wasm_exec.js
