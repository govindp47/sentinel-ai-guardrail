"""
Alembic async migration environment for SentinelAI Guardrail.

Supports:
  - sqlite+aiosqlite  (local development / single-worker)
  - postgresql+asyncpg (production / multi-worker)

URL is read exclusively from AppConfig.database_url (env var DATABASE_URL).
target_metadata is intentionally None until ORM models are defined in T-007.
"""

from __future__ import annotations

import asyncio
import sys
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import context

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import ORM Base for autogenerate support.
# Lazy import keeps env.py loadable even if sentinel package path is not yet on sys.path.
try:
    _src = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src"))
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from sentinel.infrastructure.db.models import Base as _Base  # noqa: E402
    target_metadata = _Base.metadata
except Exception:
    # Fallback: autogenerate will not detect drift, but migrations still run.
    target_metadata = None


# ---------------------------------------------------------------------------
# Database URL resolution
# ---------------------------------------------------------------------------

def _get_database_url() -> str:
    """
    Resolve the database URL in priority order:
      1. Alembic -x database_url=... CLI override
      2. DATABASE_URL environment variable (via AppConfig)
      3. Value in alembic.ini (fallback only — not recommended for production)
    """
    # 1. CLI override: alembic -x database_url=postgresql+asyncpg://...
    cli_url: str | None = context.get_x_argument(as_dictionary=True).get("database_url")
    if cli_url:
        return cli_url

    # 2. AppConfig / environment variable
    #    Imported lazily to avoid circular imports and to keep env.py loadable
    #    even before the full sentinel package is installed.
    try:
        # Ensure backend/src is on sys.path when running alembic from backend/
        _src = os.path.join(os.path.dirname(__file__), "..", "src")
        _src = os.path.normpath(_src)
        if _src not in sys.path:
            sys.path.insert(0, _src)

        from sentinel.config import AppConfig  # type: ignore[import]
        return AppConfig().database_url
    except Exception:
        pass  # fall through to alembic.ini value

    # 3. alembic.ini fallback
    return config.get_main_option("sqlalchemy.url")  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Offline migrations (no live DB connection)
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Emits migration SQL to stdout / a file without connecting to the database.
    Useful for generating SQL scripts to review before applying.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (async, live DB connection)
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    """Synchronous inner function executed inside the async connection context."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations via run_sync().

    Handles both:
      - sqlite+aiosqlite  → NullPool (SQLite does not support connection pools)
      - postgresql+asyncpg → default pool
    """
    url = _get_database_url()

    # SQLite requires NullPool — it cannot share connections across threads/coroutines.
    pool_class = pool.NullPool if url.startswith("sqlite") else pool.AsyncAdaptedQueuePool

    connectable: AsyncEngine = create_async_engine(
        url,
        poolclass=pool_class,
        echo=False,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (connected) migration mode."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point dispatch
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
