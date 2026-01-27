# E2E Test Implementation Plan

**Дата:** 2026-01-24
**PRD:** ColliderCustody_E2E_TestPlan_v0.1.1.md

---

## 1. Текущее состояние

### Существующие тесты

| Файл | Покрытие | Статус |
|------|----------|--------|
| `smoke.spec.ts` | Auth, Dashboard, Wallet | ✅ Работает |
| `integration.spec.ts` | Полный интеграционный путь | ✅ Работает |
| `deposit-flow.spec.ts` | Deposit detection + approval | ✅ Работает |
| `mpc-wallet.spec.ts` | MPC wallet creation | ✅ Работает |

### Покрытие по PRD

| Категория | PRD Тесты | Покрыто | Нужно добавить |
|-----------|-----------|---------|----------------|
| Auth (E2E-AUTH-*) | 5 | 4 | 1 (auto-enroll check) |
| Retail Wallet (E2E-RET-*) | 4 | 3 | 1 (ledger balance) |
| Scene A (Micro) | 2 | 0 | **2** |
| Scene B (Large) | 2 | 1 | **1** (reject path) |
| Scene C (KYT Review) | 3 | 0 | **3** |
| Scene D (Denylist) | 1 | 0 | **1** |
| Admin Groups/Policies | 5 | 0 | **5** |
| Approvals/SoD | 2 | 1 | **1** |
| Deposits | 4 | 3 | 1 |
| MPC | 4 | 2 | **2** |
| Audit/Evidence | 4 | 0 | **4** |
| RBAC | 3 | 1 | **2** |
| UI Validation | 4 | 2 | **2** |
| Golden Path | 1 | 0 | **1** |

**Итого:** ~25 новых тестов

---

## 2. План реализации

### Phase 1: Инфраструктура (1h)

```
frontend/e2e/
├── fixtures/
│   ├── test-data.ts      # Константы (ALLOW_ADDR, DENY_ADDR, GRAY_ADDR)
│   ├── api-helpers.ts    # API функции
│   └── auth-helpers.ts   # Login/logout helpers
├── config/
│   └── test-users.ts     # Тестовые пользователи по ролям
```

**test-data.ts:**
```typescript
export const TEST_ADDRESSES = {
  ALLOW_ADDR: '0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c', // Allowlisted
  GRAY_ADDR: '0x1234567890123456789012345678901234567890',  // KYT REVIEW
  DENY_ADDR: '0xdead000000000000000000000000000000000000',  // Denylist
  FUNDING_WALLET: '0xaf16fe7a4ff4f8c98ca24050f165aebcba239b3c',
};

export const AMOUNTS = {
  MICRO: '0.0005',      // < 0.001 ETH (RET-01)
  LARGE: '0.01',        // > 0.001 ETH (RET-02)
  THRESHOLD: '0.001',   // Policy threshold
};
```

### Phase 2: Scene Tests (3h)

#### 2.1 `retail.core.spec.ts` - Scene A/B/D

```typescript
// E2E-SCENE-A-01: Micro transfer allowlisted → SKIPPED
test('Scene A: Micro transfer to allowlist skips KYT/approval', async ({ page }) => {
  // 1. Login as retail user
  // 2. Navigate to withdraw
  // 3. Enter ALLOW_ADDR, amount=0.0005
  // 4. Submit
  // 5. Assert: FINALIZED, matched_rule=RET-01, KYT=SKIPPED, Approval=SKIPPED
});

// E2E-SCENE-A-02: Micro NOT in allowlist → BLOCK
test('Scene A: Micro transfer to unknown address blocks', async ({ page }) => {
  // Assert: BLOCKED, reason="not in allowlist"
});

// E2E-SCENE-B-01: Large transfer → KYT + Approval
test('Scene B: Large transfer requires KYT and approval', async ({ page }) => {
  // 1. Retail user creates withdrawal 0.01 ETH to ALLOW_ADDR
  // 2. Assert: status = APPROVAL_PENDING
  // 3. Admin approves
  // 4. Assert: FINALIZED, KYT=ALLOW, approval recorded
});

// E2E-SCENE-B-02: Large transfer → Admin Reject
test('Scene B: Admin can reject large transfer', async ({ page }) => {
  // Assert: status = REJECTED, audit contains reason
});

// E2E-SCENE-D-01: Denylist fail-fast
test('Scene D: Denylist blocks before KYT/approval', async ({ page }) => {
  // 1. Withdrawal to DENY_ADDR
  // 2. Assert: BLOCKED immediately, matched_rule=RET-03
  // 3. Assert: NO KYT step, NO approval step
});
```

#### 2.2 `retail.kyt-review.spec.ts` - Scene C

```typescript
// E2E-SCENE-C-01: KYT REVIEW creates case
test('Scene C: KYT REVIEW creates compliance case', async ({ page }) => {
  // 1. Withdrawal to GRAY_ADDR
  // 2. Assert: status = KYT_REVIEW
  // 3. Assert: case appears in /admin/cases
});

// E2E-SCENE-C-02: Resolve ALLOW → continues to approval
test('Scene C: Compliance ALLOW returns tx to approval queue', async ({ page }) => {
  // 1. Compliance resolves case as ALLOW with reason
  // 2. Assert: tx status = APPROVAL_PENDING
});

// E2E-SCENE-C-03: Resolve BLOCK → terminal
test('Scene C: Compliance BLOCK terminates tx', async ({ page }) => {
  // Assert: status = KYT_BLOCKED, audit contains decision
});
```

### Phase 3: Admin Tests (2h)

#### 3.1 `admin.groups-policies.spec.ts`

```typescript
// E2E-ADM-GRP-01: Groups list
test('Admin: Groups page shows Retail with counters', async ({ page }) => {
  // Navigate /admin/groups
  // Assert: Retail group visible, member count shown
});

// E2E-ADM-GRP-02: Members CRUD
test('Admin: Can add/remove group members', async ({ page }) => {
  // Add user to group, verify, remove, verify
});

// E2E-ADM-POL-01: Policy assignment
test('Admin: Can assign policy set to group', async ({ page }) => {
  // Change policy version, verify new operations use it
});

// E2E-ADM-AB-01: Allowlist CRUD
test('Admin: Allowlist entries can be managed', async ({ page }) => {
  // Add ALLOW_ADDR, save, verify Scene A passes
});

// E2E-ADM-AB-02: Denylist CRUD
test('Admin: Denylist entries block transactions', async ({ page }) => {
  // Add DENY_ADDR to denylist, verify Scene D blocks
});
```

### Phase 4: Audit & Evidence (1.5h)

#### 4.1 `audit.evidence.spec.ts`

```typescript
// E2E-AUD-01: Withdrawal evidence
test('Audit: Withdrawal evidence package contains all fields', async ({ page }) => {
  // Open completed tx → Audit button
  // Assert: intent, policy_decision, KYT, approvals, signing, tx_hash
});

// E2E-AUD-02: Deposit evidence
test('Audit: Deposit evidence package contains all fields', async ({ page }) => {
  // Open credited deposit → Audit button
  // Assert: detection, KYT, admin_decision, timestamp
});

// E2E-AUD-03: Export JSON
test('Audit: Can export evidence as JSON', async ({ page }) => {
  // Click Export JSON
  // Assert: file downloads, valid JSON, contains required blocks
});

// E2E-AUD-04: Verify chain
test('Audit: Chain verification passes', async ({ page }) => {
  // Verify button → verified=true
});
```

### Phase 5: Security & RBAC (1h)

#### 5.1 `security.rbac.spec.ts`

```typescript
// E2E-RBAC-01: Viewer no admin
test('RBAC: Viewer cannot access admin pages', async ({ page }) => {
  // Login as viewer, navigate /admin/groups
  // Assert: redirect or 403
});

// E2E-RBAC-02: Operator no resolve
test('RBAC: Operator cannot resolve KYT cases', async ({ page }) => {
  // Login as operator, open case
  // Assert: no resolve button
});

// E2E-SOD-01: Initiator cannot approve
test('SoD: User cannot approve own transaction', async ({ page }) => {
  // Create tx, try to approve
  // Assert: error/forbidden
});
```

### Phase 6: Golden Path (2h)

#### 6.1 `golden-path.spec.ts`

```typescript
/**
 * INT-GOLD-01: Full E2E path
 * Register → Create wallet → Fund → Deposit detected →
 * Admin credit → Withdraw back → Verify evidence
 */
test('Golden Path: Complete user journey', async ({ page }) => {
  // Step 1: Register new user
  const user = { username: `gold_${Date.now()}`, ... };
  await page.goto('/register');
  // ... fill form, submit

  // Step 2: Verify auto-enrolled in Retail
  // Check /admin/groups/Retail contains user

  // Step 3: Create wallet (DEV or MPC)
  await page.goto('/app');
  // ... create wallet

  // Step 4: Fund from Funding Wallet
  // API call to send 0.05 ETH from FUNDING_WALLET

  // Step 5: Wait for deposit detection
  await expect(page.getByText(/PENDING/i)).toBeVisible({ timeout: 60000 });

  // Step 6: Admin approves deposit
  await loginAdmin(page);
  await page.goto('/admin/deposits');
  await page.getByRole('button', { name: /approve/i }).click();
  // ... confirm

  // Step 7: Verify balance CREDITED
  await loginUser(page, user);
  const balance = await getBalance(page, walletId);
  expect(balance).toBeGreaterThan(0);

  // Step 8: Create withdrawal (large, triggers RET-02)
  await page.goto('/app/withdraw');
  await page.fill('[name=to]', FUNDING_WALLET);
  await page.fill('[name=amount]', '0.01');
  await page.click('button[type=submit]');

  // Step 9: Verify KYT passed
  await expect(page.getByText(/KYT.*ALLOW|APPROVAL_PENDING/i)).toBeVisible();

  // Step 10: Admin approves withdrawal
  await loginAdmin(page);
  await page.goto('/admin/withdrawals');
  await approveWithdrawal(page, txId);

  // Step 11: Wait for FINALIZED
  await expect(page.getByText(/FINALIZED|CONFIRMED/i)).toBeVisible({ timeout: 120000 });

  // Step 12: Verify audit package
  await page.click('button:has-text("Audit")');
  await expect(page.getByText(/RET-02/)).toBeVisible();
  await expect(page.getByText(/KYT.*ALLOW/)).toBeVisible();
  await expect(page.getByText(/approval.*admin/i)).toBeVisible();

  console.log('✅ Golden Path completed successfully');
});
```

---

## 3. Структура файлов (итог)

```
frontend/e2e/
├── fixtures/
│   ├── test-data.ts
│   ├── api-helpers.ts
│   └── auth-helpers.ts
├── smoke.auth.spec.ts          # AUTH-01..05
├── retail.core.spec.ts         # SCENE-A, SCENE-B, SCENE-D
├── retail.kyt-review.spec.ts   # SCENE-C
├── admin.groups-policies.spec.ts
├── admin.deposits.spec.ts      # (существует: deposit-flow.spec.ts)
├── admin.withdrawals-approvals.spec.ts
├── mpc.wallet-sign.spec.ts     # (существует: mpc-wallet.spec.ts)
├── audit.evidence.spec.ts
├── security.rbac.spec.ts
├── resilience.spec.ts          # (P2 - опционально)
├── golden-path.spec.ts         # INT-GOLD-01
└── integration.spec.ts         # (существует)
```

---

## 4. Приоритеты для CI

### Smoke (быстрые, каждый PR)
```
smoke.auth.spec.ts
retail.core.spec.ts (SCENE-A-01, SCENE-D-01)
audit.evidence.spec.ts (AUD-01)
```

### Core E2E (merge to main)
```
retail.core.spec.ts (все)
retail.kyt-review.spec.ts
admin.deposits.spec.ts
security.rbac.spec.ts
```

### Golden Integration (nightly)
```
golden-path.spec.ts
```

---

## 5. Подготовка окружения

### Backend .env
```bash
E2E_MODE=1                    # Ускоренные таймауты
KYT_MOCK_MODE=deterministic   # Предсказуемые результаты KYT
CONFIRMATIONS_REQUIRED=1      # Минимум подтверждений
```

### Seed data (миграция или скрипт)
```sql
-- Добавить тестовые адреса в address_book
INSERT INTO group_address_book (group_id, address, kind, label)
VALUES
  ('retail-group-id', '0xaf16...', 'ALLOW', 'Test Allow'),
  ('retail-group-id', '0xdead...', 'DENY', 'Test Deny');
```

### Тестовые пользователи
```
admin    / E2eTestPass2026   (ADMIN)
compliance / CompliancePass2026 (COMPLIANCE)
viewer   / ViewerPass2026    (VIEWER)
e2e_user / TestPass2026!     (USER - Retail)
```

---

## 6. Оценка времени

| Фаза | Описание | Время |
|------|----------|-------|
| 1 | Инфраструктура (fixtures, helpers) | 1h |
| 2 | Scene Tests (A/B/C/D) | 3h |
| 3 | Admin Tests (groups, policies) | 2h |
| 4 | Audit & Evidence | 1.5h |
| 5 | Security & RBAC | 1h |
| 6 | Golden Path | 2h |
| **Total** | | **10.5h** |

---

## 7. Следующий шаг

Начать с **Phase 1** (fixtures) + **Phase 2** (Scene Tests), так как они покрывают основные демо-сценарии из PRD.

```bash
# Создать структуру
mkdir -p frontend/e2e/fixtures

# Запустить один тест для проверки
npx playwright test retail.core.spec.ts --headed
```
