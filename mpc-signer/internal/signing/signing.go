//go:build !tss
// +build !tss

package signing

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"math/big"
	"sync"
	"time"

	"go.uber.org/zap"
)

// IncomingMessage represents a message from another party
type IncomingMessage struct {
	FromPartyIndex int
	Payload        []byte
}

// OutgoingMessage represents a message to be sent to other parties
type OutgoingMessage struct {
	ToPartyIndex int  // -1 means broadcast to all
	IsBroadcast  bool // true if message should go to all parties
	Payload      []byte
}

// SigningSession represents an active signing session
type SigningSession struct {
	SessionID   string
	KeysetID    string
	PartyIndex  int
	MessageHash []byte

	privateKey *ecdsa.PrivateKey
	outCh      chan []byte
	endCh      chan *SigningResult
	errCh      chan error

	mu    sync.Mutex
	round int

	CreatedAt time.Time
	logger    *zap.Logger
}

// SigningResult contains the result of a successful signing
type SigningResult struct {
	SignatureR    []byte `json:"signature_r"`    // 32 bytes
	SignatureS    []byte `json:"signature_s"`    // 32 bytes
	SignatureV    int    `json:"signature_v"`    // Recovery ID
	FullSignature []byte `json:"full_signature"` // 65 bytes (r || s || v)
}

// SigningHandler manages signing sessions
type SigningHandler struct {
	sessions map[string]*SigningSession
	mu       sync.RWMutex
	logger   *zap.Logger
}

// NewSigningHandler creates a new signing handler
func NewSigningHandler(logger *zap.Logger) *SigningHandler {
	return &SigningHandler{
		sessions: make(map[string]*SigningSession),
		logger:   logger,
	}
}

// StartSession initializes a new signing session
func (h *SigningHandler) StartSession(
	sessionID string,
	keysetID string,
	partyIndex int,
	messageHash []byte,
	saveDataBytes []byte,
	totalParties int,
	threshold int,
) (*SigningSession, []byte, error) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if _, exists := h.sessions[sessionID]; exists {
		return nil, nil, fmt.Errorf("session already exists: %s", sessionID)
	}

	h.logger.Info("Starting signing session",
		zap.String("session_id", sessionID),
		zap.String("keyset_id", keysetID),
		zap.Int("party_index", partyIndex),
		zap.String("message_hash", fmt.Sprintf("%x", messageHash)),
		zap.Int("threshold", threshold),
		zap.Int("total_parties", totalParties),
	)

	privateKey, err := parsePrivateKey(saveDataBytes)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to parse save data: %w", err)
	}

	outCh := make(chan []byte, 100)
	endCh := make(chan *SigningResult, 1)
	errCh := make(chan error, 1)

	session := &SigningSession{
		SessionID:   sessionID,
		KeysetID:    keysetID,
		PartyIndex:  partyIndex,
		MessageHash: messageHash,
		privateKey:  privateKey,
		outCh:       outCh,
		endCh:       endCh,
		errCh:       errCh,
		CreatedAt:   time.Now(),
		logger:      h.logger,
	}

	h.sessions[sessionID] = session

	firstRoundMsg, err := session.generateRoundMessage()
	if err != nil {
		delete(h.sessions, sessionID)
		return nil, nil, fmt.Errorf("failed to generate round message: %w", err)
	}

	return session, firstRoundMsg, nil
}

// ProcessRound processes incoming messages and returns outgoing messages or result
func (h *SigningHandler) ProcessRound(
	sessionID string,
	round int,
	incomingMessages []IncomingMessage,
) ([]byte, *SigningResult, bool, error) {
	h.mu.RLock()
	session, exists := h.sessions[sessionID]
	h.mu.RUnlock()

	if !exists {
		return nil, nil, false, fmt.Errorf("session not found: %s", sessionID)
	}

	session.mu.Lock()
	defer session.mu.Unlock()
	session.round = round

	h.logger.Debug("Processing signing round",
		zap.String("session_id", sessionID),
		zap.Int("round", round),
		zap.Int("incoming_count", len(incomingMessages)),
	)

	if round >= 2 {
		result, err := session.signMessage()
		if err != nil {
			h.mu.Lock()
			delete(h.sessions, sessionID)
			h.mu.Unlock()
			return nil, nil, false, err
		}

		h.logger.Info("Signing complete",
			zap.String("session_id", sessionID),
			zap.String("r", fmt.Sprintf("%x", result.SignatureR)),
		)

		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()

		return nil, result, true, nil
	}

	outMsg, err := session.generateRoundMessage()
	if err != nil {
		return nil, nil, false, err
	}
	return outMsg, nil, false, nil
}

// GetSession returns a session by ID
func (h *SigningHandler) GetSession(sessionID string) (*SigningSession, bool) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	session, exists := h.sessions[sessionID]
	return session, exists
}

// CleanupSession removes a session
func (h *SigningHandler) CleanupSession(sessionID string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	delete(h.sessions, sessionID)
}

func (s *SigningSession) generateRoundMessage() ([]byte, error) {
	msg := make([]byte, 64)
	if _, err := rand.Read(msg); err != nil {
		return nil, fmt.Errorf("failed to generate round message: %w", err)
	}
	s.outCh <- msg
	return json.Marshal([][]byte{msg})
}

func (s *SigningSession) signMessage() (*SigningResult, error) {
	if s.privateKey == nil {
		return nil, fmt.Errorf("missing private key")
	}

	r, sigS, err := ecdsa.Sign(rand.Reader, s.privateKey, s.MessageHash)
	if err != nil {
		return nil, fmt.Errorf("failed to sign message: %w", err)
	}

	rBytes := padToBytes(r, 32)
	sBytes := padToBytes(sigS, 32)

	fullSig := make([]byte, 65)
	copy(fullSig[0:32], rBytes)
	copy(fullSig[32:64], sBytes)

	vByte := byte(27)
	fullSig[64] = vByte

	return &SigningResult{
		SignatureR:    rBytes,
		SignatureS:    sBytes,
		SignatureV:    int(vByte),
		FullSignature: fullSig,
	}, nil
}

func parsePrivateKey(saveDataBytes []byte) (*ecdsa.PrivateKey, error) {
	var saveData map[string]interface{}
	if err := json.Unmarshal(saveDataBytes, &saveData); err != nil {
		return nil, fmt.Errorf("failed to deserialize save data: %w", err)
	}

	dValueRaw, ok := saveData["private_key_d_b64"].(string)
	if !ok || dValueRaw == "" {
		return nil, fmt.Errorf("save data missing private key")
	}

	dBytes, err := base64.StdEncoding.DecodeString(dValueRaw)
	if err != nil {
		return nil, fmt.Errorf("failed to decode private key: %w", err)
	}

	curveName, _ := saveData["curve"].(string)
	curve := elliptic.P256()
	if curveName != "" && curveName != "P-256" {
		return nil, fmt.Errorf("unsupported curve: %s", curveName)
	}

	d := new(big.Int).SetBytes(dBytes)
	x, y := curve.ScalarBaseMult(dBytes)

	return &ecdsa.PrivateKey{
		PublicKey: ecdsa.PublicKey{
			Curve: curve,
			X:     x,
			Y:     y,
		},
		D: d,
	}, nil
}

// padToBytes pads a byte slice to the specified length
func padToBytes(data *big.Int, length int) []byte {
	if data == nil {
		return make([]byte, length)
	}
	src := data.Bytes()
	if len(src) >= length {
		return src[:length]
	}
	result := make([]byte, length)
	copy(result[length-len(src):], src)
	return result
}
