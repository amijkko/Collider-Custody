"""KYT (Know Your Transaction) mock service."""
from datetime import datetime
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.tx_request import KYTCase
from app.models.audit import AuditEventType
from app.services.audit import AuditService


class KYTResult:
    """KYT evaluation result."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


class KYTService:
    """Mock KYT service for transaction screening."""
    
    def __init__(self, db: AsyncSession, audit: AuditService):
        self.db = db
        self.audit = audit
        self.settings = get_settings()
    
    async def evaluate_outbound(
        self,
        address: str,
        tx_request_id: str,
        correlation_id: str,
        actor_id: Optional[str] = None
    ) -> Tuple[str, Optional[KYTCase]]:
        """
        Evaluate outbound transaction recipient.
        Returns (result, case) where case is created for REVIEW.
        """
        address_lower = address.lower()
        result = KYTResult.ALLOW
        case = None
        reason = None
        
        # Check blacklist
        if address_lower in self.settings.kyt_blacklist_addresses:
            result = KYTResult.BLOCK
            reason = "Address is on blacklist"
        # Check graylist
        elif address_lower in self.settings.kyt_graylist_addresses:
            result = KYTResult.REVIEW
            reason = "Address requires manual review"
        
        # Create case for REVIEW
        if result == KYTResult.REVIEW:
            case = KYTCase(
                id=str(uuid4()),
                address=address_lower,
                direction="OUTBOUND",
                reason=reason,
                status="PENDING"
            )
            self.db.add(case)
            await self.db.flush()
            
            # Log case creation
            await self.audit.log_event(
                event_type=AuditEventType.KYT_CASE_CREATED,
                correlation_id=correlation_id,
                actor_id=actor_id,
                actor_type="SYSTEM",
                entity_type="KYT_CASE",
                entity_id=case.id,
                entity_refs={"tx_request_id": tx_request_id},
                payload={
                    "address": address_lower,
                    "direction": "OUTBOUND",
                    "reason": reason
                }
            )
        
        # Log KYT evaluation
        await self.audit.log_event(
            event_type=AuditEventType.TX_KYT_EVALUATED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_type="SYSTEM",
            entity_type="TX_REQUEST",
            entity_id=tx_request_id,
            payload={
                "address": address_lower,
                "direction": "OUTBOUND",
                "result": result,
                "reason": reason,
                "case_id": case.id if case else None
            }
        )
        
        return result, case
    
    async def evaluate_inbound(
        self,
        from_address: str,
        to_wallet_id: str,
        tx_hash: str,
        correlation_id: str
    ) -> Tuple[str, Optional[KYTCase]]:
        """
        Evaluate inbound transaction sender.
        Returns (result, case) where case is created for REVIEW.
        """
        address_lower = from_address.lower()
        result = KYTResult.ALLOW
        case = None
        reason = None
        
        # Check blacklist
        if address_lower in self.settings.kyt_blacklist_addresses:
            result = KYTResult.BLOCK
            reason = "Sender address is on blacklist"
        # Check graylist
        elif address_lower in self.settings.kyt_graylist_addresses:
            result = KYTResult.REVIEW
            reason = "Sender address requires manual review"
        
        # Create case for REVIEW or BLOCK (for inbound we track both)
        if result in [KYTResult.REVIEW, KYTResult.BLOCK]:
            case = KYTCase(
                id=str(uuid4()),
                address=address_lower,
                direction="INBOUND",
                reason=reason,
                status="PENDING" if result == KYTResult.REVIEW else "RESOLVED_BLOCK"
            )
            self.db.add(case)
            await self.db.flush()
            
            # Log case creation
            await self.audit.log_event(
                event_type=AuditEventType.KYT_CASE_CREATED,
                correlation_id=correlation_id,
                actor_type="SYSTEM",
                entity_type="KYT_CASE",
                entity_id=case.id,
                entity_refs={"wallet_id": to_wallet_id, "tx_hash": tx_hash},
                payload={
                    "address": address_lower,
                    "direction": "INBOUND",
                    "reason": reason
                }
            )
        
        # Log evaluation
        await self.audit.log_event(
            event_type=AuditEventType.DEPOSIT_KYT_EVALUATED,
            correlation_id=correlation_id,
            actor_type="SYSTEM",
            entity_type="WALLET",
            entity_id=to_wallet_id,
            payload={
                "from_address": address_lower,
                "tx_hash": tx_hash,
                "result": result,
                "reason": reason,
                "case_id": case.id if case else None
            }
        )
        
        return result, case
    
    async def get_case(self, case_id: str) -> Optional[KYTCase]:
        """Get KYT case by ID."""
        result = await self.db.execute(
            select(KYTCase).where(KYTCase.id == case_id)
        )
        return result.scalar_one_or_none()
    
    async def list_cases(
        self,
        status: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """List KYT cases with optional filters."""
        query = select(KYTCase)
        
        if status:
            query = query.where(KYTCase.status == status)
        if direction:
            query = query.where(KYTCase.direction == direction)
        
        query = query.order_by(KYTCase.created_at.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def resolve_case(
        self,
        case_id: str,
        decision: str,
        resolved_by: str,
        correlation_id: str,
        comment: Optional[str] = None
    ) -> KYTCase:
        """Resolve a KYT case."""
        case = await self.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found")
        
        if case.status != "PENDING":
            raise ValueError(f"Case {case_id} is already resolved")
        
        case.status = f"RESOLVED_{decision}"  # RESOLVED_ALLOW or RESOLVED_BLOCK
        case.resolved_by = resolved_by
        case.resolved_at = datetime.utcnow()
        case.resolution_comment = comment
        
        await self.db.flush()
        
        # Log resolution
        await self.audit.log_event(
            event_type=AuditEventType.KYT_CASE_RESOLVED,
            correlation_id=correlation_id,
            actor_id=resolved_by,
            entity_type="KYT_CASE",
            entity_id=case_id,
            payload={
                "decision": decision,
                "comment": comment
            }
        )
        
        return case

