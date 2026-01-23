//go:build tss
// +build tss

package signing

import (
	"crypto/ecdsa"
	"encoding/json"
	"fmt"
	"math/big"
	"sync"
	"time"

	"github.com/bnb-chain/tss-lib/v2/common"
	"github.com/bnb-chain/tss-lib/v2/ecdsa/keygen"
	"github.com/bnb-chain/tss-lib/v2/ecdsa/signing"
	"github.com/bnb-chain/tss-lib/v2/tss"
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

	party     tss.Party
	outCh     chan tss.Message
	endCh     chan common.SignatureData
	errCh     chan *tss.Error
	params    *tss.Parameters
	partyIDs  tss.SortedPartyIDs
	signature *common.SignatureData // Stored as pointer
	publicKey *ecdsa.PublicKey      // For signature verification

	mu sync.Mutex

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
	)

	var saveData keygen.LocalPartySaveData
	if err := json.Unmarshal(saveDataBytes, &saveData); err != nil {
		return nil, nil, fmt.Errorf("failed to deserialize save data: %w", err)
	}

	// Extract public key for signature verification
	var publicKey *ecdsa.PublicKey
	if saveData.ECDSAPub != nil {
		publicKey = saveData.ECDSAPub.ToECDSAPubKey()
	}

	// Create party IDs with 1-indexed keys (tss-lib requires Key > 0)
	partyIDs := make([]*tss.PartyID, totalParties)
	for i := 0; i < totalParties; i++ {
		partyIDs[i] = tss.NewPartyID(
			fmt.Sprintf("party-%d", i),
			fmt.Sprintf("Party %d", i),
			big.NewInt(int64(i+1)), // 1-indexed for tss-lib
		)
	}

	sortedPartyIDs := tss.SortPartyIDs(partyIDs)
	thisPartyID := sortedPartyIDs[partyIndex]

	signingPartyIDs := sortedPartyIDs[:threshold+1]
	ctx := tss.NewPeerContext(signingPartyIDs)
	params := tss.NewParameters(tss.S256(), ctx, thisPartyID, len(signingPartyIDs), threshold)

	outCh := make(chan tss.Message, 100)
	endCh := make(chan common.SignatureData, 1)
	errCh := make(chan *tss.Error, 1)

	msgHashBigInt := new(big.Int).SetBytes(messageHash)
	party := signing.NewLocalParty(msgHashBigInt, params, saveData, outCh, endCh)

	session := &SigningSession{
		SessionID:   sessionID,
		KeysetID:    keysetID,
		PartyIndex:  partyIndex,
		MessageHash: messageHash,
		party:       party,
		outCh:       outCh,
		endCh:       endCh,
		errCh:       errCh,
		params:      params,
		partyIDs:    sortedPartyIDs,
		publicKey:   publicKey,
		CreatedAt:   time.Now(),
		logger:      h.logger,
	}

	h.sessions[sessionID] = session

	go func() {
		if err := party.Start(); err != nil {
			h.logger.Error("Failed to start signing party", zap.Error(err))
			errCh <- err
		}
	}()

	firstRoundMsg, err := session.collectOutgoingMessages()
	if err != nil {
		delete(h.sessions, sessionID)
		return nil, nil, fmt.Errorf("failed to collect first round messages: %w", err)
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

	h.logger.Debug("Processing signing round",
		zap.String("session_id", sessionID),
		zap.Int("round", round),
		zap.Int("incoming_count", len(incomingMessages)),
	)

	// Process incoming messages sequentially to avoid race conditions
	for _, incoming := range incomingMessages {
		// Validate party index
		if incoming.FromPartyIndex < 0 || incoming.FromPartyIndex >= len(session.partyIDs) {
			h.logger.Warn("Invalid party index in message",
				zap.Int("from_party", incoming.FromPartyIndex),
				zap.Int("total_parties", len(session.partyIDs)),
			)
			continue
		}

		fromPartyID := session.partyIDs[incoming.FromPartyIndex]

		// Parse the wire message with correct sender
		parsedMsg, err := tss.ParseWireMessage(incoming.Payload, fromPartyID, true)
		if err != nil {
			h.logger.Warn("Failed to parse message",
				zap.Error(err),
				zap.Int("from_party", incoming.FromPartyIndex),
			)
			continue
		}

		// Update party state (sequential, no goroutine to avoid race)
		if _, err := session.party.Update(parsedMsg); err != nil {
			h.logger.Warn("Failed to update party",
				zap.Error(err),
				zap.Int("from_party", incoming.FromPartyIndex),
			)
		}
	}

	// Check for completion or errors with a small timeout to allow async processing
	select {
	case sigData := <-session.endCh:
		session.signature = &sigData
		result := session.buildResult()

		// Verify signature before returning
		if session.publicKey != nil {
			if err := session.verifySignature(result); err != nil {
				h.logger.Error("Signature verification failed",
					zap.String("session_id", sessionID),
					zap.Error(err),
				)
				h.mu.Lock()
				delete(h.sessions, sessionID)
				h.mu.Unlock()
				return nil, nil, false, fmt.Errorf("signature verification failed: %w", err)
			}
			h.logger.Debug("Signature verified successfully",
				zap.String("session_id", sessionID),
			)
		}

		h.logger.Info("Signing complete",
			zap.String("session_id", sessionID),
			zap.String("r", fmt.Sprintf("%x", result.SignatureR)),
		)

		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()

		return nil, result, true, nil

	case err := <-session.errCh:
		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()
		return nil, nil, false, fmt.Errorf("signing error: %v", err)

	case <-time.After(50 * time.Millisecond):
		// Give async tss-lib processing a moment to complete
	}

	// Collect any outgoing messages
	outMsg, err := session.collectOutgoingMessages()
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

func (s *SigningSession) collectOutgoingMessages() ([]byte, error) {
	var messages []OutgoingMessage

	// First, try to get at least one message with a longer timeout
	select {
	case msg := <-s.outCh:
		outMsg, err := s.convertTSSMessage(msg)
		if err != nil {
			s.logger.Warn("Failed to convert message", zap.Error(err))
		} else {
			messages = append(messages, outMsg...)
		}
	case <-time.After(500 * time.Millisecond):
		// No messages available yet
		return nil, nil
	}

	// Now collect any additional messages that are immediately available
	for {
		select {
		case msg := <-s.outCh:
			outMsg, err := s.convertTSSMessage(msg)
			if err != nil {
				s.logger.Warn("Failed to convert message", zap.Error(err))
				continue
			}
			messages = append(messages, outMsg...)
		default:
			// No more messages immediately available
			goto done
		}
	}

done:
	if len(messages) == 0 {
		return nil, nil
	}

	return json.Marshal(messages)
}

// convertTSSMessage converts a tss.Message to OutgoingMessage(s)
func (s *SigningSession) convertTSSMessage(msg tss.Message) ([]OutgoingMessage, error) {
	wireBytes, routing, err := msg.WireBytes()
	if err != nil {
		return nil, fmt.Errorf("failed to serialize message: %w", err)
	}

	var messages []OutgoingMessage

	if routing.IsBroadcast {
		// Broadcast message goes to all parties
		messages = append(messages, OutgoingMessage{
			ToPartyIndex: -1,
			IsBroadcast:  true,
			Payload:      wireBytes,
		})
	} else {
		// Point-to-point messages
		for _, toParty := range routing.To {
			// Find the party index
			toIndex := -1
			for i, pid := range s.partyIDs {
				if pid.Id == toParty.Id {
					toIndex = i
					break
				}
			}
			if toIndex >= 0 {
				messages = append(messages, OutgoingMessage{
					ToPartyIndex: toIndex,
					IsBroadcast:  false,
					Payload:      wireBytes,
				})
			}
		}
	}

	return messages, nil
}

func (s *SigningSession) buildResult() *SigningResult {
	if s.signature == nil {
		return nil
	}

	r := s.signature.R
	sigS := s.signature.S
	v := s.signature.SignatureRecovery

	rBytes := padToBytes(r, 32)
	sBytes := padToBytes(sigS, 32)

	fullSig := make([]byte, 65)
	copy(fullSig[0:32], rBytes)
	copy(fullSig[32:64], sBytes)

	vByte := byte(27)
	if v != nil && len(v) > 0 && v[0] == 1 {
		vByte = 28
	}
	fullSig[64] = vByte

	return &SigningResult{
		SignatureR:    rBytes,
		SignatureS:    sBytes,
		SignatureV:    int(vByte),
		FullSignature: fullSig,
	}
}

func padToBytes(data []byte, length int) []byte {
	if len(data) >= length {
		return data[:length]
	}
	result := make([]byte, length)
	copy(result[length-len(data):], data)
	return result
}

// verifySignature verifies the ECDSA signature against the message hash and public key
func (s *SigningSession) verifySignature(result *SigningResult) error {
	if s.publicKey == nil {
		return fmt.Errorf("no public key available for verification")
	}
	if result == nil {
		return fmt.Errorf("no signature result to verify")
	}

	r := new(big.Int).SetBytes(result.SignatureR)
	sigS := new(big.Int).SetBytes(result.SignatureS)

	// Verify the signature
	if !ecdsa.Verify(s.publicKey, s.MessageHash, r, sigS) {
		return fmt.Errorf("ECDSA signature verification failed")
	}

	return nil
}
