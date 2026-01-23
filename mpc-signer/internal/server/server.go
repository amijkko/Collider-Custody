package server

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/collider/mpc-signer/internal/dkg"
	mpcSigning "github.com/collider/mpc-signer/internal/signing"
	"github.com/collider/mpc-signer/internal/storage"
	"github.com/collider/mpc-signer/proto"
	"go.uber.org/zap"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	sessionTimeout = 5 * time.Minute
)

// Config holds server configuration
type Config struct {
	PermitSecret string // Secret for signing permits (required)
	NodeID       string // Unique node identifier
}

// LoadConfigFromEnv loads configuration from environment variables
func LoadConfigFromEnv() (*Config, error) {
	permitSecret := os.Getenv("MPC_PERMIT_SECRET")
	if permitSecret == "" {
		return nil, fmt.Errorf("MPC_PERMIT_SECRET environment variable is required")
	}
	if len(permitSecret) < 32 {
		return nil, fmt.Errorf("MPC_PERMIT_SECRET must be at least 32 characters")
	}

	nodeID := os.Getenv("MPC_NODE_ID")
	if nodeID == "" {
		nodeID = "bank-signer-1"
	}

	return &Config{
		PermitSecret: permitSecret,
		NodeID:       nodeID,
	}, nil
}

// MPCServer implements the gRPC MPC service
type MPCServer struct {
	proto.UnimplementedMPCSignerServer

	config         *Config
	storage        storage.Storage
	logger         *zap.Logger
	dkgHandler     *dkg.DKGHandler
	signingHandler *mpcSigning.SigningHandler
	sessions       sync.Map // sessionID -> metadata
}

// NewMPCServer creates a new MPC server instance
func NewMPCServer(config *Config, store storage.Storage, logger *zap.Logger) (*MPCServer, error) {
	if config == nil {
		return nil, fmt.Errorf("config is required")
	}
	if config.PermitSecret == "" {
		return nil, fmt.Errorf("permit secret is required")
	}

	server := &MPCServer{
		config:         config,
		storage:        store,
		logger:         logger,
		dkgHandler:     dkg.NewDKGHandler(logger),
		signingHandler: mpcSigning.NewSigningHandler(logger),
	}

	// Start cleanup goroutine
	go server.cleanupExpiredSessions()

	return server, nil
}

// Health implements health check
func (s *MPCServer) Health(ctx context.Context, req *proto.HealthRequest) (*proto.HealthResponse, error) {
	shares, _ := s.storage.ListShares()

	var activeSessions int
	s.sessions.Range(func(key, value interface{}) bool {
		activeSessions++
		return true
	})

	return &proto.HealthResponse{
		Healthy:        true,
		Version:        "1.0.0",
		ActiveSessions: int32(activeSessions),
		StoredKeysets:  int32(len(shares)),
	}, nil
}

// StartDKG initiates a new DKG session
func (s *MPCServer) StartDKG(ctx context.Context, req *proto.StartDKGRequest) (*proto.StartDKGResponse, error) {
	s.logger.Info("Starting DKG session",
		zap.String("session_id", req.SessionId),
		zap.String("wallet_id", req.WalletId),
		zap.Int32("threshold", req.Threshold),
		zap.Int32("total_parties", req.TotalParties),
	)

	// Validate parameters
	if req.Threshold < 1 || req.Threshold > req.TotalParties {
		return nil, status.Errorf(codes.InvalidArgument,
			"invalid threshold: %d of %d", req.Threshold, req.TotalParties)
	}

	// Start DKG session with tss-lib
	session, round1Msg, err := s.dkgHandler.StartSession(
		req.SessionId,
		req.WalletId,
		int(req.PartyIndex),
		int(req.Threshold),
		int(req.TotalParties),
	)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to start DKG: %v", err)
	}

	// Track session
	s.sessions.Store(req.SessionId, &sessionMeta{
		Type:      "dkg",
		CreatedAt: time.Now(),
		ExpiresAt: time.Now().Add(sessionTimeout),
	})

	_ = session // session is managed by dkgHandler

	return &proto.StartDKGResponse{
		Success:   true,
		Round1Msg: round1Msg,
	}, nil
}

// DKGRound processes a DKG protocol round
func (s *MPCServer) DKGRound(ctx context.Context, req *proto.DKGRoundRequest) (*proto.DKGRoundResponse, error) {
	s.logger.Debug("Processing DKG round",
		zap.String("session_id", req.SessionId),
		zap.Int32("round", req.Round),
		zap.Int("incoming_messages", len(req.IncomingMessages)),
	)

	// Convert incoming messages with sender information
	incomingMsgs := make([]dkg.IncomingMessage, 0, len(req.IncomingMessages))
	for _, msg := range req.IncomingMessages {
		incomingMsgs = append(incomingMsgs, dkg.IncomingMessage{
			FromPartyIndex: int(msg.FromParty),
			Payload:        msg.Payload,
		})
	}

	// Process the round
	outMsg, result, isFinal, err := s.dkgHandler.ProcessRound(
		req.SessionId,
		int(req.Round),
		incomingMsgs,
	)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "DKG round failed: %v", err)
	}

	resp := &proto.DKGRoundResponse{
		Success:     true,
		IsFinal:     isFinal,
		OutgoingMsg: outMsg,
	}

	if isFinal && result != nil {
		resp.Result = &proto.DKGResult{
			KeysetId:        result.KeysetID,
			PublicKey:       result.PublicKey,
			PublicKeyFull:   result.PublicKeyFull,
			EthereumAddress: result.EthereumAddress,
		}

		// Save the share
		shareData := &storage.ShareData{
			KeysetID:        result.KeysetID,
			WalletID:        "", // Will be set by coordinator
			PartyIndex:      0,  // This is the bank node
			Threshold:       2,  // TODO: Get from session
			TotalParties:    2,
			PublicKey:       result.PublicKey,
			EthereumAddress: result.EthereumAddress,
			ShareBytes:      result.SaveData,
			CreatedAt:       time.Now(),
			LastUsedAt:      time.Now(),
		}

		if err := s.storage.SaveShare(shareData); err != nil {
			s.logger.Error("Failed to save share", zap.Error(err))
			return nil, status.Errorf(codes.Internal, "failed to save share: %v", err)
		}

		s.logger.Info("DKG completed, share saved",
			zap.String("keyset_id", result.KeysetID),
			zap.String("address", result.EthereumAddress),
		)

		// Clean up session tracking
		s.sessions.Delete(req.SessionId)
	}

	return resp, nil
}

// FinalizeDKG finalizes the DKG session
func (s *MPCServer) FinalizeDKG(ctx context.Context, req *proto.FinalizeDKGRequest) (*proto.FinalizeDKGResponse, error) {
	// In most cases, DKG finalizes automatically when rounds complete
	return &proto.FinalizeDKGResponse{
		Success: true,
	}, nil
}

// StartSigning initiates a new signing session
func (s *MPCServer) StartSigning(ctx context.Context, req *proto.StartSigningRequest) (*proto.StartSigningResponse, error) {
	s.logger.Info("Starting signing session",
		zap.String("session_id", req.SessionId),
		zap.String("keyset_id", req.KeysetId),
		zap.String("message_hash", fmt.Sprintf("%x", req.MessageHash)),
	)

	// Validate permit
	if err := s.validatePermit(req.Permit, req.KeysetId, req.MessageHash); err != nil {
		return nil, status.Errorf(codes.PermissionDenied, "invalid permit: %v", err)
	}

	// Load share
	share, err := s.storage.GetShare(req.KeysetId)
	if err != nil {
		return nil, status.Errorf(codes.NotFound, "keyset not found: %v", err)
	}

	// Start signing session with tss-lib
	session, round1Msg, err := s.signingHandler.StartSession(
		req.SessionId,
		req.KeysetId,
		int(req.PartyIndex),
		req.MessageHash,
		share.ShareBytes,
		share.TotalParties,
		share.Threshold,
	)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to start signing: %v", err)
	}

	// Track session
	s.sessions.Store(req.SessionId, &sessionMeta{
		Type:      "signing",
		CreatedAt: time.Now(),
		ExpiresAt: time.Now().Add(sessionTimeout),
	})

	_ = session // session is managed by signingHandler

	// Update last used timestamp
	s.storage.UpdateShareLastUsed(req.KeysetId)

	return &proto.StartSigningResponse{
		Success:   true,
		Round1Msg: round1Msg,
	}, nil
}

// SigningRound processes a signing protocol round
func (s *MPCServer) SigningRound(ctx context.Context, req *proto.SigningRoundRequest) (*proto.SigningRoundResponse, error) {
	s.logger.Debug("Processing signing round",
		zap.String("session_id", req.SessionId),
		zap.Int32("round", req.Round),
	)

	// Convert incoming messages with sender information
	incomingMsgs := make([]mpcSigning.IncomingMessage, 0, len(req.IncomingMessages))
	for _, msg := range req.IncomingMessages {
		incomingMsgs = append(incomingMsgs, mpcSigning.IncomingMessage{
			FromPartyIndex: int(msg.FromParty),
			Payload:        msg.Payload,
		})
	}

	// Process the round
	outMsg, result, isFinal, err := s.signingHandler.ProcessRound(
		req.SessionId,
		int(req.Round),
		incomingMsgs,
	)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "signing round failed: %v", err)
	}

	resp := &proto.SigningRoundResponse{
		Success:     true,
		IsFinal:     isFinal,
		OutgoingMsg: outMsg,
	}

	if isFinal && result != nil {
		resp.Result = &proto.SigningResult{
			SignatureR:    result.SignatureR,
			SignatureS:    result.SignatureS,
			SignatureV:    int32(result.SignatureV),
			FullSignature: result.FullSignature,
		}

		s.logger.Info("Signing completed",
			zap.String("session_id", req.SessionId),
		)

		// Clean up session tracking
		s.sessions.Delete(req.SessionId)
	}

	return resp, nil
}

// FinalizeSigning finalizes the signing session
func (s *MPCServer) FinalizeSigning(ctx context.Context, req *proto.FinalizeSigningRequest) (*proto.FinalizeSigningResponse, error) {
	return &proto.FinalizeSigningResponse{
		Success: true,
	}, nil
}

// GetKeysetInfo returns information about a keyset
func (s *MPCServer) GetKeysetInfo(ctx context.Context, req *proto.GetKeysetInfoRequest) (*proto.GetKeysetInfoResponse, error) {
	share, err := s.storage.GetShare(req.KeysetId)
	if err != nil {
		return &proto.GetKeysetInfoResponse{Exists: false}, nil
	}

	return &proto.GetKeysetInfoResponse{
		Exists:          true,
		KeysetId:        share.KeysetID,
		WalletId:        share.WalletID,
		PublicKey:       share.PublicKey,
		EthereumAddress: share.EthereumAddress,
		CreatedAt:       share.CreatedAt.Unix(),
		LastUsedAt:      share.LastUsedAt.Unix(),
	}, nil
}

// DeleteKeyset removes a keyset (for key rotation)
func (s *MPCServer) DeleteKeyset(ctx context.Context, req *proto.DeleteKeysetRequest) (*proto.DeleteKeysetResponse, error) {
	s.logger.Warn("Deleting keyset",
		zap.String("keyset_id", req.KeysetId),
		zap.String("reason", req.Reason),
	)

	if err := s.storage.DeleteShare(req.KeysetId); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to delete keyset: %v", err)
	}

	return &proto.DeleteKeysetResponse{Success: true}, nil
}

// Helper types and methods

type sessionMeta struct {
	Type      string
	CreatedAt time.Time
	ExpiresAt time.Time
}

func (s *MPCServer) validatePermit(permit *proto.SigningPermit, keysetID string, messageHash []byte) error {
	if permit == nil {
		return fmt.Errorf("permit required")
	}

	// Check keyset ID matches
	if permit.KeysetId != keysetID {
		return fmt.Errorf("keyset ID mismatch")
	}

	// Check expiration
	if time.Now().Unix() > permit.ExpiresAt {
		return fmt.Errorf("permit expired")
	}

	// Verify coordinator signature
	expectedSig := s.computePermitSignature(permit)
	if !hmac.Equal(permit.CoordinatorSignature, expectedSig) {
		return fmt.Errorf("invalid coordinator signature")
	}

	return nil
}

func (s *MPCServer) computePermitSignature(permit *proto.SigningPermit) []byte {
	h := hmac.New(sha256.New, []byte(s.config.PermitSecret))
	h.Write([]byte(permit.TxRequestId))
	h.Write([]byte(permit.WalletId))
	h.Write([]byte(permit.KeysetId))
	h.Write(permit.TxHash)
	h.Write([]byte(fmt.Sprintf("%d", permit.ExpiresAt)))
	return h.Sum(nil)
}

func (s *MPCServer) cleanupExpiredSessions() {
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		now := time.Now()
		s.sessions.Range(func(key, value interface{}) bool {
			meta := value.(*sessionMeta)
			if now.After(meta.ExpiresAt) {
				sessionID := key.(string)
				s.sessions.Delete(key)

				// Also cleanup in handlers
				if meta.Type == "dkg" {
					s.dkgHandler.CleanupSession(sessionID)
				} else if meta.Type == "signing" {
					s.signingHandler.CleanupSession(sessionID)
				}

				s.logger.Debug("Cleaned up expired session",
					zap.String("session_id", sessionID),
				)
			}
			return true
		})
	}
}
