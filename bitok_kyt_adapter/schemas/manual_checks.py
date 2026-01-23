"""Manual check schemas for BitOK KYT API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import PaginatedResponse
from .enums import ManualCheckStatus, RiskLevel


class CheckTransferRequest(BaseModel):
    """Request to manually check a transfer."""

    network: str = Field(..., description="Network code")
    token: str | None = Field(default=None, description="Token symbol")
    tx_hash: str = Field(..., description="Transaction hash")
    output_index: int | None = Field(
        default=None, description="Output index for UTXO chains"
    )


class CheckAddressRequest(BaseModel):
    """Request to manually check an address."""

    network: str = Field(..., description="Network code")
    address: str = Field(..., description="Address to check")


class ManualCheck(BaseModel):
    """Manual check result."""

    id: int = Field(..., description="Check ID")
    status: ManualCheckStatus = Field(..., description="Check status")
    check_type: str = Field(..., description="Type: 'transfer' or 'address'")
    network: str = Field(..., description="Network code")
    token: str | None = Field(default=None, description="Token symbol")
    tx_hash: str | None = Field(default=None, description="Transaction hash")
    address: str | None = Field(default=None, description="Address")
    output_index: int | None = Field(default=None, description="Output index")
    risk_level: RiskLevel = Field(
        default=RiskLevel.UNDEFINED, description="Overall risk level"
    )
    created_at: datetime | None = Field(default=None, description="Creation timestamp")
    updated_at: datetime | None = Field(
        default=None, description="Last update timestamp"
    )


# Type alias for paginated response
ManualCheckListResponse = PaginatedResponse[ManualCheck]
