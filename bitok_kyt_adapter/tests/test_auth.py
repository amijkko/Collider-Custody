"""Tests for authentication module."""

import pytest

from bitok_kyt_adapter.auth import BitOKAuth


class TestBitOKAuth:
    """Test HMAC-SHA256 signature generation."""

    def test_golden_signature_post_request(
        self, api_key_id: str, api_secret: str
    ) -> None:
        """Test signature matches expected value from API guide.

        This is the golden test case from the BitOK KYT Office API Guide v1.4 (page 13).
        """
        auth = BitOKAuth(api_key_id, api_secret)

        # Values from API guide page 13
        method = "POST"
        endpoint = "/v1/transfers/register/"
        timestamp = 1713449845309
        body = {
            "client_id": None,
            "direction": "incoming",
            "network": "ETH",
            "tx_hash": "0x28138cd586826bbad08d1d0e64b566795b5907790ad30ebb0722948c2ba21d09",
            "token_id": "usdt",
            "output_address": "0x016606acc6b0cfe537acc221e3bf1bb44b4049ee",
        }

        signature = auth.compute_signature(method, endpoint, timestamp, body)

        # Expected signature from API guide
        expected = "2dJYm8qkR8fCO3s7ZsSVBo1xKpLgx/eYAkewE82pyIs="
        assert signature == expected

    def test_signature_with_body(self, api_key_id: str, api_secret: str) -> None:
        """Test signature generation with request body."""
        auth = BitOKAuth(api_key_id, api_secret)

        method = "POST"
        endpoint = "/v1/transfers/register/"
        timestamp = 1734362044091
        body = {
            "direction": "incoming",
            "network": "eth",
            "address": "0x1234567890abcdef1234567890abcdef12345678",
        }

        signature = auth.compute_signature(method, endpoint, timestamp, body)

        # Signature should be non-empty base64 string
        assert signature
        assert len(signature) == 44  # Base64 of SHA256 is always 44 chars

    def test_minify_json(self, api_key_id: str, api_secret: str) -> None:
        """Test JSON minification removes all whitespace."""
        auth = BitOKAuth(api_key_id, api_secret)

        body = {"key1": "value1", "key2": 123, "nested": {"a": 1, "b": 2}}
        minified = auth.minify_json(body)

        # Should have no spaces
        assert " " not in minified
        assert minified == '{"key1":"value1","key2":123,"nested":{"a":1,"b":2}}'

    def test_minify_json_none(self, api_key_id: str, api_secret: str) -> None:
        """Test minify_json returns None for None/empty body."""
        auth = BitOKAuth(api_key_id, api_secret)

        assert auth.minify_json(None) is None
        assert auth.minify_json({}) is None

    def test_get_headers(self, api_key_id: str, api_secret: str) -> None:
        """Test header generation includes all required fields."""
        auth = BitOKAuth(api_key_id, api_secret)

        headers = auth.get_headers("GET", "/v1/transfers/")

        assert "X-API-KEY" in headers
        assert "X-ACCESS-SIGN" in headers
        assert "X-ACCESS-TIMESTAMP" in headers
        assert headers["X-API-KEY"] == api_key_id

    def test_get_headers_with_body(self, api_key_id: str, api_secret: str) -> None:
        """Test headers include Content-Type when body is provided."""
        auth = BitOKAuth(api_key_id, api_secret)

        headers = auth.get_headers(
            "POST", "/v1/transfers/register/", body={"key": "value"}
        )

        assert headers.get("Content-Type") == "application/json"

    def test_timestamp_is_milliseconds(self, api_key_id: str, api_secret: str) -> None:
        """Test that timestamp is in milliseconds."""
        auth = BitOKAuth(api_key_id, api_secret)

        timestamp = auth.get_timestamp()

        # Timestamp should be around current time in milliseconds
        # It should be a 13-digit number (until year 2286)
        assert len(str(timestamp)) == 13
