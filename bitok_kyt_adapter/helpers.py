"""Polling helpers for BitOK KYT API."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .exceptions import BitOKTimeoutError
from .schemas import ExposureCheckState, ManualCheckStatus

if TYPE_CHECKING:
    from .client import BitOKKYTClient


async def await_transfer_check_complete(
    client: "BitOKKYTClient",
    transfer_id: int,
    poll_interval_ms: int = 2000,
    timeout_ms: int = 120000,
) -> None:
    """Wait for transfer exposure check to complete.

    Polls the transfer until exposure_check_state is 'checked' or 'error'.

    Args:
        client: BitOK KYT client instance.
        transfer_id: Transfer ID to poll.
        poll_interval_ms: Polling interval in milliseconds.
        timeout_ms: Timeout in milliseconds.

    Raises:
        BitOKTimeoutError: If check doesn't complete within timeout.
    """
    poll_interval = poll_interval_ms / 1000
    timeout = timeout_ms / 1000
    elapsed = 0.0

    while elapsed < timeout:
        transfer = await client.get_transfer(transfer_id)

        if transfer.exposure_check_state in (
            ExposureCheckState.CHECKED,
            ExposureCheckState.ERROR,
        ):
            return

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise BitOKTimeoutError(
        f"Transfer {transfer_id} check did not complete within {timeout_ms}ms"
    )


async def await_manual_check_complete(
    client: "BitOKKYTClient",
    check_id: int,
    poll_interval_ms: int = 2000,
    timeout_ms: int = 120000,
) -> None:
    """Wait for manual check to complete.

    Polls the manual check until status is 'checked' or 'error'.

    Args:
        client: BitOK KYT client instance.
        check_id: Manual check ID to poll.
        poll_interval_ms: Polling interval in milliseconds.
        timeout_ms: Timeout in milliseconds.

    Raises:
        BitOKTimeoutError: If check doesn't complete within timeout.
    """
    poll_interval = poll_interval_ms / 1000
    timeout = timeout_ms / 1000
    elapsed = 0.0

    while elapsed < timeout:
        check = await client.get_manual_check(check_id)

        if check.status in (
            ManualCheckStatus.CHECKED,
            ManualCheckStatus.ERROR,
        ):
            return

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise BitOKTimeoutError(
        f"Manual check {check_id} did not complete within {timeout_ms}ms"
    )
