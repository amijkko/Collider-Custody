"""Tests for BitOK KYT client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from bitok_kyt_adapter import (
    BitOKKYTClient,
    BitOKSettings,
    CheckAddressRequest,
    RegisterTransferRequest,
    TransferDirection,
)
from bitok_kyt_adapter.exceptions import (
    BitOKAuthError,
    BitOKNotFoundError,
    BitOKServerError,
    BitOKValidationError,
)


@pytest.fixture
def settings() -> BitOKSettings:
    """Create test settings."""
    return BitOKSettings(
        api_key_id="test-key",
        api_secret="test-secret",
        base_url="https://api.test.bitok.org",
        retry_attempts=1,  # Disable retries for faster tests
    )


class TestBitOKKYTClient:
    """Test BitOK KYT client methods."""

    @pytest.mark.asyncio
    async def test_context_manager(self, settings: BitOKSettings) -> None:
        """Test client works as async context manager."""
        async with BitOKKYTClient(settings) as client:
            assert client._client is not None

        # Client should be closed after exiting context
        assert client._client is None

    @pytest.mark.asyncio
    async def test_client_not_initialized_error(self, settings: BitOKSettings) -> None:
        """Test error when using client outside context manager."""
        client = BitOKKYTClient(settings)

        with pytest.raises(RuntimeError, match="Client not initialized"):
            _ = client.client

    @pytest.mark.asyncio
    async def test_list_transfers(self, settings: BitOKSettings) -> None:
        """Test list_transfers endpoint."""
        mock_response = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "id": 123,
                    "direction": "incoming",
                    "network": "eth",
                    "address": "0x1234",
                    "tx_status": "bound",
                    "exposure_check_state": "checked",
                    "counterparty_check_state": "checked",
                    "risk_level": "low",
                }
            ],
        }

        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    200, json=mock_response, request=httpx.Request("GET", "/")
                )

                result = await client.list_transfers(page=1, page_size=10)

                assert result.count == 1
                assert len(result.results) == 1
                assert result.results[0].id == 123
                assert result.results[0].direction == TransferDirection.INCOMING

    @pytest.mark.asyncio
    async def test_get_transfer(self, settings: BitOKSettings) -> None:
        """Test get_transfer endpoint."""
        mock_response = {
            "id": 123,
            "direction": "outgoing",
            "network": "btc",
            "address": "bc1q...",
            "tx_status": "bound",
            "exposure_check_state": "checked",
            "counterparty_check_state": "checked",
            "risk_level": "none",
        }

        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    200, json=mock_response, request=httpx.Request("GET", "/")
                )

                result = await client.get_transfer(123)

                assert result.id == 123
                assert result.network == "btc"

    @pytest.mark.asyncio
    async def test_register_transfer(self, settings: BitOKSettings) -> None:
        """Test register_transfer endpoint."""
        mock_response = {
            "id": 456,
            "direction": "incoming",
            "network": "eth",
            "address": "0xabcd",
            "tx_status": "none",
            "exposure_check_state": "queued",
            "counterparty_check_state": "none",
            "risk_level": "undefined",
        }

        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    201, json=mock_response, request=httpx.Request("POST", "/")
                )

                request = RegisterTransferRequest(
                    direction=TransferDirection.INCOMING,
                    network="eth",
                    address="0xabcd",
                )
                result = await client.register_transfer(request)

                assert result.id == 456
                assert result.address == "0xabcd"

    @pytest.mark.asyncio
    async def test_check_address(self, settings: BitOKSettings) -> None:
        """Test check_address endpoint."""
        mock_response = {
            "id": 789,
            "status": "checking",
            "check_type": "address",
            "network": "eth",
            "address": "0x1234",
            "risk_level": "undefined",
        }

        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    201, json=mock_response, request=httpx.Request("POST", "/")
                )

                request = CheckAddressRequest(network="eth", address="0x1234")
                result = await client.check_address(request)

                assert result.id == 789
                assert result.check_type == "address"

    @pytest.mark.asyncio
    async def test_list_alerts(self, settings: BitOKSettings) -> None:
        """Test list_alerts endpoint."""
        mock_response = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "id": 1,
                    "status": "open",
                    "risk_level": "high",
                    "description": "High risk transfer detected",
                },
                {
                    "id": 2,
                    "status": "done",
                    "risk_level": "medium",
                    "description": "Medium risk address",
                },
            ],
        }

        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    200, json=mock_response, request=httpx.Request("GET", "/")
                )

                result = await client.list_alerts()

                assert result.count == 2
                assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_error_401_raises_auth_error(self, settings: BitOKSettings) -> None:
        """Test 401 response raises BitOKAuthError."""
        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    401,
                    json={"detail": "Invalid credentials"},
                    request=httpx.Request("GET", "/"),
                )

                with pytest.raises(BitOKAuthError):
                    await client.list_transfers()

    @pytest.mark.asyncio
    async def test_error_404_raises_not_found(self, settings: BitOKSettings) -> None:
        """Test 404 response raises BitOKNotFoundError."""
        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    404,
                    json={"detail": "Transfer not found"},
                    request=httpx.Request("GET", "/"),
                )

                with pytest.raises(BitOKNotFoundError):
                    await client.get_transfer(999999)

    @pytest.mark.asyncio
    async def test_error_400_raises_validation_error(
        self, settings: BitOKSettings
    ) -> None:
        """Test 400 response raises BitOKValidationError."""
        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    400,
                    json={"detail": "Invalid request"},
                    request=httpx.Request("POST", "/"),
                )

                with pytest.raises(BitOKValidationError):
                    request = RegisterTransferRequest(
                        direction=TransferDirection.INCOMING,
                        network="invalid",
                        address="bad",
                    )
                    await client.register_transfer(request)

    @pytest.mark.asyncio
    async def test_error_500_raises_server_error(self, settings: BitOKSettings) -> None:
        """Test 500 response raises BitOKServerError."""
        async with BitOKKYTClient(settings) as client:
            with patch.object(
                client._client, "request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = httpx.Response(
                    500,
                    json={"detail": "Internal server error"},
                    request=httpx.Request("GET", "/"),
                )

                with pytest.raises(BitOKServerError):
                    await client.list_transfers()

    def test_build_endpoint_without_params(self, settings: BitOKSettings) -> None:
        """Test endpoint building without parameters."""
        client = BitOKKYTClient(settings)

        endpoint = client._build_endpoint("/v1/transfers/")
        assert endpoint == "/v1/transfers/"

    def test_build_endpoint_with_params(self, settings: BitOKSettings) -> None:
        """Test endpoint building with parameters."""
        client = BitOKKYTClient(settings)

        endpoint = client._build_endpoint(
            "/v1/transfers/", {"page": 1, "page_size": 10, "network": "eth"}
        )
        assert "page=1" in endpoint
        assert "page_size=10" in endpoint
        assert "network=eth" in endpoint

    def test_build_endpoint_filters_none(self, settings: BitOKSettings) -> None:
        """Test endpoint building filters out None values."""
        client = BitOKKYTClient(settings)

        endpoint = client._build_endpoint(
            "/v1/transfers/", {"page": 1, "network": None}
        )
        assert "page=1" in endpoint
        assert "network" not in endpoint
