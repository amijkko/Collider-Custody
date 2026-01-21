"""Transaction Request model and state machine."""
import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Enum, DateTime, Numeric, Text, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TxType(str, enum.Enum):
    """Transaction type."""
    WITHDRAW = "WITHDRAW"
    TRANSFER = "TRANSFER"
    CONTRACT_CALL = "CONTRACT_CALL"


class TxStatus(str, enum.Enum):
    """Transaction status state machine."""
    SUBMITTED = "SUBMITTED"
    KYT_PENDING = "KYT_PENDING"
    KYT_BLOCKED = "KYT_BLOCKED"
    KYT_REVIEW = "KYT_REVIEW"
    POLICY_EVAL_PENDING = "POLICY_EVAL_PENDING"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    REJECTED = "REJECTED"
    SIGN_PENDING = "SIGN_PENDING"
    SIGNED = "SIGNED"
    FAILED_SIGN = "FAILED_SIGN"
    BROADCAST_PENDING = "BROADCAST_PENDING"
    BROADCASTED = "BROADCASTED"
    FAILED_BROADCAST = "FAILED_BROADCAST"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    FINALIZED = "FINALIZED"


# Valid state transitions
VALID_TRANSITIONS = {
    TxStatus.SUBMITTED: [TxStatus.KYT_PENDING],
    TxStatus.KYT_PENDING: [TxStatus.KYT_BLOCKED, TxStatus.KYT_REVIEW, TxStatus.POLICY_EVAL_PENDING],
    TxStatus.KYT_BLOCKED: [],  # Terminal state
    TxStatus.KYT_REVIEW: [TxStatus.KYT_BLOCKED, TxStatus.POLICY_EVAL_PENDING],  # After case resolution
    TxStatus.POLICY_EVAL_PENDING: [TxStatus.POLICY_BLOCKED, TxStatus.APPROVAL_PENDING, TxStatus.SIGN_PENDING],
    TxStatus.POLICY_BLOCKED: [],  # Terminal state
    TxStatus.APPROVAL_PENDING: [TxStatus.REJECTED, TxStatus.SIGN_PENDING],
    TxStatus.REJECTED: [],  # Terminal state
    TxStatus.SIGN_PENDING: [TxStatus.SIGNED, TxStatus.FAILED_SIGN],
    TxStatus.SIGNED: [TxStatus.BROADCAST_PENDING],
    TxStatus.FAILED_SIGN: [],  # Terminal state
    TxStatus.BROADCAST_PENDING: [TxStatus.BROADCASTED, TxStatus.FAILED_BROADCAST],
    TxStatus.BROADCASTED: [TxStatus.CONFIRMING],
    TxStatus.FAILED_BROADCAST: [TxStatus.BROADCAST_PENDING],  # Can retry
    TxStatus.CONFIRMING: [TxStatus.CONFIRMED],
    TxStatus.CONFIRMED: [TxStatus.FINALIZED],
    TxStatus.FINALIZED: [],  # Terminal state
}


class TxRequest(Base):
    """Transaction request model."""
    __tablename__ = "tx_requests"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # Source wallet
    wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("wallets.id"), nullable=False, index=True)
    
    # Transaction details
    tx_type: Mapped[TxType] = mapped_column(Enum(TxType), nullable=False)
    to_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(50), nullable=False, default="ETH")  # ETH or ERC20 address
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # For CONTRACT_CALL
    
    # State machine
    status: Mapped[TxStatus] = mapped_column(Enum(TxStatus), default=TxStatus.SUBMITTED, index=True)
    
    # KYT results
    kyt_result: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    kyt_case_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("kyt_cases.id"), nullable=True)
    
    # Policy evaluation
    policy_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(default=False)
    required_approvals: Mapped[int] = mapped_column(default=0)
    
    # Signing and broadcast
    signed_tx: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True, index=True)
    gas_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 0), nullable=True)
    gas_limit: Mapped[Optional[int]] = mapped_column(nullable=True)
    nonce: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    # Confirmation tracking
    block_number: Mapped[Optional[int]] = mapped_column(nullable=True)
    confirmations: Mapped[int] = mapped_column(default=0)
    
    # Actor tracking
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    
    # Relationships
    approvals: Mapped[List["Approval"]] = relationship("Approval", back_populates="tx_request", lazy="selectin")
    kyt_case: Mapped[Optional["KYTCase"]] = relationship("KYTCase", back_populates="tx_request", lazy="selectin")
    
    __table_args__ = (
        Index("ix_tx_requests_status_created", "status", "created_at"),
        Index("ix_tx_requests_wallet_status", "wallet_id", "status"),
    )
    
    def can_transition_to(self, new_status: TxStatus) -> bool:
        """Check if transition to new status is valid."""
        return new_status in VALID_TRANSITIONS.get(self.status, [])


class Approval(Base):
    """Approval record for transaction requests."""
    __tablename__ = "approvals"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tx_request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tx_requests.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # APPROVED or REJECTED
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    tx_request: Mapped["TxRequest"] = relationship("TxRequest", back_populates="approvals")
    
    __table_args__ = (
        Index("ix_approvals_tx_user", "tx_request_id", "user_id", unique=True),
    )


class KYTCase(Base):
    """KYT review case for flagged transactions."""
    __tablename__ = "kyt_cases"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # INBOUND or OUTBOUND
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, RESOLVED_ALLOW, RESOLVED_BLOCK
    
    resolved_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    tx_request: Mapped[Optional["TxRequest"]] = relationship("TxRequest", back_populates="kyt_case", uselist=False)

