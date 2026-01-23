"""KYT (Know Your Transaction) service.

Supports:
1. Local blacklist/graylist checking (always enabled)
2. BitOK KYT API integration (optional, enabled via config)
"""
from datetime import datetime
import logging
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.tx_request import KYTCase
from app.models.audit import AuditEventType
from app.services.audit import AuditService
from app.services.bitok_integration import (
    get_bitok_integration,
    BitOKCheckResult,
    BitOKCheckResponse,
)


logger = logging.getLogger(__name__)


class KYTResult:
    """KYT evaluation result."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    UNCHECKED = "UNCHECKED"  # BitOK unavailable, passed with flag


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
        actor_id: Optional[str] = None,
        network: str = "ETH",
        from_address: Optional[str] = None,
        token_id: Optional[str] = None,
    ) -> Tuple[str, Optional[KYTCase]]:
        """
        Evaluate outbound transaction recipient.
        Returns (result, case) where case is created for REVIEW.

        Checks both local blacklist/graylist AND BitOK KYT (if enabled).
        The most restrictive result is used.
        """
        address_lower = address.lower()
        result = KYTResult.ALLOW
        case = None
        reason = None
        bitok_response: Optional[BitOKCheckResponse] = None

        # Step 1: Check local blacklist/graylist (instant)
        if address_lower in self.settings.kyt_blacklist_addresses:
            result = KYTResult.BLOCK
            reason = "Address is on blacklist"
        elif address_lower in self.settings.kyt_graylist_addresses:
            result = KYTResult.REVIEW
            reason = "Address requires manual review"

        # Step 2: BitOK check (if enabled and not already blocked)
        if result != KYTResult.BLOCK and self.settings.bitok_enabled:
            try:
                bitok = get_bitok_integration()
                bitok_response = await bitok.check_transfer_outbound(
                    network=network,
                    to_address=address_lower,
                    from_address=from_address or "",
                    token_id=token_id,
                    client_id=tx_request_id,
                )

                # Map BitOK result to KYT result
                bitok_result = self._bitok_to_kyt_result(bitok_response.result)

                # Use the more restrictive result
                if bitok_result == KYTResult.BLOCK:
                    result = KYTResult.BLOCK
                    reason = f"BitOK: {bitok_response.risk_level} risk ({bitok_response.error_message or 'high risk detected'})"
                elif bitok_result == KYTResult.REVIEW and result == KYTResult.ALLOW:
                    result = KYTResult.REVIEW
                    reason = f"BitOK: {bitok_response.risk_level} risk level requires review"
                elif bitok_result == KYTResult.UNCHECKED:
                    # BitOK unavailable - log but allow (with unchecked flag in audit)
                    logger.warning(f"BitOK check skipped for {address_lower}: {bitok_response.error_message}")

            except Exception as e:
                logger.exception(f"BitOK check failed for outbound to {address_lower}: {e}")
                # Continue with local-only result if BitOK fails

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
                    "reason": reason,
                    "bitok_transfer_id": bitok_response.transfer_id if bitok_response else None,
                    "bitok_risk_level": bitok_response.risk_level if bitok_response else None,
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
                "case_id": case.id if case else None,
                "bitok_enabled": self.settings.bitok_enabled,
                "bitok_transfer_id": bitok_response.transfer_id if bitok_response else None,
                "bitok_risk_level": bitok_response.risk_level if bitok_response else None,
                "bitok_cached": bitok_response.cached if bitok_response else None,
            }
        )

        return result, case

    def _bitok_to_kyt_result(self, bitok_result: BitOKCheckResult) -> str:
        """Convert BitOK result to KYT result."""
        mapping = {
            BitOKCheckResult.ALLOW: KYTResult.ALLOW,
            BitOKCheckResult.REVIEW: KYTResult.REVIEW,
            BitOKCheckResult.BLOCK: KYTResult.BLOCK,
            BitOKCheckResult.UNCHECKED: KYTResult.UNCHECKED,
            BitOKCheckResult.ERROR: KYTResult.UNCHECKED,
        }
        return mapping.get(bitok_result, KYTResult.REVIEW)
    
    async def evaluate_inbound(
        self,
        from_address: str,
        to_wallet_id: str,
        tx_hash: str,
        correlation_id: str,
        network: str = "ETH",
        to_address: Optional[str] = None,
        token_id: Optional[str] = None,
    ) -> Tuple[str, Optional[KYTCase]]:
        """
        Evaluate inbound transaction sender.
        Returns (result, case) where case is created for REVIEW.

        Checks both local blacklist/graylist AND BitOK KYT (if enabled).
        The most restrictive result is used.
        """
        address_lower = from_address.lower()
        result = KYTResult.ALLOW
        case = None
        reason = None
        bitok_response: Optional[BitOKCheckResponse] = None

        # Step 1: Check local blacklist/graylist (instant)
        if address_lower in self.settings.kyt_blacklist_addresses:
            result = KYTResult.BLOCK
            reason = "Sender address is on blacklist"
        elif address_lower in self.settings.kyt_graylist_addresses:
            result = KYTResult.REVIEW
            reason = "Sender address requires manual review"

        # Step 2: BitOK check (if enabled and not already blocked)
        if result != KYTResult.BLOCK and self.settings.bitok_enabled:
            try:
                bitok = get_bitok_integration()
                bitok_response = await bitok.check_transfer_inbound(
                    network=network,
                    tx_hash=tx_hash,
                    output_address=to_address or "",
                    token_id=token_id,
                    client_id=to_wallet_id,
                )

                # Map BitOK result to KYT result
                bitok_result = self._bitok_to_kyt_result(bitok_response.result)

                # Use the more restrictive result
                if bitok_result == KYTResult.BLOCK:
                    result = KYTResult.BLOCK
                    reason = f"BitOK: {bitok_response.risk_level} risk - transaction flagged"
                elif bitok_result == KYTResult.REVIEW and result == KYTResult.ALLOW:
                    result = KYTResult.REVIEW
                    reason = f"BitOK: {bitok_response.risk_level} risk level requires review"
                elif bitok_result == KYTResult.UNCHECKED:
                    logger.warning(f"BitOK check skipped for tx {tx_hash}: {bitok_response.error_message}")

            except Exception as e:
                logger.exception(f"BitOK check failed for inbound tx {tx_hash}: {e}")

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
                    "reason": reason,
                    "bitok_transfer_id": bitok_response.transfer_id if bitok_response else None,
                    "bitok_risk_level": bitok_response.risk_level if bitok_response else None,
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
                "case_id": case.id if case else None,
                "bitok_enabled": self.settings.bitok_enabled,
                "bitok_transfer_id": bitok_response.transfer_id if bitok_response else None,
                "bitok_risk_level": bitok_response.risk_level if bitok_response else None,
                "bitok_cached": bitok_response.cached if bitok_response else None,
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

