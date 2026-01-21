# План: Production WaaS + MPC Signing (tECDSA EOA) на базе Coinbase `cb-mpc`

## 0) Цель и фокус (2 фичи)
1. **WaaS в production-режим**: создание реальных **EOA-кошельков** (Ethereum) через **tECDSA DKG**, без существования “полного приватного ключа” (только shares).
2. **Production signing**: подпись EOA-транзакций через **tECDSA MPC** и интеграция в текущий **TxOrchestrator** (KYT → Policy → Approvals/SoD → Sign → Broadcast → Confirm → Finalize).

**Вне периметра (пока):**
- HSM (явно исключаем).
- Полная интеграция KYT-провайдеров (оставляем текущий mock/adapter pattern).
- Полная микросервисная декомпозиция продукта (делаем минимально необходимый MPC-кластер).

---

## 1) Почему `cb-mpc` и что именно используем
`cb-mpc` — это криптографическая библиотека (C++), из которой берём:
- **Threshold EC-DKG** для ECDSA (создание keyset / pubkey / EOA address).
- **Threshold ECDSA signing** (t-of-n) для подписи tx-hash.
- (P1) **Backup/Restore** шеров (поддержка эксплуатационного восстановления).

---

## 2) Target Architecture (минимальная, но боеспособная)

### 2.1 Компоненты
1) **MPC Coordinator (Sign Gateway)**
- API: `CreateKeyset`, `SignTx` (и admin endpoints по желанию: status/health)
- Координирует DKG/signing сессии, выбирает участников, собирает подпись.

2) **MPC Signer Nodes (n штук)**
- Хранят **зашифрованные** shares локально.
- Участвуют в DKG и signing (возвращают commitments/signature shares).

3) **Session Store**
- Метаданные сессий: idempotency, quorum, timeouts, причины ошибок, завершение.
- **Не хранит секреты**.

### 2.2 Topology по умолчанию
- `n=3`, `t=2` (устойчивость к падению 1 узла).
- Разносить узлы по разным trust-zones (VM/подсети/учётки/доступы).

---

## 3) Feature #1 — WaaS production: создание EOA кошелька через tECDSA DKG

### 3.1 User-flow
`POST /v1/wallets` с `custody_backend=MPC_TECDSA`:

1) WalletService создаёт запись кошелька в статусе `PENDING_KEYGEN`.
2) WalletService вызывает **MPC Coordinator**: `CreateKeyset(t,n, tenant, wallet_id)`.
3) Coordinator запускает **DKG** на signer nodes.
4) Coordinator возвращает:
   - `keyset_id`
   - `public_key` (secp256k1)
   - `address` (EOA, derived from pubkey)
5) WalletService сохраняет:
   - `wallet.address`
   - `wallet.key_ref = mpc-tecdsa://<cluster>/<keyset_id>`
   - метаданные t/n в `wallet.tags`
6) Audit: `MPC_KEYGEN_STARTED/COMPLETED/FAILED`, `WALLET_CREATED`.

### 3.2 Key model
- **Нет полного приватного ключа**: только shares на signer nodes.
- `key_ref` — обязательный указатель на keyset (URI).

### 3.3 Хранение shares (без HSM)
- Share на каждом node хранится только в **ciphertext** (encryption-at-rest).
- KEK хранится в secret-store (Vault/KMS/аналог; HSM не используем).
- Plaintext появляется только в RAM на время протокола, с zeroization.

### 3.4 Backup/Recovery (P1)
- Реализовать admin-процедуры backup/restore shares.
- Runbook: “умер 1 узел”, “потеряли share”, “компрометация узла”.

---

## 4) Feature #2 — Production signing: tECDSA MPC подпись EOA транзакций

### 4.1 Интеграция в текущий TxOrchestrator
Сохраняем текущий pipeline:
`KYT → Policy → Approvals/SoD → SIGN_PENDING → BROADCAST → CONFIRM → FINALIZED`

В `SIGN_PENDING`:
1) Orchestrator/SigningService формирует canonical tx payload.
2) Вычисляет `tx_hash`.
3) Вызывает MPC Coordinator: `SignTx(keyset_id, tx_hash, permit)`.
4) Coordinator собирает ECDSA signature, возвращает подпись/подписанный raw tx.
5) EthereumService делает `send_raw_transaction`.

### 4.2 Anti-bypass: SigningPermit (обязательный)
Чтобы MPC не стал “чёрным ходом”, Coordinator принимает запрос подписи **только** с валидным `SigningPermit`:

Содержимое permit:
- `tx_request_id`, `wallet_id`, `keyset_id`
- `tx_hash` (или hash canonical payload)
- snapshot контролей: KYT result, policy result, approvals (кто/сколько/required)
- `audit_anchor_hash` (привязка к audit chain)
- TTL (например 60 секунд) + одноразовость (replay protection)

Coordinator валидирует:
- подпись permit (внутренний сервисный ключ)
- TTL/replay
- соответствие `tx_hash`

### 4.3 Ретрай и error taxonomy
Классифицировать ошибки:
- **Transient**: таймаут узла, сетевые сбои → ретрай/замена участника
- **Permanent**: invalid permit, несовпадение tx_hash → отказ (terminal)
- **Protocol violation**: некорректный share/ответ → quarantine node, метрика/алерт

---

## 5) Изменения в продукте (минимально необходимые)

### 5.1 DB
Добавить таблицы:
- `mpc_keysets(keyset_id, wallet_id, t, n, pubkey, address, status, created_at)`
- `mpc_sessions(session_id, keyset_id, tx_request_id, tx_hash, status, started_at, ended_at, error_code)`
- `mpc_nodes(node_id, zone, status, last_seen_at)` (для selection/allowlist)

### 5.2 API
Сохранить текущие tx endpoints, добавить параметры в wallets:
- `POST /v1/wallets`:
  - `custody_backend`: `DEV_SIGNER | MPC_TECDSA`
  - `mpc_t`, `mpc_n` (опционально)

Опционально admin-only:
- `GET /v1/wallets/{id}/mpc` (status/meta)
- `POST /v1/wallets/{id}/mpc/refresh` / `rotate` (на P2)

### 5.3 Audit events
- `MPC_KEYGEN_STARTED/COMPLETED/FAILED`
- `MPC_SIGN_STARTED/COMPLETED/FAILED`
- `SIGN_PERMIT_ISSUED/REJECTED`

---

## 6) План реализации (по этапам)

### Этап A — WaaS keygen (DKG) end-to-end
1) Поднять MPC Coordinator + 3 Signer Nodes (контейнеры).
2) Реализовать `CreateKeyset` в Coordinator на базе cb-mpc DKG.
3) В WalletService переключить создание wallet на `CreateKeyset` при `MPC_TECDSA`.
4) Сохранить `wallet.address` + `wallet.key_ref`.
5) Интеграционный тест: create wallet → inbound deposit на Sepolia → listener фиксирует депозит.

**Выход:** реальные EOA-адреса per-wallet, shares распределены.

### Этап B — Production signing в Orchestrator
1) Реализовать `SigningPermit` issuance в Orchestrator.
2) Реализовать `SignTx` в Coordinator (t-of-n ECDSA signing).
3) Подключить `_mpc_sign(tx_dict, key_ref)` в SigningService и роутинг по `key_ref`.
4) E2E сценарий Sepolia: tx-request → approvals → MPC sign → broadcast → confirm → finalize.
5) Аудит/логирование MPC событий в audit chain.

**Выход:** подпись EOA tx происходит только через MPC и только после контролей.

### Этап C — Backup/Recovery минимум (P1)
1) Реализовать backup/restore shares (admin ops).
2) Runbooks и тесты:
   - падение signer node (t=2 из 3)
   - восстановление share
   - quarantine node и повторная подпись
3) Метрики и алёрты по latency/availability/error taxonomy.

---

## 7) Definition of Done (DoD)

### WaaS production
- `POST /v1/wallets (MPC_TECDSA)` возвращает wallet с EOA address, derived из MPC pubkey.
- Shares не существуют в plaintext на диске.
- Keygen события фиксируются в audit.

### Signing production
- Для MPC-кошельков dev signer не используется.
- Coordinator подписывает **только** при валидном `SigningPermit`.
- Транзакция подтверждается в Sepolia и доходит до `FINALIZED`.
- Ошибки классифицированы; protocol violations приводят к quarantine node.

---

## 8) Риски и ограничения
- MPC добавляет сетевые раунды и требования к отказоустойчивости — нужна дисциплина по timeouts, selection, observability.
- Выбор cb-mpc предполагает интеграцию C++ core (обычно через gRPC сервис-обёртку на C++ или Go).
- Без базового secret management и encryption-at-rest MPC запускать нельзя (минимальный baseline обязателен).

---
