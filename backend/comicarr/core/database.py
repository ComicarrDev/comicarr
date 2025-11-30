"""Database configuration and setup for Comicarr.

Handles SQLite async database setup with proper concurrency handling:
- WAL mode for better concurrent reads/writes
- Connection pooling with appropriate sizing
- Retry logic for database locks
- Session factory for dependency injection
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.metrics import (
    db_connections_active,
    db_connections_idle,
    db_connections_overflow,
    db_lock_errors_total,
    db_pool_max_overflow,
    db_pool_size,
    db_retries_failed_total,
    db_retries_succeeded_total,
    db_retry_attempts_total,
    db_retry_duration_seconds,
)

logger = structlog.get_logger("comicarr.database")

# Global storage for session factory (needed when app is mounted)
_global_session_factory: Any | None = None


def set_global_session_factory(session_factory: Any) -> None:
    """Set the global session factory.

    Args:
        session_factory: The async session factory to store globally
    """
    global _global_session_factory
    _global_session_factory = session_factory
    logger.debug("Global session factory set")


def get_global_session_factory() -> Any | None:
    """Get the global session factory.

    Returns:
        The async session factory or None if not set
    """
    return _global_session_factory


def create_database_engine(
    database_file: Path,
    echo: bool = False,
) -> AsyncEngine:
    """Create and configure the database engine for async SQLite.

    Configures SQLite for concurrent access with:
    - WAL mode (Write-Ahead Logging) for better concurrency
    - Connection pooling for performance
    - Timeout for lock retries
    - Foreign key constraints enabled

    Args:
        database_file: Path to the SQLite database file.
        echo: If True, log all SQL statements (useful for debugging).

    Returns:
        Configured AsyncEngine instance.
    """
    database_url = f"sqlite+aiosqlite:///{database_file}"

    # Configure SQLite for concurrent access:
    # - Set timeout for lock retries (30 seconds)
    #   This allows SQLite to wait for locks to be released instead of failing immediately
    connect_args = {
        "timeout": 30.0,  # Wait up to 30 seconds for locks to be released
    }

    # Connection pool configuration
    pool_size = 10
    max_overflow = 20

    # Create async engine with connection pooling
    engine = create_async_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,  # Verify connections before using (handles stale connections)
        pool_size=pool_size,
        max_overflow=max_overflow,
    )

    # Set pool size metrics
    db_pool_size.set(pool_size)
    db_pool_max_overflow.set(max_overflow)

    # Enable WAL mode and other SQLite optimizations for async connections
    # WAL mode allows multiple readers and one writer simultaneously
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
        """Enable WAL mode and other SQLite optimizations."""
        cursor = dbapi_conn.cursor()
        try:
            # WAL mode: allows concurrent reads while writing
            cursor.execute("PRAGMA journal_mode=WAL")
            # NORMAL synchronous: balance between safety and performance
            # (FULL is safer but slower, OFF is faster but riskier)
            cursor.execute("PRAGMA synchronous=NORMAL")
            # Enable foreign key constraints
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    # Instrument connection pool events for metrics
    @event.listens_for(engine.sync_engine, "checkout")
    def on_connection_checkout(
        dbapi_conn: Any, connection_record: Any, connection_proxy: Any
    ) -> None:
        """Track when a connection is checked out from the pool."""
        pool = engine.sync_engine.pool
        db_connections_active.set(pool.checkedout())  # type: ignore[attr-defined]
        db_connections_idle.set(pool.checkedin())  # type: ignore[attr-defined]
        overflow = max(0, pool.checkedout() - pool_size)  # type: ignore[attr-defined]
        db_connections_overflow.set(overflow)

    @event.listens_for(engine.sync_engine, "checkin")
    def on_connection_checkin(dbapi_conn: Any, connection_record: Any) -> None:
        """Track when a connection is returned to the pool."""
        pool = engine.sync_engine.pool
        db_connections_active.set(pool.checkedout())  # type: ignore[attr-defined]
        db_connections_idle.set(pool.checkedin())  # type: ignore[attr-defined]
        overflow = max(0, pool.checkedout() - pool_size)  # type: ignore[attr-defined]
        db_connections_overflow.set(overflow)

    logger.info(
        "Database engine created",
        database_file=str(database_file),
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[SQLModelAsyncSession]:
    """Create a session factory for database sessions.

    Uses SQLModel's AsyncSession which combines SQLAlchemy async with Pydantic.
    expire_on_commit=False is important for async sessions to avoid lazy loading issues.

    Args:
        engine: The database engine.

    Returns:
        Configured async_sessionmaker instance.
    """
    return async_sessionmaker(
        engine,
        class_=SQLModelAsyncSession,
        expire_on_commit=False,  # Important for async: prevents stale data issues
    )


async def retry_db_operation(
    operation: Callable[[], Awaitable[Any]],
    session: SQLModelAsyncSession | None = None,
    max_retries: int = 5,
    retry_delay: float = 0.1,
    operation_type: str = "unknown",
) -> Any:
    """Retry a database operation on SQLite lock errors with exponential backoff.

    SQLite can encounter OperationalError when multiple operations try to access
    the database simultaneously. This function retries the operation with exponential
    backoff, rolling back the session if needed to clear bad state.

    Args:
        operation: Async function (lambda or callable) to execute. Should be a callable
                   that returns an awaitable (not already awaited).
        session: Optional database session to rollback on lock errors.
        max_retries: Maximum number of retry attempts (default: 5).
        retry_delay: Initial delay between retries in seconds (default: 0.1).
                    Delay doubles with each retry (exponential backoff).
        operation_type: Type of operation for metrics tracking (default: "unknown").
                       Examples: "query", "insert", "update", "delete", "commit".

    Returns:
        Result of the operation.

    Raises:
        OperationalError: If operation fails after max_retries.
        PendingRollbackError: If session has pending rollback that can't be cleared.
        Any other exception raised by the operation.

    Example:
        ```python
        async with async_session_factory() as session:
            await retry_db_operation(
                lambda: session.execute(select(Model).where(Model.id == "123")),
                session=session,
                operation_type="query",
            )
        ```
    """
    start_time = time.time()
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            result = await operation()

            # Operation succeeded
            if attempt > 0:
                # This was a retry that succeeded
                db_retries_succeeded_total.labels(operation_type=operation_type).inc()
                duration = time.time() - start_time
                db_retry_duration_seconds.labels(operation_type=operation_type).observe(duration)

            return result
        except OperationalError as exc:
            error_msg = str(exc).lower()
            last_exception = exc

            # Check if it's a lock-related error
            if "locked" in error_msg and attempt < max_retries - 1:
                # Track lock error and retry attempt
                db_lock_errors_total.inc()
                db_retry_attempts_total.labels(operation_type=operation_type).inc()

                logger.debug(
                    "Database lock detected, retrying",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    operation_type=operation_type,
                    error=str(exc)[:100],  # Truncate long error messages
                )

                # Rollback session if provided to clear the bad state
                if session is not None:
                    try:
                        await session.rollback()
                    except Exception as rollback_exc:
                        logger.debug(
                            "Error during rollback after lock",
                            error=str(rollback_exc)[:100],
                        )
                        # Continue anyway - rollback might have partially worked

                # Exponential backoff: delay doubles with each retry
                delay = retry_delay * (2**attempt)
                await asyncio.sleep(delay)
                continue

            # Not a lock error, or max retries reached
            if attempt > 0:
                # Track failed retry
                duration = time.time() - start_time
                db_retry_duration_seconds.labels(operation_type=operation_type).observe(duration)

            logger.error(
                "Database operation failed",
                attempt=attempt + 1,
                max_retries=max_retries,
                operation_type=operation_type,
                error=str(exc)[:200],
            )
            raise
        except PendingRollbackError as exc:
            last_exception = exc
            # Session needs rollback before retrying
            if session is not None and attempt < max_retries - 1:
                db_retry_attempts_total.labels(operation_type=operation_type).inc()

                logger.debug(
                    "Pending rollback detected, rolling back and retrying",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    operation_type=operation_type,
                )
                try:
                    await session.rollback()
                    delay = retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
                    continue
                except Exception as rollback_exc:
                    logger.error(
                        "Error during rollback",
                        error=str(rollback_exc)[:200],
                    )
            # Can't clear pending rollback or max retries reached
            if attempt > 0:
                duration = time.time() - start_time
                db_retry_duration_seconds.labels(operation_type=operation_type).observe(duration)

            logger.error(
                "Pending rollback could not be cleared",
                attempt=attempt + 1,
                max_retries=max_retries,
                operation_type=operation_type,
            )
            raise

    # All retries exhausted - track failure
    if max_retries > 0:
        duration = time.time() - start_time
        db_retry_duration_seconds.labels(operation_type=operation_type).observe(duration)
        db_retries_failed_total.labels(operation_type=operation_type).inc()

    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError(f"Operation failed after {max_retries} retries")


async def check_database_schema(engine: AsyncEngine) -> bool:
    """Check if database migrations are needed without running them.

    Checks the current database revision against the Alembic head revision.
    Logs warnings if migrations are needed, but does not run them automatically
    (per DESIGN.md: migrations are not in the bootstrap path).

    Args:
        engine: The database engine.

    Returns:
        True if migrations are needed, False if database is up to date or check failed.
    """
    from alembic import script
    from alembic.config import Config
    from sqlalchemy import text as sa_text

    # Get the backend directory (where alembic.ini would be located)
    backend_dir = Path(__file__).resolve().parent.parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"

    if not alembic_ini_path.exists():
        logger.debug("Alembic config not found - skipping migration check")
        return False

    # Configure Alembic
    try:
        alembic_cfg = Config(str(alembic_ini_path))
        script_location = backend_dir / "comicarr" / "db" / "migrations"
        if not script_location.exists():
            logger.debug("Migration scripts directory not found - skipping migration check")
            return False

        alembic_cfg.set_main_option("script_location", str(script_location))

        # Get head revision from migration scripts
        script_dir = script.ScriptDirectory.from_config(alembic_cfg)
        head_revision = script_dir.get_current_head()

        if head_revision is None:
            logger.debug("No head revision found - skipping migration check")
            return False

        # Get current database revision
        async with engine.connect() as conn:
            # Check if alembic_version table exists
            result = await conn.execute(
                sa_text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
                )
            )
            has_version_table = result.fetchone() is not None

            if not has_version_table:
                logger.warning(
                    "⚠️  Database migrations are needed! Database is not initialized. "
                    "Run 'alembic upgrade head' to apply migrations."
                )
                return True

            # Get current revision
            result = await conn.execute(sa_text("SELECT version_num FROM alembic_version LIMIT 1"))
            row = result.fetchone()
            current_rev = row[0] if row else None

            if current_rev != head_revision:
                logger.warning(
                    "⚠️  Database migrations are needed! Current: %s, Head: %s. "
                    "Run 'alembic upgrade head' to apply migrations.",
                    current_rev or "none",
                    head_revision,
                )
                return True
            else:
                logger.debug("Database is up to date", revision=current_rev)
                return False

    except Exception as exc:
        logger.debug("Could not check migration status", error=str(exc)[:200])
        return False
