# Demo Enhancement Implementation Plan

## Overview

Реализация PRD v0.1.1 "Retail-first demo" для прохождения сценариев A/B/C/D.

---

## Gap Analysis

| Требование | Текущее состояние | Что нужно |
|------------|------------------|-----------|
| Groups | ❌ Нет | Новые таблицы + API + UI |
| Auto-enroll Retail | ❌ Нет | Изменить signup |
| Address Book (allow/deny) | ⚠️ Только config.kyt_blacklist | Per-group address book |
| Tiered Policy Rules | ⚠️ Flat policies | Условные правила RET-01/02/03 |
| Policy before KYT | ❌ KYT → Policy | Изменить orchestrator |
| Conditional KYT | ❌ Всегда выполняется | kyt_required flag |
| Conditional Approvals | ⚠️ Частично | approval_required from policy |
| Explainability | ❌ Нет | matched_rules, reasons, version |
| Evidence Package | ⚠️ Базовый audit | Собрать в единый пакет |

---

## Phase 1: Data Model

### 1.1 New Tables

```sql
-- Groups table
CREATE TABLE groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Group membership (user belongs to group)
CREATE TABLE group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);

-- Group address book (allow/deny lists per group)
CREATE TABLE group_address_book (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    address VARCHAR(42) NOT NULL,
    kind VARCHAR(10) NOT NULL CHECK (kind IN ('ALLOW', 'DENY')),
    label VARCHAR(255),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(group_id, address)
);

-- Policy sets (versioned policy collections)
CREATE TABLE policy_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    snapshot_hash VARCHAR(64), -- SHA256 of rules JSON
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(name, version)
);

-- Policy rules (within policy set)
CREATE TABLE policy_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_set_id UUID REFERENCES policy_sets(id) ON DELETE CASCADE,
    rule_id VARCHAR(50) NOT NULL, -- e.g., RET-01, RET-02, RET-03
    priority INTEGER NOT NULL DEFAULT 100, -- lower = higher priority
    conditions JSONB NOT NULL, -- {amount_lte: 0.001, address_in: "allowlist"}
    decision VARCHAR(20) NOT NULL, -- ALLOW, BLOCK, CONTINUE
    kyt_required BOOLEAN DEFAULT TRUE,
    approval_required BOOLEAN DEFAULT FALSE,
    approval_count INTEGER DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(policy_set_id, rule_id)
);

-- Group policy assignment
CREATE TABLE group_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    policy_set_id UUID REFERENCES policy_sets(id),
    assigned_at TIMESTAMP DEFAULT NOW(),
    assigned_by UUID REFERENCES users(id),
    UNIQUE(group_id) -- one active policy per group
);
```

### 1.2 Seed Data

```sql
-- Default Retail group
INSERT INTO groups (id, name, description, is_default)
VALUES ('00000000-0000-0000-0000-000000000001', 'Retail', 'Default group for retail users', true);

-- Retail policy set v3
INSERT INTO policy_sets (id, name, version, description)
VALUES ('00000000-0000-0000-0000-000000000010', 'Retail Policy', 3, 'Tiered policy for retail users');

-- RET-01: Micropayment allow (≤0.001 ETH + allowlist)
INSERT INTO policy_rules (policy_set_id, rule_id, priority, conditions, decision, kyt_required, approval_required, description)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    'RET-01',
    10,
    '{"amount_lte": "0.001", "address_in": "allowlist"}',
    'ALLOW',
    false,
    false,
    'Micropayments to allowlisted addresses - no KYT, no approval'
);

-- RET-02: Large transfer (>0.001 ETH + allowlist)
INSERT INTO policy_rules (policy_set_id, rule_id, priority, conditions, decision, kyt_required, approval_required, approval_count, description)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    'RET-02',
    20,
    '{"amount_gt": "0.001", "address_in": "allowlist"}',
    'ALLOW',
    true,
    true,
    1,
    'Large transfers to allowlisted addresses - require KYT + 1 approval'
);

-- RET-03: Denylist block
INSERT INTO policy_rules (policy_set_id, rule_id, priority, conditions, decision, kyt_required, approval_required, description)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    'RET-03',
    1, -- Highest priority
    '{"address_in": "denylist"}',
    'BLOCK',
    false,
    false,
    'Block all transfers to denylisted addresses'
);

-- Assign policy to Retail group
INSERT INTO group_policies (group_id, policy_set_id)
VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010');
```

### 1.3 Files to Create/Modify

```
app/models/group.py          # NEW - Group, GroupMember, GroupAddressBook
app/models/policy_set.py     # NEW - PolicySet, PolicyRule, GroupPolicy
app/models/__init__.py       # MODIFY - export new models
```

---

## Phase 2: Backend Services

### 2.1 Group Service

**File:** `app/services/group.py` (NEW)

```python
class GroupService:
    async def create_group(name, description, is_default=False)
    async def get_group(group_id) -> Group
    async def list_groups() -> List[Group]
    async def add_member(group_id, user_id)
    async def remove_member(group_id, user_id)
    async def get_user_groups(user_id) -> List[Group]
    async def get_default_group() -> Group  # Returns Retail
```

### 2.2 Address Book Service

**File:** `app/services/address_book.py` (NEW)

```python
class AddressBookService:
    async def add_address(group_id, address, kind, label)
    async def remove_address(group_id, address)
    async def list_addresses(group_id, kind=None) -> List[GroupAddressBook]
    async def is_allowed(group_id, address) -> bool
    async def is_denied(group_id, address) -> bool
    async def check_address(group_id, address) -> Tuple[bool, str]  # (is_ok, kind)
```

### 2.3 Policy Engine v2

**File:** `app/services/policy_v2.py` (NEW)

```python
@dataclass
class PolicyEvalResult:
    decision: str  # ALLOW, BLOCK
    matched_rules: List[str]  # [RET-01]
    reasons: List[str]  # ["Micropayment to allowlisted address"]
    kyt_required: bool
    approval_required: bool
    approval_count: int
    policy_version: str  # "Retail v3"
    policy_snapshot_hash: str
    evaluated_at: datetime

class PolicyEngineV2:
    async def evaluate(
        user_id: str,
        to_address: str,
        amount: Decimal,
        asset: str,
        wallet: Wallet
    ) -> PolicyEvalResult:
        # 1. Get user's group
        group = await self.group_service.get_user_groups(user_id)[0]

        # 2. Get group's policy set
        policy_set = await self.get_active_policy(group.id)

        # 3. Check address book first (fail-fast for denylist)
        address_status = await self.address_book.check_address(group.id, to_address)

        # 4. Evaluate rules in priority order
        for rule in sorted(policy_set.rules, key=lambda r: r.priority):
            if self._rule_matches(rule, amount, address_status):
                return PolicyEvalResult(
                    decision=rule.decision,
                    matched_rules=[rule.rule_id],
                    reasons=[rule.description],
                    kyt_required=rule.kyt_required,
                    approval_required=rule.approval_required,
                    approval_count=rule.approval_count,
                    policy_version=f"{policy_set.name} v{policy_set.version}",
                    policy_snapshot_hash=policy_set.snapshot_hash,
                    evaluated_at=datetime.utcnow()
                )

        # 5. Default: block unknown addresses
        return PolicyEvalResult(
            decision='BLOCK',
            matched_rules=['DEFAULT'],
            reasons=['Address not in allowlist'],
            ...
        )
```

### 2.4 Orchestrator v2

**File:** `app/services/orchestrator.py` (MODIFY)

**Изменение порядка:**
```
BEFORE: SUBMITTED → KYT → POLICY → APPROVAL → SIGN
AFTER:  SUBMITTED → POLICY → KYT (conditional) → APPROVAL (conditional) → SIGN
```

**Новые статусы:**
```python
class TxStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    POLICY_PENDING = "POLICY_PENDING"     # NEW
    POLICY_BLOCKED = "POLICY_BLOCKED"     # EXISTS
    KYT_PENDING = "KYT_PENDING"           # EXISTS (now conditional)
    KYT_SKIPPED = "KYT_SKIPPED"           # NEW
    KYT_BLOCKED = "KYT_BLOCKED"           # EXISTS
    KYT_REVIEW = "KYT_REVIEW"             # EXISTS
    APPROVAL_PENDING = "APPROVAL_PENDING" # EXISTS (now conditional)
    APPROVAL_SKIPPED = "APPROVAL_SKIPPED" # NEW
    ...
```

**Новый flow:**
```python
async def _process_tx(self, tx: TxRequest):
    # 1. Policy evaluation FIRST
    policy_result = await self.policy_v2.evaluate(
        user_id=tx.created_by,
        to_address=tx.to_address,
        amount=tx.amount,
        asset=tx.asset,
        wallet=wallet
    )

    # Store for evidence
    tx.policy_result = asdict(policy_result)

    # 2. Check policy decision
    if policy_result.decision == 'BLOCK':
        await self._transition_status(tx, TxStatus.POLICY_BLOCKED)
        return

    # 3. Conditional KYT
    if policy_result.kyt_required:
        kyt_result = await self._process_kyt(tx)
        if kyt_result in ['BLOCK', 'REVIEW']:
            return  # Wait or blocked
    else:
        # Log KYT skipped
        await self.audit.log_event(
            event_type=AuditEventType.KYT_SKIPPED,
            payload={'reason': policy_result.matched_rules[0]}
        )
        await self._transition_status(tx, TxStatus.KYT_SKIPPED)

    # 4. Conditional Approvals
    if policy_result.approval_required:
        tx.requires_approval = True
        tx.required_approvals = policy_result.approval_count
        await self._transition_status(tx, TxStatus.APPROVAL_PENDING)
        return  # Wait for approvals
    else:
        # Log approvals skipped
        await self.audit.log_event(
            event_type=AuditEventType.APPROVALS_SKIPPED,
            payload={'reason': policy_result.matched_rules[0]}
        )

    # 5. Proceed to signing
    await self._process_signing(tx)
```

### 2.5 Auth Service Update

**File:** `app/services/auth.py` (MODIFY)

```python
async def create_user(self, ...):
    # ... existing code ...

    # NEW: Auto-enroll in default group (Retail)
    default_group = await self.group_service.get_default_group()
    if default_group:
        await self.group_service.add_member(default_group.id, user.id)

        # Log enrollment
        await self.audit.log_event(
            event_type=AuditEventType.USER_GROUP_ENROLLED,
            entity_id=user.id,
            payload={
                'group_id': str(default_group.id),
                'group_name': default_group.name,
                'auto_enrolled': True
            }
        )

    return user
```

---

## Phase 3: API Endpoints

### 3.1 Groups API

**File:** `app/api/groups.py` (NEW)

```
GET    /v1/groups                     # List all groups (admin)
GET    /v1/groups/{id}                # Group details + members
POST   /v1/groups                     # Create group (admin)
PUT    /v1/groups/{id}                # Update group (admin)

GET    /v1/groups/{id}/members        # List members
POST   /v1/groups/{id}/members        # Add member
DELETE /v1/groups/{id}/members/{uid}  # Remove member

GET    /v1/groups/{id}/address-book   # List addresses
POST   /v1/groups/{id}/address-book   # Add address
DELETE /v1/groups/{id}/address-book/{address}  # Remove address

GET    /v1/groups/{id}/policy         # Get active policy
PUT    /v1/groups/{id}/policy         # Assign policy
```

### 3.2 Extended TX Request Response

**File:** `app/schemas/tx_request.py` (MODIFY)

```python
class PolicyDecisionBlock(BaseModel):
    decision: str  # ALLOW, BLOCK
    matched_rules: List[str]
    reasons: List[str]
    kyt_required: bool
    approval_required: bool
    policy_version: str
    policy_snapshot_hash: str

class TxRequestResponse(BaseModel):
    # ... existing fields ...

    # NEW: Explainability
    policy_decision: Optional[PolicyDecisionBlock]
    kyt_decision: Optional[str]  # ALLOW, BLOCK, REVIEW, SKIPPED
    kyt_skipped_reason: Optional[str]
    approval_skipped_reason: Optional[str]
```

### 3.3 Evidence Package API

**File:** `app/api/evidence.py` (NEW)

```
GET /v1/tx-requests/{id}/evidence    # Full evidence package
GET /v1/tx-requests/{id}/timeline    # Event timeline
```

---

## Phase 4: Frontend

### 4.1 New Pages

```
/admin/groups                    # Groups list
/admin/groups/{id}               # Group detail (members, policy, address book)
/admin/groups/{id}/address-book  # Address book management
/admin/policies                  # Policy sets list
/admin/policies/{id}             # Policy detail with rules
```

### 4.2 Enhanced TX Details

```tsx
// components/tx/tx-decision-block.tsx
// Shows: Policy decision, matched rules, KYT decision, approvals

// components/tx/tx-timeline.tsx
// Shows: Full event timeline with expandable details

// components/tx/tx-evidence.tsx
// Shows: Complete evidence package with export button
```

---

## Phase 5: Migration & Seeds

### 5.1 Alembic Migration

```bash
alembic revision -m "add_groups_and_policy_sets"
```

### 5.2 Seed Script

```python
# scripts/seed_demo.py
async def seed_demo_data():
    # 1. Create Retail group
    # 2. Create Retail Policy v3
    # 3. Create rules RET-01, RET-02, RET-03
    # 4. Add sample addresses to address book
    # 5. Assign policy to group
```

---

## Implementation Order

### Week 1: Data Model + Core Services
- [ ] 1.1 Create migration for new tables
- [ ] 1.2 Create models (Group, PolicySet, PolicyRule, etc.)
- [ ] 1.3 Create GroupService
- [ ] 1.4 Create AddressBookService
- [ ] 1.5 Create PolicyEngineV2
- [ ] 1.6 Update AuthService for auto-enroll

### Week 2: Orchestrator + API
- [ ] 2.1 Add new TxStatus values
- [ ] 2.2 Refactor orchestrator flow
- [ ] 2.3 Create Groups API
- [ ] 2.4 Create Evidence API
- [ ] 2.5 Update TxRequest schema

### Week 3: Frontend + Testing
- [ ] 3.1 Groups management pages
- [ ] 3.2 Address book UI
- [ ] 3.3 Enhanced TX details
- [ ] 3.4 Evidence package view
- [ ] 3.5 E2E tests for scenarios A/B/C/D

### Week 4: Polish + Deploy
- [ ] 4.1 Seed demo data
- [ ] 4.2 Deploy to Railway/Vercel
- [ ] 4.3 Run through all demo scenarios
- [ ] 4.4 Fix issues
- [ ] 4.5 Documentation

---

## Acceptance Criteria (E2E Tests)

```python
# test_demo_scenarios.py

async def test_scene_a_micro_transfer():
    """0.0005 ETH → allowlist → KYT skipped → no approval → finalized"""
    # 1. Create user (auto-enrolled in Retail)
    # 2. Add address to allowlist
    # 3. Create tx for 0.0005 ETH
    # 4. Assert: status = FINALIZED
    # 5. Assert: policy_result.matched_rules = ['RET-01']
    # 6. Assert: kyt_decision = 'SKIPPED'
    # 7. Assert: no approvals created

async def test_scene_b_large_transfer():
    """0.01 ETH → allowlist → KYT required → approval required → finalized"""
    # 1. Create tx for 0.01 ETH to allowlisted address
    # 2. Assert: status = APPROVAL_PENDING
    # 3. Assert: policy_result.matched_rules = ['RET-02']
    # 4. Assert: kyt_decision = 'ALLOW'
    # 5. Admin approves
    # 6. Assert: status = FINALIZED

async def test_scene_c_kyt_review():
    """0.02 ETH → gray address → case created → resolve → finalized"""
    # 1. Create tx for 0.02 ETH to graylist address
    # 2. Assert: status = KYT_REVIEW
    # 3. Assert: kyt_case created
    # 4. Resolve case with ALLOW
    # 5. Assert: moves to APPROVAL_PENDING
    # 6. Approve and finalize

async def test_scene_d_denylist_block():
    """Any amount → denylist → blocked immediately"""
    # 1. Add address to denylist
    # 2. Create tx to that address
    # 3. Assert: status = POLICY_BLOCKED
    # 4. Assert: policy_result.matched_rules = ['RET-03']
    # 5. Assert: no KYT called
    # 6. Assert: no approvals created
```

---

## Risk & Dependencies

| Risk | Mitigation |
|------|------------|
| Breaking existing tx flow | Keep old policy service, add v2 alongside |
| Migration complexity | Test on local first, then staging |
| Frontend scope creep | MVP UI first, polish later |
| BitOK not ready | Use mock mode (already implemented) |
