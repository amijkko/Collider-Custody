package dkg

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"go.uber.org/zap"
)

// DKGSession represents an active DKG session
type DKGSession struct {
	SessionID    string
	WalletID     string
	PartyIndex   int
	Threshold    int
	TotalParties int

	round        int
	completed    bool
	mu           sync.Mutex
	CreatedAt    time.Time
	logger       *zap.Logger
}

// DKGResult contains the result of a successful DKG
type DKGResult struct {
	KeysetID        string `json:"keyset_id"`
	PublicKey       []byte `json:"public_key"`        // Compressed (33 bytes)
	PublicKeyFull   []byte `json:"public_key_full"`   // Uncompressed (65 bytes)
	EthereumAddress string `json:"ethereum_address"`
	SaveData        []byte `json:"save_data"` // Serialized save data
}

// DKGHandler manages DKG sessions
type DKGHandler struct {
	sessions map[string]*DKGSession
	mu       sync.RWMutex
	logger   *zap.Logger
}

// NewDKGHandler creates a new DKG handler
func NewDKGHandler(logger *zap.Logger) *DKGHandler {
	return &DKGHandler{
		sessions: make(map[string]*DKGSession),
		logger:   logger,
	}
}

// StartSession initializes a new DKG session
func (h *DKGHandler) StartSession(
	sessionID string,
	walletID string,
	partyIndex int,
	threshold int,
	totalParties int,
) (*DKGSession, []byte, error) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if _, exists := h.sessions[sessionID]; exists {
		return nil, nil, fmt.Errorf("session already exists: %s", sessionID)
	}

	h.logger.Info("Starting DKG session",
		zap.String("session_id", sessionID),
		zap.String("wallet_id", walletID),
		zap.Int("party_index", partyIndex),
		zap.Int("threshold", threshold),
		zap.Int("total_parties", totalParties),
	)

	session := &DKGSession{
		SessionID:    sessionID,
		WalletID:     walletID,
		PartyIndex:   partyIndex,
		Threshold:    threshold,
		TotalParties: totalParties,
		round:        0,
		CreatedAt:    time.Now(),
		logger:       h.logger,
	}

	h.sessions[sessionID] = session

	// Generate first round message (simulated)
	round1Msg := make([]byte, 64)
	rand.Read(round1Msg)

	return session, round1Msg, nil
}

// ProcessRound processes incoming messages and returns outgoing messages
func (h *DKGHandler) ProcessRound(
	sessionID string,
	round int,
	incomingMessages [][]byte,
) ([]byte, *DKGResult, bool, error) {
	h.mu.RLock()
	session, exists := h.sessions[sessionID]
	h.mu.RUnlock()

	if !exists {
		return nil, nil, false, fmt.Errorf("session not found: %s", sessionID)
	}

	session.mu.Lock()
	defer session.mu.Unlock()

	h.logger.Debug("Processing DKG round",
		zap.String("session_id", sessionID),
		zap.Int("round", round),
		zap.Int("incoming_count", len(incomingMessages)),
	)

	session.round = round

	// Simulate DKG completion after round 3
	if round >= 3 {
		// Generate a key pair (simulated)
		// Using P256 for simulation (in production, use secp256k1 from tss-lib)
		privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			return nil, nil, false, fmt.Errorf("failed to generate key: %w", err)
		}

		// Serialize public key
		pubKeyCompressed := serializeCompressedPublicKey(&privateKey.PublicKey)
		pubKeyFull := serializeUncompressedPublicKey(&privateKey.PublicKey)

		// Derive Ethereum address
		address := publicKeyToAddress(&privateKey.PublicKey)

		// Generate keyset ID
		keysetID := fmt.Sprintf("keyset-%s-%d", sessionID[:8], time.Now().Unix())

		// Serialize save data (simulated)
		saveData := map[string]interface{}{
			"keyset_id": keysetID,
			"party_index": session.PartyIndex,
			"threshold": session.Threshold,
			"total_parties": session.TotalParties,
			"private_key_share": "encrypted_share_data", // In production, this would be the actual share
		}
		saveDataBytes, _ := json.Marshal(saveData)

		result := &DKGResult{
			KeysetID:        keysetID,
			PublicKey:       pubKeyCompressed,
			PublicKeyFull:   pubKeyFull,
			EthereumAddress: address,
			SaveData:        saveDataBytes,
		}

		session.completed = true

		h.logger.Info("DKG complete",
			zap.String("session_id", sessionID),
			zap.String("address", result.EthereumAddress),
		)

		// Cleanup
		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()

		return nil, result, true, nil
	}

	// Generate outgoing message for next round
	outMsg := make([]byte, 64)
	rand.Read(outMsg)
	return outMsg, nil, false, nil
}

// GetSession returns a session by ID
func (h *DKGHandler) GetSession(sessionID string) (*DKGSession, bool) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	session, exists := h.sessions[sessionID]
	return session, exists
}

// CleanupSession removes a session
func (h *DKGHandler) CleanupSession(sessionID string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	delete(h.sessions, sessionID)
}

// Helper functions

func serializeCompressedPublicKey(pub *ecdsa.PublicKey) []byte {
	// Compressed format: 0x02 or 0x03 prefix + 32 bytes X coordinate
	prefix := byte(0x02)
	if pub.Y.Bit(0) == 1 {
		prefix = 0x03
	}
	result := make([]byte, 33)
	result[0] = prefix
	pub.X.FillBytes(result[1:])
	return result
}

func serializeUncompressedPublicKey(pub *ecdsa.PublicKey) []byte {
	// Uncompressed format: 0x04 prefix + 32 bytes X + 32 bytes Y
	result := make([]byte, 65)
	result[0] = 0x04
	pub.X.FillBytes(result[1:33])
	pub.Y.FillBytes(result[33:65])
	return result
}

func publicKeyToAddress(pub *ecdsa.PublicKey) string {
	// Simplified Ethereum address derivation
	// In production, use Keccak256 hash
	pubBytes := serializeUncompressedPublicKey(pub)[1:]
	hash := sha256.Sum256(pubBytes)
	address := hash[len(hash)-20:]
	return fmt.Sprintf("0x%x", address)
}
