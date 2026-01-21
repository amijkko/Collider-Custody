"""Policy engine service."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy, PolicyType, DailyVolume
from app.models.wallet import Wallet, WalletType
from app.models.tx_request import TxRequest
from app.models.audit import AuditEventType
from app.schemas.policy import PolicyCreate
from app.services.audit import AuditService


@dataclass
class PolicyEvalResult:
    """Result of policy evaluation."""
    allowed: bool
    requires_approval: bool
    required_approvals: int
    blocked_by: Optional[str] = None
    reason: Optional[str] = None
    evaluated_policies: List[str] = None
    
    def __post_init__(self):
        if self.evaluated_policies is None:
            self.evaluated_policies = []


class PolicyService:
    """Service for policy management and evaluation."""
    
    def __init__(self, db: AsyncSession, audit: AuditService):
        self.db = db
        self.audit = audit
    
    async def create_policy(
        self,
        policy_data: PolicyCreate,
        created_by: str,
        correlation_id: str
    ) -> Policy:
        """Create a new policy."""
        policy = Policy(
            id=str(uuid4()),
            name=policy_data.name,
            policy_type=policy_data.policy_type,
            address=policy_data.address.lower() if policy_data.address else None,
            token=policy_data.token.lower() if policy_data.token else None,
            wallet_id=policy_data.wallet_id,
            wallet_type=policy_data.wallet_type,
            limit_amount=policy_data.limit_amount,
            required_approvals=policy_data.required_approvals,
            config=policy_data.config,
            is_active=policy_data.is_active,
            created_by=created_by
        )
        
        self.db.add(policy)
        await self.db.flush()
        
        # Log audit event
        await self.audit.log_event(
            event_type=AuditEventType.POLICY_CREATED,
            correlation_id=correlation_id,
            actor_id=created_by,
            entity_type="POLICY",
            entity_id=policy.id,
            payload={
                "name": policy.name,
                "policy_type": policy.policy_type.value,
                "wallet_type": policy.wallet_type,
                "limit_amount": str(policy.limit_amount) if policy.limit_amount else None
            }
        )
        
        return policy
    
    async def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Get policy by ID."""
        result = await self.db.execute(
            select(Policy).where(Policy.id == policy_id)
        )
        return result.scalar_one_or_none()
    
    async def list_policies(
        self,
        policy_type: Optional[PolicyType] = None,
        is_active: bool = True,
        limit: int = 100
    ) -> List[Policy]:
        """List policies."""
        query = select(Policy).where(Policy.is_active == is_active)
        
        if policy_type:
            query = query.where(Policy.policy_type == policy_type)
        
        query = query.order_by(Policy.created_at.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def evaluate(
        self,
        tx_request: TxRequest,
        wallet: Wallet,
        correlation_id: str,
        actor_id: Optional[str] = None
    ) -> PolicyEvalResult:
        """
        Evaluate all applicable policies for a transaction.
        Returns whether tx is allowed, requires approval, etc.
        """
        evaluated = []
        requires_approval = False
        required_approvals = 0
        
        # Get all active policies
        result = await self.db.execute(
            select(Policy).where(Policy.is_active == True)
        )
        policies = list(result.scalars().all())
        
        for policy in policies:
            # Check address denylist
            if policy.policy_type == PolicyType.ADDRESS_DENYLIST:
                if policy.address and policy.address == tx_request.to_address.lower():
                    await self._log_evaluation(
                        tx_request.id, correlation_id, actor_id,
                        evaluated, False, policy.name, "Recipient address is on denylist"
                    )
                    return PolicyEvalResult(
                        allowed=False,
                        requires_approval=False,
                        required_approvals=0,
                        blocked_by=policy.name,
                        reason="Recipient address is on denylist",
                        evaluated_policies=evaluated
                    )
                evaluated.append(f"{policy.name}: PASS")
            
            # Check token denylist
            elif policy.policy_type == PolicyType.TOKEN_DENYLIST:
                if policy.token and policy.token == tx_request.asset.lower():
                    await self._log_evaluation(
                        tx_request.id, correlation_id, actor_id,
                        evaluated, False, policy.name, "Asset/token is on denylist"
                    )
                    return PolicyEvalResult(
                        allowed=False,
                        requires_approval=False,
                        required_approvals=0,
                        blocked_by=policy.name,
                        reason="Asset/token is on denylist",
                        evaluated_policies=evaluated
                    )
                evaluated.append(f"{policy.name}: PASS")
            
            # Check per-tx limit
            elif policy.policy_type == PolicyType.TX_LIMIT:
                if self._policy_applies_to_wallet(policy, wallet):
                    if policy.limit_amount and tx_request.amount > policy.limit_amount:
                        await self._log_evaluation(
                            tx_request.id, correlation_id, actor_id,
                            evaluated, False, policy.name, 
                            f"Transaction amount {tx_request.amount} exceeds limit {policy.limit_amount}"
                        )
                        return PolicyEvalResult(
                            allowed=False,
                            requires_approval=False,
                            required_approvals=0,
                            blocked_by=policy.name,
                            reason=f"Transaction amount exceeds per-tx limit of {policy.limit_amount}",
                            evaluated_policies=evaluated
                        )
                    evaluated.append(f"{policy.name}: PASS")
            
            # Check daily limit
            elif policy.policy_type == PolicyType.DAILY_LIMIT:
                if self._policy_applies_to_wallet(policy, wallet):
                    daily_total = await self._get_daily_volume(
                        tx_request.wallet_id, 
                        tx_request.asset
                    )
                    projected = daily_total + tx_request.amount
                    
                    if policy.limit_amount and projected > policy.limit_amount:
                        await self._log_evaluation(
                            tx_request.id, correlation_id, actor_id,
                            evaluated, False, policy.name,
                            f"Daily volume {projected} would exceed limit {policy.limit_amount}"
                        )
                        return PolicyEvalResult(
                            allowed=False,
                            requires_approval=False,
                            required_approvals=0,
                            blocked_by=policy.name,
                            reason=f"Transaction would exceed daily limit of {policy.limit_amount}",
                            evaluated_policies=evaluated
                        )
                    evaluated.append(f"{policy.name}: PASS")
            
            # Check approval requirements
            elif policy.policy_type == PolicyType.APPROVAL_REQUIRED:
                if self._policy_applies_to_wallet(policy, wallet):
                    requires_approval = True
                    required_approvals = max(required_approvals, policy.required_approvals)
                    evaluated.append(f"{policy.name}: REQUIRES {policy.required_approvals} APPROVALS")
        
        # Default: TREASURY wallets require 2-of-3 approval
        if wallet.wallet_type == WalletType.TREASURY and not requires_approval:
            requires_approval = True
            required_approvals = max(required_approvals, 2)
            evaluated.append("DEFAULT_TREASURY_RULE: REQUIRES 2 APPROVALS")
        
        await self._log_evaluation(
            tx_request.id, correlation_id, actor_id,
            evaluated, True, None, None, requires_approval, required_approvals
        )
        
        return PolicyEvalResult(
            allowed=True,
            requires_approval=requires_approval,
            required_approvals=required_approvals,
            evaluated_policies=evaluated
        )
    
    def _policy_applies_to_wallet(self, policy: Policy, wallet: Wallet) -> bool:
        """Check if policy applies to specific wallet."""
        # Check specific wallet ID
        if policy.wallet_id and policy.wallet_id == wallet.id:
            return True
        # Check wallet type
        if policy.wallet_type and policy.wallet_type == wallet.wallet_type.value:
            return True
        # Global policy (no wallet restrictions)
        if not policy.wallet_id and not policy.wallet_type:
            return True
        return False
    
    async def _get_daily_volume(self, wallet_id: str, asset: str) -> Decimal:
        """Get today's transaction volume for a wallet."""
        today = date.today()
        
        result = await self.db.execute(
            select(DailyVolume)
            .where(DailyVolume.wallet_id == wallet_id)
            .where(DailyVolume.date == today)
            .where(DailyVolume.asset == asset)
        )
        volume = result.scalar_one_or_none()
        
        return volume.total_amount if volume else Decimal("0")
    
    async def update_daily_volume(
        self,
        wallet_id: str,
        asset: str,
        amount: Decimal
    ):
        """Update daily volume after successful transaction."""
        today = date.today()
        
        result = await self.db.execute(
            select(DailyVolume)
            .where(DailyVolume.wallet_id == wallet_id)
            .where(DailyVolume.date == today)
            .where(DailyVolume.asset == asset)
        )
        volume = result.scalar_one_or_none()
        
        if volume:
            volume.total_amount += amount
            volume.tx_count += 1
        else:
            volume = DailyVolume(
                id=str(uuid4()),
                wallet_id=wallet_id,
                date=today,
                asset=asset,
                total_amount=amount,
                tx_count=1
            )
            self.db.add(volume)
        
        await self.db.flush()
    
    async def _log_evaluation(
        self,
        tx_request_id: str,
        correlation_id: str,
        actor_id: Optional[str],
        evaluated: List[str],
        allowed: bool,
        blocked_by: Optional[str] = None,
        reason: Optional[str] = None,
        requires_approval: bool = False,
        required_approvals: int = 0
    ):
        """Log policy evaluation to audit."""
        await self.audit.log_event(
            event_type=AuditEventType.TX_POLICY_EVALUATED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_type="SYSTEM",
            entity_type="TX_REQUEST",
            entity_id=tx_request_id,
            payload={
                "allowed": allowed,
                "requires_approval": requires_approval,
                "required_approvals": required_approvals,
                "blocked_by": blocked_by,
                "reason": reason,
                "evaluated_policies": evaluated
            }
        )

