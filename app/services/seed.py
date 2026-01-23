"""Seed data for demo scenarios."""
import asyncio
import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupAddressBook, AddressKind
from app.models.policy_set import (
    PolicySet, PolicyRule, PolicyDecision,
    RETAIL_GROUP_ID, RETAIL_POLICY_SET_ID,
)
from app.models.audit import AuditEventType
from app.services.audit import AuditService
from app.services.group import GroupService
from app.services.address_book import AddressBookService
from app.services.policy_v2 import PolicySetService


logger = logging.getLogger(__name__)


async def seed_retail_group(db: AsyncSession, audit: AuditService) -> Group:
    """
    Create or get the default Retail group.

    The Retail group is the default group for all new users.
    """
    # Check if already exists
    result = await db.execute(
        select(Group).where(Group.id == RETAIL_GROUP_ID)
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(f"Retail group already exists: {existing.id}")
        return existing

    # Create Retail group
    group = Group(
        id=RETAIL_GROUP_ID,
        name="Retail",
        description="Default group for retail users. Auto-enrolled on signup.",
        is_default=True,
    )
    db.add(group)
    await db.flush()

    await audit.log_event(
        event_type=AuditEventType.GROUP_CREATED,
        correlation_id="seed-retail-group",
        actor_type="SYSTEM",
        entity_type="GROUP",
        entity_id=group.id,
        payload={
            "name": group.name,
            "description": group.description,
            "is_default": True,
            "seeded": True,
        }
    )

    logger.info(f"Created Retail group: {group.id}")
    return group


async def seed_retail_policy(db: AsyncSession, audit: AuditService) -> PolicySet:
    """
    Create the Retail Policy v3 with tiered rules.

    Rules:
    - RET-01: Micropayments (≤0.001 ETH) to allowlist - no KYT, no approval
    - RET-02: Large transfers (>0.001 ETH) to allowlist - KYT + approval required
    - RET-03: Denylist - block immediately
    """
    # Check if already exists
    result = await db.execute(
        select(PolicySet).where(PolicySet.id == RETAIL_POLICY_SET_ID)
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(f"Retail policy set already exists: {existing.id}")
        return existing

    # Create policy set
    policy_set = PolicySet(
        id=RETAIL_POLICY_SET_ID,
        name="Retail Policy",
        version=3,
        description="Tiered policy for retail users with micropayment fast-track",
        is_active=True,
    )
    db.add(policy_set)
    await db.flush()

    # RET-03: Denylist block (highest priority - checked first)
    rule_deny = PolicyRule(
        policy_set_id=RETAIL_POLICY_SET_ID,
        rule_id="RET-03",
        priority=1,  # Highest priority
        conditions={"address_in": "denylist"},
        decision=PolicyDecision.BLOCK,
        kyt_required=False,
        approval_required=False,
        description="Block all transfers to denylisted addresses",
    )
    db.add(rule_deny)

    # RET-01: Micropayment allow (second priority)
    rule_micro = PolicyRule(
        policy_set_id=RETAIL_POLICY_SET_ID,
        rule_id="RET-01",
        priority=10,
        conditions={
            "amount_lte": "0.001",
            "address_in": "allowlist",
        },
        decision=PolicyDecision.ALLOW,
        kyt_required=False,
        approval_required=False,
        description="Micropayments (≤0.001 ETH) to allowlisted addresses - no KYT, no approval",
    )
    db.add(rule_micro)

    # RET-02: Large transfer (lower priority)
    rule_large = PolicyRule(
        policy_set_id=RETAIL_POLICY_SET_ID,
        rule_id="RET-02",
        priority=20,
        conditions={
            "amount_gt": "0.001",
            "address_in": "allowlist",
        },
        decision=PolicyDecision.ALLOW,
        kyt_required=True,
        approval_required=True,
        approval_count=1,
        description="Large transfers (>0.001 ETH) to allowlisted addresses - require KYT + 1 admin approval",
    )
    db.add(rule_large)

    await db.flush()

    # Update snapshot hash
    result = await db.execute(
        select(PolicySet)
        .where(PolicySet.id == RETAIL_POLICY_SET_ID)
    )
    policy_set = result.scalar_one()

    # Manually load rules for hash computation
    rules_result = await db.execute(
        select(PolicyRule).where(PolicyRule.policy_set_id == RETAIL_POLICY_SET_ID)
    )
    policy_set.rules = list(rules_result.scalars().all())
    policy_set.update_snapshot_hash()
    await db.flush()

    await audit.log_event(
        event_type=AuditEventType.POLICY_SET_CREATED,
        correlation_id="seed-retail-policy",
        actor_type="SYSTEM",
        entity_type="POLICY_SET",
        entity_id=policy_set.id,
        payload={
            "name": policy_set.name,
            "version": policy_set.version,
            "rules": ["RET-01", "RET-02", "RET-03"],
            "seeded": True,
        }
    )

    logger.info(f"Created Retail Policy v{policy_set.version}: {policy_set.id}")
    return policy_set


async def seed_group_policy_assignment(db: AsyncSession, audit: AuditService) -> None:
    """Assign Retail Policy to Retail group."""
    from app.models.group import GroupPolicy

    # Check if already assigned
    result = await db.execute(
        select(GroupPolicy).where(GroupPolicy.group_id == RETAIL_GROUP_ID)
    )
    existing = result.scalar_one_or_none()

    if existing:
        logger.info("Retail policy already assigned to Retail group")
        return

    assignment = GroupPolicy(
        group_id=RETAIL_GROUP_ID,
        policy_set_id=RETAIL_POLICY_SET_ID,
    )
    db.add(assignment)
    await db.flush()

    await audit.log_event(
        event_type=AuditEventType.POLICY_SET_ASSIGNED,
        correlation_id="seed-policy-assignment",
        actor_type="SYSTEM",
        entity_type="GROUP",
        entity_id=RETAIL_GROUP_ID,
        entity_refs={"policy_set_id": RETAIL_POLICY_SET_ID},
        payload={"seeded": True}
    )

    logger.info("Assigned Retail Policy to Retail group")


async def seed_demo_addresses(
    db: AsyncSession,
    audit: AuditService,
    group_id: str = RETAIL_GROUP_ID,
) -> None:
    """
    Add sample addresses to the Retail group's address book.

    Includes:
    - Known exchange addresses (allowlist)
    - Known risky addresses (denylist)
    """
    address_book = AddressBookService(db, audit)

    # Allowlist - known safe addresses
    allowlist_addresses = [
        ("0x28c6c06298d514db089934071355e5743bf21d60", "Binance Hot Wallet"),
        ("0x21a31ee1afc51d94c2efccaa2092ad1028285549", "Binance"),
        ("0xdfd5293d8e347dfe59e90efd55b2956a1343963d", "Binance"),
        ("0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503", "Binance"),
        ("0x503828976d22510aad0201ac7ec88293211d23da", "Coinbase"),
        ("0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43", "Coinbase"),
        ("0x71660c4005ba85c37ccec55d0c4493e66fe775d3", "Coinbase"),
        ("0x2910543af39aba0cd09dbb2d50200b3e800a63d2", "Kraken"),
        ("0x0d0707963952f2fba59dd06f2b425ace40b492fe", "Gate.io"),
        ("0x1111111111111111111111111111111111111111", "Test Allowlisted Address"),
    ]

    for address, label in allowlist_addresses:
        await address_book.add_address(
            group_id=group_id,
            address=address,
            kind=AddressKind.ALLOW,
            label=label,
            correlation_id="seed-demo-addresses",
        )

    # Denylist - known risky addresses
    denylist_addresses = [
        ("0x8589427373d6d84e98730d7795d8f6f8731fda16", "Tornado Cash (OFAC Sanctioned)"),
        ("0x722122df12d4e14e13ac3b6895a86e84145b6967", "Tornado Cash Router (OFAC)"),
        ("0xd90e2f925da726b50c4ed8d0fb90ad053324f31b", "OFAC Sanctioned"),
        ("0x000000000000000000000000000000000000dead", "Burn Address / Suspicious"),
        ("0xbad0000000000000000000000000000000000bad", "Known Mixer"),
        ("0x0000000000000000000000000000000000000000", "Null Address"),
    ]

    for address, label in denylist_addresses:
        await address_book.add_address(
            group_id=group_id,
            address=address,
            kind=AddressKind.DENY,
            label=label,
            correlation_id="seed-demo-addresses",
        )

    logger.info(f"Seeded {len(allowlist_addresses)} allowlist + {len(denylist_addresses)} denylist addresses")


async def seed_all(db: AsyncSession) -> None:
    """
    Run all seed operations.

    This is idempotent - safe to run multiple times.
    """
    audit = AuditService(db)

    logger.info("Starting seed operations...")

    # 1. Create Retail group
    await seed_retail_group(db, audit)

    # 2. Create Retail Policy
    await seed_retail_policy(db, audit)

    # 3. Assign policy to group
    await seed_group_policy_assignment(db, audit)

    # 4. Add demo addresses
    await seed_demo_addresses(db, audit)

    await db.commit()
    logger.info("Seed operations completed successfully")


async def run_seeds():
    """Entry point for running seeds from command line."""
    from app.database import async_session_maker

    async with async_session_maker() as db:
        await seed_all(db)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_seeds())
