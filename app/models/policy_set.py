"""Policy set models for versioned policy rules."""
import enum
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import String, Enum, DateTime, Boolean, ForeignKey, Text, Integer, Numeric, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PolicyDecision(str, enum.Enum):
    """Policy rule decision."""
    ALLOW = "ALLOW"      # Allow and continue
    BLOCK = "BLOCK"      # Block immediately
    CONTINUE = "CONTINUE"  # Continue to next rule


class PolicySet(Base):
    """Versioned collection of policy rules."""
    __tablename__ = "policy_sets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Hash of rules for integrity verification
    snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    rules: Mapped[List["PolicyRule"]] = relationship(
        "PolicyRule", back_populates="policy_set", lazy="selectin",
        cascade="all, delete-orphan", order_by="PolicyRule.priority"
    )

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_policy_set_version"),
        Index("ix_policy_sets_name_active", "name", "is_active"),
    )

    def compute_snapshot_hash(self) -> str:
        """Compute SHA256 hash of rules for integrity verification."""
        rules_data = [
            {
                "rule_id": r.rule_id,
                "priority": r.priority,
                "conditions": r.conditions,
                "decision": r.decision.value,
                "kyt_required": r.kyt_required,
                "approval_required": r.approval_required,
                "approval_count": r.approval_count,
            }
            for r in sorted(self.rules, key=lambda x: x.priority)
        ]
        rules_json = json.dumps(rules_data, sort_keys=True, default=str)
        return hashlib.sha256(rules_json.encode()).hexdigest()

    def update_snapshot_hash(self) -> None:
        """Update the snapshot hash based on current rules."""
        self.snapshot_hash = self.compute_snapshot_hash()

    @property
    def version_string(self) -> str:
        """Get version string like 'Retail Policy v3'."""
        return f"{self.name} v{self.version}"

    def __repr__(self) -> str:
        return f"<PolicySet {self.name} v{self.version}>"


class PolicyRule(Base):
    """Individual policy rule within a policy set."""
    __tablename__ = "policy_rules"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    policy_set_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("policy_sets.id", ondelete="CASCADE"), nullable=False
    )

    # Rule identification
    rule_id: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., RET-01
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Conditions (JSONB for flexibility)
    # Examples:
    # {"amount_lte": "0.001", "address_in": "allowlist"}
    # {"amount_gt": "0.001", "address_in": "allowlist"}
    # {"address_in": "denylist"}
    conditions: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Decision
    decision: Mapped[PolicyDecision] = mapped_column(
        Enum(PolicyDecision), nullable=False, default=PolicyDecision.CONTINUE
    )

    # Control requirements
    kyt_required: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_count: Mapped[int] = mapped_column(Integer, default=0)

    # Documentation
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    policy_set: Mapped["PolicySet"] = relationship("PolicySet", back_populates="rules")

    __table_args__ = (
        UniqueConstraint("policy_set_id", "rule_id", name="uq_policy_rule_id"),
        Index("ix_policy_rules_priority", "policy_set_id", "priority"),
    )

    def matches(self, amount: Decimal, address_status: str) -> bool:
        """
        Check if this rule matches the given transaction parameters.

        Args:
            amount: Transaction amount in ETH
            address_status: 'allowlist', 'denylist', or 'unknown'

        Returns:
            True if rule conditions match
        """
        conditions = self.conditions

        # Check amount conditions
        if "amount_lte" in conditions:
            if amount > Decimal(str(conditions["amount_lte"])):
                return False

        if "amount_lt" in conditions:
            if amount >= Decimal(str(conditions["amount_lt"])):
                return False

        if "amount_gte" in conditions:
            if amount < Decimal(str(conditions["amount_gte"])):
                return False

        if "amount_gt" in conditions:
            if amount <= Decimal(str(conditions["amount_gt"])):
                return False

        # Check address conditions (support both 'address_in' and 'to_address_in')
        required_status = conditions.get("address_in") or conditions.get("to_address_in")
        if required_status:
            if address_status != required_status:
                return False

        forbidden_status = conditions.get("address_not_in") or conditions.get("to_address_not_in")
        if forbidden_status:
            if address_status == forbidden_status:
                return False

        return True

    def __repr__(self) -> str:
        return f"<PolicyRule {self.rule_id} priority={self.priority}>"


# Constants for well-known IDs (used in seeds)
RETAIL_GROUP_ID = "00000000-0000-0000-0000-000000000001"
RETAIL_POLICY_SET_ID = "00000000-0000-0000-0000-000000000010"
