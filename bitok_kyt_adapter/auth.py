"""HMAC-SHA256 authentication for BitOK KYT API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class BitOKAuth:
    """Handles HMAC-SHA256 signature generation for BitOK API requests.

    The signature is computed as:
        stringToSign = METHOD + '\\n' + endpoint + '\\n' + timestamp [+ '\\n' + minifiedJSON]
        signature = Base64(HMAC-SHA256(secret, stringToSign))
    """

    def __init__(self, api_key_id: str, api_secret: str):
        """Initialize authenticator.

        Args:
            api_key_id: The API key ID.
            api_secret: The API secret for signing.
        """
        self.api_key_id = api_key_id
        self.api_secret = api_secret

    def get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    def minify_json(self, body: dict[str, Any] | None) -> str | None:
        """Minify JSON body with no spaces.

        Args:
            body: Request body dictionary.

        Returns:
            Minified JSON string or None if body is None/empty.
        """
        if not body:
            return None
        return json.dumps(body, separators=(",", ":"), sort_keys=False)

    def compute_signature(
        self,
        method: str,
        endpoint: str,
        timestamp: int,
        body: dict[str, Any] | None = None,
    ) -> str:
        """Compute HMAC-SHA256 signature for a request.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path with query string if any.
            timestamp: Request timestamp in milliseconds.
            body: Optional request body dictionary.

        Returns:
            Base64-encoded signature.
        """
        # Build string to sign
        string_to_sign = f"{method}\n{endpoint}\n{timestamp}"

        minified = self.minify_json(body)
        if minified:
            string_to_sign += f"\n{minified}"

        # Compute HMAC-SHA256
        signature_bytes = hmac.new(
            self.api_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        # Return base64-encoded signature
        return base64.b64encode(signature_bytes).decode("utf-8")

    def get_headers(
        self,
        method: str,
        endpoint: str,
        body: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> dict[str, str]:
        """Generate authentication headers for a request.

        Args:
            method: HTTP method.
            endpoint: API endpoint path with query string.
            body: Optional request body.
            timestamp: Optional timestamp (uses current time if not provided).

        Returns:
            Dictionary of authentication headers.
        """
        if timestamp is None:
            timestamp = self.get_timestamp()

        signature = self.compute_signature(method, endpoint, timestamp, body)

        headers = {
            "X-API-KEY": self.api_key_id,
            "X-ACCESS-SIGN": signature,
            "X-ACCESS-TIMESTAMP": str(timestamp),
        }

        if body:
            headers["Content-Type"] = "application/json"

        return headers
