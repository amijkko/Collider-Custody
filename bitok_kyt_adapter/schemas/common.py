"""Common schemas for BitOK KYT API."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters for list requests."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""

    count: int = Field(..., description="Total number of items")
    next: str | None = Field(default=None, description="URL for next page")
    previous: str | None = Field(default=None, description="URL for previous page")
    results: list[T] = Field(default_factory=list, description="List of items")
