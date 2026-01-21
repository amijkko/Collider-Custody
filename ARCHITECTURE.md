# Collider Custody — Техническая Архитектура

## Обзор

**Collider Custody** — MVP on-prem решения для Transaction Security Layer + Wallet-as-a-Service (Ethereum). 
Реализован как монолитный сервис с модульной архитектурой, готовый к декомпозиции на микросервисы.

---

## Технологический стек

### Backend
| Технология | Версия | Назначение |
|------------|--------|------------|
| Python | 3.11 | Runtime |
| FastAPI | 0.109.0 | REST API Framework |
| Pydantic | 2.5.3 | Валидация данных |
| SQLAlchemy | 2.0.25 | ORM (async) |
| Alembic | 1.13.1 | Миграции БД |
| asyncpg | 0.29.0 | Async PostgreSQL driver |

### Ethereum / Web3
| Технология | Версия | Назначение |
|------------|--------|------------|
| web3.py | 6.14.0 | Ethereum RPC клиент |
| eth-account | 0.10.0 | Подпись транзакций |

### Аутентификация
| Технология | Версия | Назначение |
|------------|--------|------------|
| python-jose | 3.3.0 | JWT токены |
| passlib + bcrypt | 1.7.4 / 4.2.0 | Хеширование паролей |

### Инфраструктура
| Технология | Назначение |
|------------|------------|
| PostgreSQL 16 | Основная БД |
| Docker / Docker Compose | Контейнеризация |
| uvicorn | ASGI сервер |

---

## Архитектура компонентов

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              REST API Layer                                  │
│                           (FastAPI + Pydantic)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  /v1/auth     │  /v1/wallets  │  /v1/tx-requests  │  /v1/cases  │  /v1/audit│
├───────────────┴───────────────┴───────────────────┴─────────────┴───────────┤
│                          Middleware Layer                                    │
│              JWT RBAC │ Correlation ID │ Idempotency │ Error Handling       │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Service Layer                                       │
├──────────────┬──────────────┬──────────────┬──────────────┬─────────────────┤
│ AuthService  │ WalletService│ TxOrchestrator│ PolicyService│ AuditService   │
│              │              │ (State Machine)│             │ (Hash Chain)   │
├──────────────┼──────────────┼──────────────┼──────────────┼─────────────────┤
│              │              │ KYTService   │ SigningService│ EthereumService│
│              │              │ (Mock)       │ (Dev Signer) │ (RPC Client)   │
├──────────────┴──────────────┴──────────────┴──────────────┴─────────────────┤
│                        Chain Listener (Background)                           │
│              Confirmation Tracking │ Inbound Deposit Detection               │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Data Layer (SQLAlchemy Async)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                          PostgreSQL 16                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Модули и их статус

### 1. Wallet Registry (WaaS)
**Статус: ✅ Полностью реализован**

| Функция | Реализация |
|---------|------------|
| Создание EOA кошельков | Реальная генерация через `eth-account` |
| Типы кошельков | RETAIL, TREASURY, OPS, SETTLEMENT |
| Роли на кошельках | OWNER, OPERATOR, VIEWER, APPROVER |
| Risk Profile | LOW, MEDIUM, HIGH |
| Idempotency | Через `Idempotency-Key` header |

**Ограничение MVP**: Приватные ключи генерируются, но не сохраняются. `key_ref` содержит только адрес для dev mode.

### 2. Transaction Orchestrator
**Статус: ✅ Полностью реализован**

State Machine со следующими переходами:

```
SUBMITTED
    │
    ▼
KYT_PENDING ──────────────► KYT_BLOCKED (terminal)
    │
    ├──► KYT_REVIEW (wait) ──► KYT_BLOCKED или continue
    │
    ▼
POLICY_EVAL_PENDING ──────► POLICY_BLOCKED (terminal)
    │
    ▼
APPROVAL_PENDING (if req) ─► REJECTED (terminal)
    │
    ▼
SIGN_PENDING ─────────────► FAILED_SIGN (terminal)
    │
    ▼
SIGNED
    │
    ▼
BROADCAST_PENDING ────────► FAILED_BROADCAST (can retry)
    │
    ▼
BROADCASTED
    │
    ▼
CONFIRMING
    │
    ▼
CONFIRMED
    │
    ▼
FINALIZED (terminal success)
```

### 3. KYT Gateway
**Статус: 🔶 Mock реализация**

| Аспект | Реализация |
|--------|------------|
| Provider | Mock (конфигурируемые списки в ENV) |
| Blacklist | `KYT_BLACKLIST` env → возвращает `BLOCK` |
| Graylist | `KYT_GRAYLIST` env → возвращает `REVIEW`, создаёт Case |
| Clean address | Возвращает `ALLOW` |
| Case Management | Полностью работает (create, list, resolve) |
| Inbound KYT | Реализован для входящих депозитов |

**Для продакшена**: Интеграция с Chainalysis, Elliptic, TRM Labs через adapter pattern.

### 4. Policy Engine
**Статус: ✅ Полностью реализован**

| Тип политики | Реализация |
|--------------|------------|
| `ADDRESS_DENYLIST` | Блокирует транзакции на указанные адреса |
| `TOKEN_DENYLIST` | Блокирует транзакции с указанными токенами |
| `TX_LIMIT` | Per-transaction лимит по wallet/wallet_type |
| `DAILY_LIMIT` | Дневной лимит с отслеживанием volume |
| `APPROVAL_REQUIRED` | Требует N approvals |
| Default TREASURY rule | Hardcoded 2-of-3 для TREASURY wallets |

### 5. Approvals + SoD
**Статус: ✅ Полностью реализован**

| Функция | Реализация |
|---------|------------|
| Multi-approval | Configurable N-of-M |
| Segregation of Duties | Creator ≠ Approver (enforced) |
| Double voting prevention | Один голос на пользователя |
| Approval/Rejection | Любой rejection блокирует TX |

### 6. Signing Adapter
**Статус: ✅ DEV_SIGNER + MPC_TECDSA Simulation**

| Режим | Статус |
|-------|--------|
| Dev Signer | ✅ Работает (локальный ключ из ENV) |
| EIP-1559 | ✅ Поддерживается |
| Legacy Gas | ✅ Fallback |
| MPC_TECDSA | ✅ Simulation режим (см. раздел MPC ниже) |
| HSM Integration | 🔲 Interface готов, не реализован |

```python
# Routing по custody_backend:
if wallet.custody_backend == CustodyBackend.MPC_TECDSA:
    return await self._sign_with_mpc(...)
else:
    return await self._sign_with_dev_signer(...)
```

### 6.1 MPC tECDSA Integration (NEW)
**Статус: ✅ Simulation реализован**

Реализован полный flow для MPC signing с симуляцией `cb-mpc` библиотеки:

| Компонент | Статус | Описание |
|-----------|--------|----------|
| MPCCoordinator | ✅ | Координатор DKG и signing сессий |
| MPCKeyset | ✅ | Хранение keyset metadata (t, n, pubkey, address) |
| MPCSession | ✅ | Tracking DKG/signing sessions |
| MPCNode | ✅ | Registry signer nodes |
| SigningPermit | ✅ | Anti-bypass mechanism |

#### DKG Flow (Distributed Key Generation)
```
POST /v1/wallets/mpc
    │
    ▼
WalletService.create_mpc_wallet()
    │
    ├─► Wallet created (status: PENDING_KEYGEN)
    │
    ▼
MPCCoordinator.create_keyset(t=2, n=3)
    │
    ├─► MPCSession (type: DKG) created
    │
    ├─► Simulate DKG rounds (real: multi-round protocol)
    │
    ├─► Generate keypair (simulation)
    │
    ├─► MPCKeyset created (address derived from pubkey)
    │
    ▼
Wallet updated (status: ACTIVE, address set)
```

#### MPC Signing Flow
```
TxOrchestrator._process_signing()
    │
    ├─► Check wallet.custody_backend == MPC_TECDSA
    │
    ▼
TxOrchestrator._issue_signing_permit()
    │
    ├─► Collect control snapshots (KYT, Policy, Approvals)
    │
    ├─► Get audit_anchor_hash
    │
    ├─► Create SigningPermit (HMAC signed, 60s TTL)
    │
    ▼
SigningService._sign_with_mpc()
    │
    ▼
MPCCoordinator.sign_ethereum_transaction()
    │
    ├─► Validate SigningPermit
    │
    ├─► Create MPCSession (type: SIGNING)
    │
    ├─► Simulate threshold signing (real: multi-round)
    │
    ├─► Mark permit as used
    │
    ▼
Return (raw_tx, tx_hash)
```

#### SigningPermit - Anti-Bypass Mechanism
```json
{
  "tx_request_id": "...",
  "wallet_id": "...",
  "keyset_id": "...",
  "tx_hash": "0x...",
  "kyt_result": "ALLOW",
  "policy_result": "ALLOWED",
  "approval_snapshot": {"count": 2, "required": 2},
  "audit_anchor_hash": "abc123...",
  "expires_at": "2026-01-21T12:01:00Z",
  "permit_hash": "...",
  "signature": "HMAC(...)"
}
```

Coordinator валидирует:
- Permit not used / not revoked
- TTL not expired
- tx_hash matches
- HMAC signature valid

#### Новые таблицы БД
```
┌─────────────────┐     ┌─────────────────┐
│  mpc_keysets    │     │  mpc_sessions   │
├─────────────────┤     ├─────────────────┤
│ id (PK)         │◄────│ keyset_id (FK)  │
│ wallet_id (FK)  │     │ tx_request_id   │
│ threshold_t     │     │ session_type    │
│ total_n         │     │ status          │
│ public_key      │     │ tx_hash         │
│ address         │     │ signature_r,s,v │
│ status          │     │ error_category  │
│ cluster_id      │     │ permit_hash     │
│ key_ref         │     └─────────────────┘
│ participant_nodes│
└─────────────────┘

┌─────────────────┐     ┌─────────────────┐
│  mpc_nodes      │     │ signing_permits │
├─────────────────┤     ├─────────────────┤
│ id (PK)         │     │ id (PK)         │
│ node_name       │     │ tx_request_id   │
│ cluster_id      │     │ keyset_id       │
│ endpoint_url    │     │ tx_hash         │
│ zone            │     │ kyt_result      │
│ status          │     │ policy_result   │
│ last_seen_at    │     │ approval_snapshot│
│ quarantine_reason│     │ audit_anchor_hash│
└─────────────────┘     │ permit_hash     │
                        │ expires_at      │
                        │ is_used         │
                        └─────────────────┘
```

#### Wallets теперь поддерживают custody_backend
```python
class Wallet:
    custody_backend: CustodyBackend  # DEV_SIGNER | MPC_TECDSA
    status: WalletStatus  # PENDING_KEYGEN | ACTIVE | SUSPENDED
    mpc_keyset_id: Optional[str]
    mpc_threshold_t: Optional[int]
    mpc_total_n: Optional[int]
```

### 7. Ethereum Connectivity
**Статус: ✅ Полностью реализован**

| Функция | Реализация |
|---------|------------|
| RPC Client | web3.py HTTPProvider |
| Retry Logic | tenacity (3 attempts, exponential backoff) |
| Nonce Management | In-memory tracker + chain query |
| Gas Estimation | EIP-1559 fee history + fallback |
| Broadcast | `send_raw_transaction` |
| Receipt Fetching | Async polling |

**Конфигурация**: `ETH_RPC_URL` env (default: Sepolia public RPC)

### 8. Chain Listener
**Статус: ✅ Полностью реализован**

| Функция | Реализация |
|---------|------------|
| Confirmation Tracking | Polling pending TX receipts |
| Configurable Confirmations | `CONFIRMATION_BLOCKS` env (default: 3) |
| Inbound Detection | Scanning blocks for transfers to monitored addresses |
| Inbound KYT | Автоматическая проверка sender через KYT |
| Background Process | asyncio task в lifespan |

### 9. Audit Log
**Статус: ✅ Полностью реализован**

| Функция | Реализация |
|---------|------------|
| Append-only | INSERT only, no UPDATE/DELETE |
| Hash Chain | SHA-256, каждый event ссылается на prev_hash |
| Event Types | 23 типа (см. `AuditEventType` enum) |
| Tamper Detection | `GET /v1/audit/verify` проверяет chain integrity |
| Audit Package | Агрегированный JSON по TX с package_hash |

**Структура записи**:
```
event_id | sequence_number | timestamp | event_type | actor_id | 
entity_type | entity_id | payload | prev_hash | hash
```

---

## Безопасность (MVP Level)

| Механизм | Реализация |
|----------|------------|
| Аутентификация | JWT Bearer tokens (HS256) |
| Авторизация | RBAC (ADMIN, OPERATOR, COMPLIANCE, VIEWER) |
| Wallet-scoped roles | OWNER, OPERATOR, VIEWER, APPROVER per wallet |
| Password hashing | bcrypt |
| Idempotency | `Idempotency-Key` header для POST |
| Correlation ID | `X-Correlation-ID` для tracing |
| Audit Trail | Все значимые действия логируются |

**⚠️ НЕ реализовано для MVP**:
- Rate limiting
- API key authentication
- mTLS
- Secret management (Vault integration)
- Encryption at rest

---

## Работающие User Flows

### Flow 1: End-to-End Outbound Transaction
```
1. POST /v1/auth/register     → Создать пользователей
2. POST /v1/auth/login        → Получить JWT токен
3. POST /v1/wallets           → Создать TREASURY кошелёк
4. POST /v1/wallets/{id}/roles → Назначить APPROVER роли
5. POST /v1/policies          → Создать политики (optional)
6. POST /v1/tx-requests       → Создать TX request
   └─► Auto: KYT check → Policy eval → требует 2 approvals
7. POST /v1/tx-requests/{id}/approve (user 1) → Первый approval
8. POST /v1/tx-requests/{id}/approve (user 2) → Второй approval
   └─► Auto: Sign → Broadcast → Confirming
9. GET /v1/tx-requests/{id}   → Проверить статус
10. GET /v1/audit/packages/{id} → Получить audit package
```

### Flow 2: KYT Blocking
```
1. POST /v1/tx-requests (to blacklisted address)
   └─► Auto: KYT BLOCK → статус KYT_BLOCKED (terminal)
```

### Flow 3: KYT Review → Resolution
```
1. POST /v1/tx-requests (to graylisted address)
   └─► Auto: KYT REVIEW → статус KYT_REVIEW, создан Case
2. GET /v1/cases              → Список pending cases
3. POST /v1/cases/{id}/resolve → Resolve (ALLOW/BLOCK)
4. POST /v1/tx-requests/{id}/resume → Продолжить workflow
   └─► Если ALLOW: → Policy eval → Approvals → ...
   └─► Если BLOCK: → KYT_BLOCKED
```

### Flow 4: Policy Blocking
```
1. POST /v1/tx-requests (exceeds limit OR to denylisted address)
   └─► Auto: Policy BLOCK → статус POLICY_BLOCKED (terminal)
```

### Flow 5: Segregation of Duties Enforcement
```
1. User A: POST /v1/tx-requests → Создаёт TX
2. User A: POST /v1/tx-requests/{id}/approve
   └─► 400 Error: "Segregation of Duties: creator cannot be approver"
3. User B: POST /v1/tx-requests/{id}/approve → OK
```

### Flow 6: Audit Chain Verification
```
1. GET /v1/audit/verify
   └─► { is_valid: true, chain_intact: true, verified_events: N }
```

### Flow 7: Inbound Deposit Detection (Background)
```
Chain Listener автоматически:
1. Сканирует блоки на входящие ETH transfers
2. При обнаружении → создаёт Deposit record
3. Выполняет KYT check на sender address
4. Логирует DEPOSIT_DETECTED + DEPOSIT_KYT_EVALUATED в audit
```

### Flow 8: MPC Wallet Creation (NEW)
```
1. POST /v1/wallets/mpc
   {
     "wallet_type": "TREASURY",
     "subject_id": "org-123",
     "mpc_threshold_t": 2,
     "mpc_total_n": 3
   }
   └─► WalletService creates wallet (PENDING_KEYGEN)
   └─► MPCCoordinator.create_keyset() → DKG simulation
   └─► Wallet updated (ACTIVE, address from MPC pubkey)

Response includes:
- wallet.address (derived from MPC pubkey)
- wallet.custody_backend = "MPC_TECDSA"
- wallet.mpc_keyset_id
- wallet.mpc_threshold_t = 2
- wallet.mpc_total_n = 3
```

### Flow 9: MPC Transaction Signing (NEW)
```
1. POST /v1/tx-requests (with MPC wallet)
   └─► Auto: KYT → Policy → Approvals (if required)

2. When ready to sign (approvals collected):
   └─► TxOrchestrator._issue_signing_permit()
       - Collects KYT/Policy/Approval snapshots
       - Creates SigningPermit (60s TTL)
   
   └─► MPCCoordinator.sign_ethereum_transaction()
       - Validates permit
       - Simulates threshold signing
       - Returns signed tx

3. Broadcast → Confirm → Finalize (same as dev signer)
```

### Flow 10: Get MPC Keyset Info (NEW)
```
1. GET /v1/wallets/{wallet_id}/mpc
   └─► Returns keyset details:
       - threshold_t, total_n
       - public_key_compressed
       - address
       - status
       - last_used_at
```

---

## API Endpoints Summary

| Method | Endpoint | Описание |
|--------|----------|----------|
| POST | `/v1/auth/register` | Регистрация пользователя |
| POST | `/v1/auth/login` | Логин, получение JWT |
| GET | `/v1/auth/me` | Текущий пользователь |
| POST | `/v1/wallets` | Создать кошелёк (DEV_SIGNER или MPC_TECDSA) |
| POST | `/v1/wallets/mpc` | Создать MPC кошелёк (tECDSA DKG) |
| GET | `/v1/wallets` | Список кошельков |
| GET | `/v1/wallets/{id}` | Детали кошелька |
| GET | `/v1/wallets/{id}/mpc` | MPC keyset информация |
| POST | `/v1/wallets/{id}/roles` | Назначить роль |
| DELETE | `/v1/wallets/{id}/roles/{user_id}` | Отозвать роль |
| POST | `/v1/tx-requests` | Создать TX request |
| GET | `/v1/tx-requests` | Список TX requests |
| GET | `/v1/tx-requests/{id}` | Детали TX request |
| POST | `/v1/tx-requests/{id}/approve` | Approve/Reject |
| POST | `/v1/tx-requests/{id}/resume` | Resume после KYT resolution |
| POST | `/v1/tx-requests/{id}/check-confirmation` | Manual confirmation check |
| GET | `/v1/cases` | Список KYT cases |
| GET | `/v1/cases/{id}` | Детали case |
| POST | `/v1/cases/{id}/resolve` | Resolve case |
| POST | `/v1/policies` | Создать политику |
| GET | `/v1/policies` | Список политик |
| GET | `/v1/policies/{id}` | Детали политики |
| GET | `/v1/audit/packages/{tx_id}` | Audit package для TX |
| GET | `/v1/audit/verify` | Проверка hash chain |
| GET | `/health` | Health check |

---

## Database Schema

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   users     │     │   wallets   │     │ wallet_roles│
├─────────────┤     ├─────────────┤     ├─────────────┤
│ id (PK)     │     │ id (PK)     │◄────│ wallet_id   │
│ username    │     │ address     │     │ user_id ────┼──►│users│
│ email       │     │ wallet_type │     │ role        │
│ password_h  │     │ subject_id  │     │ created_by  │
│ role        │     │ risk_profile│     └─────────────┘
│ is_active   │     │ key_ref     │
└─────────────┘     │ tags (JSON) │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ tx_requests │     │  policies   │     │daily_volumes│
├─────────────┤     ├─────────────┤     ├─────────────┤
│ id (PK)     │     │ id (PK)     │     │ wallet_id   │
│ wallet_id   │     │ policy_type │     │ date        │
│ tx_type     │     │ address     │     │ asset       │
│ to_address  │     │ token       │     │ total_amount│
│ amount      │     │ wallet_type │     │ tx_count    │
│ status      │     │ limit_amount│     └─────────────┘
│ tx_hash     │     │ req_approvals│
│ kyt_result  │     └─────────────┘
│ policy_result│
│ confirmations│
└──────┬──────┘
       │
       ├───────────────┐
       ▼               ▼
┌─────────────┐  ┌─────────────┐
│  approvals  │  │  kyt_cases  │
├─────────────┤  ├─────────────┤
│ tx_request_id│  │ id (PK)     │
│ user_id     │  │ address     │
│ decision    │  │ direction   │
│ comment     │  │ status      │
└─────────────┘  │ resolved_by │
                 └─────────────┘

┌─────────────────┐     ┌─────────────┐
│  audit_events   │     │  deposits   │
├─────────────────┤     ├─────────────┤
│ id (PK)         │     │ id (PK)     │
│ sequence_number │     │ wallet_id   │
│ timestamp       │     │ tx_hash     │
│ event_type      │     │ from_address│
│ actor_id        │     │ amount      │
│ entity_type     │     │ kyt_result  │
│ entity_id       │     └─────────────┘
│ payload (JSONB) │
│ prev_hash       │
│ hash            │
└─────────────────┘
```

---

## Конфигурация

| Переменная | Default | Описание |
|------------|---------|----------|
| `DATABASE_URL` | PostgreSQL asyncpg | Async connection string |
| `DATABASE_URL_SYNC` | PostgreSQL | Sync connection (Alembic) |
| `ETH_RPC_URL` | Sepolia public | Ethereum RPC endpoint |
| `DEV_SIGNER_PRIVATE_KEY` | Anvil key #0 | Dev mode signing key |
| `JWT_SECRET` | dev secret | JWT signing secret |
| `JWT_EXPIRE_MINUTES` | 60 | Token expiration |
| `CONFIRMATION_BLOCKS` | 3 | Required confirmations |
| `CHAIN_LISTENER_POLL_INTERVAL` | 5 | Polling interval (sec) |
| `KYT_BLACKLIST` | sample addresses | Comma-separated |
| `KYT_GRAYLIST` | sample addresses | Comma-separated |

---

## Roadmap к Production

### Phase 1: Security Hardening
- [ ] Rate limiting
- [ ] API key authentication для service-to-service
- [ ] Vault integration для secrets
- [ ] mTLS между сервисами

### Phase 2: KYT Integration
- [ ] Chainalysis adapter
- [ ] Elliptic adapter
- [ ] TRM Labs adapter
- [ ] Webhook support для async results

### Phase 3: MPC Production (tss-lib Integration)
- [x] MPC data models (keysets, sessions, nodes, permits)
- [x] MPC Coordinator with DKG/signing simulation
- [x] SigningPermit anti-bypass mechanism
- [x] Wallet custody_backend routing
- [x] Go Bank Signer Node with tss-lib
- [x] gRPC protocol definitions
- [x] Browser MPC Client (WebSocket)
- [x] Client-side share encryption (PBKDF2 + AES-GCM)
- [x] IndexedDB share storage
- [ ] Real tss-lib DKG/Signing integration
- [ ] Share encryption at rest (KEK in Vault/KMS)
- [ ] Share backup/restore procedures
- [ ] Key rotation workflow
- [ ] Node quarantine and recovery procedures

### Phase 4: HSM Integration (Optional)
- [ ] HSM integration (AWS CloudHSM / Azure Dedicated HSM)
- [ ] Key ceremony procedures

### Phase 5: Scalability
- [ ] Декомпозиция на микросервисы
- [ ] Message queue (RabbitMQ/Kafka) для async processing
- [ ] Redis для caching и rate limiting
- [ ] Horizontal scaling chain listener
- [ ] MPC Coordinator HA (leader election)

### Phase 6: Compliance
- [ ] GDPR data retention policies
- [ ] SOC2 audit logging requirements
- [ ] PCI-DSS considerations для card-related flows

---

## Запуск

```bash
# Development
docker compose up -d

# API: http://localhost:8000
# Docs: http://localhost:8000/docs
# Health: http://localhost:8000/health

# Run demo
bash examples/curl_examples.sh
```

---

## MPC (Multi-Party Computation) Архитектура

### Обзор

Система использует 2-of-2 threshold ECDSA (tECDSA) для безопасной генерации и использования ключей:
- **Party 0 (Bank)**: Go сервис с tss-lib, хранит bank share
- **Party 1 (User)**: Browser client, хранит user share в IndexedDB

### Компоненты

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            MPC Architecture                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌────────────────┐         WebSocket         ┌────────────────────┐      │
│   │   Browser      │◄────────────────────────►│   MPC Coordinator  │       │
│   │   MPC Client   │                           │   (Python/FastAPI) │       │
│   │                │                           │                    │       │
│   │ - WASM tss-lib │                           │ - Session mgmt     │       │
│   │ - IndexedDB    │                           │ - Message routing  │       │
│   │ - Crypto (AES) │                           │ - Permit signing   │       │
│   └────────────────┘                           └─────────┬──────────┘       │
│          │                                               │                   │
│          │ user share                           gRPC     │                   │
│          ▼ (encrypted)                                   ▼                   │
│   ┌────────────────┐                           ┌────────────────────┐       │
│   │   IndexedDB    │                           │  Bank Signer Node  │       │
│   │   (Browser)    │                           │   (Go + tss-lib)   │       │
│   │                │                           │                    │       │
│   │ PBKDF2 + AES   │                           │ - DKG handler      │       │
│   │ Password-based │                           │ - Signing handler  │       │
│   └────────────────┘                           │ - Encrypted shares │       │
│                                                └────────────────────┘       │
│                                                         │                    │
│                                                         ▼                    │
│                                                ┌────────────────────┐       │
│                                                │   BadgerDB/Files   │       │
│                                                │   (AES-256-GCM)    │       │
│                                                └────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### DKG (Distributed Key Generation) Flow

```
User (Party 1)              Coordinator              Bank (Party 0)
     │                           │                         │
     │──── dkg_start ───────────►│                         │
     │                           │────── StartDKG ────────►│
     │                           │◄───── round1_msg ───────│
     │◄──── dkg_round(1) ────────│                         │
     │                           │                         │
     │──── dkg_round(1) ────────►│                         │
     │                           │────── DKGRound ────────►│
     │                           │◄───── round2_msg ───────│
     │◄──── dkg_round(2) ────────│                         │
     │         ...               │          ...            │
     │                           │                         │
     │◄──── dkg_complete ────────│                         │
     │      (address, pubkey,    │                         │
     │       user_share)         │                         │
     │                           │                         │
     │ Store encrypted share     │      Store bank share   │
     │ in IndexedDB              │      in FileStorage     │
     ▼                           ▼                         ▼
```

### Signing Flow

```
User (Party 1)              Coordinator              Bank (Party 0)
     │                           │                         │
     │──── sign_start ──────────►│                         │
     │   (keyset_id, tx_hash)    │──── CreatePermit ──────►│
     │                           │     (validates tx)      │
     │                           │────── StartSigning ────►│
     │                           │     (with permit)       │
     │                           │◄───── round1_msg ───────│
     │◄──── sign_round(1) ───────│                         │
     │                           │                         │
     │ Decrypt share,            │                         │
     │ compute MPC round         │                         │
     │                           │                         │
     │──── sign_round(1) ───────►│                         │
     │                           │────── SigningRound ────►│
     │                           │◄───── round2_msg ───────│
     │◄──── sign_round(2) ───────│                         │
     │         ...               │          ...            │
     │                           │                         │
     │◄──── sign_complete ───────│                         │
     │      (r, s, v)            │                         │
     ▼                           ▼                         ▼
```

### Безопасность

1. **Share Encryption (Bank)**:
   - PBKDF2 (100k iterations) для key derivation
   - AES-256-GCM для шифрования
   - Random salt + nonce per share

2. **Share Encryption (User)**:
   - PBKDF2 от user password
   - AES-256-GCM
   - Хранение в IndexedDB

3. **SigningPermit** (Anti-bypass):
   - HMAC-подписанный permit от Coordinator
   - Содержит: tx_request_id, wallet_id, keyset_id, tx_hash, expires_at
   - Bank signer проверяет permit перед участием в signing

### Файловая структура MPC

```
mpc-signer/                     # Go Bank Signer Node
├── cmd/signer/main.go          # Entry point
├── internal/
│   ├── dkg/dkg.go              # DKG protocol handler
│   ├── signing/signing.go      # Signing protocol handler
│   ├── server/server.go        # gRPC server
│   └── storage/storage.go      # Encrypted share storage
├── proto/mpc.proto             # gRPC protocol definitions
├── go.mod
└── Dockerfile

frontend/src/lib/mpc/           # Browser MPC Client
├── client.ts                   # WebSocket client
├── crypto.ts                   # PBKDF2 + AES-GCM
├── storage.ts                  # IndexedDB wrapper
└── index.ts

app/services/
├── mpc_coordinator.py          # MPC session coordination
├── mpc_grpc_client.py          # gRPC client for bank signer

app/api/
└── mpc_websocket.py            # WebSocket endpoint for browser
```

