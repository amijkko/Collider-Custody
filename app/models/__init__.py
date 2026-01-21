"""Database models package."""
from app.models.user import User, UserRole
from app.models.wallet import Wallet, WalletRole, WalletType, WalletRoleType, RiskProfile, CustodyBackend, WalletStatus
from app.models.tx_request import TxRequest, TxType, TxStatus, Approval, KYTCase, VALID_TRANSITIONS
from app.models.policy import Policy, PolicyType, DailyVolume
from app.models.audit import AuditEvent, AuditEventType, Deposit
from app.models.mpc import (
    MPCKeyset, MPCKeysetStatus,
    MPCSession, MPCSessionType, MPCSessionStatus,
    MPCNode, MPCNodeStatus,
    SigningPermit,
    MPCErrorCategory,
)

__all__ = [
    "User",
    "UserRole",
    "Wallet",
    "WalletRole",
    "WalletType",
    "WalletRoleType",
    "RiskProfile",
    "CustodyBackend",
    "WalletStatus",
    "TxRequest",
    "TxType",
    "TxStatus",
    "VALID_TRANSITIONS",
    "Approval",
    "KYTCase",
    "Policy",
    "PolicyType",
    "DailyVolume",
    "AuditEvent",
    "AuditEventType",
    "Deposit",
    # MPC models
    "MPCKeyset",
    "MPCKeysetStatus",
    "MPCSession",
    "MPCSessionType",
    "MPCSessionStatus",
    "MPCNode",
    "MPCNodeStatus",
    "SigningPermit",
    "MPCErrorCategory",
]
