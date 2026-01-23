package server

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/collider/mpc-signer/internal/storage"
	"github.com/collider/mpc-signer/proto"
	"go.uber.org/zap"
)

func TestLoadConfigFromEnv(t *testing.T) {
	tests := []struct {
		name          string
		envVars       map[string]string
		expectError   bool
		expectedID    string
	}{
		{
			name: "valid config",
			envVars: map[string]string{
				"MPC_PERMIT_SECRET": "this-is-a-very-long-secret-for-testing-purposes-123",
				"MPC_NODE_ID":       "test-node",
			},
			expectError: false,
			expectedID:  "test-node",
		},
		{
			name: "missing permit secret",
			envVars: map[string]string{
				"MPC_NODE_ID": "test-node",
			},
			expectError: true,
		},
		{
			name: "short permit secret",
			envVars: map[string]string{
				"MPC_PERMIT_SECRET": "short",
				"MPC_NODE_ID":       "test-node",
			},
			expectError: true,
		},
		{
			name: "default node id",
			envVars: map[string]string{
				"MPC_PERMIT_SECRET": "this-is-a-very-long-secret-for-testing-purposes-123",
			},
			expectError: false,
			expectedID:  "bank-signer-1",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Clear environment
			os.Unsetenv("MPC_PERMIT_SECRET")
			os.Unsetenv("MPC_NODE_ID")

			// Set test environment
			for k, v := range tt.envVars {
				os.Setenv(k, v)
			}

			config, err := LoadConfigFromEnv()

			if tt.expectError {
				if err == nil {
					t.Errorf("expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("unexpected error: %v", err)
				return
			}

			if config.NodeID != tt.expectedID {
				t.Errorf("expected node ID %s, got %s", tt.expectedID, config.NodeID)
			}
		})
	}
}

func TestNewMPCServer(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	// Create temp directory for storage
	tempDir, err := os.MkdirTemp("", "mpc-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	store, err := storage.NewFileStorage(tempDir, "test-password")
	if err != nil {
		t.Fatalf("failed to create storage: %v", err)
	}

	tests := []struct {
		name        string
		config      *Config
		expectError bool
	}{
		{
			name:        "nil config",
			config:      nil,
			expectError: true,
		},
		{
			name: "empty permit secret",
			config: &Config{
				PermitSecret: "",
				NodeID:       "test",
			},
			expectError: true,
		},
		{
			name: "valid config",
			config: &Config{
				PermitSecret: "valid-secret-for-testing",
				NodeID:       "test-node",
			},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server, err := NewMPCServer(tt.config, store, logger)

			if tt.expectError {
				if err == nil {
					t.Errorf("expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("unexpected error: %v", err)
				return
			}

			if server == nil {
				t.Error("server should not be nil")
			}
		})
	}
}

func TestMPCServerHealth(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	tempDir, err := os.MkdirTemp("", "mpc-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	store, err := storage.NewFileStorage(tempDir, "test-password")
	if err != nil {
		t.Fatalf("failed to create storage: %v", err)
	}

	config := &Config{
		PermitSecret: "valid-secret-for-testing",
		NodeID:       "test-node",
	}

	server, err := NewMPCServer(config, store, logger)
	if err != nil {
		t.Fatalf("failed to create server: %v", err)
	}

	ctx := context.Background()
	resp, err := server.Health(ctx, &proto.HealthRequest{})
	if err != nil {
		t.Fatalf("health check failed: %v", err)
	}

	if !resp.Healthy {
		t.Error("server should be healthy")
	}

	if resp.Version == "" {
		t.Error("version should not be empty")
	}
}

func TestMPCServerStartDKG(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	tempDir, err := os.MkdirTemp("", "mpc-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	store, err := storage.NewFileStorage(tempDir, "test-password")
	if err != nil {
		t.Fatalf("failed to create storage: %v", err)
	}

	config := &Config{
		PermitSecret: "valid-secret-for-testing",
		NodeID:       "test-node",
	}

	server, err := NewMPCServer(config, store, logger)
	if err != nil {
		t.Fatalf("failed to create server: %v", err)
	}

	ctx := context.Background()

	tests := []struct {
		name        string
		request     *proto.StartDKGRequest
		expectError bool
	}{
		{
			name: "valid request",
			request: &proto.StartDKGRequest{
				SessionId:    "test-session-1",
				WalletId:     "test-wallet-1",
				Threshold:    1,
				TotalParties: 2,
				PartyIndex:   0,
			},
			expectError: false,
		},
		{
			name: "invalid threshold",
			request: &proto.StartDKGRequest{
				SessionId:    "test-session-2",
				WalletId:     "test-wallet-2",
				Threshold:    3,
				TotalParties: 2,
				PartyIndex:   0,
			},
			expectError: true,
		},
		{
			name: "zero threshold",
			request: &proto.StartDKGRequest{
				SessionId:    "test-session-3",
				WalletId:     "test-wallet-3",
				Threshold:    0,
				TotalParties: 2,
				PartyIndex:   0,
			},
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := server.StartDKG(ctx, tt.request)

			if tt.expectError {
				if err == nil {
					t.Errorf("expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("unexpected error: %v", err)
				return
			}

			if !resp.Success {
				t.Error("expected success")
			}
		})
	}
}

func TestSessionMeta(t *testing.T) {
	meta := &sessionMeta{
		Type:      "dkg",
		CreatedAt: time.Now(),
		ExpiresAt: time.Now().Add(5 * time.Minute),
	}

	if meta.Type != "dkg" {
		t.Errorf("expected type 'dkg', got '%s'", meta.Type)
	}

	if meta.ExpiresAt.Before(meta.CreatedAt) {
		t.Error("expires at should be after created at")
	}
}

func TestValidatePermit(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	tempDir, err := os.MkdirTemp("", "mpc-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	store, err := storage.NewFileStorage(tempDir, "test-password")
	if err != nil {
		t.Fatalf("failed to create storage: %v", err)
	}

	config := &Config{
		PermitSecret: "valid-secret-for-testing-purposes",
		NodeID:       "test-node",
	}

	server, err := NewMPCServer(config, store, logger)
	if err != nil {
		t.Fatalf("failed to create server: %v", err)
	}

	tests := []struct {
		name        string
		permit      *proto.SigningPermit
		keysetID    string
		messageHash []byte
		expectError bool
	}{
		{
			name:        "nil permit",
			permit:      nil,
			keysetID:    "keyset-1",
			messageHash: []byte("hash"),
			expectError: true,
		},
		{
			name: "keyset mismatch",
			permit: &proto.SigningPermit{
				KeysetId:  "keyset-wrong",
				ExpiresAt: time.Now().Add(time.Hour).Unix(),
			},
			keysetID:    "keyset-1",
			messageHash: []byte("hash"),
			expectError: true,
		},
		{
			name: "expired permit",
			permit: &proto.SigningPermit{
				KeysetId:  "keyset-1",
				ExpiresAt: time.Now().Add(-time.Hour).Unix(),
			},
			keysetID:    "keyset-1",
			messageHash: []byte("hash"),
			expectError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := server.validatePermit(tt.permit, tt.keysetID, tt.messageHash)

			if tt.expectError {
				if err == nil {
					t.Errorf("expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}
