"""MPC (Multi-Party Computation) models for tECDSA signing."""
import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Enum, DateTime, Integer, Text, ForeignKey, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CustodyBackend(str, enum.Enum):
    """Custody backend type for wallets."""
    DEV_SIGNER = "DEV_SIGNER"  # Local dev key (current implementation)
    MPC_TECDSA = "MPC_TECDSA"  # Threshold ECDSA via MPC


class MPCKeysetStatus(str, enum.Enum):
    """Status of MPC keyset generation."""
    PENDING = "PENDING"  # DKG not started
    DKG_IN_PROGRESS = "DKG_IN_PROGRESS"  # DKG running
    ACTIVE = "ACTIVE"  # Ready for signing
    ROTATING = "ROTATING"  # Key rotation in progress
    COMPROMISED = "COMPROMISED"  # Marked as compromised
    ARCHIVED = "ARCHIVED"  # No longer in use


class MPCSessionType(str, enum.Enum):
    """Type of MPC session."""
    DKG = "DKG"  # Distributed Key Generation
    SIGNING = "SIGNING"  # Transaction signing
    REFRESH = "REFRESH"  # Share refresh
    BACKUP = "BACKUP"  # Share backup


class MPCSessionStatus(str, enum.Enum):
    """Status of MPC session."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class MPCNodeStatus(str, enum.Enum):
    """Status of MPC signer node."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    QUARANTINED = "QUARANTINED"  # Protocol violation detected
    MAINTENANCE = "MAINTENANCE"


class MPCErrorCategory(str, enum.Enum):
    """Error taxonomy for MPC operations."""
    TRANSIENT = "TRANSIENT"  # Network timeout, node unavailable - can retry
    PERMANENT = "PERMANENT"  # Invalid permit, hash mismatch - terminal failure
    PROTOCOL_VIOLATION = "PROTOCOL_VIOLATION"  # Bad share, invalid response - quarantine


class MPCKeyset(Base):
    """
    MPC Keyset - represents a distributed key created via tECDSA DKG.
    No full private key exists - only shares on signer nodes.
    """
    __tablename__ = "mpc_keysets"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # Link to wallet
    wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("wallets.id"), unique=True, nullable=False, index=True)
    
    # Threshold parameters
    threshold_t: Mapped[int] = mapped_column(Integer, nullable=False)  # t signatures required
    total_n: Mapped[int] = mapped_column(Integer, nullable=False)  # n total parties
    
    # Public key and derived address
    public_key: Mapped[str] = mapped_column(String(130), nullable=False)  # Uncompressed secp256k1 pubkey (hex)
    public_key_compressed: Mapped[str] = mapped_column(String(66), nullable=False)  # Compressed pubkey
    address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)  # Derived EOA address
    
    # Status
    status: Mapped[MPCKeysetStatus] = mapped_column(Enum(MPCKeysetStatus, name='mpckeyset_status'), default=MPCKeysetStatus.PENDING)
    
    # Metadata
    cluster_id: Mapped[str] = mapped_column(String(255), nullable=False, default="default")  # MPC cluster identifier
    key_ref: Mapped[str] = mapped_column(String(512), nullable=False)  # URI: mpc-tecdsa://<cluster>/<keyset_id>
    
    # Participating nodes
    participant_nodes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # List of node IDs
    
    # DEV ONLY: Simulated private key (encrypted) - NOT FOR PRODUCTION
    # In production, private key shares are stored only on signer nodes
    dev_private_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_mpc_keysets_status", "status"),
    )


class MPCSession(Base):
    """
    MPC Session - tracks DKG and signing operations.
    Does NOT store secrets.
    """
    __tablename__ = "mpc_sessions"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # Session type
    session_type: Mapped[MPCSessionType] = mapped_column(Enum(MPCSessionType, name='mpcsession_type'), nullable=False)
    
    # References
    keyset_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("mpc_keysets.id"), nullable=True, index=True)
    tx_request_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("tx_requests.id"), nullable=True, index=True)
    
    # For signing sessions
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)  # Hash being signed
    signature_r: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    signature_s: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    signature_v: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Permit (for signing)
    permit_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SigningPermit hash
    
    # Status
    status: Mapped[MPCSessionStatus] = mapped_column(Enum(MPCSessionStatus, name='mpcsession_status'), default=MPCSessionStatus.PENDING, index=True)
    
    # Participating nodes
    participant_nodes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    quorum_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Error tracking
    error_category: Mapped[Optional[MPCErrorCategory]] = mapped_column(Enum(MPCErrorCategory, name='mpcerror_category'), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    timeout_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Rounds tracking
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    total_rounds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    __table_args__ = (
        Index("ix_mpc_sessions_type_status", "session_type", "status"),
    )


class MPCNode(Base):
    """
    MPC Signer Node - registry of nodes participating in MPC protocol.
    Nodes store encrypted shares locally.
    """
    __tablename__ = "mpc_nodes"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # Node identification
    node_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(255), nullable=False, default="default", index=True)
    
    # Network endpoint
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)  # gRPC or HTTP endpoint
    
    # Trust zone (for distributing nodes across zones)
    zone: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    
    # Status
    status: Mapped[MPCNodeStatus] = mapped_column(Enum(MPCNodeStatus, name='mpcnode_status'), default=MPCNodeStatus.INACTIVE, index=True)
    
    # Health tracking
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    
    # Protocol violation tracking
    quarantine_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quarantined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Metadata
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Node software version
    capabilities: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Supported protocols
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SigningPermit(Base):
    """
    SigningPermit - anti-bypass mechanism for MPC signing.
    Ensures MPC Coordinator only signs after all controls pass.
    """
    __tablename__ = "signing_permits"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    
    # References
    tx_request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tx_requests.id"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("wallets.id"), nullable=False)
    keyset_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mpc_keysets.id"), nullable=False)
    
    # Transaction data
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)  # Hash to be signed
    
    # Control snapshots (proof that controls passed)
    kyt_result: Mapped[str] = mapped_column(String(50), nullable=False)
    kyt_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    policy_result: Mapped[str] = mapped_column(String(50), nullable=False)  # ALLOWED
    policy_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    approval_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)  # Who approved, count, required
    
    # Audit chain anchor
    audit_anchor_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # Links to audit chain
    
    # Security
    permit_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # Hash of permit content
    signature: Mapped[str] = mapped_column(Text, nullable=False)  # HMAC signature by internal key
    
    # Validity
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # TTL enforcement
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # One-time use
    
    # Status
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    
    __table_args__ = (
        Index("ix_signing_permits_tx_request", "tx_request_id"),
        Index("ix_signing_permits_expires", "expires_at"),
    )

