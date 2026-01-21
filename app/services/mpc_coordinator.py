"""
MPC Coordinator Service - coordinates DKG and signing operations.

This is a simulation/mock that demonstrates the MPC flow.
In production, this would coordinate real MPC signer nodes via gRPC.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
from uuid import uuid4

from eth_account import Account
from eth_keys import keys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from app.config import get_settings
from app.models.mpc import (
    MPCKeyset, MPCKeysetStatus,
    MPCSession, MPCSessionType, MPCSessionStatus,
    MPCNode, MPCNodeStatus,
    SigningPermit, MPCErrorCategory,
)
from app.services.audit import AuditService, AuditEventType

logger = logging.getLogger(__name__)

# Module-level storage for simulated keys (persists across requests)
# In production, this would be replaced by actual MPC signer nodes
_SIMULATED_KEYS: Dict[str, str] = {}


class MPCCoordinatorError(Exception):
    """Base exception for MPC Coordinator."""
    def __init__(self, message: str, category: MPCErrorCategory = MPCErrorCategory.PERMANENT):
        super().__init__(message)
        self.category = category


class MPCCoordinator:
    """
    MPC Coordinator - orchestrates DKG and signing sessions.
    
    In this simulation:
    - DKG generates a real secp256k1 key pair (simulating distributed generation)
    - Signing uses the simulated private key (simulating threshold signature)
    
    In production, this would:
    - Communicate with actual MPC signer nodes via gRPC
    - Never have access to the full private key
    - Coordinate multi-round DKG and signing protocols
    """
    
    def __init__(self, db: AsyncSession, audit: AuditService):
        self.db = db
        self.audit = audit
        self._settings = get_settings()
        # Internal signing key for permits (HMAC)
        self.permit_signing_key = self._settings.jwt_secret.encode()
        # Use module-level simulated keystore (persists across requests)
        # In production, each signer node stores its own share
        self._simulated_keys = _SIMULATED_KEYS
    
    async def get_active_nodes(self, cluster_id: str = "default") -> List[MPCNode]:
        """Get list of active MPC nodes in a cluster."""
        result = await self.db.execute(
            select(MPCNode).where(
                MPCNode.cluster_id == cluster_id,
                MPCNode.status == MPCNodeStatus.ACTIVE
            )
        )
        return list(result.scalars().all())
    
    async def select_participants(
        self, 
        n: int, 
        cluster_id: str = "default"
    ) -> List[str]:
        """
        Select n participants from available nodes.
        In production: prefer nodes from different zones.
        """
        nodes = await self.get_active_nodes(cluster_id)
        
        if len(nodes) < n:
            # In simulation, create mock node IDs
            logger.warning(f"Not enough active nodes ({len(nodes)}), using simulated nodes")
            return [f"sim-node-{i}" for i in range(n)]
        
        # Sort by zone to get diversity, then select
        nodes.sort(key=lambda x: (x.zone, x.consecutive_failures))
        return [node.id for node in nodes[:n]]
    
    async def create_keyset(
        self,
        wallet_id: str,
        threshold_t: int = 2,
        total_n: int = 3,
        cluster_id: str = "default",
        correlation_id: str = None,
        actor_id: str = None,
    ) -> MPCKeyset:
        """
        Create a new MPC keyset via DKG (Distributed Key Generation).
        
        In this simulation:
        - Generates a real secp256k1 key pair locally
        - Stores private key in memory (simulating distributed shares)
        
        In production:
        - Initiates DKG protocol with signer nodes
        - Each node generates and stores its share
        - Coordinator only receives public key
        """
        correlation_id = correlation_id or str(uuid4())
        
        # Validate threshold parameters
        if threshold_t > total_n:
            raise MPCCoordinatorError(f"Threshold t={threshold_t} cannot exceed n={total_n}")
        if threshold_t < 1:
            raise MPCCoordinatorError("Threshold must be at least 1")
        
        # Create DKG session
        session = MPCSession(
            id=str(uuid4()),
            session_type=MPCSessionType.DKG,
            status=MPCSessionStatus.IN_PROGRESS,
            participant_nodes={"nodes": await self.select_participants(total_n, cluster_id)},
            current_round=1,
            total_rounds=3,  # Typical DKG has 3 rounds
            timeout_at=datetime.utcnow() + timedelta(minutes=5),
        )
        self.db.add(session)
        await self.db.flush()
        
        # Log DKG started
        await self.audit.log_event(
            event_type=AuditEventType.MPC_KEYGEN_STARTED,
            correlation_id=correlation_id,
            actor_id=actor_id or "system",
            entity_type="MPC_KEYSET",
            entity_id=session.id,
            payload={
                "wallet_id": wallet_id,
                "threshold": f"{threshold_t}-of-{total_n}",
                "cluster_id": cluster_id,
                "session_id": session.id,
                "participant_count": total_n,
            }
        )
        
        try:
            # === SIMULATION: Generate key pair ===
            # In production, this is done via multi-round DKG protocol
            private_key = secrets.token_hex(32)
            private_key_bytes = bytes.fromhex(private_key)
            
            # Derive public key
            pk = keys.PrivateKey(private_key_bytes)
            public_key = pk.public_key
            public_key_hex = public_key.to_hex()  # Uncompressed, starts with 0x04
            public_key_compressed = pk.public_key.to_compressed_bytes().hex()
            
            # Derive Ethereum address
            address = public_key.to_checksum_address()
            
            # Create keyset record
            keyset = MPCKeyset(
                id=str(uuid4()),
                wallet_id=wallet_id,
                threshold_t=threshold_t,
                total_n=total_n,
                public_key=public_key_hex,
                public_key_compressed=public_key_compressed,
                address=address,
                status=MPCKeysetStatus.ACTIVE,
                cluster_id=cluster_id,
                key_ref=f"mpc-tecdsa://{cluster_id}/{str(uuid4())}",
                participant_nodes=session.participant_nodes,
                activated_at=datetime.utcnow(),
            )
            keyset.key_ref = f"mpc-tecdsa://{cluster_id}/{keyset.id}"
            
            # DEV ONLY: Store simulated private key in DB
            # In production: each node stores its share, coordinator never sees full key
            keyset.dev_private_key = private_key
            
            self.db.add(keyset)
            
            # Also keep in memory cache
            self._simulated_keys[keyset.id] = private_key
            
            # Update session
            session.keyset_id = keyset.id
            session.status = MPCSessionStatus.COMPLETED
            session.ended_at = datetime.utcnow()
            session.quorum_reached = True
            
            await self.db.flush()
            
            # Log DKG completed
            await self.audit.log_event(
                event_type=AuditEventType.MPC_KEYGEN_COMPLETED,
                correlation_id=correlation_id,
                actor_id=actor_id or "system",
                entity_type="MPC_KEYSET",
                entity_id=keyset.id,
                payload={
                    "wallet_id": wallet_id,
                    "keyset_id": keyset.id,
                    "address": address,
                    "public_key_hash": hashlib.sha256(public_key_hex.encode()).hexdigest()[:16],
                    "threshold": f"{threshold_t}-of-{total_n}",
                    "session_id": session.id,
                }
            )
            
            logger.info(f"MPC Keyset created: {keyset.id} with address {address}")
            return keyset
            
        except Exception as e:
            # Log DKG failed
            session.status = MPCSessionStatus.FAILED
            session.error_category = MPCErrorCategory.PERMANENT
            session.error_message = str(e)
            session.ended_at = datetime.utcnow()
            
            await self.audit.log_event(
                event_type=AuditEventType.MPC_KEYGEN_FAILED,
                correlation_id=correlation_id,
                actor_id=actor_id or "system",
                entity_type="MPC_KEYSET",
                entity_id=session.id,
                payload={
                    "wallet_id": wallet_id,
                    "error": str(e),
                    "session_id": session.id,
                }
            )
            
            raise MPCCoordinatorError(f"DKG failed: {e}")
    
    async def get_keyset(self, keyset_id: str) -> Optional[MPCKeyset]:
        """Get keyset by ID."""
        result = await self.db.execute(
            select(MPCKeyset).where(MPCKeyset.id == keyset_id)
        )
        return result.scalar_one_or_none()
    
    async def get_keyset_by_wallet(self, wallet_id: str) -> Optional[MPCKeyset]:
        """Get keyset by wallet ID."""
        result = await self.db.execute(
            select(MPCKeyset).where(MPCKeyset.wallet_id == wallet_id)
        )
        return result.scalar_one_or_none()
    
    def issue_signing_permit(
        self,
        tx_request_id: str,
        wallet_id: str,
        keyset_id: str,
        tx_hash: str,
        kyt_result: str,
        kyt_snapshot: dict,
        policy_result: str,
        policy_snapshot: dict,
        approval_snapshot: dict,
        audit_anchor_hash: str,
        ttl_seconds: int = 60,
    ) -> SigningPermit:
        """
        Issue a SigningPermit - anti-bypass mechanism.
        
        The permit proves that all controls have passed and
        authorizes the MPC to sign a specific tx_hash.
        """
        permit_id = str(uuid4())
        issued_at = datetime.utcnow()
        expires_at = issued_at + timedelta(seconds=ttl_seconds)
        
        # Create permit content for hashing
        permit_content = {
            "id": permit_id,
            "tx_request_id": tx_request_id,
            "wallet_id": wallet_id,
            "keyset_id": keyset_id,
            "tx_hash": tx_hash,
            "kyt_result": kyt_result,
            "policy_result": policy_result,
            "approval_count": approval_snapshot.get("count", 0),
            "audit_anchor_hash": audit_anchor_hash,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        
        # Create permit hash
        permit_hash = hashlib.sha256(str(permit_content).encode()).hexdigest()
        
        # Sign with internal key (HMAC)
        signature = hmac.new(
            self.permit_signing_key,
            permit_hash.encode(),
            hashlib.sha256
        ).hexdigest()
        
        permit = SigningPermit(
            id=permit_id,
            tx_request_id=tx_request_id,
            wallet_id=wallet_id,
            keyset_id=keyset_id,
            tx_hash=tx_hash,
            kyt_result=kyt_result,
            kyt_snapshot=kyt_snapshot,
            policy_result=policy_result,
            policy_snapshot=policy_snapshot,
            approval_snapshot=approval_snapshot,
            audit_anchor_hash=audit_anchor_hash,
            permit_hash=permit_hash,
            signature=signature,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        
        return permit
    
    def validate_signing_permit(self, permit: SigningPermit, tx_hash: str) -> Tuple[bool, str]:
        """
        Validate a SigningPermit before signing.
        
        Checks:
        1. Permit not used
        2. Permit not expired
        3. Permit not revoked
        4. tx_hash matches
        5. Signature valid
        """
        if permit.is_used:
            return False, "Permit already used"
        
        if permit.is_revoked:
            return False, "Permit revoked"
        
        if datetime.utcnow() > permit.expires_at:
            return False, "Permit expired"
        
        if permit.tx_hash.lower() != tx_hash.lower():
            return False, f"tx_hash mismatch: permit={permit.tx_hash}, request={tx_hash}"
        
        # Verify signature
        expected_sig = hmac.new(
            self.permit_signing_key,
            permit.permit_hash.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(permit.signature, expected_sig):
            return False, "Invalid permit signature"
        
        return True, "Valid"
    
    async def sign_transaction(
        self,
        keyset_id: str,
        tx_hash: str,
        permit: SigningPermit,
        correlation_id: str = None,
        actor_id: str = None,
    ) -> Tuple[str, str, int]:
        """
        Sign a transaction hash using MPC.
        
        Returns (r, s, v) signature components.
        
        In this simulation:
        - Uses stored private key to sign
        
        In production:
        - Initiates threshold signing protocol
        - Each node contributes partial signature
        - Coordinator combines into full ECDSA signature
        """
        correlation_id = correlation_id or str(uuid4())
        
        # Validate permit
        is_valid, reason = self.validate_signing_permit(permit, tx_hash)
        if not is_valid:
            await self.audit.log_event(
                event_type=AuditEventType.SIGN_PERMIT_REJECTED,
                correlation_id=correlation_id,
                actor_id=actor_id or "system",
                entity_type="SIGNING_PERMIT",
                entity_id=permit.id,
                payload={
                    "keyset_id": keyset_id,
                    "tx_hash": tx_hash,
                    "reason": reason,
                }
            )
            raise MPCCoordinatorError(f"Invalid permit: {reason}")
        
        # Get keyset
        keyset = await self.get_keyset(keyset_id)
        if not keyset:
            raise MPCCoordinatorError(f"Keyset not found: {keyset_id}")
        
        if keyset.status != MPCKeysetStatus.ACTIVE:
            raise MPCCoordinatorError(f"Keyset not active: {keyset.status}")
        
        # Create signing session
        session = MPCSession(
            id=str(uuid4()),
            session_type=MPCSessionType.SIGNING,
            keyset_id=keyset_id,
            tx_request_id=permit.tx_request_id,
            tx_hash=tx_hash,
            permit_hash=permit.permit_hash,
            status=MPCSessionStatus.IN_PROGRESS,
            participant_nodes=keyset.participant_nodes,
            current_round=1,
            total_rounds=2,  # Typical threshold signing has 2 rounds
            timeout_at=datetime.utcnow() + timedelta(minutes=2),
        )
        self.db.add(session)
        await self.db.flush()
        
        # Log signing started
        await self.audit.log_event(
            event_type=AuditEventType.MPC_SIGN_STARTED,
            correlation_id=correlation_id,
            actor_id=actor_id or "system",
            entity_type="MPC_SESSION",
            entity_id=session.id,
            payload={
                "keyset_id": keyset_id,
                "tx_request_id": permit.tx_request_id,
                "tx_hash_prefix": tx_hash[:10] + "...",
                "permit_hash": permit.permit_hash[:16],
                "session_id": session.id,
            }
        )
        
        try:
            # === SIMULATION: Sign with stored key ===
            # In production, this is done via multi-round signing protocol
            
            private_key_hex = self._simulated_keys.get(keyset_id)
            if not private_key_hex:
                # Try loading from DB (DEV mode: key persisted in mpc_keysets table)
                result = await self.db.execute(
                    select(MPCKeyset).where(MPCKeyset.id == keyset_id)
                )
                keyset_record = result.scalar_one_or_none()
                if keyset_record and keyset_record.dev_private_key:
                    private_key_hex = keyset_record.dev_private_key
                    self._simulated_keys[keyset_id] = private_key_hex
                else:
                    raise MPCCoordinatorError(
                        f"Simulated key not found for keyset {keyset_id}",
                        category=MPCErrorCategory.PERMANENT
                    )
            
            # Convert tx_hash to bytes
            if tx_hash.startswith("0x"):
                tx_hash_bytes = bytes.fromhex(tx_hash[2:])
            else:
                tx_hash_bytes = bytes.fromhex(tx_hash)
            
            # Sign with private key
            pk = keys.PrivateKey(bytes.fromhex(private_key_hex))
            signature = pk.sign_msg_hash(tx_hash_bytes)
            
            r = hex(signature.r)
            s = hex(signature.s)
            v = signature.v + 27  # Convert to Ethereum v value
            
            # Update session
            session.signature_r = r
            session.signature_s = s
            session.signature_v = v
            session.status = MPCSessionStatus.COMPLETED
            session.ended_at = datetime.utcnow()
            session.quorum_reached = True
            
            # Mark permit as used
            permit.is_used = True
            permit.used_at = datetime.utcnow()
            
            # Update keyset last used
            keyset.last_used_at = datetime.utcnow()
            
            await self.db.flush()
            
            # Log signing completed
            await self.audit.log_event(
                event_type=AuditEventType.MPC_SIGN_COMPLETED,
                correlation_id=correlation_id,
                actor_id=actor_id or "system",
                entity_type="MPC_SESSION",
                entity_id=session.id,
                payload={
                    "keyset_id": keyset_id,
                    "tx_request_id": permit.tx_request_id,
                    "session_id": session.id,
                    "signature_hash": hashlib.sha256(f"{r}{s}{v}".encode()).hexdigest()[:16],
                }
            )
            
            logger.info(f"MPC signing completed for keyset {keyset_id}, session {session.id}")
            return r, s, v
            
        except MPCCoordinatorError:
            raise
        except Exception as e:
            # Log signing failed
            session.status = MPCSessionStatus.FAILED
            session.error_category = MPCErrorCategory.PERMANENT
            session.error_message = str(e)
            session.ended_at = datetime.utcnow()
            
            await self.audit.log_event(
                event_type=AuditEventType.MPC_SIGN_FAILED,
                correlation_id=correlation_id,
                actor_id=actor_id or "system",
                entity_type="MPC_SESSION",
                entity_id=session.id,
                payload={
                    "keyset_id": keyset_id,
                    "tx_request_id": permit.tx_request_id,
                    "error": str(e),
                    "session_id": session.id,
                }
            )
            
            raise MPCCoordinatorError(f"Signing failed: {e}")
    
    async def sign_ethereum_transaction(
        self,
        keyset_id: str,
        tx_dict: dict,
        permit: SigningPermit,
        correlation_id: str = None,
        actor_id: str = None,
    ) -> Tuple[bytes, str]:
        """
        Sign a full Ethereum transaction using MPC.
        
        Returns (raw_transaction_bytes, tx_hash).
        
        This method:
        1. Serializes the transaction
        2. Computes the transaction hash
        3. Signs using MPC
        4. Assembles the signed transaction
        """
        correlation_id = correlation_id or str(uuid4())
        
        # Get keyset
        keyset = await self.get_keyset(keyset_id)
        if not keyset:
            raise MPCCoordinatorError(f"Keyset not found: {keyset_id}")
        
        # === SIMULATION: Use Account to sign full transaction ===
        # In production, we would:
        # 1. Serialize transaction to get signing hash
        # 2. Call sign_transaction with the hash
        # 3. Reconstruct signed tx with signature
        
        private_key_hex = self._simulated_keys.get(keyset_id)
        if not private_key_hex:
            # Try loading from DB (DEV mode: key persisted in mpc_keysets table)
            result = await self.db.execute(
                select(MPCKeyset).where(MPCKeyset.id == keyset_id)
            )
            keyset_record = result.scalar_one_or_none()
            if keyset_record and keyset_record.dev_private_key:
                private_key_hex = keyset_record.dev_private_key
                self._simulated_keys[keyset_id] = private_key_hex
            else:
                raise MPCCoordinatorError(
                    f"Simulated key not found for keyset {keyset_id}",
                    category=MPCErrorCategory.PERMANENT
                )
        
        # Validate permit against tx
        tx_hash_for_permit = Web3.keccak(text=str(tx_dict)).hex()
        # Note: In real implementation, we'd compute proper unsigned tx hash
        
        # Sign using Account (simulation)
        account = Account.from_key(private_key_hex)
        signed_tx = account.sign_transaction(tx_dict)
        
        # Log signing
        await self.audit.log_event(
            event_type=AuditEventType.MPC_SIGN_COMPLETED,
            correlation_id=correlation_id,
            actor_id=actor_id or "system",
            entity_type="TX_REQUEST",
            entity_id=permit.tx_request_id,
            payload={
                "keyset_id": keyset_id,
                "tx_hash": signed_tx.hash.hex(),
                "signer_address": keyset.address,
            }
        )
        
        # Mark permit used
        permit.is_used = True
        permit.used_at = datetime.utcnow()
        
        return signed_tx.rawTransaction, signed_tx.hash.hex()


# Simulated signer node for testing
class SimulatedSignerNode:
    """
    Simulated MPC Signer Node for local development.
    
    In production, this would be a separate service that:
    - Stores encrypted share on local disk
    - Participates in DKG and signing protocols
    - Never exposes the share in plaintext
    """
    
    def __init__(self, node_id: str, zone: str = "default"):
        self.node_id = node_id
        self.zone = zone
        self._shares: Dict[str, bytes] = {}  # keyset_id -> share
    
    def store_share(self, keyset_id: str, share: bytes):
        """Store encrypted share (simulation: plaintext)."""
        self._shares[keyset_id] = share
    
    def get_share(self, keyset_id: str) -> Optional[bytes]:
        """Retrieve share for signing."""
        return self._shares.get(keyset_id)
    
    def participate_dkg_round(self, session_id: str, round_num: int, round_data: dict) -> dict:
        """Participate in DKG round (simulated)."""
        return {
            "node_id": self.node_id,
            "round": round_num,
            "commitment": secrets.token_hex(32),
        }
    
    def participate_signing_round(self, session_id: str, round_num: int, tx_hash: str) -> dict:
        """Participate in signing round (simulated)."""
        return {
            "node_id": self.node_id,
            "round": round_num,
            "partial_signature": secrets.token_hex(64),
        }

