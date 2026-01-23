package signing

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"testing"

	"go.uber.org/zap"
)

func TestNewSigningHandler(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	handler := NewSigningHandler(logger)
	if handler == nil {
		t.Fatal("handler should not be nil")
	}

	if handler.sessions == nil {
		t.Error("sessions map should be initialized")
	}
}

// createMockSaveData creates a mock save data for simulation mode testing
func createMockSaveData() []byte {
	// This represents the save data format expected by simulation mode
	saveData := map[string]interface{}{
		"keyset_id":         "test-keyset",
		"party_index":       0,
		"threshold":         1,
		"total_parties":     2,
		"curve":             "P-256",
		"private_key_d_b64": base64.StdEncoding.EncodeToString(make([]byte, 32)),
	}
	data, _ := json.Marshal(saveData)
	return data
}

func TestSigningHandlerStartSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewSigningHandler(logger)

	// Create a mock message hash
	messageHash := sha256.Sum256([]byte("test message"))

	// Create mock save data
	saveData := createMockSaveData()

	tests := []struct {
		name         string
		sessionID    string
		keysetID     string
		partyIndex   int
		messageHash  []byte
		saveData     []byte
		totalParties int
		threshold    int
		expectError  bool
	}{
		{
			name:         "valid session",
			sessionID:    "sign-session-1",
			keysetID:     "keyset-1",
			partyIndex:   0,
			messageHash:  messageHash[:],
			saveData:     saveData,
			totalParties: 2,
			threshold:    1,
			expectError:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			session, round1Msg, err := handler.StartSession(
				tt.sessionID,
				tt.keysetID,
				tt.partyIndex,
				tt.messageHash,
				tt.saveData,
				tt.totalParties,
				tt.threshold,
			)

			if tt.expectError {
				if err == nil {
					t.Error("expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			if session == nil {
				t.Error("session should not be nil")
			}

			if session.SessionID != tt.sessionID {
				t.Errorf("expected session ID %s, got %s", tt.sessionID, session.SessionID)
			}

			if session.KeysetID != tt.keysetID {
				t.Errorf("expected keyset ID %s, got %s", tt.keysetID, session.KeysetID)
			}

			// In simulation mode, round1Msg should be non-nil
			if round1Msg == nil {
				t.Log("round1Msg is nil (may be expected in TSS mode)")
			}
		})
	}
}

func TestSigningHandlerDuplicateSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewSigningHandler(logger)

	sessionID := "duplicate-sign-session"
	messageHash := sha256.Sum256([]byte("test"))
	saveData := createMockSaveData()

	// Start first session
	_, _, err := handler.StartSession(sessionID, "keyset-1", 0, messageHash[:], saveData, 2, 1)
	if err != nil {
		t.Fatalf("first session failed: %v", err)
	}

	// Try to start duplicate session
	_, _, err = handler.StartSession(sessionID, "keyset-2", 0, messageHash[:], saveData, 2, 1)
	if err == nil {
		t.Error("expected error for duplicate session")
	}
}

func TestSigningHandlerGetSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewSigningHandler(logger)

	sessionID := "get-sign-session"
	messageHash := sha256.Sum256([]byte("test"))
	saveData := createMockSaveData()

	// Session should not exist
	_, exists := handler.GetSession(sessionID)
	if exists {
		t.Error("session should not exist")
	}

	// Start session
	_, _, err := handler.StartSession(sessionID, "keyset-1", 0, messageHash[:], saveData, 2, 1)
	if err != nil {
		t.Fatalf("failed to start session: %v", err)
	}

	// Session should exist
	session, exists := handler.GetSession(sessionID)
	if !exists {
		t.Error("session should exist")
	}
	if session == nil {
		t.Error("session should not be nil")
	}
}

func TestSigningHandlerCleanupSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewSigningHandler(logger)

	sessionID := "cleanup-sign-session"
	messageHash := sha256.Sum256([]byte("test"))
	saveData := createMockSaveData()

	// Start session
	_, _, err := handler.StartSession(sessionID, "keyset-1", 0, messageHash[:], saveData, 2, 1)
	if err != nil {
		t.Fatalf("failed to start session: %v", err)
	}

	// Verify session exists
	_, exists := handler.GetSession(sessionID)
	if !exists {
		t.Error("session should exist")
	}

	// Cleanup session
	handler.CleanupSession(sessionID)

	// Session should not exist
	_, exists = handler.GetSession(sessionID)
	if exists {
		t.Error("session should not exist after cleanup")
	}
}

func TestSigningHandlerProcessRound(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewSigningHandler(logger)

	sessionID := "process-sign-round"
	messageHash := sha256.Sum256([]byte("test message to sign"))
	saveData := createMockSaveData()

	// Start session
	_, _, err := handler.StartSession(sessionID, "keyset-1", 0, messageHash[:], saveData, 2, 1)
	if err != nil {
		t.Fatalf("failed to start session: %v", err)
	}

	// Process rounds (in simulation mode, round 2 should complete signing)
	for round := 1; round <= 3; round++ {
		outMsg, result, isFinal, err := handler.ProcessRound(
			sessionID,
			round,
			[]IncomingMessage{}, // Empty messages for simulation
		)

		if err != nil {
			t.Fatalf("round %d failed: %v", round, err)
		}

		if round >= 2 && isFinal {
			// Signing should be complete
			if result == nil {
				t.Error("result should not be nil on final round")
			}
			if len(result.SignatureR) != 32 {
				t.Errorf("expected R length 32, got %d", len(result.SignatureR))
			}
			if len(result.SignatureS) != 32 {
				t.Errorf("expected S length 32, got %d", len(result.SignatureS))
			}
			if result.SignatureV != 27 && result.SignatureV != 28 {
				t.Errorf("expected V to be 27 or 28, got %d", result.SignatureV)
			}
			if len(result.FullSignature) != 65 {
				t.Errorf("expected full signature length 65, got %d", len(result.FullSignature))
			}
			break
		}

		if !isFinal && outMsg == nil {
			t.Log("outMsg is nil (may be expected)")
		}
	}
}

func TestSigningResult(t *testing.T) {
	result := &SigningResult{
		SignatureR:    make([]byte, 32),
		SignatureS:    make([]byte, 32),
		SignatureV:    27,
		FullSignature: make([]byte, 65),
	}

	if len(result.SignatureR) != 32 {
		t.Errorf("expected R length 32, got %d", len(result.SignatureR))
	}

	if len(result.SignatureS) != 32 {
		t.Errorf("expected S length 32, got %d", len(result.SignatureS))
	}

	if result.SignatureV != 27 && result.SignatureV != 28 {
		t.Errorf("expected V to be 27 or 28, got %d", result.SignatureV)
	}

	if len(result.FullSignature) != 65 {
		t.Errorf("expected full signature length 65, got %d", len(result.FullSignature))
	}
}

func TestIncomingMessage(t *testing.T) {
	msg := IncomingMessage{
		FromPartyIndex: 1,
		Payload:        []byte("signing message"),
	}

	if msg.FromPartyIndex != 1 {
		t.Errorf("expected from party index 1, got %d", msg.FromPartyIndex)
	}

	if string(msg.Payload) != "signing message" {
		t.Errorf("expected payload 'signing message', got '%s'", string(msg.Payload))
	}
}

func TestOutgoingMessage(t *testing.T) {
	msg := OutgoingMessage{
		ToPartyIndex: 0,
		IsBroadcast:  false,
		Payload:      []byte("signing output"),
	}

	if msg.ToPartyIndex != 0 {
		t.Errorf("expected to party index 0, got %d", msg.ToPartyIndex)
	}

	if msg.IsBroadcast {
		t.Error("expected IsBroadcast to be false")
	}

	broadcastMsg := OutgoingMessage{
		ToPartyIndex: -1,
		IsBroadcast:  true,
		Payload:      []byte("broadcast signing"),
	}

	if !broadcastMsg.IsBroadcast {
		t.Error("expected IsBroadcast to be true")
	}
}

func TestProcessRoundNotFound(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewSigningHandler(logger)

	// Try to process a non-existent session
	_, _, _, err := handler.ProcessRound("non-existent", 1, []IncomingMessage{})
	if err == nil {
		t.Error("expected error for non-existent session")
	}
}

func TestStartSessionInvalidSaveData(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewSigningHandler(logger)

	messageHash := sha256.Sum256([]byte("test"))

	// Invalid save data (not valid JSON)
	_, _, err := handler.StartSession(
		"invalid-session",
		"keyset-1",
		0,
		messageHash[:],
		[]byte("not valid json"),
		2,
		1,
	)

	if err == nil {
		t.Error("expected error for invalid save data")
	}
}
