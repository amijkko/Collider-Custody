# Deployment Guide: Vercel + Railway

Полное руководство по деплою проекта Collider Custody на Vercel (Frontend) и Railway (Backend + PostgreSQL).

---

## Архитектура деплоя

```
┌─────────────────┐
│  Vercel         │  Frontend (Next.js)
│  https://...    │  → API calls
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│  Railway        │  Backend API (FastAPI)
│  https://...    │  → Database queries
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Railway        │  PostgreSQL Database
│  (Managed)      │
└─────────────────┘
```

---

## Предварительные требования

- [ ] GitHub репозиторий с кодом проекта
- [ ] Аккаунт на [Vercel](https://vercel.com)
- [ ] Аккаунт на [Railway](https://railway.app)
- [ ] Доступ к Ethereum RPC endpoint (Sepolia testnet)

---

## Часть 1: Деплой Backend на Railway

### Шаг 1.1: Создать проект на Railway

1. Войдите в [Railway Dashboard](https://railway.app)
2. Нажмите **New Project**
3. Выберите **Deploy from GitHub repo**
4. Выберите ваш репозиторий `Collider-Custody`

### Шаг 1.2: Создать PostgreSQL Service

1. В созданном проекте нажмите **+ New**
2. Выберите **Database** → **Add PostgreSQL**
3. Railway автоматически создаст PostgreSQL service
4. **Важно:** Запишите connection string из **Variables** tab

### Шаг 1.3: Настроить Backend Service

1. Railway автоматически создаст service из вашего репозитория
2. Откройте созданный service
3. Перейдите в **Settings** → **Service Connections**
4. Добавьте connection к PostgreSQL service
5. Railway автоматически добавит `DATABASE_URL` в переменные

### Шаг 1.4: Настроить переменные окружения

Откройте **Variables** tab в Backend service и добавьте:

```bash
# Database (автоматически из PostgreSQL, но нужно добавить sync версию)
DATABASE_URL_SYNC=<скопируйте DATABASE_URL, замените +asyncpg на пустую строку>

# JWT (сгенерируйте новый секрет)
JWT_SECRET=<используйте: openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Environment
ENVIRONMENT=production

# Ethereum
ETH_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com

# CORS (будет обновлено после деплоя Frontend)
CORS_ORIGINS=http://localhost:3000
PRODUCTION_DOMAIN=

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

### Шаг 1.5: Настроить деплой

1. Railway автоматически определит `Dockerfile`
2. Убедитесь что **Root Directory** пустой (или `/` если нужно)
3. Railway будет использовать `Procfile` или `Dockerfile` для запуска
4. Нажмите **Deploy**

### Шаг 1.6: Получить URL Backend

1. После успешного деплоя откройте **Settings** → **Networking**
2. Нажмите **Generate Domain**
3. Скопируйте URL (например: `https://your-app.railway.app`)
4. **Важно:** Этот URL понадобится для Frontend

### Шаг 1.7: Проверить Backend

```bash
# Проверить health endpoint
curl https://your-app.railway.app/health

# Должен вернуть:
# {"status":"healthy","environment":"production","chain_listener_running":true}
```

---

## Часть 2: Деплой Frontend на Vercel

### Шаг 2.1: Подготовить репозиторий

Убедитесь что в репозитории есть:
- ✅ `vercel.json` (в корне)
- ✅ `frontend/` директория с Next.js приложением
- ✅ `.vercelignore` (в корне)

### Шаг 2.2: Создать проект на Vercel

1. Войдите в [Vercel Dashboard](https://vercel.com)
2. Нажмите **Add New Project**
3. Импортируйте ваш GitHub репозиторий `Collider-Custody`
4. Vercel автоматически определит Next.js

### Шаг 2.3: Настроить Build Settings

Vercel должен автоматически определить настройки, но проверьте:

- **Framework Preset:** Next.js
- **Root Directory:** `frontend` (если нужно)
- **Build Command:** `cd frontend && npm install && npm run build`
- **Output Directory:** `frontend/.next`
- **Install Command:** `cd frontend && npm install`

### Шаг 2.4: Настроить переменные окружения

В **Environment Variables** добавьте:

```bash
# Backend API URL (из Railway)
NEXT_PUBLIC_CORE_API_URL=https://your-app.railway.app

# WebSocket URL (если используется MPC)
NEXT_PUBLIC_WS_URL=wss://your-app.railway.app
```

**Важно:**
- Добавьте переменные для всех окружений (Production, Preview, Development)
- После добавления переменных нужно передеплоить

### Шаг 2.5: Обновить CORS в Backend

Вернитесь в Railway Backend service и обновите переменные:

```bash
# Добавьте Vercel домен в CORS_ORIGINS
CORS_ORIGINS=https://your-app.vercel.app,https://your-app-git-main.vercel.app,http://localhost:3000

# Или если используете custom domain
PRODUCTION_DOMAIN=your-custom-domain.com
```

Перезапустите Backend service после изменения переменных.

### Шаг 2.6: Деплой

1. Нажмите **Deploy** в Vercel
2. Дождитесь завершения build
3. Vercel автоматически создаст preview URL
4. После проверки можно промоутить в Production

### Шаг 2.7: Проверить Frontend

1. Откройте созданный Vercel URL
2. Проверьте что страница загружается
3. Откройте Browser Console (F12)
4. Проверьте что API calls идут на правильный Railway URL
5. Попробуйте залогиниться

---

## Часть 3: Настройка Custom Domain (опционально)

### Vercel Custom Domain

1. В Vercel проекте откройте **Settings** → **Domains**
2. Добавьте ваш домен
3. Следуйте инструкциям для настройки DNS
4. Обновите `CORS_ORIGINS` в Railway с новым доменом

### Railway Custom Domain

1. В Railway Backend service откройте **Settings** → **Networking**
2. Нажмите **Custom Domain**
3. Добавьте поддомен (например: `api.yourdomain.com`)
4. Настройте DNS записи
5. Обновите `NEXT_PUBLIC_CORE_API_URL` в Vercel

---

## Часть 4: Проверка и тестирование

### 4.1 Проверка Backend

```bash
# Health check
curl https://your-railway-app.railway.app/health

# API docs
open https://your-railway-app.railway.app/docs

# Test endpoint
curl https://your-railway-app.railway.app/
```

### 4.2 Проверка Frontend

1. Откройте Vercel URL
2. Проверьте что все страницы загружаются
3. Протестируйте:
   - Регистрацию/Вход
   - Создание кошелька
   - Просмотр баланса
   - Создание транзакции

### 4.3 Проверка Database

1. В Railway откройте PostgreSQL service
2. Нажмите **Query** tab
3. Выполните простой запрос:
   ```sql
   SELECT COUNT(*) FROM wallets;
   ```

### 4.4 Проверка миграций

Миграции должны применяться автоматически при деплое. Проверьте логи Railway:

1. Откройте Backend service → **Deployments**
2. Откройте последний deployment → **View Logs**
3. Найдите строки с `alembic upgrade head`
4. Убедитесь что нет ошибок

---

## Troubleshooting

### Проблема: Backend не запускается

**Симптомы:** Deployment failed, service не отвечает

**Решения:**
1. Проверьте логи в Railway → Deployments → View Logs
2. Убедитесь что все переменные окружения установлены
3. Проверьте что `DATABASE_URL` правильный
4. Убедитесь что `DATABASE_URL_SYNC` создан (без `+asyncpg`)

### Проблема: CORS ошибки

**Симптомы:** `Access-Control-Allow-Origin` ошибки в браузере

**Решения:**
1. Проверьте что `CORS_ORIGINS` содержит ваш Vercel домен
2. Убедитесь что домен указан без trailing slash
3. Перезапустите Backend service после изменения переменных
4. Проверьте что используется `https://` (не `http://`)

### Проблема: Frontend не может подключиться к Backend

**Симптомы:** Network errors, 404, или timeout

**Решения:**
1. Проверьте что `NEXT_PUBLIC_CORE_API_URL` установлен в Vercel
2. Убедитесь что URL правильный (https://, без trailing slash)
3. Проверьте что Backend доступен: `curl https://your-railway-app.railway.app/health`
4. Передеплойте Frontend после изменения переменных

### Проблема: Миграции не применяются

**Симптомы:** Database errors, missing tables

**Решения:**
1. Проверьте что `DATABASE_URL_SYNC` установлен
2. Проверьте логи Railway для ошибок миграций
3. Примените миграции вручную через Railway CLI:
   ```bash
   railway run alembic upgrade head
   ```

### Проблема: WebSocket не работает

**Симптомы:** WebSocket connection failed

**Решения:**
1. Убедитесь что Railway поддерживает WebSocket (должно работать)
2. Проверьте что `NEXT_PUBLIC_WS_URL` использует `wss://` (не `ws://`)
3. Проверьте что WebSocket endpoint доступен на Backend

---

## Мониторинг и логи

### Railway Logs

1. Откройте Backend service → **Deployments**
2. Выберите deployment → **View Logs**
3. Или используйте **Logs** tab для real-time логов

### Vercel Logs

1. Откройте проект → **Deployments**
2. Выберите deployment → **View Function Logs**
3. Или используйте Vercel CLI:
   ```bash
   vercel logs
   ```

### Database Monitoring

1. В Railway PostgreSQL service откройте **Metrics**
2. Мониторьте connections, queries, storage

---

## Обновление деплоя

### Обновление Backend

1. Сделайте изменения в коде
2. Закоммитьте и запушьте в GitHub
3. Railway автоматически задеплоит изменения
4. Проверьте логи для ошибок

### Обновление Frontend

1. Сделайте изменения в коде
2. Закоммитьте и запушьте в GitHub
3. Vercel автоматически задеплоит изменения
4. Проверьте build logs

### Обновление переменных окружения

**Railway:**
1. Откройте service → **Variables**
2. Измените переменную
3. Service автоматически перезапустится

**Vercel:**
1. Откройте проект → **Settings** → **Environment Variables**
2. Измените переменную
3. Передеплойте проект (или дождитесь следующего деплоя)

---

## Безопасность

### Рекомендации

1. ✅ Используйте сильные секреты для `JWT_SECRET`
2. ✅ Ограничьте `CORS_ORIGINS` только нужными доменами
3. ✅ Не используйте `DEV_SIGNER_PRIVATE_KEY` в production
4. ✅ Регулярно обновляйте зависимости
5. ✅ Включите 2FA на Railway и Vercel
6. ✅ Мониторьте логи на подозрительную активность

### Production Checklist

- [ ] Все секреты установлены и сильные
- [ ] CORS настроен правильно
- [ ] Database backups включены (Railway автоматически)
- [ ] Health checks работают
- [ ] Логирование настроено
- [ ] Мониторинг активен
- [ ] SSL/TLS включен (автоматически на Vercel и Railway)

---

## Стоимость

### Vercel

- **Hobby Plan:** Бесплатно (достаточно для большинства проектов)
- **Pro Plan:** $20/месяц (для production)

### Railway

- **Starter Plan:** $5/месяц + usage
- **Developer Plan:** $20/месяц + usage
- PostgreSQL: ~$5-10/месяц в зависимости от размера

**Примерная стоимость:** $10-30/месяц для небольшого проекта

---

## Полезные ссылки

- [Vercel Documentation](https://vercel.com/docs)
- [Railway Documentation](https://docs.railway.app)
- [Next.js Deployment](https://nextjs.org/docs/deployment)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)

---

## Поддержка

Если возникли проблемы:

1. Проверьте логи в Railway и Vercel
2. Сверьтесь с [ENVIRONMENT_VARIABLES.md](./ENVIRONMENT_VARIABLES.md)
3. Проверьте [Troubleshooting](#troubleshooting) секцию
4. Создайте issue в GitHub репозитории

---

**Последнее обновление:** 2026-01-22

