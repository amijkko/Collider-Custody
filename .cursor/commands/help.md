# Collider Custody - Help & Commands

## 🚀 Быстрый старт

### Запуск проекта
```bash
# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker ps

# Логи
docker logs collider-custody-app -f
docker logs collider-postgres -f
```

### Остановка
```bash
docker-compose down
```

---

## 📁 Структура проекта

```
Collider-custody/
├── app/                    # Backend (Python/FastAPI)
│   ├── api/               # REST API endpoints
│   ├── models/            # SQLAlchemy models
│   ├── services/          # Business logic
│   └── schemas/           # Pydantic schemas
├── frontend/              # Frontend (Next.js/TypeScript)
│   └── src/
│       ├── app/           # Pages (App Router)
│       ├── components/    # React components
│       └── lib/           # Utilities & API client
├── mpc-signer/            # Go Bank Signer Node
│   ├── cmd/signer/        # Entry point
│   ├── internal/          # DKG, Signing, Storage
│   └── proto/             # gRPC definitions
├── migrations/            # Alembic migrations
├── docs/                  # Documentation
└── tests/                 # Unit tests
```

---

## 🔧 Основные команды

### Backend

```bash
# Применить миграции
docker exec collider-custody-app alembic upgrade head

# Создать новую миграцию
docker exec collider-custody-app alembic revision --autogenerate -m "description"

# Запустить тесты
docker exec collider-custody-app pytest

# API документация
open http://localhost:8000/docs
```

### Frontend

```bash
# Установить зависимости
cd frontend && npm install

# Запустить dev server
cd frontend && npm run dev

# Собрать production
cd frontend && npm run build
```

### MPC Signer (Go)

```bash
# Собрать образ
docker-compose build mpc-signer

# Запустить
docker-compose up mpc-signer

# Проверить логи
docker logs collider-mpc-signer -f
```

---

## 📚 Документация

### Основные документы

- **README.md** - Общее описание проекта
- **ARCHITECTURE.md** - Техническая архитектура
- **docs/MPC_INTEGRATION_PLAN.md** - План MPC интеграции
- **docs/MPC_STATUS.md** - Текущий статус MPC задачи
- **docs/SERVICES_STATUS.md** - Статус всех сервисов

### API документация

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI spec:** http://localhost:8000/openapi.json

---

## 🔑 Аутентификация

### Тестовые аккаунты

**User:**
- Username: `demo`
- Password: `demo123456`

**Admin:**
- Username: `admin2`
- Password: `admin123456`

### Получение JWT токена

```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo123456"}'
```

---

## 🎯 Основные endpoints

### Wallets
- `POST /v1/wallets` - Создать кошелек
- `GET /v1/wallets` - Список кошельков
- `GET /v1/wallets/{id}/balance` - Баланс ETH
- `POST /v1/wallets/mpc` - Создать MPC кошелек

### Transactions
- `POST /v1/tx-requests` - Создать транзакцию
- `GET /v1/tx-requests` - Список транзакций
- `POST /v1/tx-requests/{id}/approve` - Одобрить
- `POST /v1/tx-requests/{id}/sign` - Подписать

### Deposits
- `GET /v1/deposits` - Список депозитов (user)
- `GET /v1/deposits/admin` - Список депозитов (admin)
- `POST /v1/deposits/{id}/approve` - Одобрить депозит

### MPC WebSocket
- `WS /v1/mpc/ws` - WebSocket для MPC протокола

---

## 🐛 Отладка

### Проверка статуса сервисов

```bash
# Docker контейнеры
docker ps -a

# Логи backend
docker logs collider-custody-app --tail 50

# Логи PostgreSQL
docker logs collider-postgres --tail 50

# Health check
curl http://localhost:8000/health
```

### База данных

```bash
# Подключиться к PostgreSQL
docker exec -it collider-postgres psql -U collider -d collider_custody

# Полезные SQL запросы
SELECT * FROM wallets;
SELECT * FROM tx_requests ORDER BY created_at DESC LIMIT 10;
SELECT * FROM audit_events ORDER BY ts DESC LIMIT 20;
```

### Переменные окружения

```bash
# Проверить env переменные
docker exec collider-custody-app env | grep -E "DATABASE|ETH|JWT|MPC"

# Файл с примерами
cat env.example
```

---

## 🔄 Git команды

### Основные

```bash
# Статус
git status

# Добавить изменения
git add .

# Коммит
git commit -m "feat: description"

# Push
git push origin main

# Pull
git pull origin main
```

### Репозиторий

- **GitHub:** https://github.com/amijkko/Collider-Custody
- **Последний коммит:** `0b5b8a3` - "feat: MPC integration infrastructure checkpoint"

---

## 📊 Статус проекта

### Текущий прогресс

- **Core Functionality:** 95% ✅
- **MPC Integration:** 70% ⚠️
- **Frontend:** 90% ✅
- **Infrastructure:** 95% ✅

### Работающие сервисы

- ✅ PostgreSQL (port 5432)
- ✅ Core API (port 8000)
- ✅ Chain Listener (background)
- ⚠️ Frontend (port 3000) - не запущен
- ❌ MPC Signer (port 50051) - не компилируется

### Известные проблемы

1. **MPC Signer не компилируется** - требуется упростить `signing.go` или исправить tss-lib зависимости
2. **Healthcheck показывает unhealthy** - возможно проблема с endpoint
3. **Frontend не запущен** - требуется `docker-compose up frontend`

Подробнее: `docs/SERVICES_STATUS.md` и `docs/MPC_STATUS.md`

---

## 🆘 Полезные ссылки

- **API Docs:** http://localhost:8000/docs
- **Frontend:** http://localhost:3000
- **GitHub:** https://github.com/amijkko/Collider-Custody
- **Ethereum Sepolia:** https://sepolia.etherscan.io

---

## 💡 Советы

1. **Всегда проверяйте логи** при проблемах: `docker logs <container> -f`
2. **Используйте API docs** для тестирования: http://localhost:8000/docs
3. **Проверяйте статус сервисов:** `docker ps`
4. **Читайте документацию** в `docs/` перед началом работы
5. **Используйте тестовые аккаунты** для разработки

---

**Последнее обновление:** 2026-01-21

