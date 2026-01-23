"""Risk schemas for BitOK KYT API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import PaginatedResponse
from .enums import RiskLevel


class Risk(BaseModel):
    """Individual risk finding."""

    id: int = Field(..., description="Risk ID")
    risk_level: RiskLevel = Field(..., description="Risk level")
    category: str = Field(..., description="Risk category")
    description: str = Field(..., description="Risk description")
    entity_name: str | None = Field(default=None, description="Related entity name")
    exposure_percent: float | None = Field(
        default=None, description="Exposure percentage if applicable"
    )
    amount: str | None = Field(default=None, description="Related amount if applicable")


# Type alias for paginated response
RiskListResponse = PaginatedResponse[Risk]
