"""Audit service with hash-chain for tamper evidence."""
import hashlib
import json
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent, AuditEventType
from app.models.tx_request import TxRequest, Approval
from app.schemas.audit import AuditPackageResponse, AuditEventResponse, AuditVerifyResponse


class AuditService:
    """Service for managing audit events with hash chain."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_event(
        self,
        event_type: AuditEventType,
        correlation_id: str,
        actor_id: Optional[str] = None,
        actor_type: str = "USER",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        entity_refs: Optional[dict] = None,
        payload: Optional[dict] = None,
    ) -> AuditEvent:
        """Create a new audit event with hash chain."""
        # Get the previous event's hash
        prev_event = await self._get_last_event()
        prev_hash = prev_event.hash if prev_event else None
        
        # Get next sequence number
        seq_result = await self.db.execute(
            select(func.coalesce(func.max(AuditEvent.sequence_number), 0) + 1)
        )
        sequence_number = seq_result.scalar()
        
        event_id = str(uuid4())
        timestamp = datetime.utcnow()
        
        # Compute hash
        event_hash = AuditEvent.compute_hash(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type.value,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            prev_hash=prev_hash
        )
        
        event = AuditEvent(
            id=event_id,
            sequence_number=sequence_number,
            timestamp=timestamp,
            event_type=event_type,
            actor_id=actor_id,
            actor_type=actor_type,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_refs=entity_refs,
            payload=payload,
            correlation_id=correlation_id,
            prev_hash=prev_hash,
            hash=event_hash
        )
        
        self.db.add(event)
        await self.db.flush()
        
        return event
    
    async def _get_last_event(self) -> Optional[AuditEvent]:
        """Get the last audit event for hash chain continuation."""
        result = await self.db.execute(
            select(AuditEvent)
            .order_by(AuditEvent.sequence_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_last_audit_event(self) -> Optional[AuditEvent]:
        """Get the last audit event (public interface for SigningPermit anchor)."""
        return await self._get_last_event()
    
    async def get_events_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get audit events for a specific entity."""
        result = await self.db.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type)
            .where(AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.sequence_number.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def build_audit_package(
        self,
        tx_request_id: str,
        correlation_id: str
    ) -> AuditPackageResponse:
        """Build a complete audit package for a transaction request."""
        # Get the transaction request
        tx_result = await self.db.execute(
            select(TxRequest).where(TxRequest.id == tx_request_id)
        )
        tx_request = tx_result.scalar_one_or_none()
        
        if not tx_request:
            raise ValueError(f"Transaction request {tx_request_id} not found")
        
        # Get all audit events for this tx request
        events = await self.get_events_for_entity("TX_REQUEST", tx_request_id)
        
        # Get approvals
        approvals_result = await self.db.execute(
            select(Approval).where(Approval.tx_request_id == tx_request_id)
        )
        approvals = list(approvals_result.scalars().all())
        
        # Extract specific audit data
        policy_eval = None
        kyt_eval = None
        signing_info = None
        broadcast_info = None
        confirmation_info = None
        
        for event in events:
            if event.event_type == AuditEventType.TX_POLICY_EVALUATED:
                policy_eval = event.payload
            elif event.event_type == AuditEventType.TX_KYT_EVALUATED:
                kyt_eval = event.payload
            elif event.event_type == AuditEventType.TX_SIGNED:
                # Remove any sensitive data from signing info
                signing_info = {
                    "signed_at": event.timestamp.isoformat(),
                    "tx_hash": event.payload.get("tx_hash") if event.payload else None
                }
            elif event.event_type == AuditEventType.TX_BROADCASTED:
                broadcast_info = event.payload
            elif event.event_type == AuditEventType.TX_CONFIRMED:
                confirmation_info = event.payload
        
        # Build package
        package_data = {
            "tx_request_id": tx_request_id,
            "tx_request": {
                "id": tx_request.id,
                "wallet_id": tx_request.wallet_id,
                "tx_type": tx_request.tx_type.value,
                "to_address": tx_request.to_address,
                "asset": tx_request.asset,
                "amount": str(tx_request.amount),
                "status": tx_request.status.value,
                "tx_hash": tx_request.tx_hash,
                "block_number": tx_request.block_number,
                "confirmations": tx_request.confirmations,
                "created_by": tx_request.created_by,
                "created_at": tx_request.created_at.isoformat(),
            },
            "policy_evaluation": policy_eval,
            "kyt_evaluation": kyt_eval,
            "approvals": [
                {
                    "id": a.id,
                    "user_id": a.user_id,
                    "decision": a.decision,
                    "comment": a.comment,
                    "created_at": a.created_at.isoformat()
                }
                for a in approvals
            ],
            "signing": signing_info,
            "broadcast": broadcast_info,
            "confirmations": confirmation_info,
            "audit_events": [
                AuditEventResponse.model_validate(e) for e in events
            ],
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # Compute package hash
        package_hash = hashlib.sha256(
            json.dumps(package_data, sort_keys=True, default=str).encode()
        ).hexdigest()
        
        return AuditPackageResponse(
            tx_request_id=tx_request_id,
            tx_request=package_data["tx_request"],
            policy_evaluation=policy_eval,
            kyt_evaluation=kyt_eval,
            approvals=package_data["approvals"],
            signing=signing_info,
            broadcast=broadcast_info,
            confirmations=confirmation_info,
            audit_events=package_data["audit_events"],
            package_hash=package_hash,
            generated_at=datetime.utcnow()
        )
    
    async def verify_chain(
        self,
        from_sequence: Optional[int] = None,
        to_sequence: Optional[int] = None
    ) -> AuditVerifyResponse:
        """Verify the integrity of the audit hash chain."""
        query = select(AuditEvent).order_by(AuditEvent.sequence_number.asc())
        
        if from_sequence is not None:
            query = query.where(AuditEvent.sequence_number >= from_sequence)
        if to_sequence is not None:
            query = query.where(AuditEvent.sequence_number <= to_sequence)
        
        result = await self.db.execute(query)
        events = list(result.scalars().all())
        
        if not events:
            return AuditVerifyResponse(
                is_valid=True,
                total_events=0,
                verified_events=0,
                first_event_id=None,
                last_event_id=None,
                chain_intact=True,
                errors=[]
            )
        
        errors = []
        verified = 0
        prev_hash = None
        
        # For the first event in range, get its expected prev_hash
        if from_sequence and from_sequence > 1:
            prev_result = await self.db.execute(
                select(AuditEvent)
                .where(AuditEvent.sequence_number == from_sequence - 1)
            )
            prev_event = prev_result.scalar_one_or_none()
            if prev_event:
                prev_hash = prev_event.hash
        
        for event in events:
            # Check prev_hash matches
            if event.prev_hash != prev_hash:
                errors.append(
                    f"Event {event.id} (seq {event.sequence_number}): "
                    f"prev_hash mismatch. Expected {prev_hash}, got {event.prev_hash}"
                )
            
            # Recompute hash and verify
            expected_hash = AuditEvent.compute_hash(
                event_id=event.id,
                timestamp=event.timestamp,
                event_type=event.event_type.value,
                actor_id=event.actor_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                payload=event.payload,
                prev_hash=event.prev_hash
            )
            
            if event.hash != expected_hash:
                errors.append(
                    f"Event {event.id} (seq {event.sequence_number}): "
                    f"hash mismatch. Possible tampering detected."
                )
            else:
                verified += 1
            
            prev_hash = event.hash
        
        return AuditVerifyResponse(
            is_valid=len(errors) == 0,
            total_events=len(events),
            verified_events=verified,
            first_event_id=events[0].id if events else None,
            last_event_id=events[-1].id if events else None,
            chain_intact=len(errors) == 0,
            errors=errors
        )

