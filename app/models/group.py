"""Group models for user segmentation and policy assignment."""
import enum
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import String, Enum, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.policy_set import PolicySet


class AddressKind(str, enum.Enum):
    """Address book entry kind."""
    ALLOW = "ALLOW"
    DENY = "DENY"


class Group(Base):
    """User group for segmentation and policy assignment."""
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    members: Mapped[List["GroupMember"]] = relationship(
        "GroupMember", back_populates="group", lazy="selectin", cascade="all, delete-orphan"
    )
    address_book: Mapped[List["GroupAddressBook"]] = relationship(
        "GroupAddressBook", back_populates="group", lazy="selectin", cascade="all, delete-orphan"
    )
    policy_assignment: Mapped[Optional["GroupPolicy"]] = relationship(
        "GroupPolicy", back_populates="group", uselist=False, lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Group {self.name}>"


class GroupMember(Base):
    """User membership in a group."""
    __tablename__ = "group_members"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    group_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="members")
    user: Mapped["User"] = relationship("User", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_member"),
        Index("ix_group_members_user", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<GroupMember group={self.group_id} user={self.user_id}>"


class GroupAddressBook(Base):
    """Address book entry for a group (allow/deny list)."""
    __tablename__ = "group_address_book"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    group_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    address: Mapped[str] = mapped_column(String(42), nullable=False)
    kind: Mapped[AddressKind] = mapped_column(Enum(AddressKind), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="address_book")

    __table_args__ = (
        UniqueConstraint("group_id", "address", name="uq_group_address"),
        Index("ix_group_address_book_address", "address"),
        Index("ix_group_address_book_kind", "group_id", "kind"),
    )

    def __repr__(self) -> str:
        return f"<GroupAddressBook {self.kind.value}: {self.address}>"


class GroupPolicy(Base):
    """Policy set assignment to a group."""
    __tablename__ = "group_policies"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    group_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    policy_set_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("policy_sets.id"), nullable=False
    )

    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    assigned_by: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="policy_assignment")
    policy_set: Mapped["PolicySet"] = relationship("PolicySet", lazy="selectin")

    def __repr__(self) -> str:
        return f"<GroupPolicy group={self.group_id} policy={self.policy_set_id}>"
