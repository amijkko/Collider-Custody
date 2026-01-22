# Railway Environment Variables

Готовый список переменных окружения для Railway деплоя.

---

## Быстрый старт

1. Откройте файл `railway.variables.txt` в корне проекта
2. Заполните значения (особенно `DATABASE_URL_SYNC` и `JWT_SECRET`)
3. Скопируйте переменные в Railway Dashboard → Variables

Или используйте Railway CLI:
```bash
railway variables set --file railway.variables.txt
```

---

## Как использовать

1. Скопируйте переменные ниже
2. В Railway Dashboard откройте ваш Backend service → **Variables**
3. Добавьте каждую переменную вручную или используйте Railway CLI

---

## Обязательные переменные

```bash
# Database (DATABASE_URL добавляется автоматически при подключении PostgreSQL)
# DATABASE_URL_SYNC нужно создать вручную
DATABASE_URL_SYNC=<скопируйте DATABASE_URL, замените +asyncpg на пустую строку>

# JWT (сгенерируйте новый секрет)
JWT_SECRET=<openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Environment
ENVIRONMENT=production

# Ethereum
ETH_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com

# CORS (обновите после деплоя Frontend)
CORS_ORIGINS=https://your-app.vercel.app,https://your-app-git-main.vercel.app,http://localhost:3000
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

---

## Генерация JWT Secret

```bash
# Используйте одну из команд:
openssl rand -hex 32

# Или Python:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Пример заполнения

```bash
DATABASE_URL_SYNC=postgresql://postgres:abc123@containers-us-west-123.railway.app:5432/railway
JWT_SECRET=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
ENVIRONMENT=production
ETH_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
CORS_ORIGINS=https://collider-custody.vercel.app,https://collider-custody-git-main.vercel.app,http://localhost:3000
PRODUCTION_DOMAIN=collider-custody.vercel.app
CHAIN_LISTENER_POLL_INTERVAL=5
CONFIRMATION_BLOCKS=3
KYT_BLACKLIST=0x000000000000000000000000000000000000dead,0xbad0000000000000000000000000000000000bad
KYT_GRAYLIST=0x1234567890123456789012345678901234567890
MPC_SIGNER_URL=localhost:50051
MPC_SIGNER_ENABLED=false
```

---

## Порядок настройки

1. **Создайте PostgreSQL service** в Railway
2. **Подключите PostgreSQL** к Backend service (Railway автоматически добавит `DATABASE_URL`)
3. **Скопируйте `DATABASE_URL`** и создайте `DATABASE_URL_SYNC` (замените `+asyncpg` на пустую строку)
4. **Добавьте остальные переменные** из списка выше
5. **Сгенерируйте `JWT_SECRET`** (используйте команду выше)
6. **Обновите `CORS_ORIGINS`** после деплоя Frontend на Vercel

---

## Проверка переменных

После добавления всех переменных проверьте:

1. В Railway Dashboard → Backend service → **Variables**
2. Убедитесь что все переменные присутствуют
3. Проверьте что значения правильные (особенно `DATABASE_URL_SYNC`)

---

## Troubleshooting

### DATABASE_URL_SYNC не работает

**Проблема:** Миграции не применяются

**Решение:**
1. Убедитесь что `DATABASE_URL_SYNC` создан
2. Формат: `postgresql://user:pass@host:port/db` (без `+asyncpg`)
3. Скопируйте из `DATABASE_URL` и замените `postgresql+asyncpg://` на `postgresql://`

### JWT_SECRET слишком короткий

**Проблема:** Ошибки аутентификации

**Решение:**
1. Используйте минимум 32 символа
2. Сгенерируйте новый: `openssl rand -hex 32`
3. Обновите переменную в Railway

---

**Последнее обновление:** 2026-01-22

