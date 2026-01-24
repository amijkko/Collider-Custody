# MPC WASM Fixes - 2026-01-23

## Summary

Fixed critical issues preventing MPC wallet creation in the browser. The TSS WASM module now successfully generates DKG round 1 messages and can parse responses from the Bank Node.

---

## Issues Fixed

### 1. Pre-params Validation Failure

**Error:**
```
panic: `optionalPreParams` failed to validate; it might have been generated with an older version of tss-lib
```

**Root Cause:**
tss-lib v2.0.2 requires additional fields in `LocalPreParams` that were not included:
- `Alpha` - ZK proof component
- `Beta` - ZK proof component
- `P` - Safe prime (different from PaillierSK.P)
- `Q` - Safe prime (different from PaillierSK.Q)

The `ValidateWithProof()` method checks for these fields, and `NewLocalParty()` calls this validation.

**Fix:**
Updated `tss-wasm/main.go` to include all required fields:

```go
return &keygen.LocalPreParams{
    PaillierSK: &paillier.PrivateKey{
        PublicKey: paillier.PublicKey{N: paillierN},
        LambdaN: paillierLambda,
        PhiN:    paillierPhi,
        P:       paillierP,
        Q:       paillierQ,
    },
    NTildei: nTilde,
    H1i:     h1,
    H2i:     h2,
    // NEW: Proof fields required by ValidateWithProof()
    Alpha:   alpha,
    Beta:    beta,
    P:       p,
    Q:       q,
}
```

Generated fresh pre-params using:
```bash
docker run --rm -v $(pwd)/tss-wasm:/app -w /app golang:1.21-alpine \
  go run gen_script.go
```

---

### 2. Round 1 Message Generation Timeout

**Error:**
```
failed to generate round 1 message
```

**Root Cause:**
- No error logging from `party.Start()`
- 2 second timeout was insufficient
- No check for errors before collecting messages

**Fix:**
Added error checking and increased timeout in `startDKG()`:

```go
// Start the party in background
go func() {
    fmt.Println("[TSS-WASM] Starting party.Start()...")
    if err := party.Start(); err != nil {
        fmt.Printf("[TSS-WASM] party.Start() error: %v\n", err)
        errChan <- party.WrapError(err)
    }
    fmt.Println("[TSS-WASM] party.Start() completed")
}()

// Check for immediate errors
select {
case err := <-errChan:
    return errorResult(fmt.Sprintf("party start failed: %v", err))
case <-time.After(100 * time.Millisecond):
    // Give party time to start
}

// Increased timeout from 2s to 5s
round1Msgs := collectOutgoingMessages(outChan, 5*time.Second)
```

---

### 3. Bank Node Message Format Incompatibility

**Error:**
```
proto: cannot parse invalid wire-format data
```

**Root Cause:**
Bank Node (`mpc-signer`) returns messages as JSON array of `OutgoingMessage`:
```json
[{"ToPartyIndex": -1, "IsBroadcast": true, "Payload": <base64 wireBytes>}]
```

But WASM expected raw `wireBytes` directly.

**Fix:**
Added JSON parsing in `dkgRound()`:

```go
// Bank Node sends JSON array of OutgoingMessages, parse it
type BankOutgoingMessage struct {
    ToPartyIndex int    `json:"ToPartyIndex"`
    IsBroadcast  bool   `json:"IsBroadcast"`
    Payload      []byte `json:"Payload"`
}

var bankMessages []BankOutgoingMessage
if err := json.Unmarshal(payload, &bankMessages); err != nil {
    // Fallback: try as raw wire bytes
    parsedMsg, parseErr := tss.ParseWireMessage(payload, ...)
    // ...
}

// Process each message from the bank
for _, bankMsg := range bankMessages {
    parsedMsg, _ := tss.ParseWireMessage(bankMsg.Payload, session.SortedIDs[fromParty], bankMsg.IsBroadcast)
    session.Party.Update(parsedMsg)
}
```

---

### 4. Round 1 Messages Not Sent After Processing Bank's Round 1

**Error:**
```
[TSS-WASM] Round 1: collected 2 outgoing messages, first size: 3720 bytes
Cleaned up session
DKG error: session not found
```

**Root Cause:**
In Round 1, the browser client does two things:
1. Calls `startDKG()` - generates user's Round 1 broadcast message
2. Calls `processDKGRound()` with bank's Round 1 message - generates Round 2 messages

But only the `startResult.round1Msg` was sent to the backend. The `processResult.outgoingMsg` (containing Round 2 messages after processing bank's Round 1) was logged but never sent.

**Fix (frontend/src/lib/mpc/client.ts):**
```typescript
if (round === 1) {
  const startResult = await tssWasm.startDKG(...);

  // Collect ALL messages to send
  const messagesToSend: string[] = [];
  if (startResult.round1Msg) {
    messagesToSend.push(startResult.round1Msg);
  }

  if (bankMessage) {
    const processResult = await tssWasm.processDKGRound(...);
    if (processResult.outgoingMsg) {
      messagesToSend.push(processResult.outgoingMsg);
    }
  }

  // Send all messages as JSON array if multiple
  if (messagesToSend.length > 1) {
    userMessage = JSON.stringify(messagesToSend);
  } else {
    userMessage = messagesToSend[0] || '';
  }
}
```

**Fix (app/api/mpc_websocket.py):**
```python
# Parse user message - can be single hex string or JSON array
if user_message_raw.startswith('['):
    try:
        message_list = json.loads(user_message_raw)
        for msg_hex in message_list:
            if msg_hex:
                incoming_messages.append((1, bytes.fromhex(msg_hex)))
    except json.JSONDecodeError:
        incoming_messages = [(1, bytes.fromhex(user_message_raw))]
else:
    incoming_messages = [(1, bytes.fromhex(user_message_raw))]
```

---

## Files Changed

| File | Changes |
|------|---------|
| `tss-wasm/main.go` | Added Alpha, Beta, P, Q to pre-params; Added BankOutgoingMessage struct; Updated JSON parsing in dkgRound(); Added logging |
| `tss-wasm/preparams_full.json` | New file with complete pre-params including proof fields |
| `frontend/public/wasm/tss.wasm` | Rebuilt with fixes |
| `frontend/src/lib/mpc/client.ts` | Collect and send multiple messages from Round 1 as JSON array |
| `app/api/mpc_websocket.py` | Parse JSON array of hex messages in DKG round handler |

---

## Testing

### Manual Test Steps:
1. Start all services: backend (port 8000), frontend (port 3000), mpc-signer (port 50051)
2. Open http://localhost:3000
3. Login and navigate to wallet creation
4. Click "Create MPC Wallet"
5. Enter password (min 12 chars, mixed case, digits, special chars)
6. Watch console for:
   - `[TSS-WASM] Pre-params loaded and VALIDATED successfully`
   - `[TSS-WASM] DKG started, round 1 msg size: ~133KB`
   - `[TSS-WASM] Parsed N bank messages from JSON`

### Expected Console Output (Success):
```
[TSS-WASM] Loading pre-computed params...
[TSS-WASM] Pre-params loaded and VALIDATED successfully
[TSS-WASM] Initialized
[MPC] TSS WASM initialized
[MPC] DKG Round 1, bank message: yes
[TSS-WASM] Starting DKG: session=xxx, party=1, t=1, n=2
[TSS-WASM] Using pre-computed pre-parameters
[TSS-WASM] Starting party.Start()...
[TSS-WASM] party.Start() completed
[TSS-WASM] DKG started, round 1 msg size: 133755 bytes
[MPC] DKG Round 2, bank message: yes
[TSS-WASM] DKG round 2, incoming messages: 1
[TSS-WASM] Parsed 1 bank messages from JSON
...
```

---

## Rebuild Instructions

```bash
# Generate new pre-params (if needed)
cd tss-wasm
docker run --rm -v $(pwd):/app -w /app golang:1.21-alpine \
  go run gen_script.go

# Build WASM
docker run --rm -v $(pwd):/app -w /app golang:1.21-alpine \
  sh -c "GOOS=js GOARCH=wasm go build -o tss.wasm main.go"

# Copy to frontend
cp tss.wasm ../frontend/public/wasm/
```

---

## Related Documentation

- [tss-lib v2.0.2 Release Notes](https://github.com/bnb-chain/tss-lib/releases/tag/v2.0.2)
- `LocalPreParams.ValidateWithProof()` requires: Alpha, Beta, P, Q fields
- Bank Node message format: `internal/dkg/dkg_tss.go:OutgoingMessage`
