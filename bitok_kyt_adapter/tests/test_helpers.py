"""Tests for polling helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bitok_kyt_adapter.exceptions import BitOKTimeoutError
from bitok_kyt_adapter.helpers import (
    await_manual_check_complete,
    await_transfer_check_complete,
)
from bitok_kyt_adapter.schemas import (
    ExposureCheckState,
    ManualCheckStatus,
    RegisteredTransfer,
    TransferDirection,
)


class TestAwaitTransferCheckComplete:
    """Test transfer check polling."""

    @pytest.mark.asyncio
    async def test_returns_immediately_when_checked(self) -> None:
        """Test returns immediately when already checked."""
        mock_client = MagicMock()
        mock_client.get_transfer = AsyncMock(
            return_value=RegisteredTransfer(
                id=123,
                direction=TransferDirection.INCOMING,
                network="eth",
                address="0x1234",
                exposure_check_state=ExposureCheckState.CHECKED,
            )
        )

        await await_transfer_check_complete(
            mock_client, 123, poll_interval_ms=100, timeout_ms=1000
        )

        # Should only call once since already checked
        mock_client.get_transfer.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_polls_until_checked(self) -> None:
        """Test polls until check completes."""
        call_count = 0

        async def mock_get_transfer(transfer_id):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return RegisteredTransfer(
                    id=transfer_id,
                    direction=TransferDirection.INCOMING,
                    network="eth",
                    address="0x1234",
                    exposure_check_state=ExposureCheckState.CHECKING,
                )
            return RegisteredTransfer(
                id=transfer_id,
                direction=TransferDirection.INCOMING,
                network="eth",
                address="0x1234",
                exposure_check_state=ExposureCheckState.CHECKED,
            )

        mock_client = MagicMock()
        mock_client.get_transfer = mock_get_transfer

        await await_transfer_check_complete(
            mock_client, 123, poll_interval_ms=10, timeout_ms=5000
        )

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_returns_on_error_state(self) -> None:
        """Test returns when check errors."""
        mock_client = MagicMock()
        mock_client.get_transfer = AsyncMock(
            return_value=RegisteredTransfer(
                id=123,
                direction=TransferDirection.INCOMING,
                network="eth",
                address="0x1234",
                exposure_check_state=ExposureCheckState.ERROR,
            )
        )

        await await_transfer_check_complete(
            mock_client, 123, poll_interval_ms=100, timeout_ms=1000
        )

        mock_client.get_transfer.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self) -> None:
        """Test timeout raises BitOKTimeoutError."""
        mock_client = MagicMock()
        mock_client.get_transfer = AsyncMock(
            return_value=RegisteredTransfer(
                id=123,
                direction=TransferDirection.INCOMING,
                network="eth",
                address="0x1234",
                exposure_check_state=ExposureCheckState.CHECKING,
            )
        )

        with pytest.raises(BitOKTimeoutError, match="did not complete"):
            await await_transfer_check_complete(
                mock_client, 123, poll_interval_ms=50, timeout_ms=100
            )


class TestAwaitManualCheckComplete:
    """Test manual check polling."""

    @pytest.mark.asyncio
    async def test_returns_immediately_when_checked(self) -> None:
        """Test returns immediately when already checked."""
        from bitok_kyt_adapter.schemas import ManualCheck

        mock_client = MagicMock()
        mock_client.get_manual_check = AsyncMock(
            return_value=ManualCheck(
                id=456,
                status=ManualCheckStatus.CHECKED,
                check_type="address",
                network="eth",
            )
        )

        await await_manual_check_complete(
            mock_client, 456, poll_interval_ms=100, timeout_ms=1000
        )

        mock_client.get_manual_check.assert_called_once_with(456)

    @pytest.mark.asyncio
    async def test_polls_until_checked(self) -> None:
        """Test polls until check completes."""
        from bitok_kyt_adapter.schemas import ManualCheck

        call_count = 0

        async def mock_get_check(check_id):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return ManualCheck(
                    id=check_id,
                    status=ManualCheckStatus.CHECKING,
                    check_type="address",
                    network="eth",
                )
            return ManualCheck(
                id=check_id,
                status=ManualCheckStatus.CHECKED,
                check_type="address",
                network="eth",
            )

        mock_client = MagicMock()
        mock_client.get_manual_check = mock_get_check

        await await_manual_check_complete(
            mock_client, 456, poll_interval_ms=10, timeout_ms=5000
        )

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_returns_on_error_state(self) -> None:
        """Test returns when check errors."""
        from bitok_kyt_adapter.schemas import ManualCheck

        mock_client = MagicMock()
        mock_client.get_manual_check = AsyncMock(
            return_value=ManualCheck(
                id=456,
                status=ManualCheckStatus.ERROR,
                check_type="address",
                network="eth",
            )
        )

        await await_manual_check_complete(
            mock_client, 456, poll_interval_ms=100, timeout_ms=1000
        )

        mock_client.get_manual_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self) -> None:
        """Test timeout raises BitOKTimeoutError."""
        from bitok_kyt_adapter.schemas import ManualCheck

        mock_client = MagicMock()
        mock_client.get_manual_check = AsyncMock(
            return_value=ManualCheck(
                id=456,
                status=ManualCheckStatus.CHECKING,
                check_type="address",
                network="eth",
            )
        )

        with pytest.raises(BitOKTimeoutError, match="did not complete"):
            await await_manual_check_complete(
                mock_client, 456, poll_interval_ms=50, timeout_ms=100
            )
