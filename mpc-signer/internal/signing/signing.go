package signing

import (
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

// SigningSession represents an active signing session
type SigningSession struct {
	SessionID   string
	KeysetID    string
	PartyIndex  int
	MessageHash []byte

	party     tss.Party
	outCh     chan tss.Message
	endCh     chan *common.SignatureData
	errCh     chan *tss.Error
	params    *tss.Parameters
	partyIDs  tss.SortedPartyIDs
	signature *common.SignatureData

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

	// Deserialize save data
	var saveData keygen.LocalPartySaveData
	if err := json.Unmarshal(saveDataBytes, &saveData); err != nil {
		return nil, nil, fmt.Errorf("failed to deserialize save data: %w", err)
	}

	// Create party IDs (must match DKG)
	partyIDs := make([]*tss.PartyID, totalParties)
	for i := 0; i < totalParties; i++ {
		partyIDs[i] = tss.NewPartyID(
			fmt.Sprintf("party-%d", i),
			fmt.Sprintf("Party %d", i),
			big.NewInt(int64(i)),
		)
	}

	sortedPartyIDs := tss.SortPartyIDs(partyIDs)
	thisPartyID := sortedPartyIDs[partyIndex]

	// For threshold signing, we need to select which parties participate
	// In 2-of-2, both parties always participate
	signingPartyIDs := sortedPartyIDs[:threshold+1] // t+1 parties for threshold t

	// Create peer context with signing parties
	ctx := tss.NewPeerContext(signingPartyIDs)

	// Create parameters for signing
	params := tss.NewParameters(tss.S256(), ctx, thisPartyID, len(signingPartyIDs), threshold)

	// Create channels
	outCh := make(chan tss.Message, 100)
	endCh := make(chan *common.SignatureData, 1)
	errCh := make(chan *tss.Error, 1)

	// Convert message hash to big.Int
	msgHashBigInt := new(big.Int).SetBytes(messageHash)

	// Create the signing party
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
		CreatedAt:   time.Now(),
		logger:      h.logger,
	}

	h.sessions[sessionID] = session

	// Start the party in a goroutine
	go func() {
		if err := party.Start(); err != nil {
			h.logger.Error("Failed to start signing party", zap.Error(err))
			errCh <- &tss.Error{Cause: err}
		}
	}()

	// Collect first round messages
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
	incomingMessages [][]byte,
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

	// Parse and process incoming messages
	for _, msgBytes := range incomingMessages {
		msg, err := tss.ParseWireMessage(msgBytes, session.partyIDs[0], session.params.Parties().IDs()[0].KeyInt() != nil)
		if err != nil {
			h.logger.Warn("Failed to parse message", zap.Error(err))
			continue
		}

		// Route the message to the party
		go func(m tss.ParsedMessage) {
			if _, err := session.party.Update(m); err != nil {
				h.logger.Warn("Failed to update party", zap.Error(err))
			}
		}(msg)
	}

	// Check if signing is complete
	select {
	case sigData := <-session.endCh:
		// Signing complete!
		session.signature = sigData
		result := session.buildResult()

		h.logger.Info("Signing complete",
			zap.String("session_id", sessionID),
			zap.String("r", fmt.Sprintf("%x", result.SignatureR)),
		)

		// Cleanup
		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()

		return nil, result, true, nil

	case err := <-session.errCh:
		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()
		return nil, nil, false, fmt.Errorf("signing error: %v", err)

	default:
		// Collect outgoing messages for next round
		outMsg, err := session.collectOutgoingMessages()
		if err != nil {
			return nil, nil, false, err
		}
		return outMsg, nil, false, nil
	}
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

// collectOutgoingMessages collects messages from the outCh
func (s *SigningSession) collectOutgoingMessages() ([]byte, error) {
	var messages [][]byte

	// Non-blocking collection of available messages
	timeout := time.After(100 * time.Millisecond)
	for {
		select {
		case msg := <-s.outCh:
			wireBytes, _, err := msg.WireBytes()
			if err != nil {
				s.logger.Warn("Failed to serialize message", zap.Error(err))
				continue
			}
			messages = append(messages, wireBytes)
		case <-timeout:
			goto done
		}
	}

done:
	if len(messages) == 0 {
		return nil, nil
	}

	return json.Marshal(messages)
}

// buildResult creates the signing result
func (s *SigningSession) buildResult() *SigningResult {
	if s.signature == nil {
		return nil
	}

	// Get R, S, V from signature data
	r := s.signature.R
	sigS := s.signature.S
	v := s.signature.SignatureRecovery

	// Pad R and S to 32 bytes
	rBytes := padToBytes(r, 32)
	sBytes := padToBytes(sigS, 32)

	// Create full signature (65 bytes: r || s || v)
	fullSig := make([]byte, 65)
	copy(fullSig[0:32], rBytes)
	copy(fullSig[32:64], sBytes)

	// Ethereum uses v = 27 or 28 (not 0 or 1)
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

// padToBytes pads a byte slice to the specified length
func padToBytes(data []byte, length int) []byte {
	if len(data) >= length {
		return data[:length]
	}
	result := make([]byte, length)
	copy(result[length-len(data):], data)
	return result
}

