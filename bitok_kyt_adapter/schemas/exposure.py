"""Exposure schemas for BitOK KYT API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import ExposureCheckState, RiskLevel


class ExposureEntry(BaseModel):
    """Single exposure entry showing fund source/destination."""

    entity_name: str | None = Field(default=None, description="Known entity name")
    entity_category: str | None = Field(default=None, description="Entity category")
    risk_level: RiskLevel = Field(
        default=RiskLevel.UNDEFINED, description="Risk level"
    )
    exposure_percent: float = Field(..., description="Exposure percentage (0-100)")
    amount: str | None = Field(default=None, description="Exposure amount")


class TransferExposure(BaseModel):
    """Exposure analysis for a transfer."""

    transfer_id: int = Field(..., description="Transfer ID")
    check_state: ExposureCheckState = Field(
        default=ExposureCheckState.NONE, description="Check state"
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.UNDEFINED, description="Overall risk level"
    )
    direct_exposure: list[ExposureEntry] = Field(
        default_factory=list, description="Direct exposure entries"
    )
    indirect_exposure: list[ExposureEntry] = Field(
        default_factory=list, description="Indirect exposure entries"
    )


class AddressExposure(BaseModel):
    """Exposure analysis for an address."""

    address: str = Field(..., description="Address analyzed")
    check_state: ExposureCheckState = Field(
        default=ExposureCheckState.NONE, description="Check state"
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.UNDEFINED, description="Overall risk level"
    )
    incoming_exposure: list[ExposureEntry] = Field(
        default_factory=list, description="Incoming fund exposure"
    )
    outgoing_exposure: list[ExposureEntry] = Field(
        default_factory=list, description="Outgoing fund exposure"
    )
