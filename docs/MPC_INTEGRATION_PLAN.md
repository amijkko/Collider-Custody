# MPC Integration Plan: Real 2PC tECDSA

## Обзор

Интеграция реального MPC (Multi-Party Computation) для threshold ECDSA подписей. Цель: приватный ключ **никогда не существует целиком** — только shares у участников.

## Архитектура

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Browser (User)                              │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐  │
│  │   React UI      │    │  MPC Client     │    │  IndexedDB          │  │
│  │   (Next.js)     │◄──►│  (WASM/JS)      │◄──►│  (encrypted share)  │  │
│  └────────┬────────┘    └────────┬────────┘    └─────────────────────┘  │
│           │                      │                                       │
│           │              WebSocket (MPC Protocol)                        │
└───────────┼──────────────────────┼───────────────────────────────────────┘
            │                      │
            │ HTTPS (REST API)     │ WSS (MPC Sessions)
            ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Core API (Python/FastAPI)                      │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐  │
│  │  Auth/RBAC      │    │  MPC Coordinator│    │  Tx Orchestrator    │  │
│  │  Wallets        │◄──►│  (Session Mgmt) │◄──►│  Policy/Approvals   │  │
│  │  Deposits       │    │                 │    │  Broadcast          │  │
│  └─────────────────┘    └────────┬────────┘    └─────────────────────┘  │
│                                  │                                       │
│                          gRPC (MPC Protocol)                             │
└──────────────────────────────────┼───────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Bank Signer Node (Go + tss-lib)                   │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐  │
│  │  gRPC Server    │◄──►│  tss-lib        │◄──►│  Encrypted Share    │  │
│  │                 │    │  (DKG/Signing)  │    │  Storage (BadgerDB) │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Компоненты

### 1. Bank Signer Node (Go)

Отдельный микросервис на Go, использующий [tss-lib](https://github.com/bnb-chain/tss-lib) от Binance.

**Ответственности:**
- Хранение bank share (зашифрованно)
- Участие в DKG протоколе
- Участие в threshold signing
- gRPC API для MPC Coordinator

**Структура:**
```
mpc-signer/
├── cmd/
│   └── signer/
│       └── main.go
├── internal/
│   ├── dkg/           # DKG protocol handler
│   ├── signing/       # Signing protocol handler
│   ├── storage/       # Encrypted share storage
│   └── grpc/          # gRPC server
├── proto/
│   └── mpc.proto      # Protocol definitions
├── go.mod
└── Dockerfile
```

### 2. MPC Coordinator (Python - существующий)

Обновление текущего `MPCCoordinator` для работы с реальным протоколом.

**Новые обязанности:**
- WebSocket endpoint для browser client
- gRPC client для Bank Signer Node
- Message routing между участниками
- Session state management
- Timeout и retry логика

### 3. Browser MPC Client

Два варианта реализации:

**Вариант A: WASM (сложнее, быстрее)**
- Компиляция tss-lib или cb-mpc в WASM
- Требует значительных усилий

**Вариант B: Pure TypeScript (проще, медленнее)**
- Использование существующих JS crypto библиотек
- noble-secp256k1 для эллиптических кривых
- Реализация ECDSA threshold протокола

**Рекомендация:** Начать с Варианта B для быстрой демонстрации.

### 4. Client-Side Share Storage

```typescript
interface EncryptedShare {
  version: 1;
  walletId: string;
  keysetId: string;
  cipherSuite: "secp256k1-tecdsa-2pc";
  kdf: {
    name: "PBKDF2";
    hash: "SHA-256";
    iterations: 310000;
    salt_b64: string;
  };
  enc: {
    name: "AES-GCM";
    iv_b64: string;
    ciphertext_b64: string;
  };
  createdAt: string;
}
```

## Протоколы

### DKG (Distributed Key Generation)

Используем GG18/GG20 протокол из tss-lib:

```
Round 1: Commitment
  User → Coordinator → Bank: commitment_user
  Bank → Coordinator → User: commitment_bank

Round 2: Share Exchange  
  User → Coordinator → Bank: encrypted_share_for_bank
  Bank → Coordinator → User: encrypted_share_for_user

Round 3: Verification
  User → Coordinator → Bank: verification_proof_user
  Bank → Coordinator → User: verification_proof_bank

Result:
  - Public Key (shared)
  - User Share (stored in IndexedDB)
  - Bank Share (stored in Bank Node)
```

### 2PC Threshold Signing

```
Pre-signing:
  User → Coordinator: request_signing(tx_hash, keyset_id)
  Coordinator → Bank: prepare_signing(tx_hash, keyset_id, permit)
  Bank → Coordinator: ready

Round 1: Commitment
  User → Coordinator → Bank: signing_commitment_user
  Bank → Coordinator → User: signing_commitment_bank

Round 2: Partial Signatures
  User → Coordinator → Bank: partial_sig_user
  Bank → Coordinator → User: partial_sig_bank

Round 3: Signature Assembly
  Coordinator: combine(partial_sig_user, partial_sig_bank) → final_signature

Result:
  - Valid ECDSA signature (r, s, v)
  - Broadcast to network
```

## API Design

### WebSocket Protocol (Browser ↔ Coordinator)

```typescript
// Client → Server
interface MPCMessage {
  type: "dkg_start" | "dkg_round" | "sign_start" | "sign_round";
  sessionId: string;
  round: number;
  payload: string; // base64 encoded
}

// Server → Client
interface MPCResponse {
  type: "dkg_round" | "dkg_complete" | "sign_round" | "sign_complete" | "error";
  sessionId: string;
  round: number;
  payload: string;
  address?: string;      // on dkg_complete
  signature?: string;    // on sign_complete
}
```

### gRPC Protocol (Coordinator ↔ Bank Node)

```protobuf
syntax = "proto3";

package mpc;

service MPCSigner {
  // DKG
  rpc StartDKG(StartDKGRequest) returns (StartDKGResponse);
  rpc DKGRound(DKGRoundRequest) returns (DKGRoundResponse);
  rpc FinalizeDKG(FinalizeDKGRequest) returns (FinalizeDKGResponse);
  
  // Signing
  rpc StartSigning(StartSigningRequest) returns (StartSigningResponse);
  rpc SigningRound(SigningRoundRequest) returns (SigningRoundResponse);
  rpc FinalizeSigning(FinalizeSigningRequest) returns (FinalizeSigningResponse);
}

message StartDKGRequest {
  string session_id = 1;
  string wallet_id = 2;
  int32 threshold = 3;
  int32 parties = 4;
}

message StartSigningRequest {
  string session_id = 1;
  string keyset_id = 2;
  bytes tx_hash = 3;
  SigningPermit permit = 4;
}

message SigningPermit {
  string tx_request_id = 1;
  string keyset_id = 2;
  bytes tx_hash = 3;
  int64 expires_at = 4;
  bytes signature = 5; // HMAC from Core API
}
```

## План реализации

### Phase 1: Infrastructure (Week 1)

1. **Создать Go signer service**
   - Scaffold проекта
   - Интеграция tss-lib
   - gRPC server
   - Encrypted storage

2. **Обновить MPC Coordinator**
   - WebSocket endpoint
   - gRPC client
   - Session management

### Phase 2: DKG (Week 2)

1. **Bank Node DKG**
   - Implement DKG rounds
   - Share storage

2. **Browser DKG Client**
   - WebSocket client
   - DKG protocol (TypeScript)
   - IndexedDB storage

3. **Integration**
   - End-to-end DKG test
   - Wallet creation flow

### Phase 3: Signing (Week 3)

1. **Bank Node Signing**
   - Implement signing rounds
   - Permit validation

2. **Browser Signing Client**
   - Password prompt UI
   - Share decryption
   - Signing protocol

3. **Integration**
   - End-to-end signing test
   - Withdraw flow

### Phase 4: Production Hardening (Week 4)

1. **Security**
   - Share encryption audit
   - Permit validation
   - Rate limiting

2. **Reliability**
   - Timeout handling
   - Session recovery
   - Error handling

3. **Monitoring**
   - Metrics
   - Alerts
   - Audit logging

## Зависимости

### Bank Signer Node (Go)
```go
require (
    github.com/bnb-chain/tss-lib v1.3.5
    google.golang.org/grpc v1.58.0
    github.com/dgraph-io/badger/v4 v4.2.0
)
```

### Browser Client (TypeScript)
```json
{
  "dependencies": {
    "@noble/secp256k1": "^2.0.0",
    "@noble/hashes": "^1.3.0",
    "idb": "^7.1.0"
  }
}
```

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| WASM компиляция сложна | Начать с Pure TS реализации |
| tss-lib баги | Использовать проверенную версию, тесты |
| Потеря user share | Backup flow, recovery phrase |
| Network latency | Optimistic UI, progress indicators |
| Browser crashes during signing | Session recovery, idempotency |

## Метрики успеха

- [ ] DKG создаёт валидный secp256k1 public key
- [ ] Derived address совпадает с ожидаемым
- [ ] 2PC signing создаёт валидную ECDSA подпись
- [ ] Подпись принимается Ethereum сетью
- [ ] User share никогда не покидает браузер в plaintext
- [ ] Bank share никогда не покидает signer node в plaintext

