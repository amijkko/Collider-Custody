"""Basic reference data schemas for BitOK KYT API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import PaginatedResponse


class Network(BaseModel):
    """Blockchain network."""

    id: int = Field(..., description="Network ID")
    name: str = Field(..., description="Network name")
    code: str = Field(..., description="Network code (e.g., 'eth', 'btc')")
    is_active: bool = Field(default=True, description="Whether network is active")


class Token(BaseModel):
    """Token/asset on a network."""

    id: int = Field(..., description="Token ID")
    name: str = Field(..., description="Token name")
    symbol: str = Field(..., description="Token symbol")
    network_id: int = Field(..., description="Network ID this token belongs to")
    contract_address: str | None = Field(
        default=None, description="Contract address for non-native tokens"
    )
    decimals: int = Field(default=18, description="Token decimals")
    is_active: bool = Field(default=True, description="Whether token is active")


class EntityCategory(BaseModel):
    """Entity category for risk classification."""

    id: int = Field(..., description="Category ID")
    name: str = Field(..., description="Category name")
    description: str | None = Field(default=None, description="Category description")
    risk_level: str | None = Field(
        default=None, description="Default risk level for this category"
    )


# Type aliases for paginated responses
NetworkListResponse = PaginatedResponse[Network]
TokenListResponse = PaginatedResponse[Token]
EntityCategoryListResponse = PaginatedResponse[EntityCategory]
