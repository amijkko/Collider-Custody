# Build stage
FROM golang:1.21-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git gcc musl-dev

WORKDIR /app

# Copy go mod files
COPY go.mod ./

# Copy source code first for go mod tidy
COPY . .

# Download dependencies and generate go.sum
RUN go mod tidy

# Build the binary
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o mpc-signer ./cmd/signer

# Runtime stage
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/mpc-signer .

# Create data directory for shares
RUN mkdir -p /app/data/shares && chmod 700 /app/data/shares

# Non-root user for security
RUN adduser -D -g '' mpcuser && chown -R mpcuser:mpcuser /app
USER mpcuser

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:50051/health || exit 1

# Environment variables
ENV MPC_STORAGE_PASSWORD=""
ENV MPC_NODE_ID="bank-node-1"
ENV MPC_LOG_LEVEL="info"

# Run
ENTRYPOINT ["./mpc-signer"]
CMD ["-port", "50051", "-storage", "/app/data/shares", "-log-level", "info"]
