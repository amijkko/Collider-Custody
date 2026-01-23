//go:build tss
// +build tss

package dkg

import (
	"crypto/ecdsa"
	"encoding/json"
	"fmt"
	"math/big"
	"sync"
	"time"

	"github.com/bnb-chain/tss-lib/v2/ecdsa/keygen"
	"github.com/bnb-chain/tss-lib/v2/tss"
	"go.uber.org/zap"
	"golang.org/x/crypto/sha3"
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

// DKGSession represents an active DKG session
type DKGSession struct {
	SessionID    string
	WalletID     string
	PartyIndex   int
	Threshold    int
	TotalParties int

	party    tss.Party
	outCh    chan tss.Message
	endCh    chan keygen.LocalPartySaveData
	errCh    chan *tss.Error
	params   *tss.Parameters
	partyIDs tss.SortedPartyIDs

	mu sync.Mutex

	CreatedAt time.Time
	logger    *zap.Logger
}

// DKGResult contains the result of a successful DKG
type DKGResult struct {
	KeysetID        string `json:"keyset_id"`
	PublicKey       []byte `json:"public_key"`      // Compressed (33 bytes)
	PublicKeyFull   []byte `json:"public_key_full"` // Uncompressed (65 bytes)
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

	ctx := tss.NewPeerContext(sortedPartyIDs)
	params := tss.NewParameters(tss.S256(), ctx, thisPartyID, totalParties, threshold)

	// Generate preParams (safe primes) - this is computationally expensive
	h.logger.Info("Generating DKG pre-parameters (this may take a moment)...")
	preParams, err := keygen.GeneratePreParams(1 * time.Minute)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to generate preParams: %w", err)
	}
	h.logger.Info("Pre-parameters generated successfully")

	outCh := make(chan tss.Message, 100)
	endCh := make(chan keygen.LocalPartySaveData, 1)
	errCh := make(chan *tss.Error, 1)

	party := keygen.NewLocalParty(params, outCh, endCh, *preParams)

	session := &DKGSession{
		SessionID:    sessionID,
		WalletID:     walletID,
		PartyIndex:   partyIndex,
		Threshold:    threshold,
		TotalParties: totalParties,
		party:        party,
		outCh:        outCh,
		endCh:        endCh,
		errCh:        errCh,
		params:       params,
		partyIDs:     sortedPartyIDs,
		CreatedAt:    time.Now(),
		logger:       h.logger,
	}

	h.sessions[sessionID] = session

	go func() {
		if err := party.Start(); err != nil {
			h.logger.Error("Failed to start DKG party", zap.Error(err))
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

// ProcessRound processes incoming messages and returns outgoing messages
func (h *DKGHandler) ProcessRound(
	sessionID string,
	round int,
	incomingMessages []IncomingMessage,
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
	case saveData := <-session.endCh:
		result, err := buildResultFromSaveData(sessionID, saveData)
		if err != nil {
			h.mu.Lock()
			delete(h.sessions, sessionID)
			h.mu.Unlock()
			return nil, nil, false, err
		}

		h.logger.Info("DKG complete",
			zap.String("session_id", sessionID),
			zap.String("address", result.EthereumAddress),
		)

		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()

		return nil, result, true, nil

	case err := <-session.errCh:
		h.mu.Lock()
		delete(h.sessions, sessionID)
		h.mu.Unlock()
		return nil, nil, false, fmt.Errorf("dkg error: %v", err)

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

func (s *DKGSession) collectOutgoingMessages() ([]byte, error) {
	var messages []OutgoingMessage

	s.logger.Debug("Collecting outgoing messages...")

	// First, try to get at least one message with a longer timeout
	select {
	case msg := <-s.outCh:
		s.logger.Debug("Received message from outCh")
		outMsg, err := s.convertTSSMessage(msg)
		if err != nil {
			s.logger.Warn("Failed to convert message", zap.Error(err))
		} else {
			messages = append(messages, outMsg...)
		}
	case <-time.After(2 * time.Second):
		// No messages available yet
		s.logger.Debug("Timeout waiting for messages")
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
func (s *DKGSession) convertTSSMessage(msg tss.Message) ([]OutgoingMessage, error) {
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

func buildResultFromSaveData(sessionID string, saveData keygen.LocalPartySaveData) (*DKGResult, error) {
	if saveData.ECDSAPub == nil {
		return nil, fmt.Errorf("missing public key in save data")
	}

	publicKey := saveData.ECDSAPub.ToECDSAPubKey()

	pubKeyCompressed := serializeCompressedPublicKey(publicKey)
	pubKeyFull := serializeUncompressedPublicKey(publicKey)
	address := publicKeyToAddress(publicKey)
	keysetID := fmt.Sprintf("keyset-%s-%d", sessionID[:8], time.Now().Unix())

	saveDataBytes, err := json.Marshal(saveData)
	if err != nil {
		return nil, fmt.Errorf("failed to serialize save data: %w", err)
	}

	return &DKGResult{
		KeysetID:        keysetID,
		PublicKey:       pubKeyCompressed,
		PublicKeyFull:   pubKeyFull,
		EthereumAddress: address,
		SaveData:        saveDataBytes,
	}, nil
}

func serializeCompressedPublicKey(pub *ecdsa.PublicKey) []byte {
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
	result := make([]byte, 65)
	result[0] = 0x04
	pub.X.FillBytes(result[1:33])
	pub.Y.FillBytes(result[33:65])
	return result
}

func publicKeyToAddress(pub *ecdsa.PublicKey) string {
	pubBytes := serializeUncompressedPublicKey(pub)[1:]
	hasher := sha3.NewLegacyKeccak256()
	_, _ = hasher.Write(pubBytes)
	hash := hasher.Sum(nil)
	address := hash[len(hash)-20:]
	return fmt.Sprintf("0x%x", address)
}
