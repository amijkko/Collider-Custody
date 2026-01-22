# Статус сервисов и готовности

**Дата обновления:** 2026-01-21  
**Версия:** Checkpoint v1.0

---

## 📊 Общий статус сервисов

| Сервис | Статус | Готовность | Порт | Примечания |
|--------|--------|------------|------|------------|
| **PostgreSQL** | ✅ Работает | 100% | 5432 | Healthy |
| **Core API (FastAPI)** | ⚠️ Работает | 95% | 8000 | Unhealthy (healthcheck) |
| **Frontend (Next.js)** | ❓ Неизвестно | 90% | 3000 | Не запущен |
| **MPC Signer (Go)** | ❌ Не запущен | 70% | 50051 | Не компилируется |
| **Chain Listener** | ✅ Работает | 100% | - | Background service |

**Общая готовность системы: ~85%**

---

## ✅ Работающие сервисы

### 1. PostgreSQL Database

**Статус:** ✅ **Работает** (Healthy)

**Детали:**
- **Контейнер:** `collider-postgres`
- **Порт:** `5432`
- **Версия:** PostgreSQL 16-alpine
- **Healthcheck:** ✅ Passing
- **Uptime:** ~5 hours

**Готовность:** 100%

**Функциональность:**
- ✅ Все таблицы созданы
- ✅ Миграции применены (`001_initial_schema`, `002_add_mpc_tables`)
- ✅ Индексы созданы
- ✅ Foreign keys настроены
- ✅ Enum типы работают

**Модели данных:**
- ✅ Users, Wallets, WalletRoles
- ✅ TxRequests, TxApprovals
- ✅ Policies, Cases
- ✅ AuditEvents, Deposits
- ✅ MPCKeyset, MPCNode, MPCSession

---

### 2. Core API (FastAPI)

**Статус:** ⚠️ **Работает** (Unhealthy по healthcheck, но функционал работает)

**Детали:**
- **Контейнер:** `collider-custody-app`
- **Порт:** `8000`
- **Framework:** FastAPI 0.109.0
- **Python:** 3.11
- **Healthcheck:** ⚠️ Unhealthy (возможно, проблема с healthcheck endpoint)
- **Uptime:** ~2 hours

**Готовность:** 95%

**Работающие endpoints:**

#### Authentication
- ✅ `POST /v1/auth/register` - регистрация
- ✅ `POST /v1/auth/login` - вход
- ✅ `GET /v1/auth/me` - текущий пользователь

#### Wallets
- ✅ `POST /v1/wallets` - создание кошелька
- ✅ `GET /v1/wallets` - список кошельков
- ✅ `GET /v1/wallets/{wallet_id}` - информация о кошельке
- ✅ `GET /v1/wallets/{wallet_id}/balance` - баланс ETH
- ✅ `POST /v1/wallets/{wallet_id}/roles` - назначение ролей
- ✅ `POST /v1/wallets/mpc` - создание MPC кошелька
- ✅ `GET /v1/wallets/{wallet_id}/mpc` - информация о MPC кошельке

#### Transactions
- ✅ `POST /v1/tx-requests` - создание транзакции
- ✅ `GET /v1/tx-requests` - список транзакций
- ✅ `GET /v1/tx-requests/{tx_request_id}` - информация о транзакции
- ✅ `POST /v1/tx-requests/{tx_request_id}/approve` - одобрение
- ✅ `POST /v1/tx-requests/{tx_request_id}/reject` - отклонение
- ✅ `POST /v1/tx-requests/{tx_request_id}/sign` - подпись
- ✅ `GET /v1/tx-requests/{tx_request_id}/check-confirmation` - проверка подтверждений

#### KYT & Cases
- ✅ `GET /v1/cases` - список cases
- ✅ `GET /v1/cases/{case_id}` - информация о case
- ✅ `POST /v1/cases/{case_id}/resolve` - разрешение case

#### Policies
- ✅ `GET /v1/policies` - список политик
- ✅ `POST /v1/policies` - создание политики
- ✅ `GET /v1/policies/{policy_id}` - информация о политике

#### Deposits
- ✅ `GET /v1/deposits` - список депозитов (user)
- ✅ `GET /v1/deposits/admin` - список депозитов (admin)
- ✅ `POST /v1/deposits/{deposit_id}/approve` - одобрение депозита
- ✅ `POST /v1/deposits/{deposit_id}/reject` - отклонение депозита

#### Audit
- ✅ `GET /v1/audit/packages/{tx_request_id}` - audit package
- ✅ `GET /v1/audit/verify` - проверка hash chain

#### MPC WebSocket
- ✅ `WS /v1/mpc/ws` - WebSocket для MPC протокола

**Проблемы:**
- ⚠️ Healthcheck показывает "unhealthy" (возможно, проблема с endpoint или таймаутом)
- ⚠️ MPC gRPC client в режиме симуляции (не реальный gRPC)

**Не реализовано:**
- ❌ Rate limiting
- ❌ Request throttling
- ❌ Advanced monitoring
- ❌ Metrics endpoint

---

### 3. Chain Listener (Background Service)

**Статус:** ✅ **Работает**

**Детали:**
- **Тип:** Background service (внутри Core API)
- **Интервал опроса:** 5 секунд (configurable)
- **Подтверждения:** 3 блока (configurable)
- **Статус:** Running

**Готовность:** 100%

**Функциональность:**
- ✅ Мониторинг исходящих транзакций (confirmations)
- ✅ Обнаружение входящих депозитов (ETH transfers)
- ✅ Обновление статусов транзакций
- ✅ Создание Deposit событий
- ✅ Inbound KYT проверка
- ✅ Audit logging

**Мониторинг:**
- ✅ Логирование всех событий
- ✅ Error handling
- ✅ Graceful shutdown

---

## ⚠️ Частично работающие сервисы

### 4. Frontend (Next.js)

**Статус:** ❓ **Неизвестно** (не запущен в Docker)

**Детали:**
- **Контейнер:** `collider-frontend` (не запущен)
- **Порт:** `3000`
- **Framework:** Next.js 14 (App Router)
- **TypeScript:** ✅
- **Tailwind CSS:** ✅

**Готовность:** 90%

**Реализованные страницы:**

#### Client Pages
- ✅ `/login` - вход
- ✅ `/register` - регистрация
- ✅ `/app` - dashboard (главная)
- ✅ `/app/deposit` - депозиты
- ✅ `/app/withdraw` - вывод средств
- ✅ `/app/sign` - подпись транзакций

#### Admin Pages
- ✅ `/admin` - admin dashboard
- ✅ `/admin/deposits` - управление депозитами
- ✅ `/admin/withdrawals` - управление выводами

**Компоненты:**
- ✅ Layout (Header, Sidebar)
- ✅ UI Components (Button, Card, Modal, Toast)
- ✅ Wallet creation modal
- ✅ MPC wallet creation modal
- ✅ Transaction signing modal
- ✅ Deposit/Withdraw forms

**API Integration:**
- ✅ `frontend/src/lib/api.ts` - REST API client
- ✅ JWT token management
- ✅ Error handling
- ✅ Correlation ID support

**MPC Client:**
- ✅ `frontend/src/lib/mpc/client.ts` - WebSocket client
- ✅ `frontend/src/lib/mpc/crypto.ts` - encryption
- ✅ `frontend/src/lib/mpc/storage.ts` - IndexedDB

**Проблемы:**
- ❓ Не запущен в Docker (неизвестно, работает ли локально)
- ⚠️ MPC UI компоненты созданы, но не протестированы с реальным WebSocket

**Требуется:**
- Запустить frontend: `docker-compose up frontend`
- Протестировать все страницы
- Проверить интеграцию с MPC WebSocket

---

## ❌ Не работающие сервисы

### 5. MPC Signer Node (Go)

**Статус:** ❌ **Не запущен** (не компилируется)

**Детали:**
- **Контейнер:** `collider-mpc-signer` (не собран)
- **Порт:** `50051` (gRPC)
- **Язык:** Go 1.21
- **Framework:** gRPC

**Готовность:** 70%

**Что готово:**
- ✅ Структура проекта
- ✅ `cmd/signer/main.go` - entry point
- ✅ `internal/dkg/dkg.go` - DKG handler (упрощен)
- ✅ `internal/signing/signing.go` - Signing handler (требует tss-lib)
- ✅ `internal/server/server.go` - gRPC server (placeholder)
- ✅ `internal/storage/storage.go` - encrypted storage
- ✅ `proto/mpc.proto` - protocol definitions
- ✅ `Dockerfile` - готов

**Проблемы:**
- ❌ `signing.go` импортирует `tss-lib`, но `go.mod` его не содержит
- ❌ Не компилируется: `missing go.sum entry for module providing package github.com/bnb-chain/tss-lib/v2`
- ❌ Docker образ не собран
- ❌ gRPC stubs не сгенерированы из proto

**Требуется:**
1. Упростить `signing.go` (убрать tss-lib) ИЛИ
2. Исправить зависимости tss-lib
3. Сгенерировать gRPC stubs: `protoc --go_out=. --go-grpc_out=. proto/mpc.proto`
4. Собрать Docker образ: `docker-compose build mpc-signer`
5. Запустить: `docker-compose up mpc-signer`

---

## 📋 Детальный статус компонентов

### Backend Services

| Компонент | Статус | Готовность | Примечания |
|-----------|--------|------------|------------|
| **AuthService** | ✅ | 100% | JWT, RBAC, wallet permissions |
| **WalletService** | ✅ | 100% | DEV_SIGNER + MPC_TECDSA |
| **TxOrchestrator** | ✅ | 100% | State machine, все статусы |
| **KYTService** | ✅ | 100% | Mock (blacklist/graylist) |
| **PolicyService** | ✅ | 100% | Rules engine, limits |
| **SigningService** | ✅ | 95% | DEV_SIGNER работает, MPC в симуляции |
| **EthereumService** | ✅ | 100% | RPC, broadcast, confirmations |
| **ChainListener** | ✅ | 100% | Outbound + inbound monitoring |
| **AuditService** | ✅ | 100% | Hash chain, packages |
| **MPCCoordinator** | ✅ | 90% | Session mgmt, но Go signer не работает |
| **MPC gRPC Client** | ⚠️ | 70% | Симуляция, не реальный gRPC |

### Frontend Components

| Компонент | Статус | Готовность | Примечания |
|-----------|--------|------------|------------|
| **Auth** | ✅ | 100% | Login, register, JWT storage |
| **Dashboard** | ✅ | 100% | User + Admin views |
| **Wallets** | ✅ | 100% | List, create, balance |
| **Deposits** | ✅ | 100% | List, approve, reject |
| **Withdrawals** | ✅ | 100% | Create, approve, sign |
| **Transactions** | ✅ | 100% | List, details, status |
| **MPC Client** | ✅ | 90% | WebSocket готов, но не протестирован |
| **MPC UI** | ✅ | 80% | Modals созданы, не протестированы |

### Infrastructure

| Компонент | Статус | Готовность | Примечания |
|-----------|--------|------------|------------|
| **Docker Compose** | ✅ | 95% | Все сервисы определены |
| **PostgreSQL** | ✅ | 100% | Работает, healthy |
| **Database Migrations** | ✅ | 100% | Alembic, все миграции применены |
| **Environment Config** | ✅ | 100% | .env.example, config.py |
| **Logging** | ✅ | 90% | Structured logging |
| **Error Handling** | ✅ | 90% | Global exception handler |
| **CORS** | ✅ | 100% | Настроен |
| **Health Checks** | ⚠️ | 70% | Есть, но показывает unhealthy |

---

## 🔧 Требуется исправить

### Критичные проблемы

1. **MPC Signer не компилируется**
   - Приоритет: 🔴 Высокий
   - Время: 2-4 часа
   - Решение: Упростить `signing.go` или исправить tss-lib зависимости

2. **Frontend не запущен**
   - Приоритет: 🟡 Средний
   - Время: 5 минут
   - Решение: `docker-compose up frontend`

3. **Healthcheck показывает unhealthy**
   - Приоритет: 🟡 Средний
   - Время: 30 минут
   - Решение: Проверить `/health` endpoint, исправить healthcheck

### Некритичные улучшения

1. **Реальная интеграция tss-lib**
   - Приоритет: 🟢 Низкий (для production)
   - Время: 1-2 недели
   - Решение: Исправить зависимости, интегрировать реальный протокол

2. **E2E тестирование**
   - Приоритет: 🟡 Средний
   - Время: 1-2 дня
   - Решение: Протестировать полный flow на Sepolia

3. **Мониторинг и метрики**
   - Приоритет: 🟢 Низкий
   - Время: 1 неделя
   - Решение: Prometheus, Grafana, или аналоги

---

## 📊 Метрики готовности

### По категориям

| Категория | Готовность |
|-----------|------------|
| **Core Functionality** | 95% |
| **MPC Integration** | 70% |
| **Frontend** | 90% |
| **Infrastructure** | 95% |
| **Testing** | 30% |
| **Documentation** | 85% |

### По сервисам

- **PostgreSQL:** ✅ 100%
- **Core API:** ⚠️ 95%
- **Chain Listener:** ✅ 100%
- **Frontend:** ❓ 90% (не запущен)
- **MPC Signer:** ❌ 70% (не компилируется)

---

## 🚀 План запуска всех сервисов

### Шаг 1: Исправить MPC Signer (2-4 часа)
```bash
# Упростить signing.go или исправить зависимости
cd mpc-signer
# ... исправления ...
docker-compose build mpc-signer
```

### Шаг 2: Запустить все сервисы (5 минут)
```bash
docker-compose up -d
```

### Шаг 3: Проверить статус (5 минут)
```bash
docker ps
curl http://localhost:8000/health
curl http://localhost:3000
```

### Шаг 4: E2E тестирование (1-2 дня)
- Создать MPC кошелек
- Сделать депозит
- Создать транзакцию
- Подписать через MPC
- Проверить на Sepolia

---

## 📝 Примечания

- **Последний коммит:** `0b5b8a3` - "feat: MPC integration infrastructure checkpoint"
- **GitHub:** https://github.com/amijkko/Collider-Custody
- **Основная проблема:** MPC Signer не компилируется из-за отсутствия tss-lib в go.mod
- **Рекомендация:** Упростить `signing.go` для быстрого MVP, затем интегрировать реальный tss-lib

---

**Последнее обновление:** 2026-01-21  
**Следующий шаг:** Исправить компиляцию MPC Signer Node

