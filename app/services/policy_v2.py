"""Policy Engine v2 with tiered rules and explainability."""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Any, Dict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.group import Group, GroupPolicy
from app.models.policy_set import PolicySet, PolicyRule, PolicyDecision
from app.models.wallet import Wallet
from app.models.audit import AuditEventType
from app.services.audit import AuditService
from app.services.group import GroupService
from app.services.address_book import AddressBookService


@dataclass
class PolicyEvalResult:
    """Result of policy evaluation with full explainability."""

    # Decision
    decision: str  # 'ALLOW' or 'BLOCK'
    allowed: bool  # True if decision is ALLOW

    # Matched rules
    matched_rules: List[str] = field(default_factory=list)  # e.g., ['RET-01']
    reasons: List[str] = field(default_factory=list)  # Human-readable explanations

    # Control requirements (set by matching rule)
    kyt_required: bool = True
    approval_required: bool = False
    approval_count: int = 0

    # Policy metadata
    policy_version: str = ""  # e.g., "Retail Policy v3"
    policy_snapshot_hash: str = ""
    group_id: Optional[str] = None
    group_name: Optional[str] = None

    # Address status
    address_status: str = "unknown"  # 'allowlist', 'denylist', 'unknown'
    address_label: Optional[str] = None

    # Evaluation metadata
    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    evaluated_rules_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['evaluated_at'] = self.evaluated_at.isoformat()
        return result


class PolicyEngineV2:
    """
    Policy engine with tiered rules and explainability.

    Supports:
    - Group-based policy sets
    - Priority-ordered rule evaluation
    - Conditional KYT and approval requirements
    - Full explainability (matched rules, reasons, versions)
    """

    def __init__(
        self,
        db: AsyncSession,
        audit: AuditService,
        group_service: GroupService,
        address_book_service: AddressBookService,
    ):
        self.db = db
        self.audit = audit
        self.group_service = group_service
        self.address_book = address_book_service

    async def evaluate(
        self,
        user_id: str,
        to_address: str,
        amount: Decimal,
        asset: str,
        wallet: Wallet,
        tx_request_id: Optional[str] = None,
        correlation_id: str = "",
    ) -> PolicyEvalResult:
        """
        Evaluate policy for a transaction.

        Args:
            user_id: User initiating the transaction
            to_address: Recipient address
            amount: Transaction amount
            asset: Asset being transferred (e.g., 'ETH')
            wallet: Source wallet
            tx_request_id: Optional transaction request ID for logging
            correlation_id: Request correlation ID

        Returns:
            PolicyEvalResult with decision and explainability
        """
        # 1. Get user's primary group
        group = await self.group_service.get_user_primary_group(user_id)

        if not group:
            # No group - use default deny
            return PolicyEvalResult(
                decision='BLOCK',
                allowed=False,
                matched_rules=['NO_GROUP'],
                reasons=['User is not assigned to any group'],
                kyt_required=False,
                approval_required=False,
            )

        # 2. Get group's active policy set
        policy_set = await self._get_active_policy_set(group.id)

        if not policy_set:
            # No policy - default deny
            return PolicyEvalResult(
                decision='BLOCK',
                allowed=False,
                matched_rules=['NO_POLICY'],
                reasons=['Group has no active policy assigned'],
                group_id=group.id,
                group_name=group.name,
                kyt_required=False,
                approval_required=False,
            )

        # 3. Check address status in group's address book
        address_status, address_label = await self.address_book.check_address(
            group.id, to_address
        )

        # 4. Evaluate rules in priority order (lower priority = higher precedence)
        rules = sorted(policy_set.rules, key=lambda r: r.priority)

        for rule in rules:
            if rule.matches(amount, address_status):
                # Rule matched!
                result = PolicyEvalResult(
                    decision=rule.decision.value,
                    allowed=(rule.decision == PolicyDecision.ALLOW),
                    matched_rules=[rule.rule_id],
                    reasons=[rule.description or f"Matched rule {rule.rule_id}"],
                    kyt_required=rule.kyt_required,
                    approval_required=rule.approval_required,
                    approval_count=rule.approval_count,
                    policy_version=policy_set.version_string,
                    policy_snapshot_hash=policy_set.snapshot_hash or "",
                    group_id=group.id,
                    group_name=group.name,
                    address_status=address_status,
                    address_label=address_label,
                    evaluated_rules_count=rules.index(rule) + 1,
                )

                # Log evaluation
                await self._log_evaluation(
                    result=result,
                    tx_request_id=tx_request_id,
                    user_id=user_id,
                    to_address=to_address,
                    amount=amount,
                    correlation_id=correlation_id,
                )

                return result

        # 5. No rule matched - default behavior based on address status
        if address_status == 'denylist':
            result = PolicyEvalResult(
                decision='BLOCK',
                allowed=False,
                matched_rules=['DEFAULT_DENY'],
                reasons=['Address is in denylist (no explicit rule matched)'],
                kyt_required=False,
                approval_required=False,
                policy_version=policy_set.version_string,
                policy_snapshot_hash=policy_set.snapshot_hash or "",
                group_id=group.id,
                group_name=group.name,
                address_status=address_status,
                address_label=address_label,
                evaluated_rules_count=len(rules),
            )
        elif address_status == 'unknown':
            result = PolicyEvalResult(
                decision='BLOCK',
                allowed=False,
                matched_rules=['DEFAULT_UNKNOWN'],
                reasons=['Address is not in allowlist'],
                kyt_required=False,
                approval_required=False,
                policy_version=policy_set.version_string,
                policy_snapshot_hash=policy_set.snapshot_hash or "",
                group_id=group.id,
                group_name=group.name,
                address_status=address_status,
                address_label=address_label,
                evaluated_rules_count=len(rules),
            )
        else:
            # Allowlist but no matching rule - require full controls
            result = PolicyEvalResult(
                decision='ALLOW',
                allowed=True,
                matched_rules=['DEFAULT_ALLOW'],
                reasons=['Address is in allowlist (no specific rule matched, applying defaults)'],
                kyt_required=True,
                approval_required=True,
                approval_count=1,
                policy_version=policy_set.version_string,
                policy_snapshot_hash=policy_set.snapshot_hash or "",
                group_id=group.id,
                group_name=group.name,
                address_status=address_status,
                address_label=address_label,
                evaluated_rules_count=len(rules),
            )

        await self._log_evaluation(
            result=result,
            tx_request_id=tx_request_id,
            user_id=user_id,
            to_address=to_address,
            amount=amount,
            correlation_id=correlation_id,
        )

        return result

    async def _get_active_policy_set(self, group_id: str) -> Optional[PolicySet]:
        """Get the active policy set for a group."""
        result = await self.db.execute(
            select(PolicySet)
            .join(GroupPolicy)
            .options(selectinload(PolicySet.rules))
            .where(GroupPolicy.group_id == group_id)
            .where(PolicySet.is_active == True)
        )
        return result.scalar_one_or_none()

    async def _log_evaluation(
        self,
        result: PolicyEvalResult,
        tx_request_id: Optional[str],
        user_id: str,
        to_address: str,
        amount: Decimal,
        correlation_id: str,
    ) -> None:
        """Log policy evaluation to audit."""
        await self.audit.log_event(
            event_type=AuditEventType.TX_POLICY_EVALUATED,
            correlation_id=correlation_id,
            actor_id=user_id,
            actor_type="SYSTEM",
            entity_type="TX_REQUEST" if tx_request_id else "POLICY_EVAL",
            entity_id=tx_request_id or str(uuid4()),
            payload={
                "decision": result.decision,
                "matched_rules": result.matched_rules,
                "reasons": result.reasons,
                "kyt_required": result.kyt_required,
                "approval_required": result.approval_required,
                "approval_count": result.approval_count,
                "policy_version": result.policy_version,
                "policy_snapshot_hash": result.policy_snapshot_hash,
                "group_id": result.group_id,
                "group_name": result.group_name,
                "address_status": result.address_status,
                "to_address": to_address,
                "amount": str(amount),
            }
        )


class PolicySetService:
    """Service for managing policy sets and rules."""

    def __init__(self, db: AsyncSession, audit: AuditService):
        self.db = db
        self.audit = audit

    async def create_policy_set(
        self,
        name: str,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
        correlation_id: str = "",
    ) -> PolicySet:
        """Create a new policy set."""
        # Get max version for this name
        result = await self.db.execute(
            select(PolicySet.version)
            .where(PolicySet.name == name)
            .order_by(PolicySet.version.desc())
            .limit(1)
        )
        max_version = result.scalar() or 0

        policy_set = PolicySet(
            id=str(uuid4()),
            name=name,
            version=max_version + 1,
            description=description,
            created_by=created_by,
        )
        self.db.add(policy_set)
        await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.POLICY_SET_CREATED,
            correlation_id=correlation_id,
            actor_id=created_by,
            entity_type="POLICY_SET",
            entity_id=policy_set.id,
            payload={
                "name": name,
                "version": policy_set.version,
                "description": description,
            }
        )

        return policy_set

    async def get_policy_set(self, policy_set_id: str) -> Optional[PolicySet]:
        """Get a policy set by ID with rules loaded."""
        result = await self.db.execute(
            select(PolicySet)
            .options(selectinload(PolicySet.rules))
            .where(PolicySet.id == policy_set_id)
        )
        return result.scalar_one_or_none()

    async def add_rule(
        self,
        policy_set_id: str,
        rule_id: str,
        conditions: Dict[str, Any],
        decision: PolicyDecision,
        priority: int = 100,
        kyt_required: bool = True,
        approval_required: bool = False,
        approval_count: int = 0,
        description: Optional[str] = None,
        actor_id: Optional[str] = None,
        correlation_id: str = "",
    ) -> PolicyRule:
        """Add a rule to a policy set."""
        rule = PolicyRule(
            id=str(uuid4()),
            policy_set_id=policy_set_id,
            rule_id=rule_id,
            priority=priority,
            conditions=conditions,
            decision=decision,
            kyt_required=kyt_required,
            approval_required=approval_required,
            approval_count=approval_count,
            description=description,
        )
        self.db.add(rule)
        await self.db.flush()

        # Update policy set snapshot hash
        policy_set = await self.get_policy_set(policy_set_id)
        if policy_set:
            policy_set.update_snapshot_hash()
            await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.POLICY_RULE_ADDED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            entity_type="POLICY_SET",
            entity_id=policy_set_id,
            entity_refs={"rule_id": rule.id},
            payload={
                "rule_id": rule_id,
                "priority": priority,
                "conditions": conditions,
                "decision": decision.value,
                "kyt_required": kyt_required,
                "approval_required": approval_required,
            }
        )

        return rule

    async def assign_to_group(
        self,
        group_id: str,
        policy_set_id: str,
        assigned_by: Optional[str] = None,
        correlation_id: str = "",
    ) -> GroupPolicy:
        """Assign a policy set to a group."""
        from app.models.group import GroupPolicy

        # Check if group already has a policy
        result = await self.db.execute(
            select(GroupPolicy).where(GroupPolicy.group_id == group_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing assignment
            existing.policy_set_id = policy_set_id
            existing.assigned_by = assigned_by
            existing.assigned_at = datetime.utcnow()
            await self.db.flush()
            assignment = existing
        else:
            # Create new assignment
            assignment = GroupPolicy(
                id=str(uuid4()),
                group_id=group_id,
                policy_set_id=policy_set_id,
                assigned_by=assigned_by,
            )
            self.db.add(assignment)
            await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.POLICY_SET_ASSIGNED,
            correlation_id=correlation_id,
            actor_id=assigned_by,
            entity_type="GROUP",
            entity_id=group_id,
            entity_refs={"policy_set_id": policy_set_id},
            payload={
                "policy_set_id": policy_set_id,
            }
        )

        return assignment
