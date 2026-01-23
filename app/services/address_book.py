"""Address book service for group allow/deny lists."""
from typing import List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import GroupAddressBook, AddressKind
from app.models.audit import AuditEventType
from app.services.audit import AuditService


class AddressBookService:
    """Service for managing group address books (allow/deny lists)."""

    def __init__(self, db: AsyncSession, audit: AuditService):
        self.db = db
        self.audit = audit

    async def add_address(
        self,
        group_id: str,
        address: str,
        kind: AddressKind,
        label: Optional[str] = None,
        created_by: Optional[str] = None,
        correlation_id: str = "",
    ) -> GroupAddressBook:
        """
        Add an address to a group's address book.
        If address already exists, updates the kind and label.
        """
        address_lower = address.lower()

        # Check if already exists
        result = await self.db.execute(
            select(GroupAddressBook).where(
                and_(
                    GroupAddressBook.group_id == group_id,
                    GroupAddressBook.address == address_lower,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing entry
            existing.kind = kind
            existing.label = label
            await self.db.flush()

            await self.audit.log_event(
                event_type=AuditEventType.ADDRESS_BOOK_ENTRY_ADDED,
                correlation_id=correlation_id,
                actor_id=created_by,
                entity_type="GROUP",
                entity_id=group_id,
                payload={
                    "address": address_lower,
                    "kind": kind.value,
                    "label": label,
                    "updated": True,
                }
            )
            return existing

        # Create new entry
        entry = GroupAddressBook(
            id=str(uuid4()),
            group_id=group_id,
            address=address_lower,
            kind=kind,
            label=label,
            created_by=created_by,
        )
        self.db.add(entry)
        await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.ADDRESS_BOOK_ENTRY_ADDED,
            correlation_id=correlation_id,
            actor_id=created_by,
            entity_type="GROUP",
            entity_id=group_id,
            payload={
                "address": address_lower,
                "kind": kind.value,
                "label": label,
            }
        )

        return entry

    async def remove_address(
        self,
        group_id: str,
        address: str,
        actor_id: Optional[str] = None,
        correlation_id: str = "",
    ) -> bool:
        """Remove an address from a group's address book."""
        address_lower = address.lower()

        result = await self.db.execute(
            select(GroupAddressBook).where(
                and_(
                    GroupAddressBook.group_id == group_id,
                    GroupAddressBook.address == address_lower,
                )
            )
        )
        entry = result.scalar_one_or_none()

        if not entry:
            return False

        kind = entry.kind
        await self.db.delete(entry)
        await self.db.flush()

        await self.audit.log_event(
            event_type=AuditEventType.ADDRESS_BOOK_ENTRY_REMOVED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            entity_type="GROUP",
            entity_id=group_id,
            payload={
                "address": address_lower,
                "kind": kind.value,
            }
        )

        return True

    async def list_addresses(
        self,
        group_id: str,
        kind: Optional[AddressKind] = None,
    ) -> List[GroupAddressBook]:
        """List all addresses in a group's address book, optionally filtered by kind."""
        query = select(GroupAddressBook).where(GroupAddressBook.group_id == group_id)

        if kind:
            query = query.where(GroupAddressBook.kind == kind)

        query = query.order_by(GroupAddressBook.address)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_address_entry(
        self,
        group_id: str,
        address: str,
    ) -> Optional[GroupAddressBook]:
        """Get a specific address entry."""
        address_lower = address.lower()
        result = await self.db.execute(
            select(GroupAddressBook).where(
                and_(
                    GroupAddressBook.group_id == group_id,
                    GroupAddressBook.address == address_lower,
                )
            )
        )
        return result.scalar_one_or_none()

    async def is_allowed(self, group_id: str, address: str) -> bool:
        """Check if an address is in the allowlist."""
        entry = await self.get_address_entry(group_id, address)
        return entry is not None and entry.kind == AddressKind.ALLOW

    async def is_denied(self, group_id: str, address: str) -> bool:
        """Check if an address is in the denylist."""
        entry = await self.get_address_entry(group_id, address)
        return entry is not None and entry.kind == AddressKind.DENY

    async def check_address(self, group_id: str, address: str) -> Tuple[str, Optional[str]]:
        """
        Check address status in the group's address book.

        Returns:
            Tuple of (status, label) where status is one of:
            - 'allowlist': Address is in allowlist
            - 'denylist': Address is in denylist
            - 'unknown': Address is not in any list
        """
        entry = await self.get_address_entry(group_id, address)

        if entry is None:
            return 'unknown', None

        if entry.kind == AddressKind.ALLOW:
            return 'allowlist', entry.label

        if entry.kind == AddressKind.DENY:
            return 'denylist', entry.label

        return 'unknown', None

    async def get_allowlist_count(self, group_id: str) -> int:
        """Get count of allowlisted addresses."""
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(GroupAddressBook.id)).where(
                and_(
                    GroupAddressBook.group_id == group_id,
                    GroupAddressBook.kind == AddressKind.ALLOW,
                )
            )
        )
        return result.scalar() or 0

    async def get_denylist_count(self, group_id: str) -> int:
        """Get count of denylisted addresses."""
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(GroupAddressBook.id)).where(
                and_(
                    GroupAddressBook.group_id == group_id,
                    GroupAddressBook.kind == AddressKind.DENY,
                )
            )
        )
        return result.scalar() or 0
