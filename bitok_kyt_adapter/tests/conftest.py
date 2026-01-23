"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def api_key_id() -> str:
    """Test API key ID from BitOK API guide."""
    return "qgbtA4OrsHIx67APkTFGfUSctuEEwOYm"


@pytest.fixture
def api_secret() -> str:
    """Test API secret from BitOK API guide."""
    return "CXOlYKZgeSM3TpIyPwjSM84Ews2hARKi2m1MlLpnbI7UrF5bqtB2WQ3nW6Qh4vSJ"


@pytest.fixture
def mock_settings(api_key_id: str, api_secret: str):
    """Create test settings."""
    from bitok_kyt_adapter.config import BitOKSettings

    return BitOKSettings(
        api_key_id=api_key_id,
        api_secret=api_secret,
        base_url="https://api.test.bitok.org",
    )
