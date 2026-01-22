"""Alembic environment configuration."""
import logging
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.config import get_settings
from app.database import Base
from app.models import *  # noqa: Import all models for autogenerate

logger = logging.getLogger(__name__)

# this is the Alembic Config object
config = context.config

# Get database URL from settings
# Clear cache to ensure fresh settings
from app.config import get_settings
get_settings.cache_clear()
settings = get_settings()

# Log for debugging
logger.info(f"DATABASE_URL from env: {os.getenv('DATABASE_URL', 'NOT SET')}")
logger.info(f"DATABASE_URL_SYNC from env: {os.getenv('DATABASE_URL_SYNC', 'NOT SET')}")
logger.info(f"settings.database_url: {settings.database_url[:50]}...")
logger.info(f"settings.database_url_sync: {settings.database_url_sync[:50] if settings.database_url_sync else 'None'}...")

config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

