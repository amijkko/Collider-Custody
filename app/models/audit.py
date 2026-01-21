"""Audit log model with hash chain for tamper evidence."""
import enum
import hashlib
import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Enum, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditEventType(str, enum.Enum):
    """Types of auditable events."""
    # Wallet events
    WALLET_CREATED = "WALLET_CREATED"
    WALLET_ROLE_ASSIGNED = "WALLET_ROLE_ASSIGNED"
    WALLET_ROLE_REVOKED = "WALLET_ROLE_REVOKED"
    
    # Transaction events
    TX_REQUEST_CREATED = "TX_REQUEST_CREATED"
    TX_STATUS_CHANGED = "TX_STATUS_CHANGED"
    TX_KYT_EVALUATED = "TX_KYT_EVALUATED"
    TX_POLICY_EVALUATED = "TX_POLICY_EVALUATED"
    TX_APPROVAL_RECEIVED = "TX_APPROVAL_RECEIVED"
    TX_REJECTION_RECEIVED = "TX_REJECTION_RECEIVED"
    TX_SIGNED = "TX_SIGNED"
    TX_BROADCASTED = "TX_BROADCASTED"
    TX_CONFIRMED = "TX_CONFIRMED"
    TX_FINALIZED = "TX_FINALIZED"
    TX_FAILED = "TX_FAILED"
    
    # KYT events
    KYT_CASE_CREATED = "KYT_CASE_CREATED"
    KYT_CASE_RESOLVED = "KYT_CASE_RESOLVED"
    
    # Inbound events
    DEPOSIT_DETECTED = "DEPOSIT_DETECTED"
    DEPOSIT_KYT_EVALUATED = "DEPOSIT_KYT_EVALUATED"
    DEPOSIT_APPROVED = "DEPOSIT_APPROVED"
    DEPOSIT_REJECTED = "DEPOSIT_REJECTED"
    
    # Policy events
    POLICY_CREATED = "POLICY_CREATED"
    POLICY_UPDATED = "POLICY_UPDATED"
    POLICY_DELETED = "POLICY_DELETED"
    
    # Auth events
    USER_LOGIN = "USER_LOGIN"
    USER_LOGOUT = "USER_LOGOUT"
    
    # MPC events
    MPC_KEYGEN_STARTED = "MPC_KEYGEN_STARTED"
    MPC_KEYGEN_COMPLETED = "MPC_KEYGEN_COMPLETED"
    MPC_KEYGEN_FAILED = "MPC_KEYGEN_FAILED"
    MPC_SIGN_STARTED = "MPC_SIGN_STARTED"
    MPC_SIGN_COMPLETED = "MPC_SIGN_COMPLETED"
    MPC_SIGN_FAILED = "MPC_SIGN_FAILED"
    SIGN_PERMIT_ISSUED = "SIGN_PERMIT_ISSUED"
    SIGN_PERMIT_REJECTED = "SIGN_PERMIT_REJECTED"
    MPC_NODE_QUARANTINED = "MPC_NODE_QUARANTINED"


class AuditEvent(Base):
    """Append-only audit log with hash chain."""
    __tablename__ = "audit_events"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    sequence_number: Mapped[int] = mapped_column(autoincrement=True, nullable=False, unique=True)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType), nullable=False, index=True)
    
    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), default="USER")  # USER, SYSTEM, CHAIN_LISTENER
    
    # Entity references (what was affected)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # WALLET, TX_REQUEST, etc.
    entity_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    
    # Additional entity refs as JSON for complex relations
    entity_refs: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Event payload (NO sensitive data like private keys!)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Correlation ID for request tracing
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Hash chain for tamper evidence
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # NULL for first event
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_timestamp_type", "timestamp", "event_type"),
    )
    
    @staticmethod
    def compute_hash(
        event_id: str,
        timestamp: datetime,
        event_type: str,
        actor_id: Optional[str],
        entity_type: Optional[str],
        entity_id: Optional[str],
        payload: Optional[dict],
        prev_hash: Optional[str]
    ) -> str:
        """Compute SHA-256 hash for the event."""
        data = {
            "event_id": event_id,
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "actor_id": actor_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "prev_hash": prev_hash
        }
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()


class Deposit(Base):
    """Inbound deposit detection record."""
    __tablename__ = "deposits"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False, unique=True, index=True)
    from_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(50), nullable=False, default="ETH")
    amount: Mapped[str] = mapped_column(String(78), nullable=False)  # Store as string for precision
    block_number: Mapped[int] = mapped_column(nullable=False)
    
    # KYT result for inbound
    kyt_result: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    kyt_case_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING_ADMIN")
    
    # Approval tracking
    approved_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

