"""Alembic environment configuration for async SQLModel migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import metadata from db module
from comicarr.db import metadata

# Import all models to register them with SQLModel metadata
from comicarr.db.models import (  # noqa: F401 - Imported for metadata registration
    ImportJob,
    ImportPendingFile,
    ImportProcessingJob,
    ImportScanningJob,
    IncludePath,
    Indexer,
    Library,
    LibraryIssue,
    LibraryVolume,
    WeeklyReleaseItem,
    WeeklyReleaseMatchingJob,
    WeeklyReleaseProcessingJob,
    WeeklyReleaseWeek,
)

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLModel metadata for Alembic
target_metadata = metadata


def get_url() -> str:
    """Get database URL from settings.

    Uses the same configuration system as the application to ensure consistency.
    Constructs URL the same way the app does (using Path directly).
    """
    from comicarr.core.config import get_settings

    settings = get_settings()
    # Ensure database directory exists
    settings.database_dir.mkdir(parents=True, exist_ok=True)

    # Construct URL the same way the app does (using Path directly)
    # This matches create_database_engine() in database.py
    database_file = settings.database_dir / "comicarr.db"
    db_path = str(database_file.resolve())
    return f"sqlite+aiosqlite:///{db_path}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    # Enable WAL mode and other SQLite optimizations (same as app)
    # This ensures WAL files are created and migrations use the same settings
    connection.execute(sa_text("PRAGMA journal_mode=WAL"))
    connection.execute(sa_text("PRAGMA synchronous=NORMAL"))
    connection.execute(sa_text("PRAGMA foreign_keys=ON"))

    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Don't use connection pooling for migrations
    )

    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
        # Explicit commit for async transactions
        await connection.commit()

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Handles both async and sync contexts gracefully.
    If already in an async event loop, runs migrations synchronously.
    Otherwise, uses async migrations.
    """
    try:
        loop = asyncio.get_running_loop()
        # Already in async context (e.g., during FastAPI startup)
        # Run migrations synchronously using SQLite sync engine
        # This avoids async event loop conflicts
        from sqlalchemy import create_engine

        # Convert async URL to sync URL
        # For absolute paths, we need 4 slashes: sqlite:////absolute/path
        async_url = get_url()
        if async_url.startswith("sqlite+aiosqlite:///"):
            # Extract the path part
            path = async_url.replace("sqlite+aiosqlite:///", "")
            # For absolute paths on Unix, use 4 slashes
            if path.startswith("/"):
                url = f"sqlite:////{path}"
            else:
                url = f"sqlite:///{path}"
        else:
            url = async_url.replace("+aiosqlite:///", ":///")

        engine = create_engine(url, poolclass=pool.NullPool, echo=False)
        try:
            with engine.connect() as connection:
                do_run_migrations(connection)
                connection.commit()
        finally:
            engine.dispose()
    except RuntimeError:
        # No running loop - safe to use asyncio.run
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
