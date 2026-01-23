# BitOK KYT Adapter

Python client for BitOK KYT Office API v1.4.

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Configure via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BITOK_API_KEY_ID` | Yes | - | API Key ID |
| `BITOK_API_SECRET` | Yes | - | API Secret for HMAC-SHA256 signing |
| `BITOK_BASE_URL` | No | `https://api.bitok.org` | API base URL |
| `BITOK_TIMEOUT_SECONDS` | No | `30.0` | HTTP request timeout |
| `BITOK_RETRY_ATTEMPTS` | No | `3` | Retry attempts for failed requests |

Or pass settings directly:

```python
from bitok_kyt_adapter import BitOKSettings, BitOKKYTClient

settings = BitOKSettings(
    api_key_id="your-key-id",
    api_secret="your-secret",
)

async with BitOKKYTClient(settings) as client:
    ...
```

## Quick Start

```python
import asyncio
from bitok_kyt_adapter import (
    BitOKKYTClient,
    RegisterTransferRequest,
    TransferDirection,
    await_transfer_check_complete,
)

async def main():
    async with BitOKKYTClient() as client:
        # Register an incoming transfer
        transfer = await client.register_transfer(
            RegisterTransferRequest(
                direction=TransferDirection.INCOMING,
                network="eth",
                address="0x1234567890abcdef1234567890abcdef12345678",
                tx_hash="0xabc123...",
                amount="1.5",
            )
        )
        print(f"Registered transfer: {transfer.id}")

        # Wait for check to complete
        await await_transfer_check_complete(client, transfer.id)

        # Get results
        updated = await client.get_transfer(transfer.id)
        print(f"Risk level: {updated.risk_level}")

        exposure = await client.get_transfer_exposure(transfer.id)
        print(f"Direct exposures: {len(exposure.direct_exposure)}")

asyncio.run(main())
```

## Use Cases

### Inbound Flow (Deposit Screening)

Screen incoming deposits to identify risky fund sources:

```python
from bitok_kyt_adapter import (
    BitOKKYTClient,
    RegisterTransferRequest,
    TransferDirection,
    RiskLevel,
    await_transfer_check_complete,
)

async def screen_deposit(
    network: str,
    address: str,
    tx_hash: str,
    amount: str,
    client_id: str | None = None,
):
    """Screen an incoming deposit and return risk assessment."""
    async with BitOKKYTClient() as client:
        # Register the deposit
        transfer = await client.register_transfer(
            RegisterTransferRequest(
                direction=TransferDirection.INCOMING,
                network=network,
                address=address,
                tx_hash=tx_hash,
                amount=amount,
                client_id=client_id,
            )
        )

        # Wait for exposure check
        await await_transfer_check_complete(
            client, transfer.id, timeout_ms=60000
        )

        # Get final results
        transfer = await client.get_transfer(transfer.id)
        exposure = await client.get_transfer_exposure(transfer.id)
        risks = await client.get_transfer_risks(transfer.id)

        return {
            "transfer_id": transfer.id,
            "risk_level": transfer.risk_level,
            "is_high_risk": transfer.risk_level in (
                RiskLevel.HIGH, RiskLevel.SEVERE
            ),
            "exposure": exposure,
            "risks": risks.results,
        }
```

### Outbound Flow (Withdrawal Pre-Check)

Pre-screen withdrawal addresses before sending funds:

```python
from bitok_kyt_adapter import (
    BitOKKYTClient,
    RegisterTransferAttemptRequest,
    TransferDirection,
    RiskLevel,
    await_transfer_check_complete,
    BindTransactionRequest,
)

async def precheck_withdrawal(network: str, address: str, amount: str):
    """Pre-check a withdrawal address before sending."""
    async with BitOKKYTClient() as client:
        # Register as attempt (pre-check)
        transfer = await client.register_transfer_attempt(
            RegisterTransferAttemptRequest(
                direction=TransferDirection.OUTGOING,
                network=network,
                address=address,
                amount=amount,
            )
        )

        # Wait for counterparty check
        await await_transfer_check_complete(client, transfer.id)

        # Get counterparty info
        counterparty = await client.get_transfer_counterparty(transfer.id)

        is_blocked = counterparty.risk_level in (
            RiskLevel.HIGH, RiskLevel.SEVERE
        )

        return {
            "transfer_id": transfer.id,
            "address": address,
            "entity_name": counterparty.entity_name,
            "entity_category": counterparty.entity_category,
            "risk_level": counterparty.risk_level,
            "is_blocked": is_blocked,
        }


async def confirm_withdrawal(transfer_id: int, tx_hash: str):
    """Bind actual transaction after withdrawal is sent."""
    async with BitOKKYTClient() as client:
        transfer = await client.bind_transaction(
            transfer_id,
            BindTransactionRequest(tx_hash=tx_hash),
        )
        return transfer
```

### Manual Address Check

Check any address on-demand without registering a transfer:

```python
from bitok_kyt_adapter import (
    BitOKKYTClient,
    CheckAddressRequest,
    await_manual_check_complete,
)

async def check_address(network: str, address: str):
    """Manually check an address."""
    async with BitOKKYTClient() as client:
        # Start check
        check = await client.check_address(
            CheckAddressRequest(network=network, address=address)
        )

        # Wait for completion
        await await_manual_check_complete(client, check.id)

        # Get results
        check = await client.get_manual_check(check.id)
        exposure = await client.get_manual_check_address_exposure(check.id)
        risks = await client.get_manual_check_risks(check.id)

        return {
            "check_id": check.id,
            "risk_level": check.risk_level,
            "incoming_exposure": exposure.incoming_exposure,
            "outgoing_exposure": exposure.outgoing_exposure,
            "risks": risks.results,
        }
```

## API Reference

### Client Methods

#### Basics
- `list_networks(page, page_size)` - List supported networks
- `list_tokens(page, page_size)` - List supported tokens
- `list_entity_categories(page, page_size)` - List entity categories

#### Transfers
- `list_transfers(page, page_size, **filters)` - List registered transfers
- `get_transfer(id)` - Get transfer by ID
- `register_transfer(request)` - Register new transfer
- `register_transfer_attempt(request)` - Register transfer attempt (pre-screening)
- `bind_transaction(id, request)` - Bind tx hash to transfer
- `get_transfer_exposure(id)` - Get exposure analysis
- `recheck_transfer_exposure(id)` - Request exposure recheck
- `get_transfer_counterparty(id)` - Get counterparty info
- `recheck_transfer_counterparty(id)` - Request counterparty recheck
- `get_transfer_risks(id)` - Get identified risks

#### Alerts
- `list_alerts(page, page_size, **filters)` - List alerts
- `get_alert(id)` - Get alert by ID

#### Manual Checks
- `check_transfer(request)` - Check a transfer manually
- `check_address(request)` - Check an address manually
- `list_manual_checks(page, page_size)` - List manual checks
- `get_manual_check(id)` - Get manual check by ID
- `get_manual_check_risks(id)` - Get risks from manual check
- `get_manual_check_transfer_exposure(id)` - Get transfer exposure
- `get_manual_check_address_exposure(id)` - Get address exposure

### Helpers
- `await_transfer_check_complete(client, id, poll_interval_ms, timeout_ms)` - Poll until transfer check completes
- `await_manual_check_complete(client, id, poll_interval_ms, timeout_ms)` - Poll until manual check completes

### Exceptions
- `BitOKError` - Base exception
- `BitOKAuthError` - Authentication error (401/403)
- `BitOKNotFoundError` - Resource not found (404)
- `BitOKValidationError` - Validation error (400/422)
- `BitOKRateLimitError` - Rate limit exceeded (429)
- `BitOKServerError` - Server error (5xx)
- `BitOKTimeoutError` - Polling timeout
- `BitOKNetworkError` - Network connectivity error

## Running Tests

```bash
cd bitok-kyt-adapter
pip install -r requirements.txt
pytest tests/ -v
```

### Golden Signature Test

The test suite includes a golden test that verifies signature generation matches the expected output from the BitOK API documentation:

```bash
pytest tests/test_auth.py::TestBitOKAuth::test_golden_signature_get_request -v
```
