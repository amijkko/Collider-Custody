# Collider Custody — E2E Test Plan (Frontend-first) + Golden Integration Test
**Версия:** v0.1.1  
**Цель:** покрыть Playwright E2E основные пользовательские пути демо (Admin + Retail) и зафиксировать один “golden path” интеграционный тест, проходящий полный цикл: регистрация → создание кошелька → пополнение → credit approval → вывод обратно.

---

## 1) Предпосылки и фикстуры (обязательные для стабильности E2E)

### 1.1. Режимы окружения
- **E2E_MODE=1**: ускоренные таймауты, сниженное число подтверждений, предсказуемые интервалы polling.
- **RPC**: либо локальный (Anvil/Hardhat) для детерминированности, либо Sepolia (тогда тесты должны учитывать сетевую задержку и ретраи).
- **KYT**: детерминированный режим (mock/stub), чтобы одинаковые адреса всегда давали одинаковые решения.

### 1.2. Тестовые адреса (константы)
- `ALLOW_ADDR` — разрешённый адрес получателя (allowlist)
- `GRAY_ADDR` — адрес, который даёт KYT=REVIEW (создаётся case)
- `DENY_ADDR` — адрес denylist (fail-fast блокировка)

### 1.3. Тестовые пользователи (ролевая матрица)
- `admin` — права админа (approvals, deposits, policies/groups, audit)
- `compliance` — resolve KYT cases
- `viewer` — read-only (не видит админку)
- `e2e` — базовый retail пользователь для сценариев

### 1.4. Группа Retail (важно для демо)
- Все новые пользователи, созданные через регистрацию/авторизацию, **автоматически добавляются в группу Retail**.
- На группу Retail назначен `Retail Policy v3` (см. ниже).

### 1.5. Retail Policy v3 (минимальный набор правил для демо)
- **RET-01 (Micro)**: `amount ≤ 0.001 ETH` AND `to ∈ allowlist` → ALLOW, **KYT_SKIPPED**, **APPROVAL_SKIPPED**
- **RET-02 (Large)**: `amount > 0.001 ETH` AND `to ∈ allowlist` → REQUIRE_KYT + REQUIRE_APPROVAL(Admin 1-of-1)
- **RET-03 (Deny)**: `to ∈ denylist` → BLOCK (fail-fast до KYT/approval/sign)
- (Опционально) **RET-04 (Velocity)**: ограничение скорости микроплатежей

---

## 2) Рекомендуемая структура Playwright сьютов (файлы)

1. `e2e/smoke.auth.spec.ts` — login/logout/route guards
2. `e2e/retail.core.spec.ts` — Scene A/B/D (переводы)
3. `e2e/retail.kyt-review.spec.ts` — Scene C (cases + resolve)
4. `e2e/admin.groups-policies.spec.ts` — группы, политики, address book
5. `e2e/admin.deposits.spec.ts` — депозиты и админ approval
6. `e2e/admin.withdrawals-approvals.spec.ts` — approvals/SoD/очереди
7. `e2e/mpc.wallet-sign.spec.ts` — DKG + MPC signing UI путь
8. `e2e/audit.evidence.spec.ts` — evidence/timeline/export/verify
9. `e2e/security.rbac.spec.ts` — доступы/запреты
10. `e2e/resilience.spec.ts` — деградации (KYT down / signer down / RPC issues)

---

## 3) Детальный каталог E2E тестов (Frontend-first)

Нотация:
- **Preconditions** — что должно быть в системе до старта кейса
- **Steps (UI)** — действия через интерфейс
- **Asserts** — что проверяем (UI + при необходимости API-проверки через backend)

### A) Authentication & Onboarding

**E2E-AUTH-01 — Registration → auto-enroll Retail**
- Preconditions: существует группа Retail
- Steps: открыть `/register` → создать пользователя → войти
- Asserts:
  - редирект в `/app`
  - в админке `/admin/groups/Retail` новый пользователь присутствует

**E2E-AUTH-02 — Login (валидные креды)**
- Steps: `/login` → войти `admin`
- Asserts: доступ к `/admin` доступен

**E2E-AUTH-03 — Login (невалидные креды)**
- Steps: `/login` → неверный пароль
- Asserts: ошибка/тост, без входа

**E2E-AUTH-04 — Route guard**
- Steps: выйти, открыть `/app`, `/admin/groups`
- Asserts: редирект на `/login`

**E2E-AUTH-05 — Logout**
- Steps: logout
- Asserts: токен очищен, `/app` недоступен

---

### B) Retail Wallet lifecycle

**E2E-RET-01 — Dashboard отображает кошельки/балансы**
- Steps: `/app`
- Asserts: есть блок wallets; если нет кошелька — CTA “Create wallet”

**E2E-RET-02 — Create DEV wallet**
- Steps: “Create wallet” → выбрать DEV/EOA режим → создать
- Asserts: кошелёк появился, адрес отображается, wallet details открываются

**E2E-RET-03 — Create MPC wallet (DKG)**
- Preconditions: MPC WS endpoint доступен
- Steps: “Create MPC wallet” → пройти DKG flow
- Asserts:
  - кошелёк создан, address виден
  - UI фиксирует сохранение/наличие локального share (минимум индикатор “Key share present”)

**E2E-RET-04 — Ledger balance отображается отдельно**
- Steps: открыть wallet details
- Asserts: ledger/available balance отображается (и меняется только после CREDITED депозита)

---

### C) Scene A — Micro transfer ≤ 0.001 ETH

**E2E-SCENE-A-01 — Micro transfer allowlisted → KYT skipped + approvals skipped**
- Preconditions: `ALLOW_ADDR` есть в allowlist
- Steps:
  1) Retail user → Send/Withdraw
  2) `to=ALLOW_ADDR`, `amount=0.0005`
  3) Submit
- Asserts:
  - транзакция финализируется (FINALIZED/CONFIRMED)
  - в деталях транзакции:
    - matched rule: `RET-01`
    - KYT: **SKIPPED**
    - Approvals: **SKIPPED**
  - audit package доступен

**E2E-SCENE-A-02 — Micro transfer НЕ allowlisted → block**
- Steps: `to=random address not in allowlist`, `amount=0.0005`
- Asserts:
  - BLOCKED/FAILED_POLICY
  - reason: “not in allowlist” (rule id)
  - KYT не выполнялся (или отмечен как skipped)

---

### D) Scene B — Large transfer > 0.001 ETH

**E2E-SCENE-B-01 — Large transfer → KYT allow → admin approval → sign → finalized**
- Preconditions: `ALLOW_ADDR` allowlisted
- Steps:
  1) Retail user создаёт withdrawal `to=ALLOW_ADDR`, `amount=0.01`
  2) Проверить что статус KYT проходит и уходит в APPROVAL_PENDING
  3) Admin → approvals queue → Approve
  4) Ожидать signing/broadcast/confirm
- Asserts:
  - KYT decision = ALLOW (есть payload/score/tags)
  - Approval: есть запись “admin approved”
  - Tx hash присутствует
  - Audit package содержит policy+KYT+approval+tx

**E2E-SCENE-B-02 — Large transfer → admin Reject**
- Steps: как выше, но admin Reject
- Asserts:
  - terminal status REJECTED
  - audit фиксирует reject и причину (если обязательна)

---

### E) Scene C — KYT REVIEW → case → resolve

**E2E-SCENE-C-01 — KYT REVIEW создаёт case**
- Steps: Retail user withdrawal `to=GRAY_ADDR`, `amount=0.02`
- Asserts:
  - tx status = KYT_REVIEW
  - case появляется в Compliance inbox

**E2E-SCENE-C-02 — Resolve ALLOW требует reason → tx возвращается в approvals**
- Steps: Compliance → открыть case → Resolve ALLOW → ввести reason → Submit
- Asserts:
  - без reason submit невозможен
  - после ALLOW tx переходит в APPROVAL_PENDING

**E2E-SCENE-C-03 — Resolve BLOCK → terminal**
- Steps: Resolve BLOCK + reason
- Asserts:
  - tx terminal status KYT_BLOCKED/FAILED_KYT
  - audit содержит решение комплаенса

---

### F) Scene D — Denylist fail-fast

**E2E-SCENE-D-01 — DENY_ADDR блокируется до KYT/approvals/sign**
- Preconditions: `DENY_ADDR` в denylist
- Steps: Retail user withdrawal `to=DENY_ADDR`, `amount=0.0003`
- Asserts:
  - BLOCKED (fail-fast)
  - matched rule `RET-03`
  - отсутствуют шаги KYT/approval/sign (или отмечены как skipped)

---

### G) Admin — Groups / Policies / Address Book

**E2E-ADM-GRP-01 — Groups list доступен**
- Steps: admin → `/admin/groups`
- Asserts: есть Retail group, counters отображаются

**E2E-ADM-GRP-02 — Group detail: members CRUD**
- Steps: открыть Retail → add/remove user
- Asserts: изменения сохраняются

**E2E-ADM-POL-01 — Назначение policy set группе**
- Steps: Retail → сменить policy set/version
- Asserts: новая версия отображается и применяется к новым операциям

**E2E-ADM-AB-01 — Allowlist CRUD**
- Steps: добавить `ALLOW_ADDR` (label) → сохранить → удалить
- Asserts: список обновляется; операции реагируют (A-01 проходит/не проходит)

**E2E-ADM-AB-02 — Denylist CRUD**
- Steps: добавить `DENY_ADDR` → сохранить
- Asserts: Scene D блокируется

---

### H) Approvals & SoD

**E2E-SOD-01 — Initiator cannot approve own tx**
- Steps: retail user создаёт tx → пытается approve (если видит UI)
- Asserts: отказ (403/ошибка UI)

**E2E-APR-01 — Admin approvals queue**
- Steps: admin → withdrawals queue
- Asserts: pending approvals видны, фильтры работают, approve/reject работает

---

### I) Deposits (inbound + admin credit)

**E2E-DEP-01 — Deposit detected**
- Steps: отправить ETH на retail wallet (из funding wallet)
- Asserts: deposit появляется в UI как PENDING

**E2E-DEP-02 — Deposit KYT (allow/review/block)**
- Steps: deposit triggers KYT
- Asserts: статус меняется в зависимости от адреса источника

**E2E-DEP-03 — Admin approves deposit → CREDITED**
- Steps: admin → deposits → Approve
- Asserts: deposit CREDITED, ledger balance увеличился

**E2E-DEP-04 — Admin rejects deposit**
- Steps: Reject
- Asserts: ledger balance не меняется, audit есть

---

### J) MPC signing UX (если MPC — обязательный демо-режим)

**E2E-MPC-01 — MPC wallet creation (DKG)**
- Steps: DKG flow
- Asserts: wallet создан, share присутствует

**E2E-MPC-02 — Withdrawal с MPC кошелька подписывается**
- Steps: создать withdrawal → пройти MPC signing UI → confirm
- Asserts: signing success, tx finalized

**E2E-MPC-03 — Missing local share → понятная ошибка**
- Steps: очистить storage → попытка sign
- Asserts: fail с recovery-инструкцией

**E2E-MPC-04 — Bank signer down → SIGN_PENDING/FAILED_SIGN + retry**
- Steps: отключить signer endpoint → инициировать sign
- Asserts: корректный статус и возможность retry после восстановления

---

### K) Audit / Evidence

**E2E-AUD-01 — Withdrawal evidence package**
- Steps: открыть завершённую транзакцию → “Audit/Evidence”
- Asserts:
  - intent (to/amount)
  - policy decision (matched_rules, reasons, version)
  - KYT (result или SKIPPED)
  - approvals
  - signing method
  - tx hash + confirmations

**E2E-AUD-02 — Deposit evidence package**
- Аналогично для депозита

**E2E-AUD-03 — Export evidence JSON**
- Steps: export
- Asserts: файл скачан, JSON валиден и содержит ключевые блоки

**E2E-AUD-04 — Verify audit chain**
- Steps: verify (UI или endpoint)
- Asserts: verified=true

---

### L) RBAC / Security

**E2E-RBAC-01 — Viewer не видит админку**
- Steps: viewer → открыть `/admin/groups`
- Asserts: 403/redirect

**E2E-RBAC-02 — Operator не может resolve cases**
- Steps: operator → открыть case
- Asserts: нет кнопки resolve

**E2E-RBAC-03 — Compliance не может approve withdrawals (если так задумано)**
- Steps: compliance → открыть approvals
- Asserts: нет доступа/только read-only

---

### M) UI Validations

**E2E-VAL-01 — Amount validation**
- Steps: пусто/0/слишком много знаков
- Asserts: кнопка disabled, сообщение ошибки

**E2E-VAL-02 — Address validation**
- Steps: невалидный адрес
- Asserts: ошибка

**E2E-VAL-03 — Insufficient funds**
- Steps: amount > available
- Asserts: отказ до создания tx_request или блокировка с reason

**E2E-VAL-04 — Double submit**
- Steps: двойной клик submit
- Asserts: создаётся 1 tx_request

---

## 4) Отдельный “Golden Path” интеграционный тест (полный путь end-to-end)

### INT-GOLD-01 — Register → Create wallet → Fund → Deposit detected → Admin credit → Withdraw back
**Цель:** один тест, который проходит весь путь, максимально приближенный к реальному демо.

#### Preconditions
- В окружении есть “кошелёк для пополнения” (**Funding Wallet**) с балансом, доступный тестам:
  - `FUNDING_WALLET_ADDRESS`
  - возможность отправки (через приватный ключ в тестовом окружении или через внутренний funding-сервис/endpoint, если он у вас уже есть).
- Retail group включён как default auto-enroll.
- Policy Retail v3 активна.
- KYT детерминирован (Funding Wallet должен быть “зелёным”, чтобы депозит прошёл без review).

#### Steps (UI + small helpers)
1) **Регистрация** нового пользователя через UI (`/register`).
2) **Создание кошелька** (выбрать режим по цели теста):
   - Вариант A: DEV wallet (быстрее и стабильнее)
   - Вариант B: MPC wallet (если хотите “полный” контур)
3) **Пополнение**:
   - из Funding Wallet отправить фиксированную сумму (например, `0.05 ETH`) на адрес созданного кошелька.
   - (Это действие можно делать не через UI, а через helper в тесте: вызвать ваш backend endpoint “send from funding wallet” или напрямую отправить транзакцию через RPC с ключом funding wallet.)
4) **Проверка статусов депозита в UI**:
   - retail user видит депозит в списке (PENDING / DETECTED).
5) **Admin подтверждает депозит (Credit)**:
   - admin → `/admin/deposits` → approve deposit.
6) **Проверка, что баланс CREDITED**:
   - retail user → wallet details → ledger/available balance увеличился.
7) **Вывод обратно на Funding Wallet**:
   - создать withdrawal `to=FUNDING_WALLET_ADDRESS`:
     - для демонстрации approvals/KYT выберите сумму **> 0.001** (например, `0.01 ETH`), чтобы сработал `RET-02`.
8) **Проверка KYT и approvals**:
   - убедиться, что KYT = ALLOW, tx в APPROVAL_PENDING.
9) **Admin approve withdrawal**.
10) **Signing + broadcast + confirmation** (дождаться финального статуса).
11) **Проверка итогов**:
   - есть tx hash, статус FINALIZED/CONFIRMED
   - audit package доступен и содержит:
     - policy matched rules (`RET-02`)
     - KYT snapshot/decision
     - approvals
     - signing method (DEV/MPC)
12) (Опционально) **Проверка поступления на funding wallet**:
   - через RPC проверить баланс funding wallet или наличие tx receipt.

#### Asserts (минимум)
- Новый user создан и входит в Retail.
- Wallet создан.
- Deposit обнаружен и после admin approve становится CREDITED.
- Withdrawal проходит полный путь (KYT + approval + sign + confirm).
- Evidence package формируется и “объясняет” операцию.

---

## 5) Рекомендованные “гейты” для CI
- **Smoke** (быстрые): AUTH-02, RET-02, SCENE-A-01, SCENE-D-01, AUD-01
- **Core E2E**: SCENE-A/B/C/D + DEP-03 + RBAC-01
- **Golden integration**: INT-GOLD-01 (можно nightly или отдельным джобом)

---

## 6) Примечания по стабильности
- Для Sepolia: закладывайте ретраи и увеличенные таймауты на подтверждения.
- Для local chain: вы получите на порядок более стабильный прогон и сможете запускать “golden integration” на каждый PR.
