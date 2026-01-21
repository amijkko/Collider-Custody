# План реализации: Next.js демо-кабинет (Client + Admin) для WaaS + MPC tECDSA EOA (2PC)

Цель демо: пользователь банка создаёт кошелёк, делает депозит через MetaMask, админ подтверждает депозит (ledger credit), пользователь видит баланс и инициирует withdraw, который также требует подтверждения админом и **реального MPC-подписания** (tECDSA 2-of-2).  
**Важно:** MPC не мокается — в DoD включена полноценная реализация **DKG** и **2PC signing**.

---

## 1) Архитектура (минимально боеспособная)

### 1.1 Next.js как BFF (Backend-for-Frontend)
Next.js приложение выполняет две роли:
- UI (Client Portal + Admin Console)
- BFF слой через `/app/api/*` маршруты, который проксирует запросы в Core API и MPC Coordinator

Рекомендации:
- JWT хранить в **httpOnly cookie**
- RBAC через middleware: `/admin/*` только admin роли
- Centralized fetch wrapper с корреляцией (`X-Correlation-ID`) и обработкой ошибок

### 1.2 Сервисы
1) **Core API (ваш монолит):**
- auth/users
- wallets (registry)
- deposits (inbound events)
- ledger balances
- withdraw requests
- approvals / SoD / policy
- audit (package + verify)

2) **MPC Coordinator (новый сервис):**
- keygen sessions (DKG)
- signing sessions (2PC tECDSA)
- bank-side signer participation
- validation `SigningPermit` от Core API (anti-bypass)

3) **Bank Signer Node (часть MPC кластера):**
- хранит bank share (зашифрованно)
- участвует в DKG/signing

4) **Client MPC runtime (в браузере):**
- хранит user share (зашифрованно)
- участвует в DKG/signing через интерактивные шаги (WASM клиент)

---

## 2) Пользовательские флоу (end-to-end)

### 2.1 Регистрация и создание MPC-кошелька (EOA)
**Client Portal**
1) User регистрируется/логинится
2) Нажимает **Create wallet**
3) Запускается keygen session:
   - browser (user party) ↔ MPC Coordinator ↔ bank signer node (bank party)
4) По итогам **DKG**:
   - получаем pubkey → derive EOA address
   - сохраняем `wallet.address`, `wallet.key_ref=mpc-tecdsa://...`
   - user share шифруется паролем и сохраняется локально

### 2.2 Deposit через MetaMask (внешний кошелёк)
**Client**
1) отправляет test ETH на `wallet.address` в Sepolia
2) chain listener фиксирует deposit event → `PENDING_ADMIN`

**Admin**
1) видит депозит в очереди
2) нажимает **Approve deposit**
3) ledger: `pending -> available`
4) у пользователя появляется `available` баланс

### 2.3 Withdraw (admin approve + 2PC signing)
**Client**
1) вводит `to_address`, `amount`, создаёт withdraw request → `PENDING_ADMIN`
2) после admin approve появляется signing job (ожидается подпись пользователя)
3) пользователь вводит пароль, расшифровывает user share, участвует в signing session

**Admin**
1) approve withdraw → создаётся signing job + permit
2) система инициирует MPC signing session

**Signing**
- 2PC tECDSA: подпись возможна только при участии **user share** и **bank share**
- после подписи Core API отправляет raw tx в сеть
- статусы: `BROADCASTED → CONFIRMING → FINALIZED`

---

## 3) UI-модули и маршруты (Next.js App Router)

### 3.1 Общие
- `/login`, `/register`
- middleware RBAC:
  - `/app/*` — authenticated user
  - `/admin/*` — admin/approver roles

### 3.2 Client Portal
- `/app` — Dashboard:
  - wallet address / CTA Create wallet
  - balances: pending / available / locked
  - уведомления: “Signature required”
- `/app/deposit` — address + QR + deposits list
- `/app/withdraw` — форма + список withdraw requests
- `/app/sign` — список signing jobs + кнопка “Sign”

### 3.3 Admin Console
- `/admin` — deposit queue (approve/reject/hold)
- `/admin/withdrawals` — withdrawal queue (approve/reject)
- `/admin/users/[id]` — пользователь: wallets, deposits, withdrawals, audit trail

---

## 4) Ключ пользователя на фронте: password-encrypted share storage

### 4.1 Где храним
- **IndexedDB** (предпочтительно; binary blobs; устойчивее чем localStorage)

### 4.2 Как шифруем (WebCrypto)
- KDF: **PBKDF2-SHA256** (native WebCrypto)
- ENC: **AES-256-GCM**
- параметры:
  - `salt`: 16–32 bytes random
  - `iv`: 12 bytes random
  - iterations: 200k–400k (целевой ~300k)

### 4.3 Формат записи (пример)
```json
{
  "version": 1,
  "walletId": "...",
  "keysetId": "...",
  "cipherSuite": "secp256k1-tecdsa-2pc",
  "kdf": { "name": "PBKDF2", "hash": "SHA-256", "iterations": 310000, "salt_b64": "..." },
  "enc": { "name": "AES-GCM", "iv_b64": "...", "ciphertext_b64": "..." },
  "createdAt": "..."
}
```

### 4.4 UX правила
- Пароль **никогда** не отправляется на backend
- Plain share живёт в памяти только во время signing, после — очищается
- При signing: modal “Enter password to unlock signing”

---

## 5) MPC интеграция (2PC tECDSA) — контракты и сессии

### 5.1 MPC Coordinator API (минимум)
**Keygen (DKG)**
- `POST /mpc/keygen/start` → `session_id`
- `POST /mpc/keygen/step` (client msg) → (server msg)
- `POST /mpc/keygen/finalize` → `{ keyset_id, pubkey, address }`

**Signing (2PC)**
- `POST /mpc/sign/start` → `session_id`
- `POST /mpc/sign/step` (client msg) → (server msg)
- `POST /mpc/sign/finalize` → `{ signature, signed_raw_tx }` (или signature)

### 5.2 Anti-bypass: SigningPermit
Coordinator принимает `sign/start` только при наличии `SigningPermit` от Core API:
- tx_request_id / withdraw_request_id
- wallet_id / keyset_id
- tx_hash
- approvals snapshot
- policy/kyt snapshot
- audit anchor hash
- TTL + одноразовость

---

## 6) Core API: минимальные endpoints под UI

### 6.1 Балансы (ledger)
- `GET /v1/balances/me` → `{ pending, available, locked }`

### 6.2 Deposits
- `GET /v1/deposits/me`
- `GET /v1/deposits?status=PENDING_ADMIN` (admin)
- `POST /v1/deposits/{id}/approve` (admin)
- `POST /v1/deposits/{id}/reject` (admin)

### 6.3 Withdraw requests
- `POST /v1/withdraw-requests` (user)
- `GET /v1/withdraw-requests/me`
- `GET /v1/withdraw-requests?status=PENDING_ADMIN` (admin)
- `POST /v1/withdraw-requests/{id}/approve` (admin) → создаёт signing job
- `POST /v1/withdraw-requests/{id}/reject` (admin)

### 6.4 Signing jobs
- `GET /v1/signing-jobs/me` (user)
- `POST /v1/signing-jobs/{id}/start` (user/admin trigger) → инициирует MPC session
- `POST /v1/signing-jobs/{id}/client-step` (user)
- `POST /v1/signing-jobs/{id}/complete` (system)

---

## 7) План реализации по итерациям

### Итерация 1 — Next.js UI + Auth + RBAC + BFF
1) Next.js App Router
2) `/login`, `/register`
3) BFF `/api/auth/*`: login/logout, httpOnly cookies
4) middleware guards
5) skeleton UI страниц (без бизнес-логики)

**Результат:** приложение готово к интеграции и разделению ролей.

### Итерация 2 — Ledger + Deposit workflow (с реальными on-chain событиями)
1) Wallet отображение в UI (если кошелька нет — CTA)
2) Deposit page: адрес, QR, список депозитов
3) Admin deposit queue: approve/reject
4) Ledger crediting после admin approve (pending→available)

**Результат:** “как банк” депозитный цикл полностью работает.

### Итерация 3 — Реальный MPC keygen (DKG) + encrypted local share
1) Client-side crypto utilities (PBKDF2 + AES-GCM) + IndexedDB storage
2) MPC keygen sessions:
   - UI “Create wallet” запускает DKG
   - user share → encrypt → store
   - server сохраняет keyset/address/key_ref
3) Dashboard отображает EOA address, key_ref metadata

**Результат:** кошелёк реально создан через MPC DKG, share хранится у клиента.

### Итерация 4 — Withdraw workflow + реальный 2PC signing
1) Withdraw request: user инициирует, ledger available→locked
2) Admin approve withdraw: создаёт signing job + permit
3) Client получает signing job, вводит пароль, decrypt share, выполняет signing steps
4) Signed raw tx отправляется в сеть, статусы финализируются, ledger locked→settled

**Результат:** end-to-end “admin approve + user sign” через 2PC tECDSA работает.

### Итерация 5 — Полировка и стабильность демо
1) SSE/Websocket для обновлений статусов вместо polling
2) Визуальные статусы, explorer links, audit links
3) Негативные сценарии:
   - wrong password
   - admin reject deposit/withdraw
   - user не подписал (timeout)
4) Demo control panel (корреляция, быстрые ссылки)

---

## 8) Definition of Done (DoD) — критично важное уточнение

### DoD-1: MPC не мокается
- MPC keygen и signing выполняются **реальными протоколами**, а не заглушками/симуляциями.
- Запуск “Create wallet” инициирует полноценный **DKG** (Distributed Key Generation) для tECDSA 2PC:
  - оба участника (browser + bank signer node) участвуют в протоколе
  - на выходе получаем pubkey и **EOA address**
  - приватный ключ целиком **не существует**; только shares.

### DoD-2: 2PC signing реально требуется
- Withdrawal невозможно отправить в сеть без участия:
  1) admin approve (permit)
  2) user подписи (client share)
  3) bank участия (bank share)
- Подпись, полученная из MPC, является валидной ECDSA подписью и принимается Sepolia как подпись EOA.

### DoD-3: User share хранится только локально и зашифрован паролем
- Share хранится в IndexedDB только в ciphertext
- Пароль не отправляется на сервер
- Plain share не пишется в логи/диск и не хранится дольше сессии подписи

### DoD-4: Deposit crediting строго через admin approval
- Deposit отображается как `pending` до admin approve
- После approve баланс становится `available`

### DoD-5: UX и наблюдаемость
- Статусы транзакций отражаются в обоих кабинетах
- Есть ссылки на explorer и audit verify/package

---

## 9) Риски (коротко)
- Сборка C++ MPC клиента в WASM — ключевой технический блок; вынести в отдельный спринт с smoke-тестами keygen/signing.
- Парольное шифрование (PBKDF2) — демо-компромисс; важно подобрать iterations и нигде не хранить пароль.
- 2PC по определению требует обоих участников: отсутствие user подписи блокирует вывод (ожидаемая семантика).

