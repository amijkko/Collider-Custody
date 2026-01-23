//go:build js && wasm
// +build js,wasm

package main

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
	"sync"
	"syscall/js"
	"time"

	"github.com/bnb-chain/tss-lib/v2/common"
	"github.com/bnb-chain/tss-lib/v2/ecdsa/keygen"
	"github.com/bnb-chain/tss-lib/v2/ecdsa/signing"
	"github.com/bnb-chain/tss-lib/v2/tss"
	"github.com/google/uuid"
)

// Global session storage
var (
	dkgSessions     = make(map[string]*DKGSession)
	signingSessions = make(map[string]*SigningSession)
	sessionMutex    sync.RWMutex
)

// DKGSession holds state for a DKG session
type DKGSession struct {
	SessionID    string
	PartyID      *tss.PartyID
	Params       *tss.Parameters
	Party        tss.Party
	OutChan      chan tss.Message
	EndChan      chan *keygen.LocalPartySaveData
	ErrChan      chan *tss.Error
	SaveData     *keygen.LocalPartySaveData
	CurrentRound int
	SortedIDs    tss.SortedPartyIDs
}

// SigningSession holds state for a signing session
type SigningSession struct {
	SessionID    string
	PartyID      *tss.PartyID
	Params       *tss.Parameters
	Party        tss.Party
	OutChan      chan tss.Message
	EndChan      chan *common.SignatureData
	ErrChan      chan *tss.Error
	Signature    *common.SignatureData
	CurrentRound int
	SaveData     *keygen.LocalPartySaveData
	SortedIDs    tss.SortedPartyIDs
}

// Result structures for JavaScript
type DKGResult struct {
	KeysetID        string `json:"keyset_id"`
	PublicKey       string `json:"public_key"`
	PublicKeyFull   string `json:"public_key_full"`
	EthereumAddress string `json:"ethereum_address"`
	SaveData        string `json:"save_data"` // Hex encoded JSON
}

type SigningResultData struct {
	SignatureR    string `json:"signature_r"`
	SignatureS    string `json:"signature_s"`
	SignatureV    int    `json:"signature_v"`
	FullSignature string `json:"full_signature"`
}

func main() {
	// Register JavaScript functions
	js.Global().Set("tssStartDKG", js.FuncOf(startDKG))
	js.Global().Set("tssDKGRound", js.FuncOf(dkgRound))
	js.Global().Set("tssStartSigning", js.FuncOf(startSigning))
	js.Global().Set("tssSigningRound", js.FuncOf(signingRound))
	js.Global().Set("tssLoadSaveData", js.FuncOf(loadSaveData))
	js.Global().Set("tssCleanupSession", js.FuncOf(cleanupSession))

	fmt.Println("[TSS-WASM] Initialized")

	// Keep the Go program running
	select {}
}

// startDKG initializes a new DKG session
// Args: sessionID, partyIndex, threshold, totalParties
// Returns: { success: bool, round1_msg: string (hex), error: string }
func startDKG(this js.Value, args []js.Value) interface{} {
	if len(args) < 4 {
		return errorResult("startDKG requires 4 arguments: sessionID, partyIndex, threshold, totalParties")
	}

	sessionID := args[0].String()
	partyIndex := args[1].Int()
	threshold := args[2].Int()
	totalParties := args[3].Int()

	fmt.Printf("[TSS-WASM] Starting DKG: session=%s, party=%d, t=%d, n=%d\n",
		sessionID, partyIndex, threshold, totalParties)

	sessionMutex.Lock()
	defer sessionMutex.Unlock()

	// Create party IDs for all participants
	partyIDs := make(tss.UnSortedPartyIDs, totalParties)
	for i := 0; i < totalParties; i++ {
		partyIDs[i] = tss.NewPartyID(
			fmt.Sprintf("party-%d", i),
			fmt.Sprintf("Party %d", i),
			big.NewInt(int64(i+1)),
		)
	}
	sortedPartyIDs := tss.SortPartyIDs(partyIDs)

	// Our party ID
	ourPartyID := sortedPartyIDs[partyIndex]

	// Create parameters
	ctx := tss.NewPeerContext(sortedPartyIDs)
	params := tss.NewParameters(tss.S256(), ctx, ourPartyID, totalParties, threshold)

	// Create channels
	outChan := make(chan tss.Message, 100)
	endChan := make(chan *keygen.LocalPartySaveData, 1)
	errChan := make(chan *tss.Error, 1)

	// Generate pre-parameters
	// Note: In production, these should be pre-generated
	fmt.Println("[TSS-WASM] Generating pre-parameters...")
	preParams, err := keygen.GeneratePreParams(1 * time.Minute)
	if err != nil {
		return errorResult(fmt.Sprintf("failed to generate pre-params: %v", err))
	}
	fmt.Println("[TSS-WASM] Pre-parameters generated")

	// Create DKG party
	party := keygen.NewLocalParty(params, outChan, endChan, *preParams)

	// Store session
	session := &DKGSession{
		SessionID:    sessionID,
		PartyID:      ourPartyID,
		Params:       params,
		Party:        party,
		OutChan:      outChan,
		EndChan:      endChan,
		ErrChan:      errChan,
		CurrentRound: 1,
		SortedIDs:    sortedPartyIDs,
	}
	dkgSessions[sessionID] = session

	// Start the party in background
	go func() {
		if err := party.Start(); err != nil {
			errChan <- &tss.Error{Cause: err}
		}
	}()

	// Collect round 1 messages (with timeout)
	round1Msgs := collectOutgoingMessages(outChan, 2*time.Second)
	if len(round1Msgs) == 0 {
		return errorResult("failed to generate round 1 message")
	}

	fmt.Printf("[TSS-WASM] DKG started, round 1 msg size: %d bytes\n", len(round1Msgs[0]))

	return js.ValueOf(map[string]interface{}{
		"success":    true,
		"round1_msg": hex.EncodeToString(round1Msgs[0]),
	})
}

// dkgRound processes incoming messages and returns outgoing messages
// Args: sessionID, round, incomingMessages (array of {from_party: int, payload: string (hex)})
// Returns: { success: bool, outgoing_msg: string (hex), is_final: bool, result: DKGResult, error: string }
func dkgRound(this js.Value, args []js.Value) interface{} {
	if len(args) < 3 {
		return errorResult("dkgRound requires 3 arguments: sessionID, round, incomingMessages")
	}

	sessionID := args[0].String()
	round := args[1].Int()
	incomingMsgs := args[2]

	sessionMutex.RLock()
	session, exists := dkgSessions[sessionID]
	sessionMutex.RUnlock()

	if !exists {
		return errorResult("session not found")
	}

	fmt.Printf("[TSS-WASM] DKG round %d, incoming messages: %d\n", round, incomingMsgs.Length())

	// Process incoming messages
	for i := 0; i < incomingMsgs.Length(); i++ {
		msg := incomingMsgs.Index(i)
		fromParty := msg.Get("from_party").Int()
		payloadHex := msg.Get("payload").String()

		payload, err := hex.DecodeString(payloadHex)
		if err != nil {
			return errorResult(fmt.Sprintf("invalid message payload: %v", err))
		}

		// Parse wire message
		parsedMsg, err := tss.ParseWireMessage(payload, session.SortedIDs[fromParty], true)
		if err != nil {
			return errorResult(fmt.Sprintf("failed to parse message from party %d: %v", fromParty, err))
		}

		// Update the party
		ok, updateErr := session.Party.Update(parsedMsg)
		if !ok {
			if updateErr != nil {
				return errorResult(fmt.Sprintf("party update failed: %v", updateErr))
			}
		}
	}

	// Check for completion
	select {
	case saveData := <-session.EndChan:
		session.SaveData = saveData

		// Generate keyset ID
		keysetID := uuid.New().String()

		// Get public key bytes
		pubKeyX := saveData.ECDSAPub.X()
		pubKeyY := saveData.ECDSAPub.Y()

		// Compressed public key (33 bytes)
		pubKeyCompressed := make([]byte, 33)
		if pubKeyY.Bit(0) == 0 {
			pubKeyCompressed[0] = 0x02
		} else {
			pubKeyCompressed[0] = 0x03
		}
		xBytes := pubKeyX.Bytes()
		copy(pubKeyCompressed[33-len(xBytes):], xBytes)

		// Uncompressed public key (65 bytes: 04 || X || Y)
		pubKeyFull := make([]byte, 65)
		pubKeyFull[0] = 0x04
		copy(pubKeyFull[1:33], padLeft(pubKeyX.Bytes(), 32))
		copy(pubKeyFull[33:65], padLeft(pubKeyY.Bytes(), 32))

		// Calculate Ethereum address
		ethAddr := pubKeyToEthAddress(pubKeyX, pubKeyY)

		// Serialize save data
		saveDataBytes, err := json.Marshal(saveData)
		if err != nil {
			return errorResult(fmt.Sprintf("failed to serialize save data: %v", err))
		}

		result := DKGResult{
			KeysetID:        keysetID,
			PublicKey:       hex.EncodeToString(pubKeyCompressed),
			PublicKeyFull:   hex.EncodeToString(pubKeyFull),
			EthereumAddress: ethAddr,
			SaveData:        hex.EncodeToString(saveDataBytes),
		}

		resultJSON, _ := json.Marshal(result)

		fmt.Printf("[TSS-WASM] DKG complete! Address: %s\n", ethAddr)

		return js.ValueOf(map[string]interface{}{
			"success":  true,
			"is_final": true,
			"result":   string(resultJSON),
		})

	case err := <-session.ErrChan:
		return errorResult(fmt.Sprintf("DKG error: %v", err))

	default:
		// Collect outgoing messages
		outMsgs := collectOutgoingMessages(session.OutChan, 500*time.Millisecond)

		var outMsgHex string
		if len(outMsgs) > 0 {
			outMsgHex = hex.EncodeToString(outMsgs[0])
		}

		session.CurrentRound = round + 1

		return js.ValueOf(map[string]interface{}{
			"success":      true,
			"is_final":     false,
			"outgoing_msg": outMsgHex,
		})
	}
}

// startSigning initializes a new signing session
// Args: sessionID, partyIndex, messageHash (hex), saveData (hex), totalParties, threshold
// Returns: { success: bool, round1_msg: string (hex), error: string }
func startSigning(this js.Value, args []js.Value) interface{} {
	if len(args) < 6 {
		return errorResult("startSigning requires 6 arguments")
	}

	sessionID := args[0].String()
	partyIndex := args[1].Int()
	messageHashHex := args[2].String()
	saveDataHex := args[3].String()
	totalParties := args[4].Int()
	threshold := args[5].Int()

	fmt.Printf("[TSS-WASM] Starting signing: session=%s, party=%d\n", sessionID, partyIndex)

	// Decode message hash
	messageHash, err := hex.DecodeString(messageHashHex)
	if err != nil {
		return errorResult(fmt.Sprintf("invalid message hash: %v", err))
	}

	// Decode and unmarshal save data
	saveDataBytes, err := hex.DecodeString(saveDataHex)
	if err != nil {
		return errorResult(fmt.Sprintf("invalid save data hex: %v", err))
	}

	var saveData keygen.LocalPartySaveData
	if err := json.Unmarshal(saveDataBytes, &saveData); err != nil {
		return errorResult(fmt.Sprintf("failed to unmarshal save data: %v", err))
	}

	sessionMutex.Lock()
	defer sessionMutex.Unlock()

	// Create party IDs
	partyIDs := make(tss.UnSortedPartyIDs, totalParties)
	for i := 0; i < totalParties; i++ {
		partyIDs[i] = tss.NewPartyID(
			fmt.Sprintf("party-%d", i),
			fmt.Sprintf("Party %d", i),
			big.NewInt(int64(i+1)),
		)
	}
	sortedPartyIDs := tss.SortPartyIDs(partyIDs)
	ourPartyID := sortedPartyIDs[partyIndex]

	// Create parameters
	ctx := tss.NewPeerContext(sortedPartyIDs)
	params := tss.NewParameters(tss.S256(), ctx, ourPartyID, totalParties, threshold)

	// Create channels
	outChan := make(chan tss.Message, 100)
	endChan := make(chan *common.SignatureData, 1)
	errChan := make(chan *tss.Error, 1)

	// Create message to sign
	msgBigInt := new(big.Int).SetBytes(messageHash)

	// Create signing party
	party := signing.NewLocalParty(msgBigInt, params, saveData, outChan, endChan)

	// Store session
	session := &SigningSession{
		SessionID:    sessionID,
		PartyID:      ourPartyID,
		Params:       params,
		Party:        party,
		OutChan:      outChan,
		EndChan:      endChan,
		ErrChan:      errChan,
		CurrentRound: 1,
		SaveData:     &saveData,
		SortedIDs:    sortedPartyIDs,
	}
	signingSessions[sessionID] = session

	// Start the party
	go func() {
		if err := party.Start(); err != nil {
			errChan <- &tss.Error{Cause: err}
		}
	}()

	// Collect round 1 messages
	round1Msgs := collectOutgoingMessages(outChan, 2*time.Second)
	if len(round1Msgs) == 0 {
		return errorResult("failed to generate round 1 message")
	}

	fmt.Printf("[TSS-WASM] Signing started, round 1 msg size: %d bytes\n", len(round1Msgs[0]))

	return js.ValueOf(map[string]interface{}{
		"success":    true,
		"round1_msg": hex.EncodeToString(round1Msgs[0]),
	})
}

// signingRound processes incoming messages and returns outgoing messages or signature
// Args: sessionID, round, incomingMessages (array of {from_party: int, payload: string (hex)})
// Returns: { success: bool, outgoing_msg: string (hex), is_final: bool, result: SigningResult, error: string }
func signingRound(this js.Value, args []js.Value) interface{} {
	if len(args) < 3 {
		return errorResult("signingRound requires 3 arguments")
	}

	sessionID := args[0].String()
	round := args[1].Int()
	incomingMsgs := args[2]

	sessionMutex.RLock()
	session, exists := signingSessions[sessionID]
	sessionMutex.RUnlock()

	if !exists {
		return errorResult("session not found")
	}

	fmt.Printf("[TSS-WASM] Signing round %d, incoming messages: %d\n", round, incomingMsgs.Length())

	// Process incoming messages
	for i := 0; i < incomingMsgs.Length(); i++ {
		msg := incomingMsgs.Index(i)
		fromParty := msg.Get("from_party").Int()
		payloadHex := msg.Get("payload").String()

		payload, err := hex.DecodeString(payloadHex)
		if err != nil {
			return errorResult(fmt.Sprintf("invalid message payload: %v", err))
		}

		parsedMsg, err := tss.ParseWireMessage(payload, session.SortedIDs[fromParty], true)
		if err != nil {
			return errorResult(fmt.Sprintf("failed to parse message from party %d: %v", fromParty, err))
		}

		ok, updateErr := session.Party.Update(parsedMsg)
		if !ok {
			if updateErr != nil {
				return errorResult(fmt.Sprintf("party update failed: %v", updateErr))
			}
		}
	}

	// Check for completion
	select {
	case sig := <-session.EndChan:
		session.Signature = sig

		// Calculate V (recovery ID)
		v := 27
		if sig.SignatureRecovery != nil && len(sig.SignatureRecovery) > 0 {
			v = int(sig.SignatureRecovery[0]) + 27
		}

		// Create full signature (R || S || V)
		fullSig := make([]byte, 65)
		copy(fullSig[0:32], padLeft(sig.R, 32))
		copy(fullSig[32:64], padLeft(sig.S, 32))
		fullSig[64] = byte(v)

		result := SigningResultData{
			SignatureR:    hex.EncodeToString(padLeft(sig.R, 32)),
			SignatureS:    hex.EncodeToString(padLeft(sig.S, 32)),
			SignatureV:    v,
			FullSignature: hex.EncodeToString(fullSig),
		}

		resultJSON, _ := json.Marshal(result)

		fmt.Printf("[TSS-WASM] Signing complete! R=%s...\n", result.SignatureR[:16])

		return js.ValueOf(map[string]interface{}{
			"success":  true,
			"is_final": true,
			"result":   string(resultJSON),
		})

	case err := <-session.ErrChan:
		return errorResult(fmt.Sprintf("signing error: %v", err))

	default:
		outMsgs := collectOutgoingMessages(session.OutChan, 500*time.Millisecond)

		var outMsgHex string
		if len(outMsgs) > 0 {
			outMsgHex = hex.EncodeToString(outMsgs[0])
		}

		session.CurrentRound = round + 1

		return js.ValueOf(map[string]interface{}{
			"success":      true,
			"is_final":     false,
			"outgoing_msg": outMsgHex,
		})
	}
}

// loadSaveData validates and returns info about save data
// Args: saveData (hex)
// Returns: { success: bool, public_key: string, ethereum_address: string, error: string }
func loadSaveData(this js.Value, args []js.Value) interface{} {
	if len(args) < 1 {
		return errorResult("loadSaveData requires saveData argument")
	}

	saveDataHex := args[0].String()
	saveDataBytes, err := hex.DecodeString(saveDataHex)
	if err != nil {
		return errorResult(fmt.Sprintf("invalid save data hex: %v", err))
	}

	var saveData keygen.LocalPartySaveData
	if err := json.Unmarshal(saveDataBytes, &saveData); err != nil {
		return errorResult(fmt.Sprintf("failed to unmarshal save data: %v", err))
	}

	pubKeyX := saveData.ECDSAPub.X()
	pubKeyY := saveData.ECDSAPub.Y()

	// Uncompressed public key
	pubKeyFull := make([]byte, 65)
	pubKeyFull[0] = 0x04
	copy(pubKeyFull[1:33], padLeft(pubKeyX.Bytes(), 32))
	copy(pubKeyFull[33:65], padLeft(pubKeyY.Bytes(), 32))

	ethAddr := pubKeyToEthAddress(pubKeyX, pubKeyY)

	return js.ValueOf(map[string]interface{}{
		"success":          true,
		"public_key":       hex.EncodeToString(pubKeyFull),
		"ethereum_address": ethAddr,
	})
}

// cleanupSession removes a session from memory
func cleanupSession(this js.Value, args []js.Value) interface{} {
	if len(args) < 1 {
		return errorResult("cleanupSession requires sessionID argument")
	}

	sessionID := args[0].String()

	sessionMutex.Lock()
	defer sessionMutex.Unlock()

	delete(dkgSessions, sessionID)
	delete(signingSessions, sessionID)

	fmt.Printf("[TSS-WASM] Cleaned up session: %s\n", sessionID)

	return js.ValueOf(map[string]interface{}{
		"success": true,
	})
}

// Helper functions

func errorResult(msg string) interface{} {
	fmt.Printf("[TSS-WASM] Error: %s\n", msg)
	return js.ValueOf(map[string]interface{}{
		"success": false,
		"error":   msg,
	})
}

func collectOutgoingMessages(outChan chan tss.Message, timeout time.Duration) [][]byte {
	var msgs [][]byte
	deadline := time.Now().Add(timeout)

	for time.Now().Before(deadline) {
		select {
		case msg := <-outChan:
			wireBytes, _, err := msg.WireBytes()
			if err == nil {
				msgs = append(msgs, wireBytes)
			}
		default:
			if len(msgs) > 0 {
				return msgs
			}
			time.Sleep(10 * time.Millisecond)
		}
	}

	return msgs
}

func padLeft(data []byte, size int) []byte {
	if len(data) >= size {
		return data
	}
	padded := make([]byte, size)
	copy(padded[size-len(data):], data)
	return padded
}

func pubKeyToEthAddress(x, y *big.Int) string {
	// Uncompressed public key bytes (without 0x04 prefix)
	pubKeyBytes := make([]byte, 64)
	copy(pubKeyBytes[0:32], padLeft(x.Bytes(), 32))
	copy(pubKeyBytes[32:64], padLeft(y.Bytes(), 32))

	// Keccak256 hash using JavaScript
	hash := keccak256(pubKeyBytes)

	// Take last 20 bytes
	return "0x" + hex.EncodeToString(hash[12:])
}

// keccak256 calls JavaScript's keccak256 function
func keccak256(data []byte) []byte {
	// Call JavaScript keccak256 function
	result := js.Global().Call("keccak256", hex.EncodeToString(data))
	hashHex := result.String()

	// Remove 0x prefix if present
	if len(hashHex) > 2 && hashHex[:2] == "0x" {
		hashHex = hashHex[2:]
	}

	hash, _ := hex.DecodeString(hashHex)
	return hash
}
