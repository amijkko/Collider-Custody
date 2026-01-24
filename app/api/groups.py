"""Groups API - manage groups, address books, and policies."""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_correlation_id, get_current_user, require_admin
from app.models.user import User
from app.models.group import AddressKind
from app.services.audit import AuditService
from app.services.group import GroupService
from app.services.address_book import AddressBookService
from app.services.policy_v2 import PolicySetService, PolicyEngineV2
from app.schemas.common import CorrelatedResponse
from app.schemas.group import (
    GroupCreate,
    GroupResponse,
    GroupListResponse,
    AddressBookEntryCreate,
    AddressBookEntryResponse,
    AddressBookListResponse,
    AddressCheckResponse,
    PolicySetResponse,
    PolicySetListResponse,
    PolicySetCreate,
    PolicySetUpdate,
    PolicyRuleCreate,
    PolicyRuleUpdate,
    PolicyRuleResponse,
    PolicyAssignRequest,
    PolicyEvalPreviewRequest,
    PolicyEvalPreviewResponse,
)
from app.models.policy_set import PolicyDecision

router = APIRouter(prefix="/v1/groups", tags=["Groups"])


# ============== Seed Endpoint ==============

@router.post("/seed", response_model=CorrelatedResponse[dict])
async def seed_demo_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """
    Seed demo data: Retail group, tiered policies, demo addresses.

    This is idempotent - safe to run multiple times.
    Creates:
    - Retail group (default for all users)
    - Retail Policy v3 with rules RET-01, RET-02, RET-03
    - Demo addresses: Binance (allowlist), Tornado Cash (denylist)
    """
    from app.services.seed import seed_all

    await seed_all(db)

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data={
            "message": "Seed data created successfully",
            "created": {
                "group": "Retail",
                "policy": "Retail Policy v3",
                "rules": ["RET-01", "RET-02", "RET-03"],
                "allowlist_addresses": 10,
                "denylist_addresses": 6,
            }
        }
    )


# ============== Policy Set Endpoints (must be before /{group_id}) ==============

@router.get("/policies", response_model=CorrelatedResponse[PolicySetListResponse])
async def list_policy_sets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """List all policy sets (admin only)."""
    from sqlalchemy import select
    from app.models.policy_set import PolicySet
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(PolicySet)
        .options(selectinload(PolicySet.rules))
        .order_by(PolicySet.name, PolicySet.version.desc())
    )
    policy_sets = list(result.scalars().all())

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicySetListResponse(
            policy_sets=[PolicySetResponse(
                id=ps.id,
                name=ps.name,
                version=ps.version,
                description=ps.description,
                is_active=ps.is_active,
                snapshot_hash=ps.snapshot_hash,
                rules=[],  # Don't include rules in list view
                created_at=ps.created_at,
            ) for ps in policy_sets],
            total=len(policy_sets),
        )
    )


@router.get("/policies/{policy_set_id}", response_model=CorrelatedResponse[PolicySetResponse])
async def get_policy_set(
    policy_set_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Get policy set details with rules."""
    audit = AuditService(db)
    policy_service = PolicySetService(db, audit)

    ps = await policy_service.get_policy_set(policy_set_id)
    if not ps:
        raise HTTPException(status_code=404, detail="Policy set not found")

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicySetResponse(
            id=ps.id,
            name=ps.name,
            version=ps.version,
            description=ps.description,
            is_active=ps.is_active,
            snapshot_hash=ps.snapshot_hash,
            rules=[PolicyRuleResponse(
                id=r.id,
                rule_id=r.rule_id,
                priority=r.priority,
                conditions=r.conditions,
                decision=r.decision,
                kyt_required=r.kyt_required,
                approval_required=r.approval_required,
                approval_count=r.approval_count,
                description=r.description,
            ) for r in sorted(ps.rules, key=lambda x: x.priority)],
            created_at=ps.created_at,
        )
    )


@router.post("/policies", response_model=CorrelatedResponse[PolicySetResponse])
async def create_policy_set(
    data: PolicySetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Create a new policy set (admin only)."""
    audit = AuditService(db)
    policy_service = PolicySetService(db, audit)

    ps = await policy_service.create_policy_set(
        name=data.name,
        description=data.description,
        created_by=current_user.id,
        correlation_id=correlation_id,
    )
    await db.commit()

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicySetResponse(
            id=ps.id,
            name=ps.name,
            version=ps.version,
            description=ps.description,
            is_active=ps.is_active,
            snapshot_hash=ps.snapshot_hash,
            rules=[],
            created_at=ps.created_at,
        )
    )


@router.put("/policies/{policy_set_id}", response_model=CorrelatedResponse[PolicySetResponse])
async def update_policy_set(
    policy_set_id: str,
    data: PolicySetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Update a policy set (admin only)."""
    audit = AuditService(db)
    policy_service = PolicySetService(db, audit)

    ps = await policy_service.update_policy_set(
        policy_set_id=policy_set_id,
        name=data.name,
        description=data.description,
        is_active=data.is_active,
        actor_id=current_user.id,
        correlation_id=correlation_id,
    )
    if not ps:
        raise HTTPException(status_code=404, detail="Policy set not found")

    await db.commit()

    # Reload to get updated rules
    ps = await policy_service.get_policy_set(policy_set_id)

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicySetResponse(
            id=ps.id,
            name=ps.name,
            version=ps.version,
            description=ps.description,
            is_active=ps.is_active,
            snapshot_hash=ps.snapshot_hash,
            rules=[PolicyRuleResponse(
                id=r.id,
                rule_id=r.rule_id,
                priority=r.priority,
                conditions=r.conditions,
                decision=r.decision,
                kyt_required=r.kyt_required,
                approval_required=r.approval_required,
                approval_count=r.approval_count,
                description=r.description,
            ) for r in sorted(ps.rules, key=lambda x: x.priority)],
            created_at=ps.created_at,
        )
    )


@router.delete("/policies/{policy_set_id}")
async def delete_policy_set(
    policy_set_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Delete a policy set (admin only). Cannot delete if assigned to a group."""
    audit = AuditService(db)
    policy_service = PolicySetService(db, audit)

    deleted = await policy_service.delete_policy_set(
        policy_set_id=policy_set_id,
        actor_id=current_user.id,
        correlation_id=correlation_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete policy set (may be assigned to a group or not found)"
        )

    await db.commit()

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data={"message": "Policy set deleted"}
    )


# ============== Policy Rule Endpoints ==============

@router.post("/policies/{policy_set_id}/rules", response_model=CorrelatedResponse[PolicyRuleResponse])
async def add_rule(
    policy_set_id: str,
    data: PolicyRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Add a rule to a policy set (admin only)."""
    audit = AuditService(db)
    policy_service = PolicySetService(db, audit)

    # Check policy exists
    ps = await policy_service.get_policy_set(policy_set_id)
    if not ps:
        raise HTTPException(status_code=404, detail="Policy set not found")

    # Check if rule_id already exists
    existing_rule_ids = [r.rule_id for r in ps.rules]
    if data.rule_id in existing_rule_ids:
        raise HTTPException(status_code=400, detail=f"Rule {data.rule_id} already exists")

    rule = await policy_service.add_rule(
        policy_set_id=policy_set_id,
        rule_id=data.rule_id,
        conditions=data.conditions,
        decision=PolicyDecision(data.decision),
        priority=data.priority,
        kyt_required=data.kyt_required,
        approval_required=data.approval_required,
        approval_count=data.approval_count,
        description=data.description,
        actor_id=current_user.id,
        correlation_id=correlation_id,
    )
    await db.commit()

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicyRuleResponse(
            id=rule.id,
            rule_id=rule.rule_id,
            priority=rule.priority,
            conditions=rule.conditions,
            decision=rule.decision,
            kyt_required=rule.kyt_required,
            approval_required=rule.approval_required,
            approval_count=rule.approval_count,
            description=rule.description,
        )
    )


@router.put("/policies/{policy_set_id}/rules/{rule_id}", response_model=CorrelatedResponse[PolicyRuleResponse])
async def update_rule(
    policy_set_id: str,
    rule_id: str,
    data: PolicyRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Update a policy rule (admin only)."""
    audit = AuditService(db)
    policy_service = PolicySetService(db, audit)

    decision = PolicyDecision(data.decision) if data.decision else None

    rule = await policy_service.update_rule(
        policy_set_id=policy_set_id,
        rule_id=rule_id,
        priority=data.priority,
        conditions=data.conditions,
        decision=decision,
        kyt_required=data.kyt_required,
        approval_required=data.approval_required,
        approval_count=data.approval_count,
        description=data.description,
        actor_id=current_user.id,
        correlation_id=correlation_id,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.commit()

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicyRuleResponse(
            id=rule.id,
            rule_id=rule.rule_id,
            priority=rule.priority,
            conditions=rule.conditions,
            decision=rule.decision,
            kyt_required=rule.kyt_required,
            approval_required=rule.approval_required,
            approval_count=rule.approval_count,
            description=rule.description,
        )
    )


@router.delete("/policies/{policy_set_id}/rules/{rule_id}")
async def delete_rule(
    policy_set_id: str,
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Delete a rule from a policy set (admin only)."""
    audit = AuditService(db)
    policy_service = PolicySetService(db, audit)

    deleted = await policy_service.delete_rule(
        policy_set_id=policy_set_id,
        rule_id=rule_id,
        actor_id=current_user.id,
        correlation_id=correlation_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.commit()

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data={"message": "Rule deleted", "rule_id": rule_id}
    )


# ============== Group Endpoints ==============

@router.get("", response_model=CorrelatedResponse[GroupListResponse])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """List all groups (admin) or user's groups."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    address_book = AddressBookService(db, audit)

    if current_user.role.value == "ADMIN":
        groups = await group_service.list_groups()
    else:
        groups = await group_service.get_user_groups(current_user.id)

    # Build response with counts
    group_responses = []
    for g in groups:
        member_count = await group_service.get_group_member_count(g.id)
        allowlist_count = await address_book.get_allowlist_count(g.id)
        denylist_count = await address_book.get_denylist_count(g.id)

        # Get policy info if assigned
        policy_set_id = None
        policy_set_name = None
        if g.policy_assignment:
            policy_set_id = g.policy_assignment.policy_set_id
            # Load policy set name
            policy_service = PolicySetService(db, audit)
            ps = await policy_service.get_policy_set(policy_set_id)
            if ps:
                policy_set_name = f"{ps.name} v{ps.version}"

        group_responses.append(GroupResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            is_default=g.is_default,
            member_count=member_count,
            allowlist_count=allowlist_count,
            denylist_count=denylist_count,
            policy_set_id=policy_set_id,
            policy_set_name=policy_set_name,
            created_at=g.created_at,
        ))

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=GroupListResponse(groups=group_responses, total=len(group_responses))
    )


@router.get("/{group_id}", response_model=CorrelatedResponse[GroupResponse])
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Get group details."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    address_book = AddressBookService(db, audit)

    group = await group_service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check access: admin or member
    if current_user.role.value != "ADMIN":
        is_member = await group_service.is_member(group_id, current_user.id)
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this group")

    member_count = await group_service.get_group_member_count(group_id)
    allowlist_count = await address_book.get_allowlist_count(group_id)
    denylist_count = await address_book.get_denylist_count(group_id)

    policy_set_id = None
    policy_set_name = None
    if group.policy_assignment:
        policy_set_id = group.policy_assignment.policy_set_id
        policy_service = PolicySetService(db, audit)
        ps = await policy_service.get_policy_set(policy_set_id)
        if ps:
            policy_set_name = f"{ps.name} v{ps.version}"

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            is_default=group.is_default,
            member_count=member_count,
            allowlist_count=allowlist_count,
            denylist_count=denylist_count,
            policy_set_id=policy_set_id,
            policy_set_name=policy_set_name,
            created_at=group.created_at,
        )
    )


@router.post("", response_model=CorrelatedResponse[GroupResponse])
async def create_group(
    data: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Create a new group (admin only)."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)

    try:
        group = await group_service.create_group(
            name=data.name,
            description=data.description,
            is_default=data.is_default,
            created_by=current_user.id,
            correlation_id=correlation_id,
        )
        await db.commit()

        return CorrelatedResponse(
            correlation_id=correlation_id,
            data=GroupResponse(
                id=group.id,
                name=group.name,
                description=group.description,
                is_default=group.is_default,
                member_count=0,
                allowlist_count=0,
                denylist_count=0,
                policy_set_id=None,
                policy_set_name=None,
                created_at=group.created_at,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============== Address Book Endpoints ==============

@router.get("/{group_id}/addresses", response_model=CorrelatedResponse[AddressBookListResponse])
async def list_addresses(
    group_id: str,
    kind: Optional[AddressKind] = Query(None, description="Filter by kind (ALLOW or DENY)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """List addresses in group's address book."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    address_book = AddressBookService(db, audit)

    # Check group exists and user has access
    group = await group_service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if current_user.role.value != "ADMIN":
        is_member = await group_service.is_member(group_id, current_user.id)
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this group")

    entries = await address_book.list_addresses(group_id, kind)
    allowlist_count = await address_book.get_allowlist_count(group_id)
    denylist_count = await address_book.get_denylist_count(group_id)

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=AddressBookListResponse(
            entries=[AddressBookEntryResponse(
                id=e.id,
                address=e.address,
                kind=e.kind,
                label=e.label,
                created_at=e.created_at,
            ) for e in entries],
            total=len(entries),
            allowlist_count=allowlist_count,
            denylist_count=denylist_count,
        )
    )


@router.post("/{group_id}/addresses", response_model=CorrelatedResponse[AddressBookEntryResponse])
async def add_address(
    group_id: str,
    data: AddressBookEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Add address to group's address book (admin only)."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    address_book = AddressBookService(db, audit)

    group = await group_service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    entry = await address_book.add_address(
        group_id=group_id,
        address=data.address,
        kind=data.kind,
        label=data.label,
        created_by=current_user.id,
        correlation_id=correlation_id,
    )
    await db.commit()

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=AddressBookEntryResponse(
            id=entry.id,
            address=entry.address,
            kind=entry.kind,
            label=entry.label,
            created_at=entry.created_at,
        )
    )


@router.delete("/{group_id}/addresses/{address}")
async def remove_address(
    group_id: str,
    address: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Remove address from group's address book (admin only)."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    address_book = AddressBookService(db, audit)

    group = await group_service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    removed = await address_book.remove_address(
        group_id=group_id,
        address=address,
        actor_id=current_user.id,
        correlation_id=correlation_id,
    )
    await db.commit()

    if not removed:
        raise HTTPException(status_code=404, detail="Address not found in address book")

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data={"message": "Address removed", "address": address}
    )


@router.get("/{group_id}/addresses/check/{address}", response_model=CorrelatedResponse[AddressCheckResponse])
async def check_address(
    group_id: str,
    address: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Check if address is in allowlist or denylist."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    address_book = AddressBookService(db, audit)

    group = await group_service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if current_user.role.value != "ADMIN":
        is_member = await group_service.is_member(group_id, current_user.id)
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this group")

    status, label = await address_book.check_address(group_id, address)

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=AddressCheckResponse(
            address=address.lower(),
            status=status,
            label=label,
        )
    )


# ============== Group Policy Assignment Endpoints ==============

@router.post("/{group_id}/policy", response_model=CorrelatedResponse[GroupResponse])
async def assign_policy(
    group_id: str,
    data: PolicyAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    correlation_id: str = Depends(get_correlation_id),
):
    """Assign a policy set to a group (admin only)."""
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    policy_service = PolicySetService(db, audit)
    address_book = AddressBookService(db, audit)

    group = await group_service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    ps = await policy_service.get_policy_set(data.policy_set_id)
    if not ps:
        raise HTTPException(status_code=404, detail="Policy set not found")

    await policy_service.assign_to_group(
        group_id=group_id,
        policy_set_id=data.policy_set_id,
        assigned_by=current_user.id,
        correlation_id=correlation_id,
    )
    await db.commit()

    # Refresh group to get updated assignment
    group = await group_service.get_group(group_id)
    member_count = await group_service.get_group_member_count(group_id)
    allowlist_count = await address_book.get_allowlist_count(group_id)
    denylist_count = await address_book.get_denylist_count(group_id)

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=GroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            is_default=group.is_default,
            member_count=member_count,
            allowlist_count=allowlist_count,
            denylist_count=denylist_count,
            policy_set_id=data.policy_set_id,
            policy_set_name=f"{ps.name} v{ps.version}",
            created_at=group.created_at,
        )
    )


@router.post("/{group_id}/policy/preview", response_model=CorrelatedResponse[PolicyEvalPreviewResponse])
async def preview_policy_evaluation(
    group_id: str,
    data: PolicyEvalPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """
    Preview policy evaluation for an address without creating a transaction.

    Useful for UI to show what would happen before user submits.
    """
    audit = AuditService(db)
    group_service = GroupService(db, audit)
    address_book = AddressBookService(db, audit)

    group = await group_service.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if current_user.role.value != "ADMIN":
        is_member = await group_service.is_member(group_id, current_user.id)
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this group")

    # Create policy engine and evaluate
    policy_engine = PolicyEngineV2(db, audit, group_service, address_book)

    # We need a dummy wallet for evaluation - use None and handle in engine
    # For preview, we just need address book lookup and rule matching
    from app.models.wallet import Wallet

    result = await policy_engine.evaluate(
        user_id=current_user.id,
        to_address=data.to_address,
        amount=Decimal(data.amount) / Decimal(10**18),  # Convert wei to ETH
        asset=data.asset,
        wallet=None,  # Preview mode - no actual wallet
        correlation_id=correlation_id,
    )

    return CorrelatedResponse(
        correlation_id=correlation_id,
        data=PolicyEvalPreviewResponse(
            decision=result.decision,
            allowed=result.allowed,
            matched_rules=result.matched_rules,
            reasons=result.reasons,
            kyt_required=result.kyt_required,
            approval_required=result.approval_required,
            approval_count=result.approval_count,
            address_status=result.address_status,
            address_label=result.address_label,
            policy_version=result.policy_version,
        )
    )
