"""Wallet service for managing wallets and roles."""
import logging
from typing import Optional, List, TYPE_CHECKING
from uuid import uuid4

from eth_account import Account
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import Wallet, WalletRole, WalletType, WalletRoleType, CustodyBackend, WalletStatus
from app.models.audit import AuditEventType
from app.schemas.wallet import WalletCreate, WalletRoleAssign, WalletCreateMPC
from app.services.audit import AuditService

if TYPE_CHECKING:
    from app.services.mpc_coordinator import MPCCoordinator

logger = logging.getLogger(__name__)


class WalletService:
    """Service for managing wallets."""
    
    def __init__(
        self, 
        db: AsyncSession, 
        audit: AuditService,
        mpc_coordinator: Optional["MPCCoordinator"] = None
    ):
        self.db = db
        self.audit = audit
        self._mpc_coordinator = mpc_coordinator
    
    def set_mpc_coordinator(self, coordinator: "MPCCoordinator"):
        """Set the MPC coordinator (for dependency injection)."""
        self._mpc_coordinator = coordinator
    
    async def create_wallet(
        self,
        wallet_data: WalletCreate,
        created_by: str,
        correlation_id: str,
        idempotency_key: Optional[str] = None
    ) -> Wallet:
        """
        Create a new Ethereum wallet (EOA).
        
        Routes to appropriate backend based on custody_backend:
        - DEV_SIGNER: Generates local keypair
        - MPC_TECDSA: Initiates DKG via MPC Coordinator
        """
        # Check idempotency
        if idempotency_key:
            existing = await self.db.execute(
                select(Wallet).where(Wallet.idempotency_key == idempotency_key)
            )
            wallet = existing.scalar_one_or_none()
            if wallet:
                return wallet
        
        # Route based on custody backend
        if wallet_data.custody_backend == CustodyBackend.MPC_TECDSA:
            return await self._create_mpc_wallet(
                wallet_data=wallet_data,
                created_by=created_by,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
        else:
            return await self._create_dev_wallet(
                wallet_data=wallet_data,
                created_by=created_by,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
    
    async def _create_dev_wallet(
        self,
        wallet_data: WalletCreate,
        created_by: str,
        correlation_id: str,
        idempotency_key: Optional[str] = None
    ) -> Wallet:
        """Create wallet using dev signer (local keypair)."""
        # Generate new Ethereum account
        account = Account.create()
        
        # Create key reference (in dev mode, we store derivation info, not the key itself)
        key_ref = f"dev:{account.address}"
        
        wallet = Wallet(
            id=str(uuid4()),
            address=account.address.lower(),
            wallet_type=wallet_data.wallet_type,
            subject_id=wallet_data.subject_id,
            tags=wallet_data.tags,
            risk_profile=wallet_data.risk_profile,
            key_ref=key_ref,
            custody_backend=CustodyBackend.DEV_SIGNER,
            status=WalletStatus.ACTIVE,
            idempotency_key=idempotency_key
        )
        
        self.db.add(wallet)
        await self.db.flush()
        await self.db.refresh(wallet, ["roles"])
        
        # Log audit event (without private key!)
        await self.audit.log_event(
            event_type=AuditEventType.WALLET_CREATED,
            correlation_id=correlation_id,
            actor_id=created_by,
            entity_type="WALLET",
            entity_id=wallet.id,
            payload={
                "address": wallet.address,
                "wallet_type": wallet.wallet_type.value,
                "subject_id": wallet.subject_id,
                "risk_profile": wallet.risk_profile.value,
                "custody_backend": CustodyBackend.DEV_SIGNER.value,
            }
        )
        
        logger.info(f"Created DEV_SIGNER wallet: {wallet.id} with address {wallet.address}")
        return wallet
    
    async def _create_mpc_wallet(
        self,
        wallet_data: WalletCreate,
        created_by: str,
        correlation_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Wallet:
        """
        Create wallet record for MPC (tECDSA DKG).

        This only creates the wallet in PENDING_KEYGEN status.
        The actual DKG happens via WebSocket between browser WASM and MPC Signer.
        Call finalize_mpc_wallet() after DKG completes.
        """
        # Get MPC parameters - for 2-of-2 with browser + bank signer
        threshold_t = wallet_data.mpc_threshold_t or 1  # t=1 means 2-of-2
        total_n = wallet_data.mpc_total_n or 2  # 2 parties: browser + bank

        # Validate threshold
        if threshold_t >= total_n:
            raise ValueError(f"Threshold t={threshold_t} must be less than n={total_n}")

        # Create wallet record in PENDING_KEYGEN state
        wallet = Wallet(
            id=str(uuid4()),
            address=None,  # Will be set after DKG via WebSocket
            wallet_type=wallet_data.wallet_type,
            subject_id=wallet_data.subject_id,
            tags=wallet_data.tags or {},
            risk_profile=wallet_data.risk_profile,
            key_ref=None,  # Will be set after DKG
            custody_backend=CustodyBackend.MPC_TECDSA,
            status=WalletStatus.PENDING_KEYGEN,
            mpc_threshold_t=threshold_t,
            mpc_total_n=total_n,
            idempotency_key=idempotency_key
        )

        self.db.add(wallet)
        await self.db.flush()

        # Create OWNER role for the creator
        owner_role = WalletRole(
            id=str(uuid4()),
            wallet_id=wallet.id,
            user_id=created_by,
            role=WalletRoleType.OWNER,
            created_by=created_by,
        )
        self.db.add(owner_role)
        await self.db.flush()

        await self.db.refresh(wallet, ["roles"])

        # Log audit event for wallet creation (pending keygen)
        await self.audit.log_event(
            event_type=AuditEventType.WALLET_CREATED,
            correlation_id=correlation_id,
            actor_id=created_by,
            entity_type="WALLET",
            entity_id=wallet.id,
            payload={
                "wallet_type": wallet.wallet_type.value,
                "subject_id": wallet.subject_id,
                "risk_profile": wallet.risk_profile.value,
                "custody_backend": CustodyBackend.MPC_TECDSA.value,
                "status": "PENDING_KEYGEN",
                "mpc_threshold": f"{threshold_t+1}-of-{total_n}",  # Display as t+1 of n
            }
        )

        logger.info(f"Created MPC_TECDSA wallet (pending keygen): {wallet.id}")
        return wallet

    async def finalize_mpc_wallet(
        self,
        wallet_id: str,
        keyset_id: str,
        address: str,
        public_key: str,
        public_key_compressed: str,
        correlation_id: str,
        actor_id: str,
    ) -> Wallet:
        """
        Finalize MPC wallet after DKG completes via WebSocket.

        Called by the WebSocket handler when DKG between browser and MPC Signer succeeds.
        """
        from app.models.mpc import MPCKeyset, MPCKeysetStatus, MPCSession, MPCSessionType, MPCSessionStatus
        from datetime import datetime

        # Get wallet
        result = await self.db.execute(
            select(Wallet).where(Wallet.id == wallet_id)
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise ValueError(f"Wallet {wallet_id} not found")

        if wallet.status != WalletStatus.PENDING_KEYGEN:
            raise ValueError(f"Wallet {wallet_id} is not pending keygen (status: {wallet.status})")

        # Create keyset record
        keyset = MPCKeyset(
            id=keyset_id,
            wallet_id=wallet_id,
            threshold_t=wallet.mpc_threshold_t,
            total_n=wallet.mpc_total_n,
            public_key=public_key,
            public_key_compressed=public_key_compressed,
            address=address,
            status=MPCKeysetStatus.ACTIVE,
            cluster_id="default",
            key_ref=f"mpc-tecdsa://default/{keyset_id}",
            participant_nodes={"nodes": ["browser-user", "bank-signer"]},
            activated_at=datetime.utcnow(),
        )
        self.db.add(keyset)

        # Create DKG session record
        session = MPCSession(
            id=str(uuid4()),
            session_type=MPCSessionType.DKG,
            keyset_id=keyset_id,
            status=MPCSessionStatus.COMPLETED,
            participant_nodes={"nodes": ["browser-user", "bank-signer"]},
            current_round=3,
            total_rounds=3,
            quorum_reached=True,
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
        )
        self.db.add(session)

        # Update wallet
        wallet.address = address.lower()
        wallet.key_ref = keyset.key_ref
        wallet.mpc_keyset_id = keyset_id
        wallet.status = WalletStatus.ACTIVE
        wallet.tags = wallet.tags or {}
        wallet.tags["mpc_keyset_id"] = keyset_id
        wallet.tags["mpc_threshold"] = f"{wallet.mpc_threshold_t+1}-of-{wallet.mpc_total_n}"

        await self.db.flush()
        await self.db.refresh(wallet, ["roles"])

        # Log audit event
        await self.audit.log_event(
            event_type=AuditEventType.MPC_KEYGEN_COMPLETED,
            correlation_id=correlation_id,
            actor_id=actor_id,
            entity_type="WALLET",
            entity_id=wallet.id,
            payload={
                "address": wallet.address,
                "keyset_id": keyset_id,
                "public_key_hash": public_key[:16] + "...",
                "mpc_threshold": f"{wallet.mpc_threshold_t+1}-of-{wallet.mpc_total_n}",
            }
        )

        logger.info(f"Finalized MPC_TECDSA wallet: {wallet.id} with address {wallet.address}")
        return wallet
    
    async def create_mpc_wallet(
        self,
        wallet_data: WalletCreateMPC,
        created_by: str,
        correlation_id: str,
        idempotency_key: Optional[str] = None
    ) -> Wallet:
        """Create a new MPC wallet (explicit method for MPC-specific flow)."""
        # Convert to WalletCreate with MPC backend
        create_data = WalletCreate(
            wallet_type=wallet_data.wallet_type,
            subject_id=wallet_data.subject_id,
            tags=wallet_data.tags,
            risk_profile=wallet_data.risk_profile,
            custody_backend=CustodyBackend.MPC_TECDSA,
            mpc_threshold_t=wallet_data.mpc_threshold_t,
            mpc_total_n=wallet_data.mpc_total_n,
        )
        return await self.create_wallet(
            wallet_data=create_data,
            created_by=created_by,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
    
    async def get_wallet(self, wallet_id: str) -> Optional[Wallet]:
        """Get wallet by ID."""
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(Wallet).options(selectinload(Wallet.roles)).where(Wallet.id == wallet_id)
        )
        return result.scalar_one_or_none()
    
    async def get_wallet_by_address(self, address: str) -> Optional[Wallet]:
        """Get wallet by Ethereum address."""
        result = await self.db.execute(
            select(Wallet).where(Wallet.address == address.lower())
        )
        return result.scalar_one_or_none()
    
    async def list_wallets(
        self,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        wallet_type: Optional[WalletType] = None,
        subject_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Wallet]:
        """List wallets with optional filters. Non-admins only see their own wallets."""
        from sqlalchemy.orm import selectinload
        query = select(Wallet).options(selectinload(Wallet.roles))

        # Filter by user's wallet roles (unless admin)
        if user_id and not is_admin:
            query = query.where(Wallet.roles.any(user_id=user_id))

        if wallet_type:
            query = query.where(Wallet.wallet_type == wallet_type)
        if subject_id:
            query = query.where(Wallet.subject_id == subject_id)

        query = query.order_by(Wallet.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def assign_role(
        self,
        wallet_id: str,
        role_data: WalletRoleAssign,
        assigned_by: str,
        correlation_id: str
    ) -> WalletRole:
        """Assign a role to a user on a wallet."""
        # Check if role already exists
        existing = await self.db.execute(
            select(WalletRole)
            .where(WalletRole.wallet_id == wallet_id)
            .where(WalletRole.user_id == role_data.user_id)
        )
        existing_role = existing.scalar_one_or_none()
        
        if existing_role:
            # Update existing role
            existing_role.role = role_data.role
            await self.db.flush()
            role = existing_role
        else:
            # Create new role
            role = WalletRole(
                id=str(uuid4()),
                wallet_id=wallet_id,
                user_id=role_data.user_id,
                role=role_data.role,
                created_by=assigned_by
            )
            self.db.add(role)
            await self.db.flush()
        
        # Log audit event
        await self.audit.log_event(
            event_type=AuditEventType.WALLET_ROLE_ASSIGNED,
            correlation_id=correlation_id,
            actor_id=assigned_by,
            entity_type="WALLET",
            entity_id=wallet_id,
            entity_refs={"user_id": role_data.user_id},
            payload={
                "role": role_data.role.value,
                "user_id": role_data.user_id
            }
        )
        
        return role
    
    async def revoke_role(
        self,
        wallet_id: str,
        user_id: str,
        revoked_by: str,
        correlation_id: str
    ) -> bool:
        """Revoke a user's role on a wallet."""
        result = await self.db.execute(
            select(WalletRole)
            .where(WalletRole.wallet_id == wallet_id)
            .where(WalletRole.user_id == user_id)
        )
        role = result.scalar_one_or_none()
        
        if not role:
            return False
        
        await self.db.delete(role)
        await self.db.flush()
        
        # Log audit event
        await self.audit.log_event(
            event_type=AuditEventType.WALLET_ROLE_REVOKED,
            correlation_id=correlation_id,
            actor_id=revoked_by,
            entity_type="WALLET",
            entity_id=wallet_id,
            entity_refs={"user_id": user_id},
            payload={"user_id": user_id, "role": role.role.value}
        )
        
        return True
    
    async def get_all_addresses(self) -> List[str]:
        """Get all wallet addresses for chain listener monitoring."""
        result = await self.db.execute(
            select(Wallet.address).where(Wallet.address.isnot(None)).where(Wallet.address != "")
        )
        return [r[0] for r in result.all() if r[0]]

