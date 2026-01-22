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

	ctx := tss.NewPeerContext(sortedPartyIDs)
	params := tss.NewParameters(tss.S256(), ctx, thisPartyID, totalParties, threshold)

	outCh := make(chan tss.Message, 100)
	endCh := make(chan keygen.LocalPartySaveData, 1)
	errCh := make(chan *tss.Error, 1)

	party := keygen.NewLocalParty(params, outCh, endCh)

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
			errCh <- &tss.Error{Cause: err}
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

	for _, msgBytes := range incomingMessages {
		msg, err := tss.ParseWireMessage(msgBytes, session.partyIDs[0], session.params.Parties().IDs()[0].KeyInt() != nil)
		if err != nil {
			h.logger.Warn("Failed to parse message", zap.Error(err))
			continue
		}

		go func(m tss.ParsedMessage) {
			if _, err := session.party.Update(m); err != nil {
				h.logger.Warn("Failed to update party", zap.Error(err))
			}
		}(msg)
	}

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

	default:
		outMsg, err := session.collectOutgoingMessages()
		if err != nil {
			return nil, nil, false, err
		}
		return outMsg, nil, false, nil
	}
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
	var messages [][]byte

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

func buildResultFromSaveData(sessionID string, saveData keygen.LocalPartySaveData) (*DKGResult, error) {
	if saveData.ECDSAPub == nil {
		return nil, fmt.Errorf("missing public key in save data")
	}

	publicKey, err := saveData.ECDSAPub.ToECDSAPubKey()
	if err != nil {
		return nil, fmt.Errorf("failed to convert public key: %w", err)
	}

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
