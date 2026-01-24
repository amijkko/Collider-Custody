# Collider Custody - Описание тестов

**Дата обновления:** Январь 2026

---

## Обзор

Проект содержит комплексный набор тестов:
- **Backend Unit тесты** — проверка бизнес-логики
- **Frontend E2E тесты** — проверка UI и интеграции

### Статистика

| Категория | Количество | Время |
|-----------|------------|-------|
| Backend Unit | 15+ | ~5 сек |
| E2E Smoke | 8 | ~9 сек |
| E2E Integration | 34 | ~3.5 мин |
| E2E Deposit Flow | 10 | ~2 мин |
| **Всего** | **67+** | — |

---

## 1. Backend Unit тесты (`/tests`)

### Файл: `tests/conftest.py`

**Назначение:** Pytest fixtures и настройка тестовой БД

**Fixtures:**
- `engine` — SQLite async engine для тестов
- `session` — Async сессия с авто-откатом
- `client` — TestClient для FastAPI

---

### Файл: `tests/test_audit.py`

**Назначение:** Тестирование аудит-трейла

| Тест | Описание |
|------|----------|
| `test_audit_event_creation` | Создание события аудита с корректными полями |
| `test_hash_chain_integrity` | Проверка целостности hash-chain |
| `test_audit_event_types` | Проверка всех 23+ типов событий |
| `test_audit_package_generation` | Генерация пакета аудита для транзакции |
| `test_tamper_detection` | Обнаружение подделки в цепочке |

---

### Файл: `tests/test_kyt.py`

**Назначение:** Тестирование KYT-скрининга

| Тест | Описание |
|------|----------|
| `test_blacklist_blocking` | Адрес из blacklist блокирует транзакцию |
| `test_graylist_review` | Адрес из graylist создаёт кейс на ревью |
| `test_allow_clean_address` | Чистый адрес проходит проверку |
| `test_case_creation` | Создание KYT-кейса |
| `test_case_resolution_allow` | Резолюция кейса: ALLOW |
| `test_case_resolution_block` | Резолюция кейса: BLOCK |
| `test_inbound_kyt_screening` | KYT-проверка входящих транзакций |

---

### Файл: `tests/test_policy.py`

**Назначение:** Тестирование движка политик

| Тест | Описание |
|------|----------|
| `test_tx_limit_policy` | Лимит на одну транзакцию |
| `test_daily_limit_policy` | Дневной лимит с накоплением |
| `test_address_denylist` | Блокировка по адресу |
| `test_token_denylist` | Блокировка по токену |
| `test_approval_required` | Требование N-of-M апрувов |
| `test_policy_priority` | Приоритет политик |
| `test_policy_scope` | Scope политик (WALLET, GLOBAL) |

---

### Файл: `tests/test_sod.py`

**Назначение:** Тестирование Segregation of Duties

| Тест | Описание |
|------|----------|
| `test_creator_cannot_approve` | Создатель не может апрувить свою транзакцию |
| `test_double_approval_prevented` | Нельзя апрувить дважды |
| `test_any_rejection_blocks` | Один реджект блокирует транзакцию |
| `test_required_approvals_count` | Проверка количества требуемых апрувов |

---

### Запуск backend тестов

```bash
# Все тесты
pytest tests/ -v

# С покрытием
pytest tests/ -v --cov=app

# Конкретный файл
pytest tests/test_kyt.py -v

# Конкретный тест
pytest tests/test_kyt.py::test_blacklist_blocking -v
```

---

## 2. Frontend E2E тесты (`/frontend/e2e`)

### Конфигурация: `playwright.config.ts`

```typescript
{
  testDir: './e2e',
  baseURL: 'https://collider-cust.vercel.app',
  projects: [{ name: 'chromium' }],
  reporter: 'html'
}
```

---

### Файл: `e2e/smoke.spec.ts`

**Назначение:** Быстрые smoke-тесты для CI/CD

| # | Тест | Описание | Время |
|---|------|----------|-------|
| 1 | `homepage loads and redirects to login` | Главная редиректит на /login | ~1s |
| 2 | `login page loads correctly` | Форма входа отображается | ~1s |
| 3 | `register page loads correctly` | Форма регистрации отображается | ~1s |
| 4 | `login with invalid credentials shows error` | Неверные данные показывают ошибку | ~2s |
| 5 | `admin login works` | Успешный вход админа (e2e_bot) | ~3s |
| 6 | `authenticated user can access deposit page` | Авторизованный пользователь видит депозиты | ~3s |
| 7 | `authenticated admin can access deposits management` | Админ видит управление депозитами | ~2s |
| 8 | `API health check` | Backend отвечает на /health | ~0.5s |

**Общее время:** ~9 секунд

---

### Файл: `e2e/integration.spec.ts`

**Назначение:** Полный интеграционный тест всех функций

#### Секция 1: Authentication (6 тестов)

| # | Тест | Описание |
|---|------|----------|
| 1.1 | `Login page displays correctly` | UI логина: форма, demo credentials |
| 1.2 | `Register page displays correctly` | UI регистрации: все поля |
| 1.3 | `Invalid login shows error` | Ошибка при неверных данных |
| 1.4 | `Register new user` | Регистрация нового пользователя |
| 1.5 | `Login as new user` | Вход под тестовым пользователем |
| 1.6 | `Login as admin` | Вход под админом (e2e_bot) |

#### Секция 2: Dashboard & Navigation (3 теста)

| # | Тест | Описание |
|---|------|----------|
| 2.1 | `Dashboard loads correctly` | Dashboard показывает баланс |
| 2.2 | `Navigation sidebar works` | Навигация между разделами |
| 2.3 | `User menu shows profile info` | Профиль пользователя |

#### Секция 3: Wallet Management (3 теста)

| # | Тест | Описание |
|---|------|----------|
| 3.1 | `Create MPC wallet if needed` | Создание или использование существующего |
| 3.2 | `Wallet address is displayed` | Адрес показывается на странице депозита |
| 3.3 | `Copy address button works` | Кнопка копирования адреса |

#### Секция 4: Deposit Flow (3 теста)

| # | Тест | Описание |
|---|------|----------|
| 4.1 | `Deposit page shows correct info` | Страница депозита с адресом и QR |
| 4.2 | `Simulate deposit and check detection` | **Реальная транзакция 0.0005 ETH**, ожидание детекции |
| 4.3 | `User sees pending deposit in history` | Депозит появляется в истории |

**Важно:** Тест 4.2 отправляет реальную транзакцию в Sepolia!

#### Секция 5: Admin Deposit Management (4 теста)

| # | Тест | Описание |
|---|------|----------|
| 5.1 | `Admin deposits page loads` | Страница управления депозитами |
| 5.2 | `Admin can see pending deposits` | Pending депозиты видны |
| 5.3 | `Admin approves deposit` | Апрув депозита через UI или API |
| 5.4 | `Approved deposit shows in processed list` | Депозит в статусе CREDITED |

#### Секция 6: Withdrawal Flow (4 теста)

| # | Тест | Описание |
|---|------|----------|
| 6.1 | `Withdraw page loads correctly` | Форма вывода, баланс |
| 6.2 | `User balance updated after deposit approval` | Баланс обновился после апрува |
| 6.3 | `Withdrawal validation works` | Валидация формы вывода |
| 6.4 | `Create withdrawal request` | Создание запроса на вывод |

#### Секция 7: Transaction History (2 теста)

| # | Тест | Описание |
|---|------|----------|
| 7.1 | `Dashboard shows recent activity section` | Секция Recent Activity |
| 7.2 | `Deposit history on deposit page` | История на странице депозитов |

#### Секция 8: UI & Responsiveness (4 теста)

| # | Тест | Описание |
|---|------|----------|
| 8.1 | `Mobile viewport works` | Адаптивность (375x667) |
| 8.2 | `Dark theme is applied` | Тёмная тема (rgb(9, 9, 11)) |
| 8.3 | `Loading states are shown` | Индикаторы загрузки |
| 8.4 | `Error boundaries work` | 404 страница |

#### Секция 9: Security (3 теста)

| # | Тест | Описание |
|---|------|----------|
| 9.1 | `Unauthenticated access redirects to login` | Редирект без авторизации |
| 9.2 | `Admin routes protected from regular users` | Обычный user не видит /admin |
| 9.3 | `Session persists across page reload` | Сессия сохраняется при F5 |

#### Секция 10: Final Checks (2 теста)

| # | Тест | Описание |
|---|------|----------|
| 10.1 | `Logout works` | Выход из системы |
| 10.2 | `Summary - print test results` | Вывод итогов теста |

**Общее время:** ~3.5 минуты

---

### Файл: `e2e/deposit-flow.spec.ts`

**Назначение:** Детальный тест flow депозита (serial)

| # | Тест | Описание |
|---|------|----------|
| 1 | `Admin can login` | Вход админа для получения токена |
| 2 | `Register new test user` | Регистрация нового тестового пользователя |
| 3 | `User can login and see dashboard` | Вход и проверка dashboard |
| 4 | `User creates MPC wallet` | Создание MPC-кошелька |
| 5 | `User views deposit page with address` | Просмотр адреса для депозита |
| 6 | `Simulate deposit via API` | Отправка ETH через API |
| 7 | `Admin sees pending deposit` | Pending депозит в админке |
| 8 | `Admin approves deposit` | Апрув депозита |
| 9 | `User sees updated balance` | Баланс обновлён |
| 10 | `Deposit history shows credited deposit` | История показывает CREDITED |

**Общее время:** ~2 минуты

---

## 3. Тестовые данные и credentials

### Пользователи для тестов

| Username | Password | Роль | Использование |
|----------|----------|------|---------------|
| `e2e_bot` | `E2eTestPass2026` | ADMIN | Основной тестовый админ |
| `e2e_user_1575` | `TestPass2026!` | VIEWER | Тестовый пользователь |
| `admin2` | `admin123456` | ADMIN | Demo админ |
| `demo` | `demo123456` | VIEWER | Demo пользователь |

### Тестовый кошелёк

```
Адрес: 0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c
Сеть: Sepolia
Использование: Источник ETH для тестов
```

### URLs

| Сервис | URL |
|--------|-----|
| Frontend (prod) | https://collider-cust.vercel.app |
| Backend (prod) | https://discerning-rebirth-production.up.railway.app |
| API Health | https://discerning-rebirth-production.up.railway.app/health |

---

## 4. Запуск E2E тестов

### Smoke тесты (быстрые)

```bash
cd frontend

# Все smoke тесты
npx playwright test smoke.spec.ts

# С отчётом
npx playwright test smoke.spec.ts --reporter=html

# В headed режиме (видно браузер)
npx playwright test smoke.spec.ts --headed
```

### Integration тесты (полные)

```bash
cd frontend

# Все integration тесты
npx playwright test integration.spec.ts

# С выводом в консоль
npx playwright test integration.spec.ts --reporter=line

# В debug режиме
npx playwright test integration.spec.ts --debug
```

### Deposit flow тесты

```bash
cd frontend
npx playwright test deposit-flow.spec.ts
```

### Все тесты

```bash
cd frontend

# Все E2E тесты
npx playwright test

# Параллельно
npx playwright test --workers=4
```

---

## 5. Структура теста (пример)

### Smoke тест

```typescript
test('login page loads correctly', async ({ page }) => {
  await page.goto('/login');

  // Проверка UI элементов
  await expect(page.getByText(/Welcome|Sign in/i).first()).toBeVisible();
  await expect(page.getByPlaceholder(/enter your username/i)).toBeVisible();
  await expect(page.getByPlaceholder(/enter your password/i)).toBeVisible();
  await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
});
```

### Integration тест с API

```typescript
test('4.2 Simulate deposit and check detection', async ({ page }) => {
  test.setTimeout(120000); // 2 минуты таймаут

  // Создание транзакции через API
  const txRes = await api('POST', '/v1/tx-requests', adminToken, {
    wallet_id: adminWallet.id,
    tx_type: 'TRANSFER',
    to_address: userWalletAddress,
    asset: 'ETH',
    amount: '500000000000000', // 0.0005 ETH
  });

  // Подписание
  await api('POST', `/v1/tx-requests/${txRes.data.id}/sign`, adminToken);

  // Ожидание детекции депозита (40 сек)
  await page.waitForTimeout(40000);

  // Проверка через API
  const deposits = await api('GET', `/v1/deposits?wallet_id=${userWalletId}`, userToken);
  const pending = deposits.data?.find((d: any) => d.status === 'PENDING_ADMIN');

  expect(pending).toBeTruthy();
});
```

---

## 6. CI/CD интеграция

### GitHub Actions (пример)

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install dependencies
        run: |
          cd frontend
          npm ci
          npx playwright install chromium

      - name: Run smoke tests
        run: |
          cd frontend
          npx playwright test smoke.spec.ts

      - name: Upload report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

---

## 7. Отчёты и артефакты

### HTML отчёт

```bash
# Генерация
npx playwright test --reporter=html

# Просмотр
npx playwright show-report
```

### Скриншоты при ошибках

Автоматически сохраняются в `test-results/` при падении теста.

### Trace файлы

```bash
# С trace
npx playwright test --trace=on

# Просмотр trace
npx playwright show-trace test-results/.../trace.zip
```

---

## 8. Troubleshooting

### Тест падает на логине

**Причина:** Неверные credentials или изменился UI

**Решение:**
```typescript
// Проверить placeholder текст
await page.getByPlaceholder(/enter your username/i)
```

### Timeout на депозит тесте

**Причина:** Chain listener не успел обнаружить депозит

**Решение:**
```typescript
test.setTimeout(120000); // Увеличить таймаут
await page.waitForTimeout(45000); // Увеличить ожидание
```

### localStorage не работает

**Причина:** Попытка доступа до навигации

**Решение:**
```typescript
// Сначала навигация
await page.goto('/login');
// Потом localStorage
await page.evaluate((t) => localStorage.setItem('access_token', t), token);
```

### Admin routes показывают dashboard

**Причина:** Редирект для обычных пользователей работает корректно

**Проверка:**
```typescript
const currentUrl = page.url();
const redirectedAway = !currentUrl.includes('/admin');
expect(redirectedAway).toBeTruthy();
```

---

## 9. Расширение тестов

### Добавление нового smoke теста

```typescript
// e2e/smoke.spec.ts
test('new feature works', async ({ page }) => {
  await page.goto('/app/new-feature');
  await expect(page.getByText(/Feature Title/i)).toBeVisible();
});
```

### Добавление integration теста

```typescript
// e2e/integration.spec.ts (внутри describe)
test('X.Y New test name', async ({ page }) => {
  // Setup
  await page.goto('/');
  await page.evaluate((t) => localStorage.setItem('access_token', t), userToken);

  // Action
  await page.goto('/app/feature');

  // Assert
  await expect(page.getByText(/Expected/i)).toBeVisible();
});
```

---

## 10. Контакты и ресурсы

- **Playwright Docs:** https://playwright.dev/docs/intro
- **Pytest Docs:** https://docs.pytest.org/
- **Проект GitHub:** (internal)

---

**Последнее обновление:** Все 67+ тестов проходят успешно.
