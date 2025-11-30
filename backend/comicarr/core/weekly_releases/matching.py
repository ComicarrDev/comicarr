"""ComicVine matching for weekly releases.

Matches weekly release items to ComicVine to enable deduplication.
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.import_scan import _issue_has_file, _search_comicvine_for_file
from comicarr.core.utils import (
    _extract_year,
    _normalized_strings_match,
    _simplify_label,
    normalize_issue_number,
)
from comicarr.db.models import WeeklyReleaseItem

logger = structlog.get_logger("comicarr.weekly_releases.matching")


async def match_weekly_release_to_comicvine(
    item: WeeklyReleaseItem,
    session: SQLModelAsyncSession,
) -> dict[str, Any]:
    """Match a weekly release item to ComicVine.

    Uses the same logic as _search_comicvine_for_file but adapted for weekly releases.

    Args:
        item: WeeklyReleaseItem to match
        session: Database session

    Returns:
        Dictionary with ComicVine match data or None if no match
    """
    # Extract series and issue_number from metadata
    metadata = json.loads(item.metadata_json or "{}")
    series = metadata.get("series") or item.title
    issue_number = metadata.get("issue_number")

    # Extract year from release_date if available
    year = None
    if item.release_date:
        try:
            from datetime import datetime

            release_date = datetime.fromisoformat(item.release_date.replace("Z", "+00:00"))
            year = release_date.year
        except (ValueError, AttributeError):
            pass

    # If no year from release_date, try to extract from title
    if not year:
        year = _extract_year(item.title)

    logger.debug(
        "Matching weekly release to ComicVine",
        item_id=item.id,
        title=item.title,
        series=series,
        issue_number=issue_number,
        year=year,
    )

    # Use existing ComicVine search logic
    # Convert year to int if it's a string
    year_int: int | None = None
    if year is not None:
        if isinstance(year, int):
            year_int = year
        elif isinstance(year, str) and year.isdigit():
            year_int = int(year)

    comicvine_data = await _search_comicvine_for_file(
        series_name=series,
        issue_number=issue_number,
        year=year_int,
        session=session,
    )

    if not comicvine_data:
        logger.debug("No ComicVine match found", item_id=item.id, title=item.title)
        return {}

    # Update item with ComicVine data
    item.comicvine_volume_id = comicvine_data.get("volume_id")
    item.comicvine_issue_id = comicvine_data.get("issue_id")
    item.comicvine_volume_name = comicvine_data.get("volume_name")
    item.comicvine_issue_name = comicvine_data.get("issue_name")
    item.comicvine_confidence = comicvine_data.get("confidence", 0.0)
    item.cv_search_query = comicvine_data.get("search_query")
    item.cv_results_count = comicvine_data.get("results_count", 0)
    item.cv_results_sample = comicvine_data.get("results_sample")

    # Extract issue number from ComicVine if available
    if item.comicvine_issue_id:
        # Try to get issue number from ComicVine API response
        # For now, we'll use the issue_number from metadata
        # In the future, we could fetch full issue details
        item.comicvine_issue_number = issue_number

    # Extract cover date if available (would need to fetch full issue details)
    # For now, we'll leave it as None

    logger.info(
        "Matched weekly release to ComicVine",
        item_id=item.id,
        title=item.title,
        volume_id=item.comicvine_volume_id,
        issue_id=item.comicvine_issue_id,
        confidence=item.comicvine_confidence,
    )

    return comicvine_data


async def match_week_to_comicvine(
    week_id: str,
    session: SQLModelAsyncSession,
    limit: int | None = None,
) -> dict[str, Any]:
    """Match all items in a week to ComicVine.

    Args:
        week_id: Week ID to match
        session: Database session
        limit: Optional limit on number of items to match (for testing)

    Returns:
        Dictionary with matching statistics
    """
    from sqlmodel import col, select

    # Get all items for this week
    items_result = await session.exec(
        select(WeeklyReleaseItem)
        .where(WeeklyReleaseItem.week_id == week_id)
        .where(col(WeeklyReleaseItem.comicvine_issue_id).is_(None))  # Only match unmatched items
    )
    items = items_result.all()

    if limit:
        items = items[:limit]

    logger.info("Matching week to ComicVine", week_id=week_id, items_count=len(items))

    matched_count = 0
    failed_count = 0

    for item in items:
        try:
            comicvine_data = await match_weekly_release_to_comicvine(item, session)
            if comicvine_data and comicvine_data.get("volume_id"):
                matched_count += 1
            else:
                failed_count += 1
        except Exception as exc:
            logger.exception("Failed to match item", item_id=item.id, error=str(exc))
            failed_count += 1

    await session.commit()

    logger.info(
        "Completed matching week to ComicVine",
        week_id=week_id,
        matched=matched_count,
        failed=failed_count,
        total=len(items),
    )

    # Automatically deduplicate after matching
    if matched_count > 0:
        logger.info("Auto-deduplicating after matching", week_id=week_id)
        dedup_result = await deduplicate_week_by_comicvine(week_id, session)
        return {
            "matched": matched_count,
            "failed": failed_count,
            "total": len(items),
            "deduplicated": dedup_result["deduplicated"],
            "kept": dedup_result["kept"],
            "removed": dedup_result["removed"],
        }

    return {
        "matched": matched_count,
        "failed": failed_count,
        "total": len(items),
    }


async def deduplicate_week_by_comicvine(
    week_id: str,
    session: SQLModelAsyncSession,
) -> dict[str, Any]:
    """Deduplicate items in a week by ComicVine IDs.

    Groups items by ComicVine issue_id (or volume_id + issue_number) and merges
    sources into a single item with sources_json.

    Args:
        week_id: Week ID to deduplicate
        session: Database session

    Returns:
        Dictionary with deduplication statistics
    """
    from sqlmodel import col, select

    # Get all items for this week that have ComicVine matches (volume_id or issue_id)
    items_result = await session.exec(
        select(WeeklyReleaseItem)
        .where(WeeklyReleaseItem.week_id == week_id)
        .where(col(WeeklyReleaseItem.comicvine_volume_id).isnot(None))
    )
    items = items_result.all()

    if not items:
        logger.info("No items with ComicVine matches to deduplicate", week_id=week_id)
        return {
            "deduplicated": 0,
            "kept": 0,
            "removed": 0,
        }

    logger.info("Deduplicating week by ComicVine", week_id=week_id, items_count=len(items))

    # Group items by ComicVine issue_id
    # Key: (comicvine_issue_id, comicvine_volume_id) or (volume_id, issue_number)
    groups: dict[tuple[int | None, int | None, str | None], list[WeeklyReleaseItem]] = {}

    for item in items:
        # Use issue_id as primary key, fallback to volume_id + issue_number from metadata
        if item.comicvine_issue_id:
            key = (item.comicvine_issue_id, item.comicvine_volume_id, None)
        elif item.comicvine_volume_id:
            # Fallback: use volume_id + issue_number from metadata
            metadata = json.loads(item.metadata_json or "{}")
            issue_number = metadata.get("issue_number") or item.comicvine_issue_number
            if issue_number:
                key = (None, item.comicvine_volume_id, issue_number)
            else:
                # Skip items without issue number
                continue
        else:
            # Skip items without enough ComicVine data
            continue

        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    kept_count = 0
    removed_count = 0

    # Process each group
    for key, group_items in groups.items():
        if len(group_items) <= 1:
            # No duplicates, keep the item
            kept_count += 1
            continue

        # Sort by confidence (highest first), then by created_at (oldest first)
        group_items.sort(
            key=lambda x: (
                -(x.comicvine_confidence or 0.0),
                x.created_at or 0,
            )
        )

        # Keep the first item (highest confidence, oldest)
        primary_item = group_items[0]

        # Collect all sources
        sources = set()
        sources.add(primary_item.source)

        # Parse existing sources_json if present
        if primary_item.sources_json:
            try:
                existing_sources = json.loads(primary_item.sources_json)
                if isinstance(existing_sources, list):
                    sources.update(existing_sources)
            except (json.JSONDecodeError, TypeError):
                pass

        # Add sources from duplicate items
        for duplicate_item in group_items[1:]:
            sources.add(duplicate_item.source)

            # Merge metadata if needed
            try:
                duplicate_metadata = json.loads(duplicate_item.metadata_json or "{}")
                primary_metadata = json.loads(primary_item.metadata_json or "{}")

                # Merge URLs (keep all)
                if duplicate_item.url and duplicate_item.url not in (primary_item.url or ""):
                    # Store additional URLs in metadata
                    if "urls" not in primary_metadata:
                        primary_metadata["urls"] = []
                    if primary_item.url:
                        primary_metadata["urls"].append(
                            {"source": primary_item.source, "url": primary_item.url}
                        )
                    primary_metadata["urls"].append(
                        {"source": duplicate_item.source, "url": duplicate_item.url}
                    )

                # Update primary item metadata
                primary_item.metadata_json = json.dumps(primary_metadata)
            except (json.JSONDecodeError, TypeError):
                pass

            # Delete duplicate item
            await session.delete(duplicate_item)
            removed_count += 1

        # Update primary item with merged sources
        primary_item.sources_json = json.dumps(sorted(list(sources)))
        primary_item.source = "combined"  # Mark as combined source
        primary_item.updated_at = int(time.time())

        kept_count += 1

    await session.commit()

    logger.info(
        "Completed deduplication",
        week_id=week_id,
        kept=kept_count,
        removed=removed_count,
        groups_processed=len(groups),
    )

    return {
        "deduplicated": len([g for g in groups.values() if len(g) > 1]),
        "kept": kept_count,
        "removed": removed_count,
    }


async def match_weekly_release_to_library(
    item: WeeklyReleaseItem,
    session: SQLModelAsyncSession,
) -> dict[str, Any]:
    """Match a weekly release item to existing library issues.

    Args:
        item: WeeklyReleaseItem to match
        session: Database session

    Returns:
        Dictionary with library match data
    """
    from sqlmodel import col, select

    from comicarr.db.models import LibraryIssue, LibraryVolume

    # First try to match by ComicVine IDs (most reliable)
    if item.comicvine_issue_id:
        issue_result = await session.exec(
            select(LibraryIssue).where(LibraryIssue.comicvine_id == item.comicvine_issue_id)
        )
        library_issue = issue_result.first()
        if library_issue:
            volume = await session.get(LibraryVolume, library_issue.volume_id)
            if not volume:
                logger.warning(
                    "Library issue has invalid volume_id",
                    issue_id=library_issue.id,
                    volume_id=library_issue.volume_id,
                )
                # Continue to try other matching methods
            elif volume:
                # Check if issue has a file
                issue_has_file = await _issue_has_file(library_issue.id, session)
                # Match the issue regardless of whether it has a file - if it exists in the library, it's a match
                item.matched_volume_id = volume.id
                item.matched_issue_id = library_issue.id
                if issue_has_file:
                    # Issue has a file - it's in the library, mark as skipped
                    if item.status != "skipped":
                        old_status = item.status
                        item.status = "skipped"
                        logger.debug(
                            "Changed status to 'skipped' (issue has file)",
                            item_id=item.id,
                            old_status=old_status,
                            new_status="skipped",
                        )
                else:
                    # Issue exists but no file - still match it, but mark as import (wanted)
                    if item.status == "pending":
                        old_status = item.status
                        item.status = "import"
                        logger.debug(
                            "Changed status to 'import' (issue exists but no file)",
                            item_id=item.id,
                            old_status=old_status,
                            new_status="import",
                        )

                item.updated_at = int(time.time())
                # Ensure item is tracked by session
                session.add(item)
                logger.info(
                    "Matched weekly release to library by ComicVine ID",
                    item_id=item.id,
                    comicvine_issue_id=item.comicvine_issue_id,
                    library_issue_id=library_issue.id,
                    has_file=issue_has_file,
                    status=item.status,
                )
                return {
                    "matched": True,
                    "volume_id": volume.id,
                    "issue_id": library_issue.id,
                    "method": "comicvine_id",
                    "has_file": issue_has_file,
                }

    # Fall back to series name + issue number matching
    metadata = json.loads(item.metadata_json or "{}")
    series = metadata.get("series") or item.title
    issue_number = metadata.get("issue_number")

    if not series or not issue_number:
        logger.debug(
            "Cannot match: missing series or issue number",
            item_id=item.id,
            title=item.title,
            series=series,
            issue_number=issue_number,
            metadata=metadata,
        )
        return {"matched": False, "reason": "missing_series_or_issue"}

    issue_numeric = normalize_issue_number(issue_number)
    if issue_numeric is None:
        logger.debug(
            "Cannot match: invalid issue number",
            item_id=item.id,
            title=item.title,
            series=series,
            issue_number=issue_number,
        )
        return {"matched": False, "reason": "invalid_issue_number"}

    # Get all library issues with matching issue number
    issues_result = await session.exec(
        select(LibraryIssue).where(col(LibraryIssue.number).isnot(None))
    )
    all_issues = issues_result.all()

    # Build index by normalized issue number
    issue_index: dict[float, list[LibraryIssue]] = {}
    for issue in all_issues:
        issue_num = normalize_issue_number(issue.number)
        if issue_num:
            issue_index.setdefault(issue_num, []).append(issue)

    # Find matching issues by number
    matching_issues = issue_index.get(issue_numeric, [])
    if not matching_issues:
        logger.debug(
            "Cannot match: no issues in library with this issue number",
            item_id=item.id,
            title=item.title,
            series=series,
            issue_number=issue_number,
            issue_numeric=issue_numeric,
        )
        return {"matched": False, "reason": "no_matching_issue_number"}

    # Only use exact matches - no fuzzy matching to prevent false positives
    series_name_lower = _simplify_label(series)

    logger.debug(
        "Attempting to match by series name",
        item_id=item.id,
        series=series,
        series_normalized=series_name_lower,
        issue_number=issue_number,
        matching_issues_count=len(matching_issues),
    )

    for issue in matching_issues:
        volume_result = await session.exec(
            select(LibraryVolume).where(LibraryVolume.id == issue.volume_id)
        )
        volume = volume_result.one_or_none()
        if not volume:
            continue

        volume_title_simplified = _simplify_label(volume.title)

        logger.debug(
            "Comparing series names",
            item_id=item.id,
            series=series,
            volume_title=volume.title,
            series_normalized=series_name_lower,
            volume_normalized=volume_title_simplified,
        )

        # Prevent substring matches FIRST - before any matching logic
        # (e.g., "starwars" should not match "starwarsunion", "batman" should not match "batmangothambygaslightaleagueforjustice")
        shorter = min(series_name_lower, volume_title_simplified, key=len)
        longer = max(series_name_lower, volume_title_simplified, key=len)
        if shorter and longer and shorter != longer:
            if shorter in longer:
                # One is a substring of the other - reject this match immediately
                logger.debug(
                    "Rejecting substring match",
                    item_id=item.id,
                    series=series,
                    volume_title=volume.title,
                    series_normalized=series_name_lower,
                    volume_normalized=volume_title_simplified,
                )
                continue

        # Exact match on normalized strings (strips special chars except word-connected hyphens, lowercases)
        # Also handles common words like "the", "a", "an" as optional
        strings_match = _normalized_strings_match(volume_title_simplified, series_name_lower)
        logger.debug(
            "Series name match result",
            item_id=item.id,
            series=series,
            volume_title=volume.title,
            strings_match=strings_match,
        )

        if strings_match:
            # Check if issue has a file
            issue_has_file = await _issue_has_file(issue.id, session)
            # Match the issue regardless of whether it has a file - if it exists in the library, it's a match
            item.matched_volume_id = volume.id
            item.matched_issue_id = issue.id
            if issue_has_file:
                # Issue has a file - it's in the library, mark as skipped
                if item.status != "skipped":
                    old_status = item.status
                    item.status = "skipped"
                    logger.debug(
                        "Changed status to 'skipped' (issue has file)",
                        item_id=item.id,
                        old_status=old_status,
                        new_status="skipped",
                    )
            else:
                # Issue exists but no file - still match it, but mark as import (wanted)
                if item.status == "pending":
                    old_status = item.status
                    item.status = "import"
                    logger.debug(
                        "Changed status to 'import' (issue exists but no file)",
                        item_id=item.id,
                        old_status=old_status,
                        new_status="import",
                    )

            item.updated_at = int(time.time())
            # Ensure item is tracked by session
            session.add(item)
            logger.info(
                "Matched weekly release to library by series name",
                item_id=item.id,
                series=series,
                volume_title=volume.title,
                library_issue_id=issue.id,
                has_file=issue_has_file,
                status=item.status,
            )
            return {
                "matched": True,
                "volume_id": volume.id,
                "issue_id": issue.id,
                "method": "series_name",
                "has_file": issue_has_file,
            }

        # Skip fuzzy matching - only use exact matches to prevent false positives
        # If the series name doesn't match exactly, don't try fuzzy matching
        # This prevents matching items to series that aren't actually in the library

    # Don't use fuzzy matching - only exact matches are allowed
    # If we get here, no exact match was found, so return no match
    # Log the volumes we checked for debugging
    checked_volumes = []
    for issue in matching_issues[:5]:  # Log first 5 for debugging
        volume_result = await session.exec(
            select(LibraryVolume).where(LibraryVolume.id == issue.volume_id)
        )
        volume = volume_result.one_or_none()
        if volume:
            checked_volumes.append(volume.title)

    logger.debug(
        "No exact series name match found",
        item_id=item.id,
        title=item.title,
        series=series,
        series_normalized=series_name_lower,
        issue_number=issue_number,
        matching_issues_checked=len(matching_issues),
        checked_volumes=checked_volumes[:5],  # Show first 5 volumes checked
    )

    # Return no match - fuzzy matching is disabled to prevent false positives
    return {"matched": False, "reason": "no_exact_series_match"}

    # If no issue match found, check if volume exists (by ComicVine ID or series name)
    # If volume exists, create the issue and mark it as wanted
    matched_volume = None

    # Try to match volume by ComicVine ID first
    if item.comicvine_volume_id:
        volume_result = await session.exec(
            select(LibraryVolume).where(LibraryVolume.comicvine_id == item.comicvine_volume_id)
        )
        matched_volume = volume_result.first()

    # If no ComicVine match, try to match by series name
    if not matched_volume and series:
        volumes_result = await session.exec(select(LibraryVolume))
        all_volumes = volumes_result.all()

        series_name_lower = _simplify_label(series)
        best_volume_match = None
        best_volume_confidence = 0.0

        for vol in all_volumes:
            volume_title_simplified = _simplify_label(vol.title)

            # For volume creation, only allow exact matches on normalized strings
            # This prevents creating issues in wrong volumes (e.g., "Star Wars" vs "Star Wars: Union")
            # Also handles common words like "the", "a", "an" as optional
            if _normalized_strings_match(volume_title_simplified, series_name_lower):
                matched_volume = vol
                break

    # If volume exists but issue doesn't, create the issue
    if matched_volume and not item.matched_issue_id:
        # Check if issue already exists in this volume (maybe it wasn't matched earlier)
        existing_issue_result = await session.exec(
            select(LibraryIssue).where(
                LibraryIssue.volume_id == matched_volume.id,
                LibraryIssue.number == issue_number,
            )
        )
        existing_issue = existing_issue_result.first()

        if existing_issue:
            # Check if issue has a file
            issue_has_file = await _issue_has_file(existing_issue.id, session)
            # Match the issue regardless of whether it has a file - if it exists in the library, it's a match
            item.matched_volume_id = matched_volume.id
            item.matched_issue_id = existing_issue.id
            if issue_has_file:
                # Issue already has a file - mark as skipped
                if item.status != "skipped":
                    old_status = item.status
                    item.status = "skipped"
                    logger.debug(
                        "Changed status to 'skipped' (issue has file)",
                        item_id=item.id,
                        old_status=old_status,
                        new_status="skipped",
                    )
            else:
                # Issue exists but no file - still match it, but mark as import (wanted)
                if item.status == "pending":
                    old_status = item.status
                    item.status = "import"
                    logger.debug(
                        "Changed status to 'import' (issue exists but no file)",
                        item_id=item.id,
                        old_status=old_status,
                        new_status="import",
                    )
            item.updated_at = int(time.time())
            session.add(item)

            logger.info(
                "Issue exists in library - matched",
                item_id=item.id,
                volume_id=matched_volume.id,
                issue_id=existing_issue.id,
                issue_number=issue_number,
                has_file=issue_has_file,
                status=item.status,
            )

            return {
                "matched": True,
                "volume_id": matched_volume.id,
                "issue_id": existing_issue.id,
                "method": "marked_wanted",
                "created": False,
                "has_file": issue_has_file,
            }
        else:
            # Create new issue for existing volume
            import uuid

            new_issue = LibraryIssue(
                id=uuid.uuid4().hex,
                volume_id=matched_volume.id,
                comicvine_id=item.comicvine_issue_id,
                number=issue_number,
                title=item.comicvine_issue_name or item.title,
                release_date=item.release_date,
                monitored=True,
                status="wanted",
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
            session.add(new_issue)
            await session.flush()
            await session.refresh(new_issue)

            item.matched_volume_id = matched_volume.id
            item.matched_issue_id = new_issue.id
            # Auto-mark as "import" when matched to library (unless already skipped)
            if item.status != "skipped":
                old_status = item.status
                item.status = "import"
                logger.debug(
                    "Changed status to 'import'",
                    item_id=item.id,
                    old_status=old_status,
                    new_status="import",
                )
            item.updated_at = int(time.time())
            # Ensure item is tracked by session
            session.add(item)

            # When creating a new issue for an existing volume, mark all weekly release items
            # for this volume as "import" (to be processed later)
            # This makes it consistent with import behavior
            from comicarr.db.models import WeeklyReleaseItem

            # Find all weekly release items in this week that match the same volume
            all_week_items_result = await session.exec(
                select(WeeklyReleaseItem).where(
                    WeeklyReleaseItem.week_id == item.week_id,
                    WeeklyReleaseItem.matched_volume_id == matched_volume.id,
                )
            )
            all_week_items = all_week_items_result.all()

            items_updated = 0
            for week_item in all_week_items:
                # Mark as "import" if currently "pending" (so they'll be processed)
                if week_item.status == "pending":
                    week_item.status = "import"
                    week_item.updated_at = int(time.time())
                    items_updated += 1

            # Also update all library issues in this volume to "wanted" if they're "missing"
            all_volume_issues_result = await session.exec(
                select(LibraryIssue).where(LibraryIssue.volume_id == matched_volume.id)
            )
            all_volume_issues = all_volume_issues_result.all()

            library_issues_updated = 0
            for vol_issue in all_volume_issues:
                # Update status to "wanted" if it's "missing" (similar to import behavior)
                if vol_issue.status == "missing":
                    vol_issue.status = "wanted"
                    vol_issue.monitored = True
                    vol_issue.updated_at = int(time.time())
                    library_issues_updated += 1

            logger.info(
                "Created new issue for existing volume and updated weekly release items",
                item_id=item.id,
                volume_id=matched_volume.id,
                issue_id=new_issue.id,
                issue_number=issue_number,
                weekly_items_updated=items_updated,
                library_issues_updated=library_issues_updated,
            )

            return {
                "matched": True,
                "volume_id": matched_volume.id,
                "issue_id": new_issue.id,
                "method": "created_for_volume",
                "created": True,
            }

    return {"matched": False, "reason": "no_good_match"}


async def match_week_to_library(
    week_id: str,
    session: SQLModelAsyncSession,
) -> dict[str, Any]:
    """Match all items in a week to library.

    Args:
        week_id: Week ID to match
        session: Database session

    Returns:
        Dictionary with matching statistics
    """
    from sqlmodel import select

    # Get all items for this week
    items_result = await session.exec(
        select(WeeklyReleaseItem).where(WeeklyReleaseItem.week_id == week_id)
    )
    items = items_result.all()

    logger.info("Matching week to library", week_id=week_id, items_count=len(items))

    matched_count = 0
    not_matched_count = 0

    for item in items:
        try:
            result = await match_weekly_release_to_library(item, session)
            if result.get("matched"):
                matched_count += 1
                # Ensure item changes are tracked
                session.add(item)
            else:
                not_matched_count += 1
        except Exception as exc:
            logger.exception("Failed to match item to library", item_id=item.id, error=str(exc))
            not_matched_count += 1

    # Flush before commit to ensure all changes are tracked
    await session.flush()
    await session.commit()

    logger.info(
        "Completed matching week to library",
        week_id=week_id,
        matched=matched_count,
        not_matched=not_matched_count,
        total=len(items),
    )

    return {
        "matched": matched_count,
        "not_matched": not_matched_count,
        "total": len(items),
    }
