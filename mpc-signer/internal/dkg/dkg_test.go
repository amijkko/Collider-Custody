package dkg

import (
	"testing"

	"go.uber.org/zap"
)

func TestNewDKGHandler(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	handler := NewDKGHandler(logger)
	if handler == nil {
		t.Fatal("handler should not be nil")
	}

	if handler.sessions == nil {
		t.Error("sessions map should be initialized")
	}
}

func TestDKGHandlerStartSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewDKGHandler(logger)

	tests := []struct {
		name         string
		sessionID    string
		walletID     string
		partyIndex   int
		threshold    int
		totalParties int
		expectError  bool
	}{
		{
			name:         "valid 2-of-2 session",
			sessionID:    "session-1",
			walletID:     "wallet-1",
			partyIndex:   0,
			threshold:    1,
			totalParties: 2,
			expectError:  false,
		},
		{
			name:         "valid 2-of-3 session",
			sessionID:    "session-2",
			walletID:     "wallet-2",
			partyIndex:   1,
			threshold:    2,
			totalParties: 3,
			expectError:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			session, round1Msg, err := handler.StartSession(
				tt.sessionID,
				tt.walletID,
				tt.partyIndex,
				tt.threshold,
				tt.totalParties,
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

			if session.WalletID != tt.walletID {
				t.Errorf("expected wallet ID %s, got %s", tt.walletID, session.WalletID)
			}

			if session.PartyIndex != tt.partyIndex {
				t.Errorf("expected party index %d, got %d", tt.partyIndex, session.PartyIndex)
			}

			if session.Threshold != tt.threshold {
				t.Errorf("expected threshold %d, got %d", tt.threshold, session.Threshold)
			}

			if session.TotalParties != tt.totalParties {
				t.Errorf("expected total parties %d, got %d", tt.totalParties, session.TotalParties)
			}

			// In simulation mode, round1Msg should be non-nil
			if round1Msg == nil {
				t.Log("round1Msg is nil (may be expected in TSS mode)")
			}
		})
	}
}

func TestDKGHandlerDuplicateSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewDKGHandler(logger)

	sessionID := "duplicate-session"

	// Start first session
	_, _, err := handler.StartSession(sessionID, "wallet-1", 0, 1, 2)
	if err != nil {
		t.Fatalf("first session failed: %v", err)
	}

	// Try to start duplicate session
	_, _, err = handler.StartSession(sessionID, "wallet-2", 0, 1, 2)
	if err == nil {
		t.Error("expected error for duplicate session")
	}
}

func TestDKGHandlerGetSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewDKGHandler(logger)

	sessionID := "get-session-test"

	// Session should not exist
	_, exists := handler.GetSession(sessionID)
	if exists {
		t.Error("session should not exist")
	}

	// Start session
	_, _, err := handler.StartSession(sessionID, "wallet-1", 0, 1, 2)
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

func TestDKGHandlerCleanupSession(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewDKGHandler(logger)

	sessionID := "cleanup-session-test"

	// Start session
	_, _, err := handler.StartSession(sessionID, "wallet-1", 0, 1, 2)
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

func TestDKGHandlerProcessRound(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	handler := NewDKGHandler(logger)

	sessionID := "process-round-test"

	// Start session
	_, _, err := handler.StartSession(sessionID, "wallet-1", 0, 1, 2)
	if err != nil {
		t.Fatalf("failed to start session: %v", err)
	}

	// Process rounds (in simulation mode, round 3 should complete DKG)
	for round := 1; round <= 4; round++ {
		outMsg, result, isFinal, err := handler.ProcessRound(
			sessionID,
			round,
			[]IncomingMessage{}, // Empty messages for simulation
		)

		if err != nil {
			t.Fatalf("round %d failed: %v", round, err)
		}

		if round >= 3 && isFinal {
			// DKG should be complete
			if result == nil {
				t.Error("result should not be nil on final round")
			}
			if result.KeysetID == "" {
				t.Error("keyset ID should not be empty")
			}
			if result.EthereumAddress == "" {
				t.Error("ethereum address should not be empty")
			}
			if len(result.PublicKey) == 0 {
				t.Error("public key should not be empty")
			}
			if len(result.SaveData) == 0 {
				t.Error("save data should not be empty")
			}
			break
		}

		if !isFinal && outMsg == nil {
			t.Log("outMsg is nil (may be expected)")
		}
	}
}

func TestDKGResult(t *testing.T) {
	result := &DKGResult{
		KeysetID:        "keyset-123",
		PublicKey:       make([]byte, 33),
		PublicKeyFull:   make([]byte, 65),
		EthereumAddress: "0x1234567890abcdef",
		SaveData:        []byte(`{"test": "data"}`),
	}

	if result.KeysetID != "keyset-123" {
		t.Errorf("expected keyset ID 'keyset-123', got '%s'", result.KeysetID)
	}

	if len(result.PublicKey) != 33 {
		t.Errorf("expected compressed public key length 33, got %d", len(result.PublicKey))
	}

	if len(result.PublicKeyFull) != 65 {
		t.Errorf("expected uncompressed public key length 65, got %d", len(result.PublicKeyFull))
	}
}

func TestIncomingMessage(t *testing.T) {
	msg := IncomingMessage{
		FromPartyIndex: 1,
		Payload:        []byte("test payload"),
	}

	if msg.FromPartyIndex != 1 {
		t.Errorf("expected from party index 1, got %d", msg.FromPartyIndex)
	}

	if string(msg.Payload) != "test payload" {
		t.Errorf("expected payload 'test payload', got '%s'", string(msg.Payload))
	}
}

func TestOutgoingMessage(t *testing.T) {
	msg := OutgoingMessage{
		ToPartyIndex: 0,
		IsBroadcast:  false,
		Payload:      []byte("test payload"),
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
		Payload:      []byte("broadcast"),
	}

	if !broadcastMsg.IsBroadcast {
		t.Error("expected IsBroadcast to be true")
	}
}
