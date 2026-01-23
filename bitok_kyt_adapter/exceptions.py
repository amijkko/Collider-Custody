"""Custom exceptions for BitOK KYT Adapter."""

from __future__ import annotations

from typing import Any


class BitOKError(Exception):
    """Base exception for BitOK KYT API errors."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class BitOKAuthError(BitOKError):
    """Authentication/authorization error (401/403)."""

    pass


class BitOKNotFoundError(BitOKError):
    """Resource not found error (404)."""

    pass


class BitOKValidationError(BitOKError):
    """Request validation error (400/422)."""

    pass


class BitOKRateLimitError(BitOKError):
    """Rate limit exceeded error (429)."""

    pass


class BitOKServerError(BitOKError):
    """Server-side error (5xx)."""

    pass


class BitOKTimeoutError(BitOKError):
    """Timeout error for polling operations."""

    pass


class BitOKNetworkError(BitOKError):
    """Network connectivity error."""

    pass
