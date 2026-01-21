"""Policy engine models."""
import enum
from datetime import datetime
from datetime import date as date_type
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Enum, DateTime, Numeric, Boolean, Date, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PolicyType(str, enum.Enum):
    """Policy rule types."""
    ADDRESS_DENYLIST = "ADDRESS_DENYLIST"
    TOKEN_DENYLIST = "TOKEN_DENYLIST"
    TX_LIMIT = "TX_LIMIT"
    DAILY_LIMIT = "DAILY_LIMIT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class Policy(Base):
    """Policy rules stored in database."""
    __tablename__ = "policies"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_type: Mapped[PolicyType] = mapped_column(Enum(PolicyType), nullable=False, index=True)
    
    # For denylists
    address: Mapped[Optional[str]] = mapped_column(String(42), nullable=True, index=True)
    token: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    
    # For limits
    wallet_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("wallets.id"), nullable=True, index=True)
    wallet_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # Apply to all wallets of type
    limit_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(36, 18), nullable=True)
    
    # For approval rules
    required_approvals: Mapped[int] = mapped_column(default=0)
    
    # Additional config as JSON
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)


class DailyVolume(Base):
    """Track daily transaction volume per wallet for limit enforcement."""
    __tablename__ = "daily_volumes"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("wallets.id"), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    asset: Mapped[str] = mapped_column(String(50), nullable=False, default="ETH")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0"))
    tx_count: Mapped[int] = mapped_column(default=0)
    
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )

