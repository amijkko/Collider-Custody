"""Seed default Retail group with tiered policy

Revision ID: 004_seed_retail_group
Revises: 003_add_groups_and_policies
Create Date: 2026-01-24

This migration creates the default "Retail" group required by PRD BR-AUTH-RET-02.
All new users are automatically enrolled in this group (BR-AUTH-RET-01).

The Retail policy implements tiered rules:
- RET-01: Micropayments ≤0.001 ETH - no KYT, no approval
- RET-02: Large transfers >0.001 ETH - KYT + approval required
- RET-03: Denylist addresses - immediate block
"""
from typing import Sequence, Union
from datetime import datetime
import hashlib
import json

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed UUIDs for idempotent seeding
RETAIL_GROUP_ID = "00000000-0000-0000-0000-000000000001"
RETAIL_POLICY_SET_ID = "00000000-0000-0000-0000-000000000002"
RETAIL_RULE_01_ID = "00000000-0000-0000-0000-000000000003"
RETAIL_RULE_02_ID = "00000000-0000-0000-0000-000000000004"
RETAIL_RULE_03_ID = "00000000-0000-0000-0000-000000000005"
GROUP_POLICY_ID = "00000000-0000-0000-0000-000000000006"


def compute_snapshot_hash(rules: list) -> str:
    """Compute SHA256 hash of policy rules for audit trail."""
    content = json.dumps(rules, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def upgrade() -> None:
    """Create default Retail group with tiered policy."""
    now = datetime.utcnow().isoformat()

    # Define the rules for hash computation
    rules_data = [
        {
            "rule_id": "RET-01",
            "priority": 10,
            "conditions": {"amount_lte": "0.001", "to_address_in": "allowlist"},
            "decision": "ALLOW",
            "kyt_required": False,
            "approval_required": False,
        },
        {
            "rule_id": "RET-02",
            "priority": 20,
            "conditions": {"amount_gt": "0.001", "to_address_in": "allowlist"},
            "decision": "ALLOW",
            "kyt_required": True,
            "approval_required": True,
        },
        {
            "rule_id": "RET-03",
            "priority": 1,
            "conditions": {"to_address_in": "denylist"},
            "decision": "BLOCK",
            "kyt_required": False,
            "approval_required": False,
        }
    ]

    snapshot_hash = compute_snapshot_hash(rules_data)

    conn = op.get_bind()

    # Create Retail group
    conn.execute(
        sa.text("""
            INSERT INTO groups (id, name, description, is_default, created_at, updated_at)
            VALUES (:id, :name, :description, :is_default, :created_at, :updated_at)
            ON CONFLICT (name) DO UPDATE SET is_default = true, updated_at = :updated_at
        """),
        {
            "id": RETAIL_GROUP_ID,
            "name": "Retail",
            "description": "Default group for retail users with tiered policy enforcement. All new users are automatically enrolled.",
            "is_default": True,
            "created_at": now,
            "updated_at": now,
        }
    )

    # Create Retail policy set
    conn.execute(
        sa.text("""
            INSERT INTO policy_sets (id, name, version, description, is_active, snapshot_hash, created_at, updated_at)
            VALUES (:id, :name, :version, :description, :is_active, :snapshot_hash, :created_at, :updated_at)
            ON CONFLICT (name, version) DO UPDATE SET
                is_active = true,
                snapshot_hash = :snapshot_hash,
                updated_at = :updated_at
        """),
        {
            "id": RETAIL_POLICY_SET_ID,
            "name": "Retail",
            "version": 1,
            "description": "Tiered policy for Retail users: micropayments auto-approve, large transfers require KYT+approval, denylist blocks",
            "is_active": True,
            "snapshot_hash": snapshot_hash,
            "created_at": now,
            "updated_at": now,
        }
    )

    # RET-03: Denylist block (highest priority - checked first)
    conn.execute(
        sa.text("""
            INSERT INTO policy_rules (id, policy_set_id, rule_id, priority, conditions, decision, kyt_required, approval_required, approval_count, description, created_at)
            VALUES (:id, :policy_set_id, :rule_id, :priority, :conditions, :decision, :kyt_required, :approval_required, :approval_count, :description, :created_at)
            ON CONFLICT (policy_set_id, rule_id) DO UPDATE SET
                priority = :priority,
                conditions = :conditions,
                decision = :decision,
                kyt_required = :kyt_required,
                approval_required = :approval_required,
                approval_count = :approval_count,
                description = :description
        """),
        {
            "id": RETAIL_RULE_03_ID,
            "policy_set_id": RETAIL_POLICY_SET_ID,
            "rule_id": "RET-03",
            "priority": 1,
            "conditions": json.dumps({"to_address_in": "denylist"}),
            "decision": "BLOCK",
            "kyt_required": False,
            "approval_required": False,
            "approval_count": 0,
            "description": "Denylist addresses - immediate block before any processing",
            "created_at": now,
        }
    )

    # RET-01: Micropayment allow
    conn.execute(
        sa.text("""
            INSERT INTO policy_rules (id, policy_set_id, rule_id, priority, conditions, decision, kyt_required, approval_required, approval_count, description, created_at)
            VALUES (:id, :policy_set_id, :rule_id, :priority, :conditions, :decision, :kyt_required, :approval_required, :approval_count, :description, :created_at)
            ON CONFLICT (policy_set_id, rule_id) DO UPDATE SET
                priority = :priority,
                conditions = :conditions,
                decision = :decision,
                kyt_required = :kyt_required,
                approval_required = :approval_required,
                approval_count = :approval_count,
                description = :description
        """),
        {
            "id": RETAIL_RULE_01_ID,
            "policy_set_id": RETAIL_POLICY_SET_ID,
            "rule_id": "RET-01",
            "priority": 10,
            "conditions": json.dumps({"amount_lte": "0.001", "to_address_in": "allowlist"}),
            "decision": "ALLOW",
            "kyt_required": False,
            "approval_required": False,
            "approval_count": 0,
            "description": "Micropayments ≤0.001 ETH to allowlisted addresses - auto-approve without KYT",
            "created_at": now,
        }
    )

    # RET-02: Large transfer with KYT+approval
    conn.execute(
        sa.text("""
            INSERT INTO policy_rules (id, policy_set_id, rule_id, priority, conditions, decision, kyt_required, approval_required, approval_count, description, created_at)
            VALUES (:id, :policy_set_id, :rule_id, :priority, :conditions, :decision, :kyt_required, :approval_required, :approval_count, :description, :created_at)
            ON CONFLICT (policy_set_id, rule_id) DO UPDATE SET
                priority = :priority,
                conditions = :conditions,
                decision = :decision,
                kyt_required = :kyt_required,
                approval_required = :approval_required,
                approval_count = :approval_count,
                description = :description
        """),
        {
            "id": RETAIL_RULE_02_ID,
            "policy_set_id": RETAIL_POLICY_SET_ID,
            "rule_id": "RET-02",
            "priority": 20,
            "conditions": json.dumps({"amount_gt": "0.001", "to_address_in": "allowlist"}),
            "decision": "ALLOW",
            "kyt_required": True,
            "approval_required": True,
            "approval_count": 1,
            "description": "Large transfers >0.001 ETH - require KYT screening and admin approval",
            "created_at": now,
        }
    )

    # Assign policy to group
    conn.execute(
        sa.text("""
            INSERT INTO group_policies (id, group_id, policy_set_id, assigned_at)
            VALUES (:id, :group_id, :policy_set_id, :assigned_at)
            ON CONFLICT (group_id) DO UPDATE SET
                policy_set_id = :policy_set_id,
                assigned_at = :assigned_at
        """),
        {
            "id": GROUP_POLICY_ID,
            "group_id": RETAIL_GROUP_ID,
            "policy_set_id": RETAIL_POLICY_SET_ID,
            "assigned_at": now,
        }
    )


def downgrade() -> None:
    """Remove Retail group seed data."""
    conn = op.get_bind()

    # Remove in reverse order
    conn.execute(
        sa.text("DELETE FROM group_policies WHERE id = :id"),
        {"id": GROUP_POLICY_ID}
    )
    conn.execute(
        sa.text("DELETE FROM policy_rules WHERE policy_set_id = :policy_set_id"),
        {"policy_set_id": RETAIL_POLICY_SET_ID}
    )
    conn.execute(
        sa.text("DELETE FROM policy_sets WHERE id = :id"),
        {"id": RETAIL_POLICY_SET_ID}
    )
    conn.execute(
        sa.text("DELETE FROM groups WHERE id = :id"),
        {"id": RETAIL_GROUP_ID}
    )
