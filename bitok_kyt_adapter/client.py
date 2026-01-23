"""BitOK KYT API client."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .auth import BitOKAuth
from .config import BitOKSettings
from .exceptions import (
    BitOKAuthError,
    BitOKError,
    BitOKNetworkError,
    BitOKNotFoundError,
    BitOKRateLimitError,
    BitOKServerError,
    BitOKValidationError,
)
from .schemas import (
    AddressExposure,
    Alert,
    AlertListResponse,
    BindTransactionRequest,
    CheckAddressRequest,
    CheckTransferRequest,
    Counterparty,
    ManualCheck,
    ManualCheckListResponse,
    RegisteredTransfer,
    RegisterTransferAttemptRequest,
    RegisterTransferRequest,
    RiskListResponse,
    TransferExposure,
    TransferListResponse,
)
from .schemas.basics import (
    EntityCategoryListResponse,
    NetworkListResponse,
    TokenListResponse,
)


class BitOKKYTClient:
    """Async client for BitOK KYT API.

    Usage:
        async with BitOKKYTClient(settings) as client:
            transfers = await client.list_transfers()
    """

    def __init__(self, settings: BitOKSettings | None = None):
        """Initialize client.

        Args:
            settings: BitOK settings. If not provided, loads from environment.
        """
        self.settings = settings or BitOKSettings()
        self.auth = BitOKAuth(self.settings.api_key_id, self.settings.api_secret)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BitOKKYTClient":
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=httpx.Timeout(self.settings.timeout_seconds),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client, ensuring it's initialized."""
        if self._client is None:
            raise RuntimeError(
                "Client not initialized. Use 'async with BitOKKYTClient() as client:'"
            )
        return self._client

    def _build_endpoint(
        self, path: str, params: dict[str, Any] | None = None
    ) -> str:
        """Build endpoint path with query parameters.

        Args:
            path: API path (e.g., '/v1/transfers/').
            params: Optional query parameters.

        Returns:
            Endpoint with query string if params provided.
        """
        if not params:
            return path
        # Filter out None values
        filtered = {k: v for k, v in params.items() if v is not None}
        if not filtered:
            return path
        return f"{path}?{urlencode(filtered)}"

    def _handle_error(self, response: httpx.Response) -> None:
        """Raise appropriate exception for error response.

        Args:
            response: HTTP response to check.

        Raises:
            BitOKAuthError: For 401/403 responses.
            BitOKNotFoundError: For 404 responses.
            BitOKValidationError: For 400/422 responses.
            BitOKRateLimitError: For 429 responses.
            BitOKServerError: For 5xx responses.
            BitOKError: For other error responses.
        """
        if response.is_success:
            return

        try:
            details = response.json()
        except Exception:
            details = response.text

        status = response.status_code
        message = f"HTTP {status}"

        if status in (401, 403):
            raise BitOKAuthError(message, details)
        elif status == 404:
            raise BitOKNotFoundError(message, details)
        elif status in (400, 422):
            raise BitOKValidationError(message, details)
        elif status == 429:
            raise BitOKRateLimitError(message, details)
        elif status >= 500:
            raise BitOKServerError(message, details)
        else:
            raise BitOKError(message, details)

    def _create_retry_decorator(self):
        """Create retry decorator with current settings."""
        return retry(
            retry=retry_if_exception_type(
                (BitOKServerError, BitOKNetworkError, httpx.NetworkError, httpx.TimeoutException)
            ),
            stop=stop_after_attempt(self.settings.retry_attempts),
            wait=wait_exponential(
                min=self.settings.retry_min_wait_seconds,
                max=self.settings.retry_max_wait_seconds,
            ),
            reraise=True,
        )

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make authenticated request to the API.

        Args:
            method: HTTP method.
            path: API path.
            params: Query parameters.
            body: Request body.

        Returns:
            Response JSON data.
        """
        endpoint = self._build_endpoint(path, params)
        headers = self.auth.get_headers(method, endpoint, body)

        @self._create_retry_decorator()
        async def _do_request():
            try:
                response = await self.client.request(
                    method=method,
                    url=endpoint,
                    headers=headers,
                    json=body if body else None,
                )
            except httpx.NetworkError as e:
                raise BitOKNetworkError(f"Network error: {e}")
            except httpx.TimeoutException as e:
                raise BitOKNetworkError(f"Timeout: {e}")

            self._handle_error(response)
            return response.json()

        return await _do_request()

    # ==================== Basics API ====================

    async def list_networks(
        self, page: int = 1, page_size: int = 20
    ) -> NetworkListResponse:
        """List available networks.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Paginated list of networks.
        """
        data = await self._request(
            "GET", "/v1/basics/networks/", params={"page": page, "page_size": page_size}
        )
        return NetworkListResponse(**data)

    async def list_tokens(
        self, page: int = 1, page_size: int = 20
    ) -> TokenListResponse:
        """List available tokens.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Paginated list of tokens.
        """
        data = await self._request(
            "GET", "/v1/basics/tokens/", params={"page": page, "page_size": page_size}
        )
        return TokenListResponse(**data)

    async def list_entity_categories(
        self, page: int = 1, page_size: int = 20
    ) -> EntityCategoryListResponse:
        """List entity categories.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Paginated list of entity categories.
        """
        data = await self._request(
            "GET",
            "/v1/basics/entity-categories/",
            params={"page": page, "page_size": page_size},
        )
        return EntityCategoryListResponse(**data)

    # ==================== Transfers API ====================

    async def list_transfers(
        self,
        page: int = 1,
        page_size: int = 20,
        **filters: Any,
    ) -> TransferListResponse:
        """List registered transfers.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            **filters: Additional filters (direction, network, risk_level, etc.).

        Returns:
            Paginated list of transfers.
        """
        params = {"page": page, "page_size": page_size, **filters}
        data = await self._request("GET", "/v1/transfers/", params=params)
        return TransferListResponse(**data)

    async def get_transfer(self, transfer_id: int) -> RegisteredTransfer:
        """Get a specific transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Transfer details.
        """
        data = await self._request("GET", f"/v1/transfers/{transfer_id}/")
        return RegisteredTransfer(**data)

    async def register_transfer(
        self, request: RegisterTransferRequest
    ) -> RegisteredTransfer:
        """Register a new transfer for monitoring.

        Args:
            request: Transfer registration details.

        Returns:
            Registered transfer.
        """
        data = await self._request(
            "POST", "/v1/transfers/register/", body=request.model_dump(exclude_none=True)
        )
        return RegisteredTransfer(**data)

    async def register_transfer_attempt(
        self, request: RegisterTransferAttemptRequest
    ) -> RegisteredTransfer:
        """Register a transfer attempt for pre-screening.

        Args:
            request: Transfer attempt details.

        Returns:
            Registered transfer.
        """
        data = await self._request(
            "POST",
            "/v1/transfers/register-attempt/",
            body=request.model_dump(exclude_none=True),
        )
        return RegisteredTransfer(**data)

    async def bind_transaction(
        self, transfer_id: int, request: BindTransactionRequest
    ) -> RegisteredTransfer:
        """Bind a transaction hash to a registered transfer.

        Args:
            transfer_id: Transfer ID.
            request: Transaction binding details.

        Returns:
            Updated transfer.
        """
        data = await self._request(
            "POST",
            f"/v1/transfers/{transfer_id}/bind-transaction/",
            body=request.model_dump(exclude_none=True),
        )
        return RegisteredTransfer(**data)

    async def get_transfer_exposure(self, transfer_id: int) -> TransferExposure:
        """Get exposure analysis for a transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Transfer exposure analysis.
        """
        data = await self._request("GET", f"/v1/transfers/{transfer_id}/exposure/")
        return TransferExposure(**data)

    async def recheck_transfer_exposure(self, transfer_id: int) -> TransferExposure:
        """Request recheck of transfer exposure.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Updated transfer exposure.
        """
        data = await self._request(
            "POST", f"/v1/transfers/{transfer_id}/recheck-exposure/"
        )
        return TransferExposure(**data)

    async def get_transfer_counterparty(self, transfer_id: int) -> Counterparty:
        """Get counterparty information for a transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Counterparty information.
        """
        data = await self._request("GET", f"/v1/transfers/{transfer_id}/counterparty/")
        return Counterparty(**data)

    async def recheck_transfer_counterparty(self, transfer_id: int) -> Counterparty:
        """Request recheck of transfer counterparty.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Updated counterparty information.
        """
        data = await self._request(
            "POST", f"/v1/transfers/{transfer_id}/recheck-counterparty/"
        )
        return Counterparty(**data)

    async def get_transfer_risks(
        self, transfer_id: int, page: int = 1, page_size: int = 20
    ) -> RiskListResponse:
        """Get risks identified for a transfer.

        Args:
            transfer_id: Transfer ID.
            page: Page number.
            page_size: Items per page.

        Returns:
            Paginated list of risks.
        """
        data = await self._request(
            "GET",
            f"/v1/transfers/{transfer_id}/risks/",
            params={"page": page, "page_size": page_size},
        )
        return RiskListResponse(**data)

    # ==================== Alerts API ====================

    async def list_alerts(
        self,
        page: int = 1,
        page_size: int = 20,
        **filters: Any,
    ) -> AlertListResponse:
        """List alerts.

        Args:
            page: Page number.
            page_size: Items per page.
            **filters: Additional filters (status, risk_level, etc.).

        Returns:
            Paginated list of alerts.
        """
        params = {"page": page, "page_size": page_size, **filters}
        data = await self._request("GET", "/v1/alerts/", params=params)
        return AlertListResponse(**data)

    async def get_alert(self, alert_id: int) -> Alert:
        """Get a specific alert.

        Args:
            alert_id: Alert ID.

        Returns:
            Alert details.
        """
        data = await self._request("GET", f"/v1/alerts/{alert_id}/")
        return Alert(**data)

    # ==================== Manual Checks API ====================

    async def check_transfer(self, request: CheckTransferRequest) -> ManualCheck:
        """Manually check a transfer.

        Args:
            request: Check transfer request.

        Returns:
            Manual check result.
        """
        data = await self._request(
            "POST",
            "/v1/manual-checks/check-transfer/",
            body=request.model_dump(exclude_none=True),
        )
        return ManualCheck(**data)

    async def check_address(self, request: CheckAddressRequest) -> ManualCheck:
        """Manually check an address.

        Args:
            request: Check address request.

        Returns:
            Manual check result.
        """
        data = await self._request(
            "POST",
            "/v1/manual-checks/check-address/",
            body=request.model_dump(exclude_none=True),
        )
        return ManualCheck(**data)

    async def list_manual_checks(
        self, page: int = 1, page_size: int = 20
    ) -> ManualCheckListResponse:
        """List manual checks.

        Args:
            page: Page number.
            page_size: Items per page.

        Returns:
            Paginated list of manual checks.
        """
        data = await self._request(
            "GET",
            "/v1/manual-checks/",
            params={"page": page, "page_size": page_size},
        )
        return ManualCheckListResponse(**data)

    async def get_manual_check(self, check_id: int) -> ManualCheck:
        """Get a specific manual check.

        Args:
            check_id: Manual check ID.

        Returns:
            Manual check details.
        """
        data = await self._request("GET", f"/v1/manual-checks/{check_id}/")
        return ManualCheck(**data)

    async def get_manual_check_risks(
        self, check_id: int, page: int = 1, page_size: int = 20
    ) -> RiskListResponse:
        """Get risks identified in a manual check.

        Args:
            check_id: Manual check ID.
            page: Page number.
            page_size: Items per page.

        Returns:
            Paginated list of risks.
        """
        data = await self._request(
            "GET",
            f"/v1/manual-checks/{check_id}/risks/",
            params={"page": page, "page_size": page_size},
        )
        return RiskListResponse(**data)

    async def get_manual_check_transfer_exposure(
        self, check_id: int
    ) -> TransferExposure:
        """Get transfer exposure for a manual check.

        Args:
            check_id: Manual check ID.

        Returns:
            Transfer exposure analysis.
        """
        data = await self._request(
            "GET", f"/v1/manual-checks/{check_id}/transfer-exposure/"
        )
        return TransferExposure(**data)

    async def get_manual_check_address_exposure(self, check_id: int) -> AddressExposure:
        """Get address exposure for a manual check.

        Args:
            check_id: Manual check ID.

        Returns:
            Address exposure analysis.
        """
        data = await self._request(
            "GET", f"/v1/manual-checks/{check_id}/address-exposure/"
        )
        return AddressExposure(**data)
