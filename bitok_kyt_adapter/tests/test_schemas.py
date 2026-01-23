"""Tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from bitok_kyt_adapter.schemas import (
    Alert,
    AlertStatus,
    CheckAddressRequest,
    CheckTransferRequest,
    CounterpartyCheckState,
    ExposureCheckState,
    ExposureEntry,
    ManualCheck,
    ManualCheckStatus,
    PaginatedResponse,
    PaginationParams,
    RegisteredTransfer,
    RegisterTransferAttemptRequest,
    RegisterTransferRequest,
    Risk,
    RiskLevel,
    TransferDirection,
    TransferExposure,
    TxStatus,
)


class TestEnums:
    """Test enum definitions."""

    def test_risk_level_values(self) -> None:
        """Test RiskLevel enum values."""
        assert RiskLevel.NONE == "none"
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.SEVERE == "severe"
        assert RiskLevel.UNDEFINED == "undefined"

    def test_tx_status_values(self) -> None:
        """Test TxStatus enum values."""
        assert TxStatus.NONE == "none"
        assert TxStatus.BOUND == "bound"
        assert TxStatus.BINDING == "binding"
        assert TxStatus.NOT_FOUND == "not_found"
        assert TxStatus.ERROR == "error"

    def test_transfer_direction_values(self) -> None:
        """Test TransferDirection enum values."""
        assert TransferDirection.INCOMING == "incoming"
        assert TransferDirection.OUTGOING == "outgoing"

    def test_alert_status_values(self) -> None:
        """Test AlertStatus enum values."""
        assert AlertStatus.OPEN == "open"
        assert AlertStatus.IN_PROGRESS == "in_progress"
        assert AlertStatus.AWAITING_RESPONSE == "awaiting_response"
        assert AlertStatus.DONE == "done"


class TestPaginationParams:
    """Test pagination parameters."""

    def test_default_values(self) -> None:
        """Test default pagination values."""
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20

    def test_custom_values(self) -> None:
        """Test custom pagination values."""
        params = PaginationParams(page=5, page_size=50)
        assert params.page == 5
        assert params.page_size == 50

    def test_page_must_be_positive(self) -> None:
        """Test page must be >= 1."""
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

    def test_page_size_limits(self) -> None:
        """Test page_size must be 1-100."""
        with pytest.raises(ValidationError):
            PaginationParams(page_size=0)
        with pytest.raises(ValidationError):
            PaginationParams(page_size=101)


class TestRegisterTransferRequest:
    """Test transfer registration request."""

    def test_minimal_request(self) -> None:
        """Test minimal valid request."""
        request = RegisterTransferRequest(
            direction=TransferDirection.INCOMING,
            network="eth",
            address="0x1234567890abcdef1234567890abcdef12345678",
        )
        assert request.direction == TransferDirection.INCOMING
        assert request.network == "eth"

    def test_full_request(self) -> None:
        """Test full request with all fields."""
        request = RegisterTransferRequest(
            direction=TransferDirection.OUTGOING,
            network="btc",
            token=None,
            tx_hash="abc123",
            address="bc1q...",
            output_index=0,
            amount="1.5",
            client_id="client-123",
            transfer_id="transfer-456",
        )
        assert request.output_index == 0
        assert request.amount == "1.5"

    def test_direction_required(self) -> None:
        """Test direction is required."""
        with pytest.raises(ValidationError):
            RegisterTransferRequest(network="eth", address="0x1234")


class TestRegisterTransferAttemptRequest:
    """Test transfer attempt registration request."""

    def test_valid_request(self) -> None:
        """Test valid attempt request."""
        request = RegisterTransferAttemptRequest(
            direction=TransferDirection.OUTGOING,
            network="eth",
            address="0xabcd",
            amount="100",
        )
        assert request.direction == TransferDirection.OUTGOING


class TestRegisteredTransfer:
    """Test registered transfer model."""

    def test_from_api_response(self) -> None:
        """Test creating from typical API response."""
        data = {
            "id": 123,
            "direction": "incoming",
            "network": "eth",
            "address": "0x1234",
            "tx_status": "bound",
            "exposure_check_state": "checked",
            "counterparty_check_state": "checked",
            "risk_level": "low",
        }
        transfer = RegisteredTransfer(**data)

        assert transfer.id == 123
        assert transfer.direction == TransferDirection.INCOMING
        assert transfer.tx_status == TxStatus.BOUND
        assert transfer.exposure_check_state == ExposureCheckState.CHECKED
        assert transfer.risk_level == RiskLevel.LOW

    def test_defaults(self) -> None:
        """Test default values."""
        transfer = RegisteredTransfer(
            id=1,
            direction=TransferDirection.INCOMING,
            network="eth",
            address="0x123",
        )
        assert transfer.tx_status == TxStatus.NONE
        assert transfer.exposure_check_state == ExposureCheckState.NONE
        assert transfer.risk_level == RiskLevel.UNDEFINED


class TestTransferExposure:
    """Test transfer exposure model."""

    def test_with_exposures(self) -> None:
        """Test exposure with entries."""
        data = {
            "transfer_id": 123,
            "check_state": "checked",
            "risk_level": "medium",
            "direct_exposure": [
                {
                    "entity_name": "Exchange A",
                    "entity_category": "exchange",
                    "risk_level": "none",
                    "exposure_percent": 80.5,
                    "amount": "0.8",
                }
            ],
            "indirect_exposure": [],
        }
        exposure = TransferExposure(**data)

        assert exposure.transfer_id == 123
        assert len(exposure.direct_exposure) == 1
        assert exposure.direct_exposure[0].exposure_percent == 80.5


class TestManualCheck:
    """Test manual check model."""

    def test_from_api_response(self) -> None:
        """Test creating from API response."""
        data = {
            "id": 456,
            "status": "checked",
            "check_type": "address",
            "network": "eth",
            "address": "0xabcd",
            "risk_level": "high",
        }
        check = ManualCheck(**data)

        assert check.id == 456
        assert check.status == ManualCheckStatus.CHECKED
        assert check.risk_level == RiskLevel.HIGH


class TestCheckAddressRequest:
    """Test check address request."""

    def test_valid_request(self) -> None:
        """Test valid request."""
        request = CheckAddressRequest(network="eth", address="0x1234")
        assert request.network == "eth"
        assert request.address == "0x1234"


class TestCheckTransferRequest:
    """Test check transfer request."""

    def test_valid_request(self) -> None:
        """Test valid request."""
        request = CheckTransferRequest(
            network="btc", tx_hash="abc123def456", output_index=0
        )
        assert request.tx_hash == "abc123def456"


class TestAlert:
    """Test alert model."""

    def test_from_api_response(self) -> None:
        """Test creating from API response."""
        data = {
            "id": 789,
            "status": "open",
            "risk_level": "severe",
            "description": "Severe risk detected",
            "transfer_id": 123,
        }
        alert = Alert(**data)

        assert alert.id == 789
        assert alert.status == AlertStatus.OPEN
        assert alert.risk_level == RiskLevel.SEVERE


class TestRisk:
    """Test risk model."""

    def test_from_api_response(self) -> None:
        """Test creating from API response."""
        data = {
            "id": 1,
            "risk_level": "high",
            "category": "darknet",
            "description": "Funds traced to darknet marketplace",
            "entity_name": "Hydra Market",
            "exposure_percent": 15.5,
        }
        risk = Risk(**data)

        assert risk.id == 1
        assert risk.risk_level == RiskLevel.HIGH
        assert risk.category == "darknet"


class TestPaginatedResponse:
    """Test paginated response."""

    def test_generic_response(self) -> None:
        """Test generic paginated response."""
        data = {
            "count": 100,
            "next": "https://api.example.com/?page=2",
            "previous": None,
            "results": [{"id": 1}, {"id": 2}],
        }
        response = PaginatedResponse[dict](**data)

        assert response.count == 100
        assert response.next is not None
        assert response.previous is None
        assert len(response.results) == 2
