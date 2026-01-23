"""Group management service."""
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.group import Group, GroupMember, GroupAddressBook, AddressKind
from app.models.audit import AuditEventType
from app.services.audit import AuditService


class GroupService:
    """Service for managing user groups."""

    def __init__(self, db: AsyncSession, audit: AuditService):
        self.db = db
        self.audit = audit

    async def create_group(
        self,
        name: str,
        description: Optional[str] = None,
        is_default: bool = False,
        created_by: Optional[str] = None,
        correlation_id: str = "",
    ) -> Group:
        """Create a new group."""
        group = Group(
            id=str(uuid4()),
            name=name,
            description=description,
            is_default=is_default,
            created_by=created_by,
        )
        self.db.add(group)
        await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.GROUP_CREATED,
            correlation_id=correlation_id,
            actor_id=created_by,
            entity_type="GROUP",
            entity_id=group.id,
            payload={
                "name": name,
                "description": description,
                "is_default": is_default,
            }
        )

        return group

    async def get_group(self, group_id: str) -> Optional[Group]:
        """Get a group by ID with all relationships loaded."""
        result = await self.db.execute(
            select(Group)
            .options(
                selectinload(Group.members).selectinload(GroupMember.user),
                selectinload(Group.address_book),
                selectinload(Group.policy_assignment),
            )
            .where(Group.id == group_id)
        )
        return result.scalar_one_or_none()

    async def get_group_by_name(self, name: str) -> Optional[Group]:
        """Get a group by name."""
        result = await self.db.execute(
            select(Group).where(Group.name == name)
        )
        return result.scalar_one_or_none()

    async def get_default_group(self) -> Optional[Group]:
        """Get the default group (Retail)."""
        result = await self.db.execute(
            select(Group).where(Group.is_default == True)
        )
        return result.scalar_one_or_none()

    async def list_groups(self) -> List[Group]:
        """List all groups."""
        result = await self.db.execute(
            select(Group).order_by(Group.name)
        )
        return list(result.scalars().all())

    async def add_member(
        self,
        group_id: str,
        user_id: str,
        correlation_id: str = "",
        actor_id: Optional[str] = None,
    ) -> GroupMember:
        """Add a user to a group. Idempotent - returns existing if already member."""
        # Check if already a member
        result = await self.db.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        member = GroupMember(
            id=str(uuid4()),
            group_id=group_id,
            user_id=user_id,
        )
        self.db.add(member)
        await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.GROUP_MEMBER_ADDED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            entity_type="GROUP",
            entity_id=group_id,
            entity_refs={"user_id": user_id},
            payload={"user_id": user_id}
        )

        return member

    async def remove_member(
        self,
        group_id: str,
        user_id: str,
        correlation_id: str = "",
        actor_id: Optional[str] = None,
    ) -> bool:
        """Remove a user from a group. Returns True if removed, False if not found."""
        result = await self.db.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False

        await self.db.delete(member)
        await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.GROUP_MEMBER_REMOVED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            entity_type="GROUP",
            entity_id=group_id,
            entity_refs={"user_id": user_id},
            payload={"user_id": user_id}
        )

        return True

    async def get_user_groups(self, user_id: str) -> List[Group]:
        """Get all groups a user belongs to."""
        result = await self.db.execute(
            select(Group)
            .join(GroupMember)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.name)
        )
        return list(result.scalars().all())

    async def get_user_primary_group(self, user_id: str) -> Optional[Group]:
        """Get user's primary group (first group, or default if none)."""
        groups = await self.get_user_groups(user_id)
        if groups:
            # Prefer default group if user is member
            for g in groups:
                if g.is_default:
                    return g
            return groups[0]
        return await self.get_default_group()

    async def is_member(self, group_id: str, user_id: str) -> bool:
        """Check if a user is a member of a group."""
        result = await self.db.execute(
            select(GroupMember).where(
                and_(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_group_member_count(self, group_id: str) -> int:
        """Get the number of members in a group."""
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(GroupMember.id)).where(GroupMember.group_id == group_id)
        )
        return result.scalar() or 0
