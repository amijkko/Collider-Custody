"""BitOK KYT integration service.

This module provides integration with BitOK KYT Office API for transaction screening.
Features:
- Async operation with polling for check completion
- In-memory caching with TTL
- Graceful fallback when BitOK is unavailable
- Mock mode for testing without real API credentials
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from app.config import get_settings


logger = logging.getLogger(__name__)


# Known risky addresses for mock mode (for demo/testing)
MOCK_RISKY_ADDRESSES: Dict[str, Dict[str, Any]] = {
    # Sanctioned addresses (OFAC)
    "0x8589427373d6d84e98730d7795d8f6f8731fda16": {
        "risk_level": "severe",
        "result": "BLOCK",
        "category": "sanctions",
        "description": "OFAC Sanctioned Address (Tornado Cash)",
    },
    "0x722122df12d4e14e13ac3b6895a86e84145b6967": {
        "risk_level": "severe",
        "result": "BLOCK",
        "category": "sanctions",
        "description": "OFAC Sanctioned Address (Tornado Cash Router)",
    },
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": {
        "risk_level": "severe",
        "result": "BLOCK",
        "category": "sanctions",
        "description": "OFAC Sanctioned Address",
    },
    # High risk - darknet/mixer
    "0x000000000000000000000000000000000000dead": {
        "risk_level": "high",
        "result": "REVIEW",
        "category": "darknet_market",
        "description": "Associated with darknet market",
    },
    "0xbad0000000000000000000000000000000000bad": {
        "risk_level": "high",
        "result": "REVIEW",
        "category": "mixer",
        "description": "Mixing service interaction detected",
    },
    # Medium risk - gambling/unknown exchange
    "0x1234567890123456789012345678901234567890": {
        "risk_level": "medium",
        "result": "REVIEW",
        "category": "gambling",
        "description": "Online gambling platform",
    },
}

# Known good addresses for mock mode
MOCK_CLEAN_ADDRESSES: List[str] = [
    "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Binance
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d",  # Binance
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503",  # Binance
]


class BitOKCheckResult(str, Enum):
    """Result of BitOK KYT check."""
    ALLOW = "ALLOW"  # Risk level: none, low
    REVIEW = "REVIEW"  # Risk level: medium, high
    BLOCK = "BLOCK"  # Risk level: severe
    UNCHECKED = "UNCHECKED"  # BitOK unavailable, fallback mode
    ERROR = "ERROR"  # Check failed


@dataclass
class BitOKCheckResponse:
    """Response from BitOK KYT check."""
    result: BitOKCheckResult
    risk_level: Optional[str] = None  # none, low, medium, high, severe
    transfer_id: Optional[int] = None  # BitOK transfer ID
    check_id: Optional[int] = None  # BitOK manual check ID
    exposure_direct: float = 0.0  # Direct exposure percentage
    exposure_indirect: float = 0.0  # Indirect exposure percentage
    risks: list = field(default_factory=list)  # List of identified risks
    cached: bool = False  # Whether this result was from cache
    error_message: Optional[str] = None
    checked_at: Optional[datetime] = None


@dataclass
class CacheEntry:
    """Cache entry for KYT check results."""
    response: BitOKCheckResponse
    expires_at: datetime


class BitOKIntegration:
    """BitOK KYT integration service with caching and fallback."""

    def __init__(self):
        self.settings = get_settings()
        self._cache: Dict[str, CacheEntry] = {}
        self._client = None

    def _get_cache_key(self, network: str, address: str, direction: str) -> str:
        """Generate cache key for address check."""
        return f"{network.lower()}:{address.lower()}:{direction.lower()}"

    def _get_tx_cache_key(self, network: str, tx_hash: str, direction: str) -> str:
        """Generate cache key for transaction check."""
        return f"tx:{network.lower()}:{tx_hash.lower()}:{direction.lower()}"

    def _get_from_cache(self, cache_key: str) -> Optional[BitOKCheckResponse]:
        """Get result from cache if valid."""
        entry = self._cache.get(cache_key)
        if entry and entry.expires_at > datetime.utcnow():
            response = entry.response
            response.cached = True
            return response
        elif entry:
            # Expired, remove from cache
            del self._cache[cache_key]
        return None

    def _add_to_cache(self, cache_key: str, response: BitOKCheckResponse) -> None:
        """Add result to cache."""
        ttl_hours = self.settings.bitok_cache_ttl_hours
        self._cache[cache_key] = CacheEntry(
            response=response,
            expires_at=datetime.utcnow() + timedelta(hours=ttl_hours)
        )

    def _risk_level_to_result(self, risk_level: str) -> BitOKCheckResult:
        """Convert BitOK risk level to check result."""
        risk_mapping = {
            "none": BitOKCheckResult.ALLOW,
            "low": BitOKCheckResult.ALLOW,
            "medium": BitOKCheckResult.REVIEW,
            "high": BitOKCheckResult.REVIEW,
            "severe": BitOKCheckResult.BLOCK,
            "undefined": BitOKCheckResult.REVIEW,  # Treat undefined as review
        }
        return risk_mapping.get(risk_level.lower(), BitOKCheckResult.REVIEW)

    async def _get_client(self):
        """Get or create BitOK client."""
        if self._client is None:
            # Import here to avoid circular imports and allow optional dependency
            try:
                from bitok_kyt_adapter import BitOKKYTClient, BitOKSettings
            except ImportError:
                logger.error("bitok_kyt_adapter not installed")
                return None

            settings = BitOKSettings(
                api_key_id=self.settings.bitok_api_key_id,
                api_secret=self.settings.bitok_api_secret,
                base_url=self.settings.bitok_base_url,
                timeout=self.settings.bitok_timeout_seconds,
            )
            self._client = BitOKKYTClient(settings)
        return self._client

    def _generate_mock_response(self, address: str) -> BitOKCheckResponse:
        """Generate mock response based on address for testing."""
        address_lower = address.lower()

        # Check if it's a known risky address
        if address_lower in MOCK_RISKY_ADDRESSES:
            risk_info = MOCK_RISKY_ADDRESSES[address_lower]
            return BitOKCheckResponse(
                result=BitOKCheckResult[risk_info["result"]],
                risk_level=risk_info["risk_level"],
                check_id=random.randint(10000, 99999),
                exposure_direct=random.uniform(10.0, 90.0) if risk_info["result"] != "ALLOW" else 0.0,
                exposure_indirect=random.uniform(5.0, 30.0) if risk_info["result"] != "ALLOW" else 0.0,
                risks=[{
                    "risk_level": risk_info["risk_level"],
                    "risk_type": "recipient_entity",
                    "entity_category": risk_info["category"],
                    "description": risk_info["description"],
                    "proximity": "direct",
                }],
                cached=False,
                checked_at=datetime.utcnow(),
            )

        # Check if it's a known clean address
        if address_lower in [a.lower() for a in MOCK_CLEAN_ADDRESSES]:
            return BitOKCheckResponse(
                result=BitOKCheckResult.ALLOW,
                risk_level="none",
                check_id=random.randint(10000, 99999),
                exposure_direct=0.0,
                exposure_indirect=0.0,
                risks=[],
                cached=False,
                checked_at=datetime.utcnow(),
            )

        # For unknown addresses, use deterministic "random" based on address hash
        # This ensures consistent results for the same address
        addr_hash = int(hashlib.md5(address_lower.encode()).hexdigest(), 16)
        risk_score = (addr_hash % 100) / 100.0

        if risk_score < 0.7:  # 70% chance of clean
            return BitOKCheckResponse(
                result=BitOKCheckResult.ALLOW,
                risk_level="none" if risk_score < 0.5 else "low",
                check_id=random.randint(10000, 99999),
                exposure_direct=0.0,
                exposure_indirect=risk_score * 5.0,
                risks=[],
                cached=False,
                checked_at=datetime.utcnow(),
            )
        elif risk_score < 0.9:  # 20% chance of medium risk
            return BitOKCheckResponse(
                result=BitOKCheckResult.REVIEW,
                risk_level="medium",
                check_id=random.randint(10000, 99999),
                exposure_direct=risk_score * 20.0,
                exposure_indirect=risk_score * 10.0,
                risks=[{
                    "risk_level": "medium",
                    "risk_type": "recipient_exposure",
                    "entity_category": "unknown_service",
                    "proximity": "indirect",
                }],
                cached=False,
                checked_at=datetime.utcnow(),
            )
        else:  # 10% chance of high risk
            return BitOKCheckResponse(
                result=BitOKCheckResult.REVIEW,
                risk_level="high",
                check_id=random.randint(10000, 99999),
                exposure_direct=risk_score * 40.0,
                exposure_indirect=risk_score * 20.0,
                risks=[{
                    "risk_level": "high",
                    "risk_type": "recipient_exposure",
                    "entity_category": "high_risk_exchange",
                    "proximity": "indirect",
                }],
                cached=False,
                checked_at=datetime.utcnow(),
            )

    async def _simulate_api_delay(self) -> None:
        """Simulate API call delay in mock mode."""
        await asyncio.sleep(random.uniform(0.5, 2.0))

    async def check_address_outbound(
        self,
        network: str,
        address: str,
        client_id: Optional[str] = None,
    ) -> BitOKCheckResponse:
        """
        Check outbound transaction recipient address.

        This is used before sending funds to verify the recipient is not high-risk.
        Uses manual check API since we don't have a transaction yet.
        """
        if not self.settings.bitok_enabled:
            return BitOKCheckResponse(
                result=BitOKCheckResult.UNCHECKED,
                error_message="BitOK integration disabled"
            )

        # Mock mode for testing
        if self.settings.bitok_mock_mode:
            logger.info(f"BitOK MOCK: Checking address {address}")
            cache_key = self._get_cache_key(network, address, "outgoing")
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

            await self._simulate_api_delay()
            response = self._generate_mock_response(address)
            self._add_to_cache(cache_key, response)
            return response

        # Check cache first
        cache_key = self._get_cache_key(network, address, "outgoing")
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"BitOK cache hit for {address} (outbound)")
            return cached

        try:
            client = await self._get_client()
            if client is None:
                return self._fallback_response("BitOK client not available")

            async with client:
                from bitok_kyt_adapter.schemas import CheckAddressRequest
                from bitok_kyt_adapter.helpers import await_manual_check_complete

                # Submit address check
                request = CheckAddressRequest(
                    network=network.upper(),
                    address=address,
                )
                check = await client.check_address(request)
                logger.info(f"BitOK manual check created: {check.id}")

                # Wait for check to complete
                completed_check = await await_manual_check_complete(
                    client,
                    check.id,
                    poll_interval_ms=self.settings.bitok_poll_interval_ms,
                    timeout_ms=self.settings.bitok_poll_timeout_ms,
                )

                # Get exposure details
                exposure = await client.get_manual_check_address_exposure(check.id)
                risks = await client.get_manual_check_risks(check.id)

                response = BitOKCheckResponse(
                    result=self._risk_level_to_result(completed_check.risk_level.value),
                    risk_level=completed_check.risk_level.value,
                    check_id=completed_check.id,
                    exposure_direct=getattr(exposure, 'exposure_direct', 0.0) or 0.0,
                    exposure_indirect=getattr(exposure, 'exposure_indirect', 0.0) or 0.0,
                    risks=[r.dict() for r in risks] if risks else [],
                    cached=False,
                    checked_at=datetime.utcnow(),
                )

                # Cache the result
                self._add_to_cache(cache_key, response)
                return response

        except Exception as e:
            logger.exception(f"BitOK check failed for {address}: {e}")
            return self._fallback_response(str(e))

    async def check_transfer_inbound(
        self,
        network: str,
        tx_hash: str,
        output_address: str,
        token_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> BitOKCheckResponse:
        """
        Check inbound transaction (deposit).

        Registers the transfer and waits for exposure analysis.
        """
        if not self.settings.bitok_enabled:
            return BitOKCheckResponse(
                result=BitOKCheckResult.UNCHECKED,
                error_message="BitOK integration disabled"
            )

        # Mock mode for testing
        if self.settings.bitok_mock_mode:
            logger.info(f"BitOK MOCK: Checking inbound tx {tx_hash}")
            cache_key = self._get_tx_cache_key(network, tx_hash, "incoming")
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

            await self._simulate_api_delay()
            # For inbound, generate response based on a mock "sender" address
            # derived from tx_hash for consistency
            mock_sender = "0x" + tx_hash[2:42] if tx_hash.startswith("0x") else "0x" + tx_hash[:40]
            response = self._generate_mock_response(mock_sender)
            response.transfer_id = random.randint(10000, 99999)
            self._add_to_cache(cache_key, response)
            return response

        # Check cache first
        cache_key = self._get_tx_cache_key(network, tx_hash, "incoming")
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"BitOK cache hit for tx {tx_hash} (inbound)")
            return cached

        try:
            client = await self._get_client()
            if client is None:
                return self._fallback_response("BitOK client not available")

            async with client:
                from bitok_kyt_adapter.schemas import RegisterTransferRequest, TransferDirection
                from bitok_kyt_adapter.helpers import await_transfer_check_complete

                # Register the transfer
                request = RegisterTransferRequest(
                    direction=TransferDirection.INCOMING,
                    network=network.upper(),
                    tx_hash=tx_hash,
                    output_address=output_address,
                    token_id=token_id,
                    client_id=client_id,
                )
                transfer = await client.register_transfer(request)
                logger.info(f"BitOK transfer registered: {transfer.id}")

                # Wait for check to complete
                completed_transfer = await await_transfer_check_complete(
                    client,
                    transfer.id,
                    poll_interval_ms=self.settings.bitok_poll_interval_ms,
                    timeout_ms=self.settings.bitok_poll_timeout_ms,
                )

                # Get exposure and risks
                exposure = await client.get_transfer_exposure(transfer.id)
                risks = await client.get_transfer_risks(transfer.id)

                response = BitOKCheckResponse(
                    result=self._risk_level_to_result(completed_transfer.risk_level.value),
                    risk_level=completed_transfer.risk_level.value,
                    transfer_id=completed_transfer.id,
                    exposure_direct=getattr(exposure, 'exposure_direct', 0.0) or 0.0,
                    exposure_indirect=getattr(exposure, 'exposure_indirect', 0.0) or 0.0,
                    risks=[r.dict() for r in risks] if risks else [],
                    cached=False,
                    checked_at=datetime.utcnow(),
                )

                # Cache the result
                self._add_to_cache(cache_key, response)
                return response

        except Exception as e:
            logger.exception(f"BitOK check failed for tx {tx_hash}: {e}")
            return self._fallback_response(str(e))

    async def check_transfer_outbound(
        self,
        network: str,
        to_address: str,
        from_address: str,
        token_id: Optional[str] = None,
        amount: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> BitOKCheckResponse:
        """
        Pre-check outbound transaction (withdrawal attempt).

        Uses register-attempt API to check before the transaction is created.
        """
        if not self.settings.bitok_enabled:
            return BitOKCheckResponse(
                result=BitOKCheckResult.UNCHECKED,
                error_message="BitOK integration disabled"
            )

        # Mock mode for testing
        if self.settings.bitok_mock_mode:
            logger.info(f"BitOK MOCK: Checking outbound to {to_address}")
            cache_key = self._get_cache_key(network, to_address, "outgoing")
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached

            await self._simulate_api_delay()
            response = self._generate_mock_response(to_address)
            response.transfer_id = random.randint(10000, 99999)
            self._add_to_cache(cache_key, response)
            return response

        # For outbound, we check the recipient address
        # Use cache key based on recipient
        cache_key = self._get_cache_key(network, to_address, "outgoing")
        cached = self._get_from_cache(cache_key)
        if cached:
            logger.info(f"BitOK cache hit for {to_address} (outbound)")
            return cached

        try:
            client = await self._get_client()
            if client is None:
                return self._fallback_response("BitOK client not available")

            async with client:
                from bitok_kyt_adapter.schemas import RegisterAttemptRequest, TransferDirection
                from bitok_kyt_adapter.helpers import await_transfer_check_complete

                # Register the attempt
                request = RegisterAttemptRequest(
                    direction=TransferDirection.OUTGOING,
                    network=network.upper(),
                    output_address=to_address,
                    token_id=token_id,
                    client_id=client_id,
                )
                transfer = await client.register_transfer_attempt(request)
                logger.info(f"BitOK transfer attempt registered: {transfer.id}")

                # Wait for check to complete
                completed_transfer = await await_transfer_check_complete(
                    client,
                    transfer.id,
                    poll_interval_ms=self.settings.bitok_poll_interval_ms,
                    timeout_ms=self.settings.bitok_poll_timeout_ms,
                )

                # Get exposure and risks
                exposure = await client.get_transfer_exposure(transfer.id)
                risks = await client.get_transfer_risks(transfer.id)

                response = BitOKCheckResponse(
                    result=self._risk_level_to_result(completed_transfer.risk_level.value),
                    risk_level=completed_transfer.risk_level.value,
                    transfer_id=completed_transfer.id,
                    exposure_direct=getattr(exposure, 'exposure_direct', 0.0) or 0.0,
                    exposure_indirect=getattr(exposure, 'exposure_indirect', 0.0) or 0.0,
                    risks=[r.dict() for r in risks] if risks else [],
                    cached=False,
                    checked_at=datetime.utcnow(),
                )

                # Cache the result
                self._add_to_cache(cache_key, response)
                return response

        except Exception as e:
            logger.exception(f"BitOK check failed for outbound to {to_address}: {e}")
            return self._fallback_response(str(e))

    def _fallback_response(self, error_message: str) -> BitOKCheckResponse:
        """Create fallback response when BitOK is unavailable."""
        if self.settings.bitok_fallback_on_error:
            logger.warning(f"BitOK fallback: passing with UNCHECKED flag. Error: {error_message}")
            return BitOKCheckResponse(
                result=BitOKCheckResult.UNCHECKED,
                error_message=error_message,
                checked_at=datetime.utcnow(),
            )
        else:
            logger.error(f"BitOK error, no fallback: {error_message}")
            return BitOKCheckResponse(
                result=BitOKCheckResult.ERROR,
                error_message=error_message,
                checked_at=datetime.utcnow(),
            )

    def clear_cache(self) -> int:
        """Clear all cached entries. Returns number of entries cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = datetime.utcnow()
        valid_entries = sum(1 for e in self._cache.values() if e.expires_at > now)
        expired_entries = len(self._cache) - valid_entries
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "ttl_hours": self.settings.bitok_cache_ttl_hours,
        }


# Singleton instance
_bitok_integration: Optional[BitOKIntegration] = None


def get_bitok_integration() -> BitOKIntegration:
    """Get BitOK integration singleton."""
    global _bitok_integration
    if _bitok_integration is None:
        _bitok_integration = BitOKIntegration()
    return _bitok_integration
