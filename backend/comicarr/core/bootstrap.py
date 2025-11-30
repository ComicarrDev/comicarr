"""Bootstrap logic for initial application setup."""

from __future__ import annotations

import os

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.auth import hash_password
from comicarr.core.config import get_settings
from comicarr.core.indexers import BUILTIN_INDEXERS
from comicarr.core.security import SecurityConfig
from comicarr.db.models import Indexer, Library

logger = structlog.get_logger("comicarr.bootstrap")


def bootstrap_security() -> None:
    """Bootstrap security configuration.

    Checks if security.json exists:
    - If not, checks for COMICARR_USERNAME and COMICARR_PASSWORD env vars
    - If env vars exist, auto-creates user (LinuxServer.io mode)
    - If not, waits for setup via /api/auth/setup endpoint
    """
    settings = get_settings()
    security_config = SecurityConfig.load()

    # If security config already exists, we're done
    if security_config is not None:
        logger.debug(
            "Security config already exists",
            auth_method=security_config.auth_method,
            path=str(security_config.security_file),
        )
        return

    logger.info(
        "No security config found, checking for environment variables...",
        path=str(settings.config_dir / "security.json"),
    )

    # Check for environment variables (LinuxServer.io mode)
    username = os.getenv("COMICARR_USERNAME")
    password = os.getenv("COMICARR_PASSWORD")

    if username and password:
        logger.info(
            "Found COMICARR_USERNAME and COMICARR_PASSWORD env vars, auto-creating user",
            username=username,
        )

        # Create security config from env vars
        password_hash = hash_password(password)
        security_config = SecurityConfig(
            auth_method="forms",
            username=username,
            password_hash=password_hash,
        )

        try:
            security_config.save()
            logger.info(
                "Security config created from environment variables",
                username=username,
                auth_method=security_config.auth_method,
            )
        except Exception as e:
            logger.error(
                "Failed to create security config from environment variables",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
    else:
        logger.info(
            "No environment variables found, waiting for setup via /api/auth/setup endpoint",
            hint="Set COMICARR_USERNAME and COMICARR_PASSWORD for auto-setup",
        )


async def bootstrap_indexers(session: SQLModelAsyncSession) -> None:
    """Seed built-in indexers if they don't exist.

    Args:
        session: Database session
    """
    logger.debug("Bootstrapping built-in indexers...")

    for builtin_data in BUILTIN_INDEXERS:
        existing = await session.get(Indexer, builtin_data["id"])
        if existing is None:
            indexer = Indexer(**builtin_data)
            session.add(indexer)
            logger.info(
                "Seeded built-in indexer",
                indexer_id=builtin_data["id"],
                name=builtin_data["name"],
            )
        else:
            logger.debug(
                "Built-in indexer already exists",
                indexer_id=builtin_data["id"],
            )

    await session.commit()
    logger.info("Built-in indexers bootstrap complete")


async def bootstrap_libraries(session: SQLModelAsyncSession) -> None:
    """Bootstrap libraries (no-op - users create libraries via UI).

    Args:
        session: Database session
    """
    logger.debug("Bootstrapping libraries...")

    # No automatic library creation - users should create libraries via the UI
    from sqlmodel import select

    result = await session.exec(select(Library))
    existing_count = len(result.all())

    if existing_count == 0:
        logger.info("No libraries found - users can create libraries via the UI")
    else:
        logger.debug(f"Found {existing_count} existing library/libraries")

    logger.info("Libraries bootstrap complete")
