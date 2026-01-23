"""Alembic environment configuration."""
import logging
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.config import get_settings
from app.database import Base
from app.models import *  # noqa: Import all models for autogenerate

# Setup basic logging BEFORE anything else to ensure we see debug messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# this is the Alembic Config object
config = context.config

# Get database URL from settings
# Clear cache to ensure fresh settings
get_settings.cache_clear()
settings = get_settings()

# Log for debugging - use both logger and print to ensure visibility
db_url_env = os.getenv('DATABASE_URL', 'NOT SET')
db_sync_env = os.getenv('DATABASE_URL_SYNC', 'NOT SET')
db_url_setting = settings.database_url[:50] + "..." if len(settings.database_url) > 50 else settings.database_url
db_sync_setting = (settings.database_url_sync[:50] + "..." if settings.database_url_sync and len(settings.database_url_sync) > 50 else (settings.database_url_sync or 'None'))

# Print to stderr for guaranteed visibility
print(f"[Alembic] DATABASE_URL from env: {db_url_env}", file=sys.stderr, flush=True)
print(f"[Alembic] DATABASE_URL_SYNC from env: {db_sync_env}", file=sys.stderr, flush=True)
print(f"[Alembic] settings.database_url: {db_url_setting}", file=sys.stderr, flush=True)
print(f"[Alembic] settings.database_url_sync: {db_sync_setting}", file=sys.stderr, flush=True)

logger.info(f"DATABASE_URL from env: {db_url_env}")
logger.info(f"DATABASE_URL_SYNC from env: {db_sync_env}")
logger.info(f"settings.database_url: {db_url_setting}")
logger.info(f"settings.database_url_sync: {db_sync_setting}")

# Validate that we have a valid database URL
# Allow localhost for local development
if not settings.database_url_sync:
    error_msg = f"ERROR: DATABASE_URL_SYNC is empty!"
    print(f"[Alembic] {error_msg}", file=sys.stderr, flush=True)
    logger.error(error_msg)
    raise ValueError(f"Invalid database configuration. DATABASE_URL_SYNC must be set.")

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

