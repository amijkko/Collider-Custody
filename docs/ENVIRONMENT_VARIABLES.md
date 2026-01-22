# Environment Variables Documentation

Документация по переменным окружения для деплоя на Vercel и Railway.

---

## Vercel (Frontend)

### Обязательные переменные

| Переменная | Описание | Пример | Где настроить |
|-----------|----------|--------|---------------|
| `NEXT_PUBLIC_CORE_API_URL` | URL Backend API (Railway) | `https://your-app.railway.app` | Vercel Dashboard → Settings → Environment Variables |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL для MPC (опционально) | `wss://your-app.railway.app` | Vercel Dashboard → Settings → Environment Variables |

### Настройка в Vercel Dashboard

1. Перейдите в ваш проект на Vercel
2. Откройте **Settings** → **Environment Variables**
3. Добавьте переменные для всех окружений (Production, Preview, Development):

```
NEXT_PUBLIC_CORE_API_URL=https://your-railway-app.railway.app
NEXT_PUBLIC_WS_URL=wss://your-railway-app.railway.app
```

**Важно:** 
- Переменные с префиксом `NEXT_PUBLIC_` доступны в браузере
- После добавления переменных нужно передеплоить проект

---

## Railway (Backend API)

### Обязательные переменные

| Переменная | Описание | Пример | Где настроить |
|-----------|----------|--------|---------------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:port/db` | Railway Dashboard → PostgreSQL Service → Variables (автоматически) |
| `DATABASE_URL_SYNC` | Sync версия для Alembic | `postgresql://user:pass@host:port/db` | Railway Dashboard → Backend Service → Variables |
| `JWT_SECRET` | Секретный ключ для JWT токенов | `your-super-secret-key-here` | Railway Dashboard → Backend Service → Variables |
| `ENVIRONMENT` | Окружение | `production` | Railway Dashboard → Backend Service → Variables |
| `ETH_RPC_URL` | Ethereum RPC endpoint | `https://ethereum-sepolia-rpc.publicnode.com` | Railway Dashboard → Backend Service → Variables |

### Рекомендуемые переменные

| Переменная | Описание | Значение по умолчанию | Где настроить |
|-----------|----------|----------------------|---------------|
| `PORT` | Порт приложения | `8000` | Railway устанавливает автоматически |
| `CORS_ORIGINS` | Разрешенные CORS origins (через запятую) | `http://localhost:3000` | Railway Dashboard → Backend Service → Variables |
| `PRODUCTION_DOMAIN` | Production домен (для CORS) | - | Railway Dashboard → Backend Service → Variables |
| `CHAIN_LISTENER_POLL_INTERVAL` | Интервал опроса блокчейна (секунды) | `5` | Railway Dashboard → Backend Service → Variables |
| `CONFIRMATION_BLOCKS` | Количество подтверждений | `3` | Railway Dashboard → Backend Service → Variables |
| `KYT_BLACKLIST` | Заблокированные адреса (через запятую) | - | Railway Dashboard → Backend Service → Variables |
| `KYT_GRAYLIST` | Адреса для review (через запятую) | - | Railway Dashboard → Backend Service → Variables |
| `MPC_SIGNER_URL` | URL MPC Signer Node (если используется) | `localhost:50051` | Railway Dashboard → Backend Service → Variables |
| `MPC_SIGNER_ENABLED` | Включить MPC Signer | `false` | Railway Dashboard → Backend Service → Variables |

### Переменные для разработки (не использовать в production)

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `DEV_SIGNER_PRIVATE_KEY` | Приватный ключ для dev кошельков | `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80` |

**⚠️ ВНИМАНИЕ:** Никогда не используйте `DEV_SIGNER_PRIVATE_KEY` в production с реальными средствами!

---

## Настройка в Railway Dashboard

### Шаг 1: Создать PostgreSQL Service

1. В Railway Dashboard создайте новый проект
2. Добавьте **PostgreSQL** service
3. Railway автоматически создаст переменную `DATABASE_URL`
4. Скопируйте connection string

### Шаг 2: Создать Backend Service

1. Добавьте **New Service** → **GitHub Repo** (выберите ваш репозиторий)
2. Railway автоматически определит Dockerfile
3. Откройте **Variables** tab

### Шаг 3: Добавить переменные окружения

Добавьте следующие переменные в **Variables** tab:

```bash
# Database (из PostgreSQL service)
DATABASE_URL=<автоматически из PostgreSQL service>
DATABASE_URL_SYNC=<скопируйте из DATABASE_URL, замените +asyncpg на пустую строку>

# JWT
JWT_SECRET=<сгенерируйте случайную строку, минимум 32 символа>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Environment
ENVIRONMENT=production

# Ethereum
ETH_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com

# CORS (замените на ваш Vercel домен)
CORS_ORIGINS=https://your-app.vercel.app,https://your-custom-domain.com
PRODUCTION_DOMAIN=your-app.vercel.app

# Chain Listener
CHAIN_LISTENER_POLL_INTERVAL=5
CONFIRMATION_BLOCKS=3

# KYT
KYT_BLACKLIST=0x000000000000000000000000000000000000dead,0xbad0000000000000000000000000000000000bad
KYT_GRAYLIST=0x1234567890123456789012345678901234567890

# MPC (опционально)
MPC_SIGNER_URL=localhost:50051
MPC_SIGNER_ENABLED=false
```

### Шаг 4: Связать PostgreSQL с Backend

1. В Backend service откройте **Settings** → **Service Connections**
2. Добавьте connection к PostgreSQL service
3. Railway автоматически добавит `DATABASE_URL` в переменные

---

## Генерация секретных ключей

### JWT Secret

```bash
# Генерация случайного секрета (32+ символов)
openssl rand -hex 32

# Или используйте Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Database Password

Railway генерирует пароль автоматически для PostgreSQL service.

---

## Проверка переменных

### Локальная проверка (перед деплоем)

```bash
# Frontend
cd frontend
npm run build
# Проверьте что NEXT_PUBLIC_CORE_API_URL используется в build

# Backend
# Проверьте что все переменные доступны
python3 -c "from app.config import get_settings; s = get_settings(); print(s.database_url)"
```

### После деплоя

```bash
# Проверить что Backend работает
curl https://your-railway-app.railway.app/health

# Проверить что Frontend подключается к Backend
# Откройте браузер console на Vercel сайте
# Проверьте что API calls идут на правильный URL
```

---

## Troubleshooting

### Проблема: CORS ошибки

**Решение:**
1. Убедитесь что `CORS_ORIGINS` содержит ваш Vercel домен
2. Проверьте что домен указан без trailing slash
3. Перезапустите Backend service после изменения переменных

### Проблема: Database connection failed

**Решение:**
1. Проверьте что `DATABASE_URL` правильно скопирован из PostgreSQL service
2. Убедитесь что `DATABASE_URL_SYNC` создан (замените `+asyncpg` на пустую строку)
3. Проверьте что PostgreSQL service запущен

### Проблема: Frontend не может подключиться к Backend

**Решение:**
1. Проверьте что `NEXT_PUBLIC_CORE_API_URL` установлен в Vercel
2. Убедитесь что URL правильный (https://, без trailing slash)
3. Передеплойте Frontend после изменения переменных

### Проблема: Миграции не применяются

**Решение:**
1. Проверьте что `DATABASE_URL_SYNC` установлен
2. Проверьте логи Railway для ошибок миграций
3. Можно применить миграции вручную через Railway CLI

---

## Безопасность

### ⚠️ Важные правила:

1. **Никогда не коммитьте** `.env` файлы в git
2. **Используйте сильные секреты** для `JWT_SECRET` (минимум 32 символа)
3. **Не используйте** `DEV_SIGNER_PRIVATE_KEY` в production
4. **Ограничьте CORS origins** только нужными доменами
5. **Регулярно ротируйте** секретные ключи

### Рекомендации:

- Используйте Railway Secrets для чувствительных данных
- Включите 2FA на Railway и Vercel аккаунтах
- Регулярно проверяйте логи на подозрительную активность
- Используйте разные секреты для разных окружений (dev/staging/prod)

---

**Последнее обновление:** 2026-01-21

