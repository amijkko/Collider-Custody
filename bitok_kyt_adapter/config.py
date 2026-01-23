"""Configuration settings for BitOK KYT Adapter."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BitOKSettings(BaseSettings):
    """BitOK KYT API configuration.

    All settings can be configured via environment variables with BITOK_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="BITOK_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    api_key_id: str = Field(
        ...,
        description="BitOK API Key ID",
    )
    api_secret: str = Field(
        ...,
        description="BitOK API Secret for HMAC-SHA256 signing",
    )
    base_url: str = Field(
        default="https://api.bitok.org",
        description="BitOK API base URL",
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="HTTP request timeout in seconds",
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed requests",
    )
    retry_min_wait_seconds: float = Field(
        default=1.0,
        description="Minimum wait time between retries in seconds",
    )
    retry_max_wait_seconds: float = Field(
        default=10.0,
        description="Maximum wait time between retries in seconds",
    )
