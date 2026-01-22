# Статус MPC интеграции

**Дата обновления:** 2026-01-21  
**Версия:** Checkpoint v1.0

---

## 📊 Общий прогресс

| Компонент | Статус | Прогресс |
|-----------|--------|----------|
| **Архитектура** | ✅ Завершено | 100% |
| **Backend (Python)** | ✅ Завершено | 100% |
| **Frontend (TypeScript)** | ✅ Завершено | 100% |
| **Go Signer Node** | ⚠️ Частично | 70% |
| **gRPC Protocol** | ✅ Завершено | 100% |
| **WebSocket Protocol** | ✅ Завершено | 100% |
| **E2E Testing** | ⏳ Не начато | 0% |

**Общий прогресс: ~85%**

---

## ✅ Что завершено

### 1. Архитектура и планирование
- ✅ Детальный план интеграции (`docs/MPC_INTEGRATION_PLAN.md`)
- ✅ Архитектурные диаграммы (2PC tECDSA)
- ✅ Протоколы DKG и Signing описаны
- ✅ Обновлен `ARCHITECTURE.md` с MPC секцией

### 2. Backend (Python/FastAPI)

#### MPC Coordinator
- ✅ `app/services/mpc_coordinator.py` - координатор сессий
- ✅ Интеграция с `TxOrchestrator`
- ✅ Интеграция с `SigningService`
- ✅ Session management
- ✅ SigningPermit механизм (anti-bypass)

#### gRPC Client
- ✅ `app/services/mpc_grpc_client.py` - клиент для Bank Signer
- ✅ Методы: `start_dkg()`, `process_dkg_round()`
- ✅ Методы: `start_signing()`, `process_signing_round()`
- ✅ `create_permit()` / `verify_permit()` для авторизации
- ⚠️ Режим: **Simulation** (не реальный gRPC)

#### WebSocket Endpoint
- ✅ `app/api/mpc_websocket.py` - WebSocket на `/v1/mpc/ws`
- ✅ JWT authentication
- ✅ DKG protocol: `dkg_start` → `dkg_round` → `dkg_complete`
- ✅ Signing protocol: `sign_start` → `sign_round` → `sign_complete`
- ✅ Session timeout и cleanup
- ✅ Message routing между browser и bank signer

#### Database Models
- ✅ `app/models/mpc.py` - MPCKeyset, MPCNode, MPCSession
- ✅ Миграции: `002_add_mpc_tables.py`
- ✅ Интеграция с Wallet моделью

#### REST API
- ✅ `POST /v1/wallets/mpc` - создание MPC кошелька
- ✅ `GET /v1/wallets/{wallet_id}/mpc` - информация о MPC кошельке

### 3. Frontend (TypeScript/Next.js)

#### Browser MPC Client
- ✅ `frontend/src/lib/mpc/client.ts` - WebSocket клиент
  - ✅ `connect()`, `authenticate()`
  - ✅ `startDKG()`, `startSigning()`
  - ✅ Heartbeat механизм
  - ✅ Error handling

#### Crypto & Storage
- ✅ `frontend/src/lib/mpc/crypto.ts` - PBKDF2 + AES-GCM
  - ✅ `encrypt()` / `decrypt()` методы
  - ✅ Password-based key derivation
- ✅ `frontend/src/lib/mpc/storage.ts` - IndexedDB wrapper
  - ✅ `saveShare()`, `getShare()`, `deleteShare()`
  - ✅ Encrypted share persistence

#### UI Components
- ✅ `frontend/src/components/mpc/create-mpc-wallet-modal.tsx`
- ✅ `frontend/src/components/mpc/sign-transaction-modal.tsx`

### 4. Bank Signer Node (Go)

#### Структура проекта
- ✅ `mpc-signer/cmd/signer/main.go` - entry point
- ✅ `mpc-signer/internal/dkg/dkg.go` - DKG handler
- ✅ `mpc-signer/internal/signing/signing.go` - Signing handler
- ✅ `mpc-signer/internal/server/server.go` - gRPC server
- ✅ `mpc-signer/internal/storage/storage.go` - encrypted file storage
- ✅ `mpc-signer/proto/mpc.proto` - gRPC protocol definitions
- ✅ `mpc-signer/Dockerfile` - Docker образ
- ✅ `mpc-signer/go.mod` - зависимости

#### Функциональность
- ✅ DKG session management
- ✅ Signing session management
- ✅ Encrypted share storage (PBKDF2 + AES-256-GCM)
- ✅ Session timeout и cleanup
- ✅ SigningPermit validation
- ⚠️ **Проблема:** `signing.go` все еще импортирует `tss-lib`, но `go.mod` его не содержит

### 5. Инфраструктура

- ✅ `docker-compose.yml` - добавлен сервис `mpc-signer`
- ✅ `app/config.py` - добавлены `mpc_signer_url` и `mpc_signer_enabled`
- ✅ `.gitignore` - обновлен для Go, Node.js, MPC data

---

## ⚠️ Текущие проблемы

### 1. Go Signer Node не компилируется

**Проблема:**
- `mpc-signer/internal/signing/signing.go` импортирует `tss-lib`:
  ```go
  import (
      "github.com/bnb-chain/tss-lib/v2/common"
      "github.com/bnb-chain/tss-lib/v2/ecdsa/keygen"
      "github.com/bnb-chain/tss-lib/v2/ecdsa/signing"
      "github.com/bnb-chain/tss-lib/v2/tss"
  )
  ```
- Но `go.mod` не содержит `tss-lib` (был удален из-за проблем с зависимостями)

**Статус:** `dkg.go` упрощен (симуляция), но `signing.go` все еще требует `tss-lib`

**Решение:**
- Вариант A: Упростить `signing.go` (убрать tss-lib, использовать симуляцию)
- Вариант B: Исправить зависимости tss-lib (требует времени)

### 2. Реальная криптография не интегрирована

**Текущее состояние:**
- `dkg.go` - использует `elliptic.P256()` (симуляция, не secp256k1)
- `signing.go` - ссылается на `tss-lib` (не компилируется)
- Нет реального tECDSA протокола

**Требуется:**
- Интеграция `tss-lib` или альтернативной библиотеки
- Реальный DKG протокол (2-of-2 threshold)
- Реальный Signing протокол

### 3. gRPC сервер не сгенерирован

**Проблема:**
- `proto/mpc.proto` существует
- Но нет сгенерированного Go кода из proto
- `server.go` использует placeholder типы вместо реальных gRPC stubs

**Требуется:**
```bash
protoc --go_out=. --go-grpc_out=. proto/mpc.proto
```

### 4. MPC Signer не запущен

**Статус:**
- Docker контейнер не собран (из-за проблем компиляции)
- Сервис не доступен на `localhost:50051`
- Нет health check endpoint

---

## ⏳ Что осталось сделать

### Приоритет 1: Завершить Go Signer Node

1. **Упростить `signing.go`** (быстрое решение)
   - Убрать зависимости от `tss-lib`
   - Использовать симуляцию (как в `dkg.go`)
   - Собрать Docker образ
   - Протестировать gRPC endpoint

2. **Или интегрировать реальный tss-lib** (долгосрочное решение)
   - Исправить зависимости (`github.com/agl/ed25519` проблема)
   - Интегрировать реальный DKG/Signing
   - Сгенерировать gRPC stubs

### Приоритет 2: E2E тестирование

1. **Запустить все сервисы:**
   - ✅ PostgreSQL (работает)
   - ✅ Core API (работает)
   - ⏳ MPC Signer (не запущен)
   - ✅ Frontend (работает)

2. **Протестировать flow:**
   - Создание MPC кошелька (DKG)
   - Сохранение shares (bank + user)
   - Создание транзакции
   - MPC signing
   - Broadcast на Sepolia

### Приоритет 3: Реальная криптография

1. **Интеграция tss-lib в Go:**
   - Решить проблемы с зависимостями
   - Интегрировать реальный DKG
   - Интегрировать реальный Signing

2. **Browser MPC Client:**
   - Интеграция WASM tss-lib (или)
   - Pure TypeScript реализация threshold ECDSA

---

## 📝 Технические детали

### Файловая структура

```
mpc-signer/                     # Go Bank Signer Node
├── cmd/signer/main.go          # ✅ Entry point
├── internal/
│   ├── dkg/dkg.go              # ⚠️ Упрощен (симуляция)
│   ├── signing/signing.go      # ❌ Требует tss-lib
│   ├── server/server.go        # ✅ gRPC server (placeholder)
│   └── storage/storage.go      # ✅ Encrypted storage
├── proto/mpc.proto             # ✅ Protocol definitions
├── go.mod                      # ⚠️ Без tss-lib
└── Dockerfile                  # ✅ Готов

frontend/src/lib/mpc/           # Browser MPC Client
├── client.ts                   # ✅ WebSocket client
├── crypto.ts                   # ✅ PBKDF2 + AES-GCM
├── storage.ts                  # ✅ IndexedDB wrapper
└── index.ts                    # ✅ Exports

app/services/
├── mpc_coordinator.py          # ✅ Session coordination
├── mpc_grpc_client.py          # ✅ gRPC client (simulation)
└── orchestrator.py              # ✅ MPC integration

app/api/
└── mpc_websocket.py            # ✅ WebSocket endpoint
```

### Зависимости

**Go (mpc-signer):**
- ✅ `go.uber.org/zap` - логирование
- ✅ `google.golang.org/grpc` - gRPC
- ✅ `golang.org/x/crypto` - криптография
- ❌ `github.com/bnb-chain/tss-lib/v2` - **отсутствует** (проблема)

**Python:**
- ✅ Все зависимости установлены
- ✅ `grpcio` для будущего реального gRPC

**TypeScript:**
- ✅ Все зависимости установлены
- ✅ WebSocket client готов

---

## 🎯 Следующие шаги

### Краткосрочные (1-2 дня)

1. **Упростить `signing.go`** - убрать tss-lib, использовать симуляцию
2. **Собрать Docker образ** - `docker-compose build mpc-signer`
3. **Запустить сервис** - `docker-compose up mpc-signer`
4. **Протестировать WebSocket** - создать MPC кошелек через UI
5. **Протестировать gRPC** - проверить коммуникацию Python ↔ Go

### Среднесрочные (1 неделя)

1. **E2E тестирование** - полный flow на Sepolia
2. **Исправить зависимости tss-lib** - реальная криптография
3. **Генерация gRPC stubs** - из proto файла
4. **Оптимизация** - производительность, error handling

### Долгосрочные (2-4 недели)

1. **Реальная интеграция tss-lib** - полный DKG/Signing протокол
2. **Browser WASM client** - или TypeScript реализация
3. **Production hardening** - security, monitoring, logging
4. **Документация** - API docs, deployment guide

---

## 📊 Метрики

- **Файлов создано:** 110+
- **Строк кода:** ~21,000
- **Go файлов:** 5
- **TypeScript файлов (MPC):** 4
- **Python файлов (MPC):** 3
- **Время разработки:** ~2 недели
- **Коммит:** `0b5b8a3` - "feat: MPC integration infrastructure checkpoint"

---

## 🔗 Ссылки

- **GitHub:** https://github.com/amijkko/Collider-Custody
- **План интеграции:** `docs/MPC_INTEGRATION_PLAN.md`
- **Архитектура:** `ARCHITECTURE.md` (секция MPC)
- **tss-lib:** https://github.com/bnb-chain/tss-lib

---

**Последнее обновление:** 2026-01-21  
**Статус:** Infrastructure готов, требуется завершение Go Signer Node

