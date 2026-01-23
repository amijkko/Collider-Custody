"""Enumerations for BitOK KYT API."""

from enum import Enum


class RiskLevel(str, Enum):
    """Risk level classification."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SEVERE = "severe"
    UNDEFINED = "undefined"


class TxStatus(str, Enum):
    """Transaction binding status."""

    NONE = "none"
    BOUND = "bound"
    BINDING = "binding"
    NOT_FOUND = "not_found"
    ERROR = "error"


class ExposureCheckState(str, Enum):
    """Exposure check state."""

    NONE = "none"
    QUEUED = "queued"
    CHECKED = "checked"
    CHECKING = "checking"
    ERROR = "error"


class CounterpartyCheckState(str, Enum):
    """Counterparty check state."""

    NONE = "none"
    CHECKED = "checked"
    CHECKING = "checking"
    ERROR = "error"


class ManualCheckStatus(str, Enum):
    """Manual check status."""

    CHECKED = "checked"
    CHECKING = "checking"
    ERROR = "error"


class TransferDirection(str, Enum):
    """Transfer direction."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"


class AlertStatus(str, Enum):
    """Alert status."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    AWAITING_RESPONSE = "awaiting_response"
    DONE = "done"
