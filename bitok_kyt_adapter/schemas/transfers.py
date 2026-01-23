"""Transfer schemas for BitOK KYT API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import PaginatedResponse
from .enums import (
    CounterpartyCheckState,
    ExposureCheckState,
    RiskLevel,
    TransferDirection,
    TxStatus,
)


class RegisterTransferRequest(BaseModel):
    """Request to register a new transfer."""

    direction: TransferDirection = Field(..., description="Transfer direction")
    network: str = Field(..., description="Network code (e.g., 'eth', 'btc')")
    token: str | None = Field(
        default=None, description="Token symbol (None for native asset)"
    )
    tx_hash: str | None = Field(default=None, description="Transaction hash if known")
    address: str = Field(..., description="Counterparty address")
    output_index: int | None = Field(
        default=None, description="Output index for UTXO chains"
    )
    amount: str | None = Field(default=None, description="Transfer amount")
    client_id: str | None = Field(default=None, description="Your internal client ID")
    transfer_id: str | None = Field(
        default=None, description="Your internal transfer ID"
    )


class RegisterTransferAttemptRequest(BaseModel):
    """Request to register a transfer attempt (pre-screening)."""

    direction: TransferDirection = Field(..., description="Transfer direction")
    network: str = Field(..., description="Network code")
    token: str | None = Field(default=None, description="Token symbol")
    address: str = Field(..., description="Counterparty address")
    amount: str | None = Field(default=None, description="Transfer amount")
    client_id: str | None = Field(default=None, description="Your internal client ID")
    transfer_id: str | None = Field(
        default=None, description="Your internal transfer ID"
    )


class BindTransactionRequest(BaseModel):
    """Request to bind a transaction to a registered transfer."""

    tx_hash: str = Field(..., description="Transaction hash")
    output_index: int | None = Field(
        default=None, description="Output index for UTXO chains"
    )


class RegisteredTransfer(BaseModel):
    """Registered transfer with check state."""

    id: int = Field(..., description="Transfer ID in BitOK system")
    direction: TransferDirection = Field(..., description="Transfer direction")
    network: str = Field(..., description="Network code")
    token: str | None = Field(default=None, description="Token symbol")
    tx_hash: str | None = Field(default=None, description="Transaction hash")
    address: str = Field(..., description="Counterparty address")
    output_index: int | None = Field(default=None, description="Output index")
    amount: str | None = Field(default=None, description="Transfer amount")
    client_id: str | None = Field(default=None, description="Your internal client ID")
    transfer_id: str | None = Field(
        default=None, description="Your internal transfer ID"
    )
    tx_status: TxStatus = Field(
        default=TxStatus.NONE, description="Transaction binding status"
    )
    exposure_check_state: ExposureCheckState = Field(
        default=ExposureCheckState.NONE, description="Exposure check state"
    )
    counterparty_check_state: CounterpartyCheckState = Field(
        default=CounterpartyCheckState.NONE, description="Counterparty check state"
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.UNDEFINED, description="Overall risk level"
    )
    created_at: datetime | None = Field(default=None, description="Creation timestamp")
    updated_at: datetime | None = Field(
        default=None, description="Last update timestamp"
    )


class Counterparty(BaseModel):
    """Counterparty information for a transfer."""

    address: str = Field(..., description="Counterparty address")
    entity_name: str | None = Field(default=None, description="Known entity name")
    entity_category: str | None = Field(default=None, description="Entity category")
    risk_level: RiskLevel = Field(
        default=RiskLevel.UNDEFINED, description="Counterparty risk level"
    )
    check_state: CounterpartyCheckState = Field(
        default=CounterpartyCheckState.NONE, description="Check state"
    )


# Type alias for paginated response
TransferListResponse = PaginatedResponse[RegisteredTransfer]
