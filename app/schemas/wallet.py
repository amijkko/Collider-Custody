"""Wallet-related schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models.wallet import WalletType, RiskProfile, WalletRoleType, CustodyBackend, WalletStatus


class WalletCreate(BaseModel):
    """Schema for creating a new wallet."""
    wallet_type: WalletType
    subject_id: str = Field(..., min_length=1, max_length=255)
    tags: Optional[dict] = None
    risk_profile: RiskProfile = RiskProfile.MEDIUM
    
    # MPC options
    custody_backend: CustodyBackend = CustodyBackend.DEV_SIGNER
    mpc_threshold_t: Optional[int] = Field(None, ge=1, description="Threshold t for t-of-n MPC")
    mpc_total_n: Optional[int] = Field(None, ge=1, description="Total n parties for t-of-n MPC")
    
    class Config:
        json_schema_extra = {
            "example": {
                "wallet_type": "TREASURY",
                "subject_id": "org-123",
                "tags": {"department": "finance"},
                "risk_profile": "HIGH",
                "custody_backend": "DEV_SIGNER"
            }
        }


class WalletCreateMPC(BaseModel):
    """Schema for creating a new MPC wallet."""
    wallet_type: WalletType
    subject_id: str = Field(..., min_length=1, max_length=255)
    tags: Optional[dict] = None
    risk_profile: RiskProfile = RiskProfile.MEDIUM
    mpc_threshold_t: int = Field(2, ge=1, description="Threshold t for t-of-n MPC")
    mpc_total_n: int = Field(3, ge=2, description="Total n parties for t-of-n MPC")
    cluster_id: str = Field("default", description="MPC cluster ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "wallet_type": "TREASURY",
                "subject_id": "org-123",
                "tags": {"department": "finance"},
                "risk_profile": "HIGH",
                "mpc_threshold_t": 2,
                "mpc_total_n": 3,
                "cluster_id": "default"
            }
        }


class WalletResponse(BaseModel):
    """Schema for wallet response."""
    id: str
    address: Optional[str]  # May be None for PENDING_KEYGEN
    wallet_type: WalletType
    subject_id: str
    tags: Optional[dict]
    risk_profile: RiskProfile
    custody_backend: CustodyBackend
    status: WalletStatus
    key_ref: Optional[str] = None
    mpc_keyset_id: Optional[str] = None
    mpc_threshold_t: Optional[int] = None
    mpc_total_n: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    roles: List["WalletRoleResponse"] = []
    
    class Config:
        from_attributes = True


class MPCKeysetResponse(BaseModel):
    """Schema for MPC keyset response."""
    id: str
    wallet_id: str
    threshold_t: int
    total_n: int
    public_key_compressed: str
    address: str
    status: str
    cluster_id: str
    key_ref: str
    created_at: datetime
    activated_at: Optional[datetime]
    last_used_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class WalletRoleAssign(BaseModel):
    """Schema for assigning a role to a wallet."""
    user_id: str
    role: WalletRoleType
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "role": "APPROVER"
            }
        }


class WalletRoleResponse(BaseModel):
    """Schema for wallet role response."""
    id: str
    wallet_id: str
    user_id: str
    role: WalletRoleType
    created_at: datetime
    created_by: str
    
    class Config:
        from_attributes = True


# Update forward references
WalletResponse.model_rebuild()

