"""Transaction request schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

from app.models.tx_request import TxType, TxStatus


class TxRequestCreate(BaseModel):
    """Schema for creating a transaction request."""
    wallet_id: str
    tx_type: TxType
    to_address: str = Field(..., min_length=42, max_length=42)
    asset: str = Field(default="ETH", max_length=50)
    amount: Decimal = Field(..., gt=0)
    data: Optional[str] = None  # For CONTRACT_CALL
    
    @field_validator("to_address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate Ethereum address format."""
        if not v.startswith("0x"):
            raise ValueError("Address must start with 0x")
        if len(v) != 42:
            raise ValueError("Address must be 42 characters")
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("Invalid hex address")
        return v.lower()
    
    class Config:
        json_schema_extra = {
            "example": {
                "wallet_id": "550e8400-e29b-41d4-a716-446655440000",
                "tx_type": "TRANSFER",
                "to_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD20",
                "asset": "ETH",
                "amount": "1.5"
            }
        }


class TxRequestResponse(BaseModel):
    """Schema for transaction request response."""
    id: str
    wallet_id: str
    tx_type: TxType
    to_address: str
    asset: str
    amount: Decimal
    data: Optional[str]
    status: TxStatus
    kyt_result: Optional[str]
    kyt_case_id: Optional[str]
    policy_result: Optional[dict]
    requires_approval: bool
    required_approvals: int
    tx_hash: Optional[str]
    block_number: Optional[int]
    confirmations: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    approvals: List["ApprovalResponse"] = []
    
    class Config:
        from_attributes = True


class ApprovalCreate(BaseModel):
    """Schema for approving/rejecting a transaction."""
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    comment: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "decision": "APPROVED",
                "comment": "Reviewed and approved for processing"
            }
        }


class ApprovalResponse(BaseModel):
    """Schema for approval response."""
    id: str
    tx_request_id: str
    user_id: str
    decision: str
    comment: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class KYTCaseResponse(BaseModel):
    """Schema for KYT case response."""
    id: str
    address: str
    direction: str
    reason: str
    status: str
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    resolution_comment: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class KYTCaseResolve(BaseModel):
    """Schema for resolving a KYT case."""
    decision: str = Field(..., pattern="^(ALLOW|BLOCK)$")
    comment: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "decision": "ALLOW",
                "comment": "Verified legitimate transaction after manual review"
            }
        }


# Update forward references
TxRequestResponse.model_rebuild()

