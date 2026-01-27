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
	"github.com/bnb-chain/tss-lib/v2/crypto/paillier"
	"github.com/bnb-chain/tss-lib/v2/ecdsa/keygen"
	"github.com/bnb-chain/tss-lib/v2/ecdsa/signing"
	"github.com/bnb-chain/tss-lib/v2/tss"
	"github.com/google/uuid"
)

// Pre-generated params (generated offline with native Go, NOT in WASM)
// WARNING: These are for TESTING ONLY. In production, generate unique params per user.
var cachedPreParams *keygen.LocalPreParams

func init() {
	// Load pre-computed params immediately (no generation needed)
	cachedPreParams = loadPrecomputedParams()

	// Validate params
	if cachedPreParams != nil {
		if cachedPreParams.Validate() {
			fmt.Println("[TSS-WASM] Pre-params loaded and VALIDATED successfully")
		} else {
			fmt.Println("[TSS-WASM] WARNING: Pre-params failed validation!")
		}
	} else {
		fmt.Println("[TSS-WASM] ERROR: Pre-params is nil!")
	}
}

func loadPrecomputedParams() *keygen.LocalPreParams {
	// These values were generated with native Go using keygen.GeneratePreParams()
	// Generated fresh on 2026-01-23 for tss-lib v2.0.2
	// Includes Alpha, Beta, P, Q required by ValidateWithProof()
	fmt.Println("[TSS-WASM] Loading pre-computed params...")

	paillierN, ok := new(big.Int).SetString("22071432498181975862170451241412367065357009793275132890341717972836958947991599270104236307197224310418778938953867821996366948685889617422034900043214440557053388751763501938491426032610092713378120935660989837521994088438345198291521816145622520008733725330978991712102426120014768801246486446301824458654406046565513805610026956939221970745126023215311451628752199405598385904999285934381683312025430852685971077981101170372236639790316428585585461489964406442661037565723629769887722347214411766482597105004083358726573590119582538333967089510130310996454688287453892625385421152448968097129358883793158041529093", 10)
	if !ok {
		fmt.Println("[TSS-WASM] ERROR: Failed to parse paillierN")
	}
	paillierLambda, _ := new(big.Int).SetString("11035716249090987931085225620706183532678504896637566445170858986418479473995799635052118153598612155209389469476933910998183474342944808711017450021607220278526694375881750969245713016305046356689060467830494918760997044219172599145760908072811260004366862665489495856051213060007384400623243223150912229327054335988516367302311926736316752687044298056994465997738028216507643350195619047046763726685311663068114933994259418608062196731604828036756965994321655506449983976797821419953750376924650284550873494620848301074153391293971408196313548358766032031685256810882733985274911642326114930101591477362746874285734", 10)
	paillierPhi, _ := new(big.Int).SetString("22071432498181975862170451241412367065357009793275132890341717972836958947991599270104236307197224310418778938953867821996366948685889617422034900043214440557053388751763501938491426032610092713378120935660989837521994088438345198291521816145622520008733725330978991712102426120014768801246486446301824458654108671977032734604623853472633505374088596113988931995476056433015286700391238094093527453370623326136229867988518837216124393463209656073513931988643311012899967953595642839907500753849300569101746989241696602148306782587942816392627096717532064063370513621765467970549823284652229860203182954725493748571468", 10)
	paillierP, _ := new(big.Int).SetString("142647511927437934535712032774286443743284843542261754341539853674928215350111886083282271873542511432440635889405268662144287086521456710508784861009467538594850435803468701636162520458024972550445964197660977500947200534397038254272115327183314953386526666557573411473624210638457601825689525557220961463439", 10)
	paillierQ, _ := new(big.Int).SetString("154727076553633070867391433814178927294142257780257878934603118908170989257935954204873586781265015117300574103177064493967959240585315801562744640311627891166219176324518228344059072907086224830404151564725779077319606997242683687067877465414931979697647999130851243361973657158280635100486403510443331494187", 10)

	nTilde, _ := new(big.Int).SetString("27621973237202218537399260670116979459985468247791919962297992397106852255396762051232045143912246787608443726429175400538119956510835663576035704110114985088647580415060471661743881785334568180671901545771290851097891082618991971331756380128674277939074509109074747101192319387824965161721345155495731812718005233132704015917083386238647489491425934409736447409132922003711594859791188584238889889157591449624359776231948379892832414649300072688598381173072072785847121952298825452567676333995905962766123378883469406272946205546893174099879317408324779371999067491560230519286637950433523335419009604848404531769709", 10)
	h1, _ := new(big.Int).SetString("18848026236083476044154415721789857497597312196851797637685371987831358988956506897143486569630585916194124533705312346612075570781230906945319349085034771835918017612923801870593427537075817058933097391104119475851683256269343732240398318796600314197055541361137165799997393659848164605286126883005382681800644162619630920404251562398941942393536380071097625700549590384273400967317298108700476007908287938927930334328014587645595703004695826529654770391206592412014962556550000094208525323626330524858241002745349037117509596689286148802787510970409609319095491443091616654748376086967900532503705467285723227702244", 10)
	h2, _ := new(big.Int).SetString("4935727917793355784378076137648716436719885447571035460469132320734376385344589299167467571402878912935521724104205762365806596396458230110815067316700126998885574713661636187939543954011366155057705492065492975768720033593508579817949727451002758658064326003995213866231656982487521105402080243630222072147658085796852445865887066912002231556731039455516438480358023816229060617587954388718866506465109415243292000896757447117220725802056954031808683135502885401959665333683445851767252384206460294163789791613335541078778677823187243554627772213815822275806999487749220560945779224418216079786374846668074297636974", 10)

	// Proof fields required by ValidateWithProof()
	alpha, _ := new(big.Int).SetString("11671573136499443755387229067787418325700775472934941005286197573173116336250449354399645517717833178141503492937164487573860795247166973840153305702793762993983459063565130451067541664743843910506207351450932782851353174283714087963117901890488099471791604045987310529135902895513674873553260748780486545960752696746022764352228323463497461921681790366206671175259160334834047025976634176691758133764196155073617149800420848625118630358765914097736658555107202193265505256011736072512857358463500874133771743004898197004009179063624607746866740321476472735920534673080339807447123251841214390723214897635635130257628", 10)
	beta, _ := new(big.Int).SetString("832502527357683565252046183421257138620639102101433967672944157998382968711872321780493708555305783515361797309891487812053666665057024376825926530264760696364705796333406477448466211458679980783712802462085885458052128976663839930520946315944484578642595702612012786933750070853432482758595993336068619334561341960665269632667996255100927549644788471114825488011104487739143890534035188799116734112484521653590187132837420385382095861797017637671318758152600996013441177699609112044027459039674150426172712735921081124609664795025959102588332199562296266339024444919033680320611732745768999918539032145868795701565", 10)
	p, _ := new(big.Int).SetString("88007895328162224526994093342713501684198568329430736790209800684872842413778091406898618978441315750128799126678691360226375849375076300601345797843659115753170673665244433183319055485708402144317773182749951753484582132924346639390840041511027861873855800730696228335337492029000098643345756349964607425433", 10)
	q, _ := new(big.Int).SetString("78464475074099635580312414660267831659173297185621846898528400587685507473196447173231724717121826680645332880047605841826118688756690238593143011187173030967786973201697659706268953951888744484935053777544980654391092631847651546120258043543568479869833267812164024641037554287607097928083286814894025124463", 10)

	return &keygen.LocalPreParams{
		PaillierSK: &paillier.PrivateKey{
			PublicKey: paillier.PublicKey{
				N: paillierN,
			},
			LambdaN: paillierLambda,
			PhiN:    paillierPhi,
			P:       paillierP,
			Q:       paillierQ,
		},
		NTildei: nTilde,
		H1i:     h1,
		H2i:     h2,
		Alpha:   alpha,
		Beta:    beta,
		P:       p,
		Q:       q,
	}
}

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

// BankOutgoingMessage matches the JSON format from Bank Node
type BankOutgoingMessage struct {
	ToPartyIndex int    `json:"ToPartyIndex"`
	IsBroadcast  bool   `json:"IsBroadcast"`
	Payload      []byte `json:"Payload"`
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

	// Use pre-computed params (loaded at init)
	if cachedPreParams == nil {
		return errorResult("pre-params not loaded")
	}
	preParams := cachedPreParams
	fmt.Println("[TSS-WASM] Using pre-computed pre-parameters")

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
		fmt.Println("[TSS-WASM] Starting party.Start()...")
		if err := party.Start(); err != nil {
			fmt.Printf("[TSS-WASM] party.Start() error: %v\n", err)
			errChan <- party.WrapError(err)
		}
		fmt.Println("[TSS-WASM] party.Start() completed")
	}()

	// Check for immediate errors and collect round 1 messages
	select {
	case err := <-errChan:
		return errorResult(fmt.Sprintf("party start failed: %v", err))
	case <-time.After(100 * time.Millisecond):
		// Give party time to start
	}

	// Collect round 1 messages with metadata (with timeout)
	round1Msgs := collectOutgoingMessagesWithMeta(outChan, 5*time.Second, sortedPartyIDs)
	if len(round1Msgs) == 0 {
		// Check if there was an error
		select {
		case err := <-errChan:
			return errorResult(fmt.Sprintf("DKG error: %v", err))
		default:
			return errorResult("failed to generate round 1 message (timeout)")
		}
	}

	// Return as JSON array with metadata (same format as dkgRound)
	jsonBytes, err := json.Marshal(round1Msgs)
	if err != nil {
		return errorResult(fmt.Sprintf("failed to serialize round 1 messages: %v", err))
	}

	fmt.Printf("[TSS-WASM] DKG started, round 1 msg count: %d, first size: %d bytes\n", len(round1Msgs), len(round1Msgs[0].Payload))

	return js.ValueOf(map[string]interface{}{
		"success":    true,
		"round1_msg": string(jsonBytes),
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
			return errorResult(fmt.Sprintf("invalid message payload hex: %v", err))
		}

		// Bank Node sends JSON array of OutgoingMessages, parse it
		var bankMessages []BankOutgoingMessage
		if err := json.Unmarshal(payload, &bankMessages); err != nil {
			// If not JSON array, try as raw wire bytes
			fmt.Printf("[TSS-WASM] Payload is not JSON array, trying as raw wire bytes\n")
			parsedMsg, parseErr := tss.ParseWireMessage(payload, session.SortedIDs[fromParty], true)
			if parseErr != nil {
				return errorResult(fmt.Sprintf("failed to parse message from party %d: %v", fromParty, parseErr))
			}
			ok, updateErr := session.Party.Update(parsedMsg)
			if !ok && updateErr != nil {
				return errorResult(fmt.Sprintf("party update failed: %v", updateErr))
			}
			continue
		}

		fmt.Printf("[TSS-WASM] Parsed %d bank messages from JSON\n", len(bankMessages))

		// Process each message from the bank
		for _, bankMsg := range bankMessages {
			if len(bankMsg.Payload) == 0 {
				continue
			}

			fmt.Printf("[TSS-WASM] Processing bank message: ToParty=%d, IsBroadcast=%v, PayloadLen=%d\n",
				bankMsg.ToPartyIndex, bankMsg.IsBroadcast, len(bankMsg.Payload))

			// Parse wire message
			parsedMsg, parseErr := tss.ParseWireMessage(bankMsg.Payload, session.SortedIDs[fromParty], bankMsg.IsBroadcast)
			if parseErr != nil {
				return errorResult(fmt.Sprintf("failed to parse bank message: %v", parseErr))
			}

			// Update the party
			ok, updateErr := session.Party.Update(parsedMsg)
			fmt.Printf("[TSS-WASM] Party.Update result: ok=%v, err=%v\n", ok, updateErr)
			if !ok && updateErr != nil {
				return errorResult(fmt.Sprintf("party update failed: %v", updateErr))
			}

			// Check if DKG completed after this update
			select {
			case saveData := <-session.EndChan:
				fmt.Println("[TSS-WASM] DKG completed after processing message!")
				session.SaveData = saveData
				return buildDKGCompleteResult(saveData)
			default:
			}
		}
	}

	// Check for completion
	select {
	case saveData := <-session.EndChan:
		session.SaveData = saveData
		return buildDKGCompleteResult(saveData)

	case err := <-session.ErrChan:
		return errorResult(fmt.Sprintf("DKG error: %v", err))

	default:
		// Give party time to process and generate outgoing messages
		time.Sleep(100 * time.Millisecond)

		// Collect outgoing messages with metadata (IsBroadcast, ToPartyIndex)
		outMsgs := collectOutgoingMessagesWithMeta(session.OutChan, 3*time.Second, session.SortedIDs)

		var outMsgHex string
		if len(outMsgs) > 0 {
			// Always return as JSON array with metadata (same format as bank signer)
			jsonBytes, err := json.Marshal(outMsgs)
			if err != nil {
				return errorResult(fmt.Sprintf("failed to serialize outgoing messages: %v", err))
			}
			outMsgHex = string(jsonBytes)
			fmt.Printf("[TSS-WASM] Round %d: collected %d outgoing messages, first size: %d bytes\n",
				round, len(outMsgs), len(outMsgs[0].Payload))
		} else {
			fmt.Printf("[TSS-WASM] Round %d: no outgoing messages\n", round)
		}

		session.CurrentRound = round + 1

		// Check again for completion after collecting messages
		select {
		case saveData := <-session.EndChan:
			session.SaveData = saveData
			return buildDKGCompleteResult(saveData)
		default:
		}

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
			errChan <- party.WrapError(err)
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

		// Bank Node sends JSON array of OutgoingMessages, parse it
		var bankMessages []BankOutgoingMessage
		if err := json.Unmarshal(payload, &bankMessages); err != nil {
			// If not JSON array, try as raw wire bytes
			fmt.Printf("[TSS-WASM] Payload is not JSON array, trying as raw wire bytes\n")
			parsedMsg, parseErr := tss.ParseWireMessage(payload, session.SortedIDs[fromParty], true)
			if parseErr != nil {
				return errorResult(fmt.Sprintf("failed to parse message from party %d: %v", fromParty, parseErr))
			}
			ok, updateErr := session.Party.Update(parsedMsg)
			if !ok && updateErr != nil {
				return errorResult(fmt.Sprintf("party update failed: %v", updateErr))
			}
			continue
		}

		fmt.Printf("[TSS-WASM] Parsed %d bank messages from JSON\n", len(bankMessages))

		// Process each message from the bank
		for _, bankMsg := range bankMessages {
			if len(bankMsg.Payload) == 0 {
				continue
			}

			fmt.Printf("[TSS-WASM] Processing bank message: ToParty=%d, IsBroadcast=%v, PayloadLen=%d\n",
				bankMsg.ToPartyIndex, bankMsg.IsBroadcast, len(bankMsg.Payload))

			// Parse wire message
			parsedMsg, parseErr := tss.ParseWireMessage(bankMsg.Payload, session.SortedIDs[fromParty], bankMsg.IsBroadcast)
			if parseErr != nil {
				return errorResult(fmt.Sprintf("failed to parse bank message: %v", parseErr))
			}

			// Update the party
			ok, updateErr := session.Party.Update(parsedMsg)
			fmt.Printf("[TSS-WASM] Party.Update result: ok=%v, err=%v\n", ok, updateErr)
			if !ok && updateErr != nil {
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
		// Give party time to process and generate outgoing messages
		time.Sleep(100 * time.Millisecond)

		// Collect outgoing messages with metadata (same as DKG)
		outMsgs := collectOutgoingMessagesWithMeta(session.OutChan, 3*time.Second, session.SortedIDs)

		var outMsgHex string
		if len(outMsgs) > 0 {
			// Return as JSON array with metadata (same format as bank signer)
			jsonBytes, err := json.Marshal(outMsgs)
			if err != nil {
				return errorResult(fmt.Sprintf("failed to serialize outgoing messages: %v", err))
			}
			outMsgHex = string(jsonBytes)
			fmt.Printf("[TSS-WASM] Signing round %d: collected %d outgoing messages\n",
				round, len(outMsgs))
		} else {
			fmt.Printf("[TSS-WASM] Signing round %d: no outgoing messages\n", round)
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

func buildDKGCompleteResult(saveData *keygen.LocalPartySaveData) interface{} {
	keysetID := uuid.New().String()

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
}

func errorResult(msg string) interface{} {
	fmt.Printf("[TSS-WASM] Error: %s\n", msg)
	return js.ValueOf(map[string]interface{}{
		"success": false,
		"error":   msg,
	})
}

// OutgoingMessageHex matches the format expected by bank signer (with hex-encoded payload)
type OutgoingMessageHex struct {
	ToPartyIndex int    `json:"ToPartyIndex"` // -1 means broadcast
	IsBroadcast  bool   `json:"IsBroadcast"`
	Payload      string `json:"Payload"` // Hex-encoded bytes
}

func collectOutgoingMessagesWithMeta(outChan chan tss.Message, timeout time.Duration, sortedIDs tss.SortedPartyIDs) []OutgoingMessageHex {
	var msgs []OutgoingMessageHex
	deadline := time.Now().Add(timeout)

	for time.Now().Before(deadline) {
		select {
		case msg := <-outChan:
			wireBytes, routing, err := msg.WireBytes()
			if err != nil {
				continue
			}

			// Hex-encode the payload
			payloadHex := hex.EncodeToString(wireBytes)

			if routing.IsBroadcast {
				// Broadcast message
				msgs = append(msgs, OutgoingMessageHex{
					ToPartyIndex: -1,
					IsBroadcast:  true,
					Payload:      payloadHex,
				})
			} else {
				// Point-to-point messages
				for _, toParty := range routing.To {
					// Find party index
					toIndex := -1
					for i, pid := range sortedIDs {
						if pid.Id == toParty.Id {
							toIndex = i
							break
						}
					}
					if toIndex >= 0 {
						msgs = append(msgs, OutgoingMessageHex{
							ToPartyIndex: toIndex,
							IsBroadcast:  false,
							Payload:      payloadHex,
						})
					}
				}
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

// Legacy function for compatibility
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

