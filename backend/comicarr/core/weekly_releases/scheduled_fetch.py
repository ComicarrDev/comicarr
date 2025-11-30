"""Scheduled task for automatically fetching weekly releases."""

from __future__ import annotations

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.settings_persistence import get_effective_settings
from comicarr.core.weekly_releases import (
    fetch_comicgeeks_releases,
    fetch_previewsworld_releases,
    fetch_readcomicsonline_releases,
    get_or_create_week,
    store_releases,
)
from comicarr.core.weekly_releases.comicgeeks import current_week_wednesday

logger = structlog.get_logger("comicarr.weekly_releases.scheduled_fetch")


async def fetch_current_week_releases(session: SQLModelAsyncSession) -> None:
    """Fetch releases from enabled sources for the current week (last Wednesday).

    This function is designed to be called by a scheduler.
    It fetches from enabled sources and stores the results.

    Args:
        session: Database session
    """
    try:
        # Get settings to check if fetching is enabled and which sources are enabled
        settings = get_effective_settings()
        weekly_releases = settings.get("weekly_releases", {})

        # Check if automatic fetching is enabled
        if not weekly_releases.get("auto_fetch_enabled", False):
            logger.debug("Automatic weekly release fetching is disabled")
            return

        # Calculate current week's Wednesday
        week_start_date = current_week_wednesday()
        week_start_iso = week_start_date.isoformat()

        logger.info("Starting scheduled fetch for current week", week_start=week_start_iso)

        # Get or create week
        week = await get_or_create_week(session, week_start_iso)

        # Define all sources with their fetch functions
        all_sources = {
            "previewsworld": fetch_previewsworld_releases,
            "comicgeeks": fetch_comicgeeks_releases,
            "readcomicsonline": fetch_readcomicsonline_releases,
        }

        # Get enabled sources from settings (default to all enabled if not specified)
        source_enabled = weekly_releases.get("sources", {})
        enabled_sources = {
            name: func
            for name, func in all_sources.items()
            if source_enabled.get(name, {}).get("enabled", True)  # Default to enabled
        }

        if not enabled_sources:
            logger.info("No sources enabled for automatic fetching")
            return

        total_stored = 0
        for source_name, fetch_func in enabled_sources.items():
            try:
                logger.info("Fetching from source", source=source_name, week_start=week_start_iso)
                releases = await fetch_func(week_start_date)

                if releases:
                    stored_count = await store_releases(
                        session,
                        week,
                        week_start_iso,
                        releases,
                        source_name,
                    )
                    total_stored += stored_count
                    logger.info(
                        "Fetched and stored releases",
                        source=source_name,
                        count=stored_count,
                        week_start=week_start_iso,
                    )
                else:
                    logger.info("No releases found", source=source_name, week_start=week_start_iso)

            except Exception as e:
                logger.error(
                    "Failed to fetch from source",
                    source=source_name,
                    week_start=week_start_iso,
                    error=str(e),
                    exc_info=True,
                )
                # Continue with other sources even if one fails

        logger.info(
            "Scheduled fetch completed",
            week_start=week_start_iso,
            total_stored=total_stored,
        )

    except Exception as e:
        logger.error(
            "Scheduled fetch failed",
            error=str(e),
            exc_info=True,
        )
