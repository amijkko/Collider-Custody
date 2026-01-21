"""Policy schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

from app.models.policy import PolicyType


class PolicyCreate(BaseModel):
    """Schema for creating a policy."""
    name: str = Field(..., min_length=1, max_length=255)
    policy_type: PolicyType
    address: Optional[str] = Field(None, min_length=42, max_length=42)
    token: Optional[str] = Field(None, min_length=42, max_length=42)
    wallet_id: Optional[str] = None
    wallet_type: Optional[str] = None
    limit_amount: Optional[Decimal] = Field(None, gt=0)
    required_approvals: int = Field(default=0, ge=0)
    config: Optional[dict] = None
    is_active: bool = True
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Treasury Daily Limit",
                "policy_type": "DAILY_LIMIT",
                "wallet_type": "TREASURY",
                "limit_amount": "100.0",
                "required_approvals": 2
            }
        }


class PolicyResponse(BaseModel):
    """Schema for policy response."""
    id: str
    name: str
    policy_type: PolicyType
    address: Optional[str]
    token: Optional[str]
    wallet_id: Optional[str]
    wallet_type: Optional[str]
    limit_amount: Optional[Decimal]
    required_approvals: int
    config: Optional[dict]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    
    class Config:
        from_attributes = True

