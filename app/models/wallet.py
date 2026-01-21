"""Wallet models."""
import enum
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Enum, DateTime, ForeignKey, JSON, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WalletType(str, enum.Enum):
    """Wallet type classification."""
    RETAIL = "RETAIL"
    TREASURY = "TREASURY"
    OPS = "OPS"
    SETTLEMENT = "SETTLEMENT"


class RiskProfile(str, enum.Enum):
    """Wallet risk profile."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CustodyBackend(str, enum.Enum):
    """Custody backend type for wallet key management."""
    DEV_SIGNER = "DEV_SIGNER"  # Local dev key (for development only)
    MPC_TECDSA = "MPC_TECDSA"  # Threshold ECDSA via MPC (production)


class WalletStatus(str, enum.Enum):
    """Wallet status for MPC keygen flow."""
    PENDING_KEYGEN = "PENDING_KEYGEN"  # MPC DKG not yet complete
    ACTIVE = "ACTIVE"  # Ready for use
    SUSPENDED = "SUSPENDED"  # Temporarily disabled
    ARCHIVED = "ARCHIVED"  # No longer in use


class Wallet(Base):
    """Wallet registry model."""
    __tablename__ = "wallets"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    address: Mapped[Optional[str]] = mapped_column(String(42), unique=True, nullable=True, index=True)  # Nullable for PENDING_KEYGEN
    wallet_type: Mapped[WalletType] = mapped_column(Enum(WalletType), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    risk_profile: Mapped[RiskProfile] = mapped_column(Enum(RiskProfile), default=RiskProfile.MEDIUM)
    key_ref: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # URI to key (nullable for PENDING)
    
    # Custody backend selection
    custody_backend: Mapped[CustodyBackend] = mapped_column(
        Enum(CustodyBackend, name='custodybackend'), 
        default=CustodyBackend.DEV_SIGNER,
        index=True
    )
    
    # Wallet status (for MPC flow)
    status: Mapped[WalletStatus] = mapped_column(Enum(WalletStatus, name='walletstatus'), default=WalletStatus.ACTIVE, index=True)
    
    # MPC-specific fields (populated when custody_backend=MPC_TECDSA)
    mpc_keyset_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    mpc_threshold_t: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # t-of-n threshold
    mpc_total_n: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # n total parties
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Idempotency key for creation
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    
    # Relationships
    roles: Mapped[List["WalletRole"]] = relationship("WalletRole", back_populates="wallet", lazy="selectin")
    
    __table_args__ = (
        Index("ix_wallets_subject_type", "subject_id", "wallet_type"),
        Index("ix_wallets_custody_status", "custody_backend", "status"),
    )
    
    @property
    def is_mpc(self) -> bool:
        """Check if wallet uses MPC custody."""
        return self.custody_backend == CustodyBackend.MPC_TECDSA


class WalletRoleType(str, enum.Enum):
    """Role types for wallet access."""
    OWNER = "OWNER"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"
    APPROVER = "APPROVER"


class WalletRole(Base):
    """Role assignment on a wallet."""
    __tablename__ = "wallet_roles"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("wallets.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    role: Mapped[WalletRoleType] = mapped_column(Enum(WalletRoleType), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    
    # Relationships
    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="roles")
    
    __table_args__ = (
        Index("ix_wallet_roles_wallet_user", "wallet_id", "user_id", unique=True),
    )

