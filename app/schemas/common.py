"""Common schema definitions."""
from datetime import datetime
from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel, Field

T = TypeVar("T")


class CorrelatedResponse(BaseModel, Generic[T]):
    """Response wrapper with correlation ID."""
    correlation_id: str = Field(..., description="Request correlation ID for tracing")
    data: T
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    correlation_id: str
    items: List[T]
    total: int
    page: int
    page_size: int
    has_more: bool


class ErrorResponse(BaseModel):
    """Standard error response."""
    correlation_id: str
    error: str
    error_code: str
    details: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

