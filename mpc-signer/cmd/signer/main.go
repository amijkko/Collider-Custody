package main

import (
	"context"
	"flag"
	"fmt"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/collider/mpc-signer/internal/server"
	"github.com/collider/mpc-signer/internal/storage"
	mpc "github.com/collider/mpc-signer/proto"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

func main() {
	// Parse flags
	port := flag.Int("port", 50051, "gRPC server port")
	storageDir := flag.String("storage", "./data/shares", "Directory for encrypted share storage")
	logLevel := flag.String("log-level", "info", "Log level (debug, info, warn, error)")
	flag.Parse()

	// Setup logger
	logger := setupLogger(*logLevel)
	defer logger.Sync()

	// Load server configuration from environment
	config, err := server.LoadConfigFromEnv()
	if err != nil {
		logger.Fatal("Failed to load configuration", zap.Error(err))
	}

	logger.Info("Starting MPC Signer Node",
		zap.String("node_id", config.NodeID),
		zap.Int("port", *port),
		zap.String("storage_dir", *storageDir),
	)

	// Get storage password from environment
	storagePassword := os.Getenv("MPC_STORAGE_PASSWORD")
	if storagePassword == "" {
		storagePassword = "development-password-change-in-production"
		logger.Warn("Using default storage password - set MPC_STORAGE_PASSWORD in production!")
	}

	// Initialize storage (prefer PostgreSQL if DATABASE_URL is set)
	var store storage.Storage
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL != "" {
		logger.Info("Using PostgreSQL storage")
		pgStore, err := storage.NewPostgresStorage(databaseURL, storagePassword)
		if err != nil {
			logger.Fatal("Failed to initialize PostgreSQL storage", zap.Error(err))
		}
		store = pgStore
	} else {
		logger.Info("Using file storage", zap.String("path", *storageDir))
		fileStore, err := storage.NewFileStorage(*storageDir, storagePassword)
		if err != nil {
			logger.Fatal("Failed to initialize file storage", zap.Error(err))
		}
		store = fileStore
	}

	// List existing shares
	existingShares, _ := store.ListShares()
	logger.Info("Loaded existing shares",
		zap.Int("count", len(existingShares)),
		zap.Strings("keysets", existingShares),
	)

	// Create gRPC server
	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(loggingInterceptor(logger)),
	)

	// Create MPC server
	mpcServer, err := server.NewMPCServer(config, store, logger)
	if err != nil {
		logger.Fatal("Failed to create MPC server", zap.Error(err))
	}

	// Register service
	mpc.RegisterMPCSignerServer(grpcServer, mpcServer)

	// Enable reflection for debugging
	reflection.Register(grpcServer)

	// Start listening
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", *port))
	if err != nil {
		logger.Fatal("Failed to listen", zap.Error(err))
	}

	// Handle shutdown
	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, syscall.SIGINT, syscall.SIGTERM)

	// Start server in goroutine
	go func() {
		logger.Info("gRPC server listening", zap.Int("port", *port))
		if err := grpcServer.Serve(lis); err != nil {
			logger.Fatal("gRPC server failed", zap.Error(err))
		}
	}()

	// Wait for shutdown signal
	<-shutdown
	logger.Info("Shutting down gracefully...")
	grpcServer.GracefulStop()
	logger.Info("Server stopped")
}

func setupLogger(level string) *zap.Logger {
	var zapLevel zapcore.Level
	switch level {
	case "debug":
		zapLevel = zapcore.DebugLevel
	case "warn":
		zapLevel = zapcore.WarnLevel
	case "error":
		zapLevel = zapcore.ErrorLevel
	default:
		zapLevel = zapcore.InfoLevel
	}

	config := zap.Config{
		Level:       zap.NewAtomicLevelAt(zapLevel),
		Development: false,
		Encoding:    "json",
		EncoderConfig: zapcore.EncoderConfig{
			TimeKey:        "ts",
			LevelKey:       "level",
			NameKey:        "logger",
			CallerKey:      "caller",
			MessageKey:     "msg",
			StacktraceKey:  "stacktrace",
			LineEnding:     zapcore.DefaultLineEnding,
			EncodeLevel:    zapcore.LowercaseLevelEncoder,
			EncodeTime:     zapcore.ISO8601TimeEncoder,
			EncodeDuration: zapcore.SecondsDurationEncoder,
			EncodeCaller:   zapcore.ShortCallerEncoder,
		},
		OutputPaths:      []string{"stdout"},
		ErrorOutputPaths: []string{"stderr"},
	}

	logger, err := config.Build()
	if err != nil {
		panic(err)
	}

	return logger
}

func loggingInterceptor(logger *zap.Logger) grpc.UnaryServerInterceptor {
	return func(
		ctx context.Context,
		req interface{},
		info *grpc.UnaryServerInfo,
		handler grpc.UnaryHandler,
	) (interface{}, error) {
		start := time.Now()

		logger.Debug("gRPC request",
			zap.String("method", info.FullMethod),
		)

		resp, err := handler(ctx, req)

		logger.Info("gRPC response",
			zap.String("method", info.FullMethod),
			zap.Duration("duration", time.Since(start)),
			zap.Error(err),
		)

		return resp, err
	}
}
