from __future__ import annotations
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# In container, this file is at /app/backend/alembic/env.py
# Project root for imports should be /app
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load .env so Alembic can access DB URLs like the app does
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except Exception:
    # If python-dotenv isn't available, rely on environment variables
    pass

from backend.app import models  # noqa: E402
from backend.app.base import Base  # noqa: E402
# User and RefreshToken models are now in models.py, so they're already imported above

config = context.config

# Ensure script_location is set (critical for container environment)
if not config.get_main_option("script_location"):
    # When config_file_name is None or script_location missing, set it manually
    alembic_dir = os.path.join(os.path.dirname(__file__))
    config.set_main_option("script_location", alembic_dir)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL_SYNC")
    if not url:
        async_url = os.getenv("DATABASE_URL_ASYNC") or os.getenv("DATABASE_URL")
        if not async_url:
            raise RuntimeError("DATABASE_URL_SYNC or DATABASE_URL_ASYNC must be set in environment for Alembic.")
        url = async_url.replace("+asyncpg", "")
    return url


def run_migrations_offline() -> None:
    url = _get_database_url()
    config.set_main_option("sqlalchemy.url", url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _get_database_url()
    config.set_main_option("sqlalchemy.url", url)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

