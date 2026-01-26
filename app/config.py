"""Application configuration."""
import os
from functools import lru_cache
from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://collider:collider_dev_pass@localhost:5432/collider_custody"
    database_url_sync: Optional[str] = None

    @model_validator(mode='after')
    def process_database_urls(self):
        """Process database URLs for async/sync compatibility."""
        # Strip whitespace/newlines from URLs (Railway sometimes adds trailing newlines)
        self.database_url = self.database_url.strip()
        if self.database_url_sync:
            self.database_url_sync = self.database_url_sync.strip()

        # Convert postgresql:// to postgresql+asyncpg:// for async driver
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Auto-generate DATABASE_URL_SYNC from DATABASE_URL if not set
        if self.database_url_sync is None or self.database_url_sync == "":
            # Replace +asyncpg with empty string for sync connection
            self.database_url_sync = self.database_url.replace("+asyncpg", "")
        return self
    
    # Ethereum
    eth_rpc_url: str = "https://ethereum-sepolia-rpc.publicnode.com"
    
    # Dev Signer (NEVER use in production with real funds!)
    dev_signer_private_key: str = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    
    # JWT
    jwt_secret: str = "dev_jwt_secret_change_in_production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    
    # Environment
    environment: str = "development"
    
    # Chain Listener
    chain_listener_poll_interval: int = 5
    confirmation_blocks: int = 3
    
    # KYT Mock Config
    kyt_blacklist: str = "0x000000000000000000000000000000000000dead,0xbad0000000000000000000000000000000000bad"
    kyt_graylist: str = "0x1234567890123456789012345678901234567890"
    
    # MPC Signer (Bank Node)
    mpc_signer_url: str = "localhost:50051"
    mpc_signer_enabled: bool = False  # Set to True when using real MPC
    mpc_permit_secret: str = "dev_permit_secret_minimum_32_characters_long"

    # Auto-seed demo data on startup
    auto_seed: bool = False  # Set to True to seed Retail group and policies on startup

    # BitOK KYT Integration
    bitok_enabled: bool = False  # Set to True to enable BitOK KYT
    bitok_mock_mode: bool = False  # Mock mode for testing without real API
    bitok_api_key_id: str = ""
    bitok_api_secret: str = ""
    bitok_base_url: str = "https://kyt-api.bitok.org"
    bitok_timeout_seconds: int = 30
    bitok_cache_ttl_hours: int = 24
    bitok_poll_interval_ms: int = 2000
    bitok_poll_timeout_ms: int = 120000
    bitok_fallback_on_error: bool = True  # Pass transactions with "unchecked" flag when BitOK unavailable
    
    @property
    def kyt_blacklist_addresses(self) -> List[str]:
        """Parse blacklist addresses."""
        return [addr.lower().strip() for addr in self.kyt_blacklist.split(",") if addr.strip()]
    
    @property
    def kyt_graylist_addresses(self) -> List[str]:
        """Parse graylist addresses."""
        return [addr.lower().strip() for addr in self.kyt_graylist.split(",") if addr.strip()]
    
    class Config:
        env_file = ".env"
        extra = "ignore"
        # Allow reading from environment variables (case-insensitive)
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    import logging
    logger = logging.getLogger(__name__)
    
    settings = Settings()
    
    # Log for debugging (hide sensitive parts)
    db_url_masked = settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url[:30]
    db_sync_masked = settings.database_url_sync.split('@')[-1] if settings.database_url_sync and '@' in settings.database_url_sync else (settings.database_url_sync[:30] if settings.database_url_sync else 'None')
    logger.info(f"Settings loaded - DATABASE_URL: ...@{db_url_masked}, DATABASE_URL_SYNC: ...@{db_sync_masked}")
    
    return settings

