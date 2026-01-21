package server

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"fmt"
	"sync"
	"time"

	"github.com/collider/mpc-signer/internal/dkg"
	mpcSigning "github.com/collider/mpc-signer/internal/signing"
	"github.com/collider/mpc-signer/internal/storage"
	"github.com/google/uuid"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

const (
	sessionTimeout = 5 * time.Minute
	permitSecret   = "mpc-permit-secret-change-in-production" // TODO: Load from env
)

// MPCServer implements the gRPC MPC service
type MPCServer struct {
	UnimplementedMPCSignerServer

	storage        storage.Storage
	nodeID         string
	logger         *zap.Logger
	dkgHandler     *dkg.DKGHandler
	signingHandler *mpcSigning.SigningHandler
	sessions       sync.Map // sessionID -> metadata
}

// NewMPCServer creates a new MPC server instance
func NewMPCServer(store storage.Storage, nodeID string, logger *zap.Logger) *MPCServer {
	server := &MPCServer{
		storage:        store,
		nodeID:         nodeID,
		logger:         logger,
		dkgHandler:     dkg.NewDKGHandler(logger),
		signingHandler: mpcSigning.NewSigningHandler(logger),
	}

	// Start cleanup goroutine
	go server.cleanupExpiredSessions()

	return server
}

// Health implements health check
func (s *MPCServer) Health(ctx context.Context, req *HealthRequest) (*HealthResponse, error) {
	shares, _ := s.storage.ListShares()

	var activeSessions int
	s.sessions.Range(func(key, value interface{}) bool {
		activeSessions++
		return true
	})

	return &HealthResponse{
		Healthy:        true,
		Version:        "1.0.0",
		ActiveSessions: int32(activeSessions),
		StoredKeysets:  int32(len(shares)),
	}, nil
}

// StartDKG initiates a new DKG session
func (s *MPCServer) StartDKG(ctx context.Context, req *StartDKGRequest) (*StartDKGResponse, error) {
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

	return &StartDKGResponse{
		Success:   true,
		Round1Msg: round1Msg,
	}, nil
}

// DKGRound processes a DKG protocol round
func (s *MPCServer) DKGRound(ctx context.Context, req *DKGRoundRequest) (*DKGRoundResponse, error) {
	s.logger.Debug("Processing DKG round",
		zap.String("session_id", req.SessionId),
		zap.Int32("round", req.Round),
		zap.Int("incoming_messages", len(req.IncomingMessages)),
	)

	// Convert incoming messages
	var incomingMsgs [][]byte
	for _, msg := range req.IncomingMessages {
		incomingMsgs = append(incomingMsgs, msg.Payload)
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

	resp := &DKGRoundResponse{
		Success:     true,
		IsFinal:     isFinal,
		OutgoingMsg: outMsg,
	}

	if isFinal && result != nil {
		resp.Result = &DKGResult{
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
func (s *MPCServer) FinalizeDKG(ctx context.Context, req *FinalizeDKGRequest) (*FinalizeDKGResponse, error) {
	// In most cases, DKG finalizes automatically when rounds complete
	return &FinalizeDKGResponse{
		Success: true,
	}, nil
}

// StartSigning initiates a new signing session
func (s *MPCServer) StartSigning(ctx context.Context, req *StartSigningRequest) (*StartSigningResponse, error) {
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

	return &StartSigningResponse{
		Success:   true,
		Round1Msg: round1Msg,
	}, nil
}

// SigningRound processes a signing protocol round
func (s *MPCServer) SigningRound(ctx context.Context, req *SigningRoundRequest) (*SigningRoundResponse, error) {
	s.logger.Debug("Processing signing round",
		zap.String("session_id", req.SessionId),
		zap.Int32("round", req.Round),
	)

	// Convert incoming messages
	var incomingMsgs [][]byte
	for _, msg := range req.IncomingMessages {
		incomingMsgs = append(incomingMsgs, msg.Payload)
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

	resp := &SigningRoundResponse{
		Success:     true,
		IsFinal:     isFinal,
		OutgoingMsg: outMsg,
	}

	if isFinal && result != nil {
		resp.Result = &SigningResult{
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
func (s *MPCServer) FinalizeSigning(ctx context.Context, req *FinalizeSigningRequest) (*FinalizeSigningResponse, error) {
	return &FinalizeSigningResponse{
		Success: true,
	}, nil
}

// GetKeysetInfo returns information about a keyset
func (s *MPCServer) GetKeysetInfo(ctx context.Context, req *GetKeysetInfoRequest) (*GetKeysetInfoResponse, error) {
	share, err := s.storage.GetShare(req.KeysetId)
	if err != nil {
		return &GetKeysetInfoResponse{Exists: false}, nil
	}

	return &GetKeysetInfoResponse{
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
func (s *MPCServer) DeleteKeyset(ctx context.Context, req *DeleteKeysetRequest) (*DeleteKeysetResponse, error) {
	s.logger.Warn("Deleting keyset",
		zap.String("keyset_id", req.KeysetId),
		zap.String("reason", req.Reason),
	)

	if err := s.storage.DeleteShare(req.KeysetId); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to delete keyset: %v", err)
	}

	return &DeleteKeysetResponse{Success: true}, nil
}

// Helper types and methods

type sessionMeta struct {
	Type      string
	CreatedAt time.Time
	ExpiresAt time.Time
}

func (s *MPCServer) validatePermit(permit *SigningPermit, keysetID string, messageHash []byte) error {
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

func (s *MPCServer) computePermitSignature(permit *SigningPermit) []byte {
	h := hmac.New(sha256.New, []byte(permitSecret))
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

// Placeholder for generated gRPC code
// In production, this would be generated from mpc.proto

type UnimplementedMPCSignerServer struct{}

type HealthRequest struct{}
type HealthResponse struct {
	Healthy        bool
	Version        string
	ActiveSessions int32
	StoredKeysets  int32
}

type StartDKGRequest struct {
	SessionId    string
	WalletId     string
	Threshold    int32
	TotalParties int32
	PartyIndex   int32
}

type StartDKGResponse struct {
	Success   bool
	Error     string
	Round1Msg []byte
}

type DKGRoundRequest struct {
	SessionId        string
	Round            int32
	IncomingMessages []*PartyMessage
}

type PartyMessage struct {
	FromParty int32
	Payload   []byte
}

type DKGRoundResponse struct {
	Success     bool
	Error       string
	IsFinal     bool
	OutgoingMsg []byte
	Result      *DKGResult
}

type DKGResult struct {
	KeysetId        string
	PublicKey       []byte
	PublicKeyFull   []byte
	EthereumAddress string
}

type FinalizeDKGRequest struct {
	SessionId string
}

type FinalizeDKGResponse struct {
	Success bool
	Error   string
	Result  *DKGResult
}

type SigningPermit struct {
	TxRequestId          string
	WalletId             string
	KeysetId             string
	TxHash               []byte
	ExpiresAt            int64
	CoordinatorSignature []byte
}

type StartSigningRequest struct {
	SessionId   string
	KeysetId    string
	MessageHash []byte
	Permit      *SigningPermit
	PartyIndex  int32
}

type StartSigningResponse struct {
	Success   bool
	Error     string
	Round1Msg []byte
}

type SigningRoundRequest struct {
	SessionId        string
	Round            int32
	IncomingMessages []*PartyMessage
}

type SigningRoundResponse struct {
	Success     bool
	Error       string
	IsFinal     bool
	OutgoingMsg []byte
	Result      *SigningResult
}

type SigningResult struct {
	SignatureR    []byte
	SignatureS    []byte
	SignatureV    int32
	FullSignature []byte
}

type FinalizeSigningRequest struct {
	SessionId string
}

type FinalizeSigningResponse struct {
	Success bool
	Error   string
	Result  *SigningResult
}

type GetKeysetInfoRequest struct {
	KeysetId string
}

type GetKeysetInfoResponse struct {
	Exists          bool
	KeysetId        string
	WalletId        string
	PublicKey       []byte
	EthereumAddress string
	CreatedAt       int64
	LastUsedAt      int64
}

type DeleteKeysetRequest struct {
	KeysetId string
	Reason   string
}

type DeleteKeysetResponse struct {
	Success bool
	Error   string
}

func RegisterMPCSignerServer(s *grpc.Server, srv *MPCServer) {
	// TODO: Register actual generated gRPC service
	// pb.RegisterMPCSignerServer(s, srv)
}
