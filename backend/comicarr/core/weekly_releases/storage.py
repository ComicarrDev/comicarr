"""Storage utilities for weekly releases.

Minimal functions for storing parsed releases in the database.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.utils import _simplify_label, normalize_issue_number
from comicarr.db.models import WeeklyReleaseItem, WeeklyReleaseWeek

logger = structlog.get_logger("comicarr.weekly_releases.storage")


def parse_issue_from_title(title: str) -> tuple[str, str | None, str | None]:
    """Parse series, issue number, and issue token from title.

    Returns:
        (series, issue_number_text, issue_token)
    """
    # Look for pattern like "Series #123" or "Series #123.5"
    import re

    match = re.search(r"^(.+?)\s+#\s*(\d+(?:\.\d+)?)", title, re.IGNORECASE)
    if match:
        series = match.group(1).strip(" -:")
        issue_text = match.group(2)
        issue_num = normalize_issue_number(issue_text)
        issue_token = f"{issue_num:.3f}".rstrip("0").rstrip(".") if issue_num else None
        return series, issue_text, issue_token

    # Fallback: try to find # anywhere
    if "#" in title:
        parts = title.split("#", 1)
        series = parts[0].strip(" -:")
        issue_match = re.search(r"(\d+(?:\.\d+)?)", parts[1])
        if issue_match:
            issue_text = issue_match.group(1)
            issue_num = normalize_issue_number(issue_text)
            issue_token = f"{issue_num:.3f}".rstrip("0").rstrip(".") if issue_num else None
            return series, issue_text, issue_token

    # No issue number found
    series = title.strip()
    return series, None, None


def build_issue_key(series: str, issue_number: str | None, source: str) -> str:
    """Build a unique issue key for matching."""
    series_key = _simplify_label(series) if series else ""
    if issue_number:
        issue_num = normalize_issue_number(issue_number)
        if issue_num:
            issue_token = f"{issue_num:.3f}".rstrip("0").rstrip(".")
            if series_key:
                return f"{series_key}#{issue_token}"
            return f"{source}:{issue_token}"

    if series_key:
        return f"{source}:{series_key}"

    return f"{source}:{uuid.uuid4().hex}"


async def get_or_create_week(
    session: SQLModelAsyncSession,
    week_start: str,
) -> WeeklyReleaseWeek:
    """Get or create a weekly release week."""
    week_result = await session.exec(
        select(WeeklyReleaseWeek).where(WeeklyReleaseWeek.week_start == week_start)
    )
    week = week_result.first()

    if week is None:
        week = WeeklyReleaseWeek(
            week_start=week_start,
            status="completed",
            fetched_at=int(time.time()),
        )
        session.add(week)
        await session.flush()
    else:
        week.fetched_at = int(time.time())

    return week


async def store_releases(
    session: SQLModelAsyncSession,
    week: WeeklyReleaseWeek,
    week_start: str,
    releases: list[dict[str, Any]],
    source: str,
) -> int:
    """Store parsed releases in the database.

    Deduplicates at fetch time using series name, issue number, and publisher.

    Args:
        session: Database session
        week: WeeklyReleaseWeek instance
        week_start: Week start date ISO string
        releases: List of parsed release dictionaries
        source: Source name (e.g., 'previewsworld', 'comicgeeks')

    Returns:
        Number of releases stored
    """
    week_id = week.id
    stored_count = 0
    merged_count = 0

    for release in releases:
        title = release.get("title", "")
        series, issue_number, issue_token = parse_issue_from_title(title)
        publisher = release.get("publisher")

        # Build a deduplication key: series + issue_number + publisher
        # Normalize series name for matching
        series_key = _simplify_label(series) if series else ""

        # Normalize issue number
        issue_num = normalize_issue_number(issue_number) if issue_number else None
        issue_token_for_match = f"{issue_num:.3f}".rstrip("0").rstrip(".") if issue_num else None

        # Normalize publisher for matching
        publisher_key = _simplify_label(publisher) if publisher else None

        # Search for existing item by series + issue_number + publisher
        # First try with publisher
        existing_query = select(WeeklyReleaseItem).where(
            WeeklyReleaseItem.week_id == week_id,
        )

        # Build conditions for matching
        conditions = []

        # Match by series (normalized)
        if series_key:
            # We need to check series from metadata or title
            # For now, match by title similarity or check metadata
            # This is a simplified approach - we'll match by checking if the normalized
            # series appears in existing items' metadata
            pass  # We'll handle this differently

        # Instead, let's match by checking all items and comparing
        all_items_result = await session.exec(
            select(WeeklyReleaseItem).where(WeeklyReleaseItem.week_id == week_id)
        )
        all_items = all_items_result.all()

        # Find matching item
        matching_item = None
        for existing_item in all_items:
            existing_metadata = json.loads(existing_item.metadata_json or "{}")
            existing_series = existing_metadata.get("series") or existing_item.title
            existing_series_key = _simplify_label(existing_series)
            existing_issue_number = existing_metadata.get("issue_number")
            existing_issue_num = (
                normalize_issue_number(existing_issue_number) if existing_issue_number else None
            )
            existing_issue_token = (
                f"{existing_issue_num:.3f}".rstrip("0").rstrip(".") if existing_issue_num else None
            )
            existing_publisher = existing_item.publisher
            existing_publisher_key = (
                _simplify_label(existing_publisher) if existing_publisher else None
            )

            # Match if series and issue number match
            series_match = series_key and existing_series_key and series_key == existing_series_key
            issue_match = (
                issue_token_for_match
                and existing_issue_token
                and issue_token_for_match == existing_issue_token
            ) or (not issue_token_for_match and not existing_issue_token)

            # Publisher match (optional - if both have publishers, they should match)
            publisher_match = True
            if publisher_key and existing_publisher_key:
                publisher_match = publisher_key == existing_publisher_key
            elif publisher_key or existing_publisher_key:
                # If only one has publisher, still allow match (publisher might be missing from one source)
                publisher_match = True

            if series_match and issue_match and publisher_match:
                matching_item = existing_item
                break

        if matching_item is None:
            # Create new item
            issue_key = build_issue_key(series, issue_number, source)
            metadata = {
                "source": source,
                "raw": release,
                "series": series,
                "issue_number": issue_number,
                "issue_token": issue_token,
            }

            item = WeeklyReleaseItem(
                week_id=week_id,
                week_start=week_start,
                source=source,
                issue_key=issue_key,
                title=title or series,
                publisher=publisher,
                release_date=release.get("release_date"),
                url=release.get("url"),
                status="pending",
                metadata_json=json.dumps(metadata),
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
            session.add(item)
            stored_count += 1
        else:
            # Merge with existing item
            # Collect sources
            sources = set()
            sources.add(matching_item.source)

            # Parse existing sources_json if present
            if matching_item.sources_json:
                try:
                    existing_sources = json.loads(matching_item.sources_json)
                    if isinstance(existing_sources, list):
                        sources.update(existing_sources)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Add new source
            sources.add(source)

            # Update sources_json
            matching_item.sources_json = json.dumps(sorted(list(sources)))
            matching_item.source = "combined"

            # Merge metadata
            existing_metadata = json.loads(matching_item.metadata_json or "{}")
            new_metadata = {
                "source": source,
                "raw": release,
                "series": series,
                "issue_number": issue_number,
                "issue_token": issue_token,
            }

            # Merge URLs
            if release.get("url") and release.get("url") != matching_item.url:
                if "urls" not in existing_metadata:
                    existing_metadata["urls"] = []
                if matching_item.url:
                    existing_metadata["urls"].append(
                        {"source": matching_item.source, "url": matching_item.url}
                    )
                existing_metadata["urls"].append({"source": source, "url": release.get("url")})

            # Update metadata
            existing_metadata["sources"] = existing_metadata.get("sources", [])
            if source not in existing_metadata["sources"]:
                existing_metadata["sources"].append(source)
            existing_metadata[source] = new_metadata

            matching_item.metadata_json = json.dumps(existing_metadata)

            # Update other fields if missing
            if not matching_item.publisher and publisher:
                matching_item.publisher = publisher
            if not matching_item.release_date and release.get("release_date"):
                matching_item.release_date = release.get("release_date")

            matching_item.updated_at = int(time.time())
            merged_count += 1

    await session.commit()
    logger.info(
        "Stored releases",
        source=source,
        stored=stored_count,
        merged=merged_count,
        week_start=week_start,
    )
    return stored_count
