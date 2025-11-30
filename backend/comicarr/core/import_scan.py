"""Import scanning service for finding and matching comic files."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.matching import (
    build_volume_picker_result,
    evaluate_issue_candidate,
    evaluate_volume_candidate,
    get_matching_config,
    normalize_confidence,
)
from comicarr.core.utils import (
    SCANNABLE_EXTENSIONS,
    _extract_numeric_id,
    _simplify_label,
    normalize_issue_number,
)
from comicarr.db.models import (
    ImportJob,
    ImportPendingFile,
    Library,
    LibraryIssue,
    LibraryVolume,
)

logger = structlog.get_logger("comicarr.core.import_scan")


async def _issue_has_file(issue_id: str, session: SQLModelAsyncSession) -> bool:
    """Check if a library issue already has a file.

    Args:
        issue_id: The library issue ID to check
        session: Database session

    Returns:
        True if the issue exists and has a non-empty file_path, False otherwise
    """
    issue = await session.get(LibraryIssue, issue_id)
    if not issue:
        logger.debug("Issue not found in library", issue_id=issue_id)
        return False

    # Check if file_path exists and is not empty/whitespace
    has_file = bool(issue.file_path and issue.file_path.strip())
    if has_file:
        logger.debug(
            "Issue already has a file",
            issue_id=issue_id,
            existing_file_path=issue.file_path,
        )
    else:
        logger.debug("Issue exists but has no file", issue_id=issue_id)

    return has_file


def _collect_comic_files(folder: Path) -> list[Path]:
    """Collect all comic files from a folder recursively.

    Args:
        folder: Folder path to scan

    Returns:
        List of comic file paths
    """
    files: list[Path] = []
    try:
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in SCANNABLE_EXTENSIONS:
                files.append(path)
    except (OSError, PermissionError) as e:
        logger.warning("Error scanning folder", folder=str(folder), error=str(e))
    return files


def _extract_series_from_filename(
    filename: str,
) -> tuple[str | None, str | None, int | None, str | None, str | None]:
    """Extract series name, issue number, year, month, and volume from filename.

    Returns:
        Tuple of (series_name, issue_number, year, month, volume)
    """
    stem = Path(filename).stem

    # Extract issue number patterns
    issue_number = None
    issue_patterns = [
        r"#(\d+(?:\.\d+)?)",  # #001, #1.5
        r"(\d{1,4}(?:\.\d{1,2})?)(?:\s|$)",  # 001, 1.5 at end
        r"Issue\s+(\d+(?:\.\d+)?)",  # Issue 001
    ]
    for pattern in issue_patterns:
        match = re.search(pattern, stem, re.IGNORECASE)
        if match:
            issue_number = match.group(1)
            break

    # Extract volume identifier (v2022, Vol. 2022, Volume 2022, etc.)
    volume = None
    volume_patterns = [
        r"\bv(\d{4})\b",  # v2022
        r"\bvol\.?\s*(\d{4})\b",  # Vol. 2022, Vol 2022
        r"\bvolume\s*(\d{4})\b",  # Volume 2022
        r"\bvol\.?\s*(\d+)\b",  # Vol. 1, Vol 2
        r"\bvolume\s*(\d+)\b",  # Volume 1, Volume 2
    ]
    for pattern in volume_patterns:
        match = re.search(pattern, stem, re.IGNORECASE)
        if match:
            volume = match.group(1)
            break

    # Extract year (from date, not volume)
    year = None
    year_match = re.search(r"(19|20)\d{2}", stem)
    if year_match:
        try:
            year = int(year_match.group(0))
        except ValueError:
            pass

    # Extract month (simplified)
    month = None
    month_match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
        stem,
        re.IGNORECASE,
    )
    if month_match:
        month = month_match.group(1)

    # Extract series name - remove issue number, year, volume, and common patterns
    series_name = stem
    # Remove issue number
    if issue_number:
        series_name = re.sub(
            rf"#?\s*{re.escape(issue_number)}\s*", "", series_name, flags=re.IGNORECASE
        )
    # Remove volume identifier - handle "v2022" without requiring word boundary after "v"
    if volume:
        # Match "v" followed by optional space and volume number (word boundary after number)
        series_name = re.sub(rf"\bv\s*{re.escape(volume)}\b", "", series_name, flags=re.IGNORECASE)
        # Also handle "vol." and "volume" patterns
        series_name = re.sub(
            rf"\bvol\.?\s*{re.escape(volume)}\b", "", series_name, flags=re.IGNORECASE
        )
        series_name = re.sub(
            rf"\bvolume\s*{re.escape(volume)}\b", "", series_name, flags=re.IGNORECASE
        )
    # Remove year (but be careful not to remove year that's part of volume)
    if year:
        # Only remove year if it's not the volume identifier
        if not volume or str(year) != volume:
            series_name = re.sub(rf"\b{year}\b", "", series_name)
    # Remove parentheticals
    series_name = re.sub(r"\s*\([^)]*\)", "", series_name)
    # Remove common separators and clean up
    series_name = re.sub(r"\s*[-_]\s*", " ", series_name)
    series_name = re.sub(r"\s+", " ", series_name).strip()

    if not series_name or len(series_name) < 2:
        series_name = None

    return series_name, issue_number, year, month, volume


# _evaluate_issue_candidate is now provided by comicarr.core.matching
# Keeping this as a wrapper for backward compatibility during refactoring
def _evaluate_issue_candidate(
    issue_item: dict[str, Any],
    volume_info: dict[str, Any],
    series_name: str,
    normalized_issue_number: float | None,
    year: int | None,
) -> tuple[float, list[str]]:
    """Evaluate an issue candidate using weighted scoring (like experiment branch).

    This is a wrapper around the modular matching system.

    Args:
        issue_item: Issue data from ComicVine
        volume_info: Full volume data (with publisher, start_year, etc.)
        series_name: Series name we're searching for
        normalized_issue_number: Normalized issue number (float) or None
        year: Year we're searching for or None

    Returns:
        Tuple of (raw_score, match_details_list)
        Returns (-1.0, details) if candidate should be rejected
    """
    search_params = {
        "series_name": series_name,
        "issue_number": normalized_issue_number,
        "year": year,
        "publisher": None,  # Not used in current implementation
    }

    result = evaluate_issue_candidate(issue_item, volume_info, search_params, get_matching_config())

    if result.rejected:
        return -1.0, result.details

    return result.score, result.details


async def _search_comicvine_for_file(
    series_name: str | None,
    issue_number: str | None,
    year: int | None,
    session: SQLModelAsyncSession,
) -> dict[str, Any] | None:
    """Search ComicVine for a file that doesn't match library.

    This function searches ISSUES first (if issue_number provided), then falls back to volumes.
    This matches the experiment branch's approach for better accuracy.

    Args:
        series_name: Series name extracted from filename
        issue_number: Issue number extracted from filename
        year: Year extracted from filename
        session: Database session

    Returns:
        ComicVine match data if found, None otherwise
    """
    if not series_name:
        return None

    # Import here to avoid circular dependencies
    from comicarr.core.config import get_settings
    from comicarr.core.search.cache import CacheManager
    from comicarr.routes.comicvine import fetch_comicvine, normalize_comicvine_payload
    from comicarr.routes.settings import _get_external_apis

    # Get ComicVine settings
    external_apis = _get_external_apis()
    normalized = normalize_comicvine_payload(external_apis["comicvine"])

    if not normalized.get("enabled") or not normalized.get("api_key"):
        return None

    # Initialize cache manager if caching is enabled
    config = get_matching_config()
    cache_enabled = config.comicvine_cache_enabled
    cache_manager = None
    if cache_enabled:
        settings = get_settings()
        if hasattr(settings, "cache_dir") and settings.cache_dir:
            cache_manager = CacheManager(settings.cache_dir)

    normalized_issue_number = normalize_issue_number(issue_number) if issue_number else None

    # Build search query
    search_query = series_name
    if year:
        search_query = f"{series_name} {year}"
    if issue_number:
        search_query = f"{search_query} {issue_number}"

    api_query = search_query

    logger.debug(
        "Searching ComicVine",
        series_name=series_name,
        issue_number=issue_number,
        year=year,
        search_query=search_query,
        api_query=api_query,
    )

    best_candidate = None
    best_score = -1.0
    volume_results_for_picker: list[dict[str, Any]] = []
    volume_detail_cache: dict[int, dict[str, Any]] = {}
    volume_issue_images: dict[int, str] = {}  # Track best issue image per volume

    # STEP 1: Search issues first (if we have an issue number) - like experiment branch
    if normalized_issue_number is not None:
        try:
            logger.debug(
                "Searching ComicVine issues first",
                query=search_query,
                series_name=series_name,
                issue_number=issue_number,
                normalized_issue_number=normalized_issue_number,
            )

            config = get_matching_config()

            # Check cache first
            cached_search = None
            if cache_enabled and cache_manager:
                cached_search = await cache_manager.get_comicvine_search(
                    "issue",
                    search_query,
                    config.issue_search_limit,
                )

            if cached_search:
                issue_payload = cached_search
                logger.debug("Using cached ComicVine issue search", query=search_query)
            else:
                issue_payload = await fetch_comicvine(
                    normalized,
                    "search",
                    {
                        "resources": "issue",
                        "query": search_query,
                        "limit": config.issue_search_limit,
                        "field_list": "id,name,issue_number,cover_date,site_detail_url,volume,image",
                    },
                )

                # Cache the search results
                if cache_enabled and cache_manager:
                    await cache_manager.store_comicvine_search(
                        "issue",
                        search_query,
                        config.issue_search_limit,
                        issue_payload,
                    )

            issue_results = issue_payload.get("results", [])
            logger.debug(
                "ComicVine issue search response",
                results_count=len(issue_results),
            )

            for item in issue_results:
                if item.get("resource_type") != "issue":
                    continue

                # Extract volume from issue
                volume_ref = item.get("volume") or {}
                volume_id = _extract_numeric_id(volume_ref.get("id"))

                if not volume_id:
                    continue

                # Fetch full volume details if not in cache
                if volume_id not in volume_detail_cache:
                    # Check persistent cache first (if enabled)
                    cached_volume_data = None
                    if cache_enabled and cache_manager:
                        comicvine_id_str = f"4050-{volume_id}"
                        cached_volume_data = await cache_manager.get_comicvine_metadata(
                            comicvine_id_str
                        )

                    if cached_volume_data:
                        # Use cached volume data
                        # Cache stores normalized format, convert back to raw API format
                        cached_volume = cached_volume_data.get("volume", {})
                        # Convert normalized format back to raw API format
                        publisher_name = cached_volume.get("publisher")
                        publisher_dict = {"name": publisher_name} if publisher_name else None

                        image_url = cached_volume.get("image")
                        image_dict = {"medium_url": image_url} if image_url else None

                        volume_detail_cache[volume_id] = {
                            "id": cached_volume.get("id") or f"4050-{volume_id}",
                            "name": cached_volume.get("name"),
                            "start_year": cached_volume.get("start_year"),
                            "publisher": publisher_dict,
                            "site_detail_url": cached_volume.get("site_url"),
                            "image": image_dict,
                            "count_of_issues": cached_volume.get("count_of_issues"),
                        }
                        logger.debug("Using cached volume details", volume_id=volume_id)
                    else:
                        # Fetch from API
                        try:
                            volume_detail_payload = await fetch_comicvine(
                                normalized,
                                f"volume/4050-{volume_id}",
                                {
                                    "field_list": "id,name,start_year,publisher,site_detail_url,image,count_of_issues",
                                },
                            )
                            volume_result = volume_detail_payload.get("results", {})
                            volume_detail_cache[volume_id] = volume_result

                            # Cache the result (if enabled)
                            if cache_enabled and cache_manager:
                                comicvine_id_str = f"4050-{volume_id}"
                                # Store in cache format (volume + issues)
                                # Convert raw API format to normalized format for cache
                                from comicarr.routes.comicvine import build_comicvine_volume_result

                                volume_data = await build_comicvine_volume_result(
                                    normalized, volume_result
                                )
                                await cache_manager.store_comicvine_metadata(
                                    comicvine_id_str,
                                    {"volume": volume_data, "issues": []},
                                )
                                logger.debug("Cached volume details", volume_id=volume_id)
                        except Exception as exc:
                            logger.debug(
                                "Failed to fetch volume details",
                                volume_id=volume_id,
                                error=str(exc),
                            )
                            volume_detail_cache[volume_id] = volume_ref

                full_volume_info = volume_detail_cache[volume_id]

                # Evaluate this issue candidate using weighted scoring
                candidate_score, match_details = _evaluate_issue_candidate(
                    item, full_volume_info, series_name, normalized_issue_number, year
                )

                # Extract issue image URL for cover comparison
                issue_image_url = None
                image_data = item.get("image")
                if isinstance(image_data, dict):
                    issue_image_url = (
                        image_data.get("super_url")
                        or image_data.get("medium_url")
                        or image_data.get("small_url")
                        or image_data.get("thumb_url")
                    )
                elif image_data:
                    issue_image_url = str(image_data)

                # Track best issue image per volume (use the one with highest score)
                # We'll use this when building the volume picker result
                if issue_image_url:
                    # Store issue image for this volume if we haven't seen it, or if this score is better
                    if volume_id not in volume_issue_images:
                        volume_issue_images[volume_id] = issue_image_url
                    else:
                        # Check if this issue has a better score than the one we stored
                        # (We'll compare scores when we actually build the result)
                        # For now, just store the first one we see - we can improve this later
                        pass

                # Track best candidate (even if rejected, for debugging)
                if candidate_score > best_score:
                    best_score = candidate_score
                    best_candidate = {
                        "issue": item,
                        "volume": full_volume_info,
                        "volume_id": volume_id,
                        "issue_id": _extract_numeric_id(item.get("id")),
                        "score": candidate_score,
                        "match_details": match_details,
                    }

                # Add volume to picker results (deduplicate) - ADD ALL, even rejected ones
                if volume_id not in [v.get("cv_volume_id") for v in volume_results_for_picker]:
                    # Use modular matching system to evaluate and build result
                    search_params = {
                        "series_name": series_name,
                        "year": year,
                        "publisher": None,
                    }
                    volume_result = evaluate_volume_candidate(
                        full_volume_info,
                        search_params,
                        get_matching_config(),
                    )

                    # Get issue image URL for this volume (if available)
                    volume_issue_image = volume_issue_images.get(volume_id)

                    picker_result = build_volume_picker_result(
                        full_volume_info,
                        volume_result.score,
                        volume_result.details,
                        get_matching_config(),
                        rank=len(volume_results_for_picker),
                        issue_image_url=volume_issue_image,
                    )

                    # Mark if this was rejected during issue evaluation
                    if candidate_score < 0:
                        picker_result["rejected"] = True
                        picker_result["rejection_reason"] = (
                            match_details[0] if match_details else "Rejected during evaluation"
                        )

                    volume_results_for_picker.append(picker_result)

            # If we found a good issue match, use it
            config = get_matching_config()
            if best_candidate and best_score >= config.minimum_issue_match_score:
                # Extract issue details
                issue_item = best_candidate["issue"]
                issue_id = best_candidate["issue_id"]
                volume_id = best_candidate["volume_id"]
                volume_info = best_candidate["volume"]

                # Extract issue image
                issue_image_url = None
                if isinstance(issue_item, dict):
                    image_data = issue_item.get("image")
                    if isinstance(image_data, dict):
                        issue_image_url = (
                            image_data.get("super_url")
                            or image_data.get("medium_url")
                            or image_data.get("small_url")
                        )

                # Extract volume image
                volume_image_url = None
                if isinstance(volume_info, dict):
                    vol_image_data = volume_info.get("image")
                    if isinstance(vol_image_data, dict):
                        volume_image_url = (
                            vol_image_data.get("super_url")
                            or vol_image_data.get("medium_url")
                            or vol_image_data.get("small_url")
                            or vol_image_data.get("thumb_url")
                        )

                # Extract publisher
                publisher_name = None
                if isinstance(volume_info, dict):
                    pub_data = volume_info.get("publisher")
                    if isinstance(pub_data, dict):
                        publisher_name = pub_data.get("name")
                    elif pub_data:
                        publisher_name = str(pub_data)

                # Mark best match in picker results
                for vol in volume_results_for_picker:
                    if vol.get("cv_volume_id") == volume_id:
                        vol["is_best_match"] = True
                        break

                # Sort results by raw_score
                volume_results_for_picker.sort(key=lambda v: v.get("raw_score", 0), reverse=True)

                # Normalize confidence (max possible: 5.0 issue + 3.0 name + 0.5 year = 8.5)
                config = get_matching_config()
                confidence = normalize_confidence(best_score, config.max_issue_score, config)

                # Ensure we have results for the picker (should always have at least the best match)
                if not volume_results_for_picker:
                    logger.warning(
                        "No volume results in picker despite having a match",
                        series_name=series_name,
                        volume_id=volume_id,
                    )
                    # Build a result for the best match manually
                    picker_result: dict[str, Any] | None = None
                    if isinstance(volume_info, dict):
                        search_params = {
                            "series_name": series_name,
                            "year": year,
                            "publisher": None,
                        }
                        volume_result = evaluate_volume_candidate(
                            volume_info,
                            search_params,
                            get_matching_config(),
                        )
                        # Convert volume_id to int for dict lookup
                        volume_id_int = (
                            int(volume_id)
                            if isinstance(volume_id, (int, str)) and str(volume_id).isdigit()
                            else None
                        )
                        volume_issue_image = (
                            volume_issue_images.get(volume_id_int)
                            if volume_id_int is not None
                            else None
                        )
                        picker_result = build_volume_picker_result(
                            volume_info,
                            volume_result.score,
                            volume_result.details,
                            get_matching_config(),
                            rank=0,
                            issue_image_url=volume_issue_image,
                        )
                    if picker_result:
                        picker_result["is_best_match"] = True
                        volume_results_for_picker.append(picker_result)

                # Log volume results for debugging
                logger.debug(
                    "Volume results for picker",
                    count=len(volume_results_for_picker),
                    volume_ids=[v.get("cv_volume_id") for v in volume_results_for_picker],
                )

                results_sample_json = json.dumps(volume_results_for_picker[:10])

                logger.info(
                    "ComicVine issue search found match",
                    series_name=series_name,
                    issue_number=issue_number,
                    volume_id=volume_id,
                    issue_id=issue_id,
                    best_score=best_score,
                    confidence=confidence,
                    volume_results_count=len(volume_results_for_picker),
                )

                volume_name = volume_info.get("name") if isinstance(volume_info, dict) else None
                issue_name = issue_item.get("name") if isinstance(issue_item, dict) else None
                return {
                    "volume_id": volume_id,
                    "volume_name": volume_name,
                    "issue_id": issue_id,
                    "issue_name": issue_name,
                    "issue_image_url": issue_image_url,
                    "volume_image_url": volume_image_url,
                    "publisher": publisher_name,
                    "confidence": confidence,
                    "search_query": search_query,
                    "api_query": api_query,
                    "results_count": len(issue_results),
                    "results_sample": results_sample_json,
                }

        except Exception as exc:
            logger.warning("Issue search failed, falling back to volume search", error=str(exc))

    # STEP 2: Fall back to volume search (if no good issue match or no issue number)
    try:
        # Build search query for volume search
        volume_search_query = series_name
        if year:
            volume_search_query = f"{series_name} {year}"

        logger.debug("Falling back to volume search", query=volume_search_query)

        # Search volumes
        config = get_matching_config()

        # Check cache first
        cached_search = None
        if cache_enabled and cache_manager:
            cached_search = await cache_manager.get_comicvine_search(
                "volume",
                volume_search_query,
                config.volume_search_limit,
            )

        if cached_search:
            volume_payload = cached_search
            logger.debug("Using cached ComicVine volume search", query=volume_search_query)
        else:
            volume_payload = await fetch_comicvine(
                normalized,
                "search",
                {
                    "resources": "volume",
                    "query": volume_search_query,
                    "limit": config.volume_search_limit,
                    "field_list": "id,name,start_year,publisher,site_detail_url,image,count_of_issues",
                },
            )

            # Cache the search results
            if cache_enabled and cache_manager:
                await cache_manager.store_comicvine_search(
                    "volume",
                    volume_search_query,
                    config.volume_search_limit,
                    volume_payload,
                )

        results = volume_payload.get("results", [])
        if not results:
            logger.debug(
                "No ComicVine volume results found",
                series_name=series_name,
                search_query=volume_search_query,
            )
            # If we have issue results from earlier, return them even if no volume match
            if volume_results_for_picker:
                results_sample_json = json.dumps(volume_results_for_picker[:10])
                return {
                    "volume_id": None,
                    "volume_name": None,
                    "issue_id": None,
                    "issue_image_url": None,
                    "confidence": 0.0,
                    "search_query": search_query,
                    "api_query": api_query,
                    "results_count": len(volume_results_for_picker),
                    "results_sample": results_sample_json,
                }
            return None

        # Build results sample for volume picker
        # Don't reinitialize - preserve any results from issue search above
        if not volume_results_for_picker:
            volume_results_for_picker = []

        # Find best matching volume
        best_match = None
        best_score = 0.0
        series_key = _simplify_label(series_name)

        logger.debug(
            "Evaluating ComicVine results",
            series_name=series_name,
            series_key=series_key,
            results_count=len(results),
        )

        for idx, result in enumerate(results):
            if result.get("resource_type") != "volume":
                continue

            volume_id = _extract_numeric_id(result.get("id"))
            if not volume_id:
                continue

            # Use modular matching system to evaluate volume
            search_params = {
                "series_name": series_name,
                "year": year,
                "publisher": None,
            }
            config = get_matching_config()
            volume_result = evaluate_volume_candidate(
                result,
                search_params,
                config,
            )

            logger.debug(
                "ComicVine volume candidate",
                volume_name=result.get("name", ""),
                volume_id=volume_id,
                score=volume_result.score,
                details="; ".join(volume_result.details) if volume_result.details else "No match",
            )

            # Build picker result using modular system
            picker_result = build_volume_picker_result(
                result,
                volume_result.score,
                volume_result.details,
                config,
                rank=idx,
            )
            volume_results_for_picker.append(picker_result)

            # Use raw_score for comparison (not normalized confidence)
            # This ensures year matches properly differentiate volumes
            if volume_result.score > best_score:
                best_score = volume_result.score
                best_match = result

        # Sort results by raw_score (descending) so best matches appear first
        volume_results_for_picker.sort(key=lambda v: v.get("raw_score", 0), reverse=True)

        # Mark best match
        if best_match:
            best_volume_id = _extract_numeric_id(best_match.get("id"))
            for vol in volume_results_for_picker:
                if vol.get("cv_volume_id") == best_volume_id:
                    vol["is_best_match"] = True
                    break

        # Normalize best_score for logging (convert raw score to confidence)
        config = get_matching_config()
        best_confidence = normalize_confidence(best_score, config.max_volume_score, config)

        logger.info(
            "ComicVine search completed",
            series_name=series_name,
            results_count=len(results),
            best_match=best_match.get("name") if best_match else None,
            best_score=best_score,
            best_confidence=best_confidence,
        )

        # Use normalized confidence for threshold check
        # Threshold of 0.3 confidence = ~1.05 raw score (0.3 * 3.5)
        if not best_match or best_confidence < 0.3:
            # Still return results_sample even if no good match for manual selection
            results_sample_json = (
                json.dumps(volume_results_for_picker[:10])
                if volume_results_for_picker
                else json.dumps([])
            )
            return {
                "volume_id": None,
                "volume_name": None,
                "issue_id": None,
                "issue_image_url": None,
                "confidence": 0.0,
                "search_query": search_query,  # Human-readable query
                "api_query": api_query,  # Exact query sent to ComicVine API
                "results_count": len(results),
                "results_sample": results_sample_json,
            }

        # Extract volume ID
        volume_id = _extract_numeric_id(best_match.get("id"))
        if not volume_id:
            return None

        # If we have an issue number, try to find the matching issue
        issue_id = None
        issue_image_url = None
        issue_name = None

        if issue_number:
            normalized_issue_num = normalize_issue_number(issue_number)
            if normalized_issue_num is not None:
                try:
                    # Search for issues in this volume
                    issue_payload = await fetch_comicvine(
                        normalized,
                        "issues",
                        {
                            "filter": f"volume:{volume_id}",
                            "limit": 100,
                            "field_list": "id,name,issue_number,image,site_detail_url",
                        },
                    )

                    issue_results = issue_payload.get("results", [])
                    for issue in issue_results:
                        issue_num_raw = issue.get("issue_number")
                        issue_num = normalize_issue_number(
                            str(issue_num_raw) if issue_num_raw else None
                        )

                        if issue_num is not None and abs(issue_num - normalized_issue_num) < 0.01:
                            issue_id = _extract_numeric_id(issue.get("id"))
                            issue_name = issue.get("name")

                            # Extract issue image
                            image_data = issue.get("image")
                            if isinstance(image_data, dict):
                                issue_image_url = (
                                    image_data.get("super_url")
                                    or image_data.get("medium_url")
                                    or image_data.get("small_url")
                                    or image_data.get("thumb_url")
                                )
                            elif image_data:
                                issue_image_url = str(image_data)
                            break
                except Exception as exc:
                    # Log but don't fail - we still have volume match
                    logger.debug("Failed to fetch issues", volume_id=volume_id, error=str(exc))

        # Extract volume image
        volume_image_url = None
        image_data = best_match.get("image")
        if isinstance(image_data, dict):
            volume_image_url = (
                image_data.get("super_url")
                or image_data.get("medium_url")
                or image_data.get("small_url")
                or image_data.get("thumb_url")
            )
        elif image_data:
            volume_image_url = str(image_data)

        # Extract publisher
        publisher_name = None
        pub_data = best_match.get("publisher")
        if isinstance(pub_data, dict):
            publisher_name = pub_data.get("name")
        elif pub_data:
            publisher_name = str(pub_data)

        # Build results sample JSON
        results_sample_json = (
            json.dumps(volume_results_for_picker[:10])
            if volume_results_for_picker
            else json.dumps([])
        )

        # Normalize best_score to confidence (0.0-1.0) for return value
        config = get_matching_config()
        confidence = normalize_confidence(best_score, config.max_volume_score, config)

        return {
            "volume_id": volume_id,
            "volume_name": best_match.get("name"),
            "issue_id": issue_id,
            "issue_name": issue_name,
            "issue_image_url": issue_image_url,
            "volume_image_url": volume_image_url,
            "publisher": publisher_name,
            "confidence": confidence,  # Normalized 0.0-1.0
            "search_query": search_query,  # Human-readable query
            "api_query": api_query,  # Exact query sent to ComicVine API
            "results_count": len(results),
            "results_sample": results_sample_json,
        }

    except Exception as exc:
        logger.warning("ComicVine volume search failed", series_name=series_name, error=str(exc))
        # If we have issue results from earlier, return them even if volume search failed
        if volume_results_for_picker:
            results_sample_json = json.dumps(volume_results_for_picker[:10])
            return {
                "volume_id": None,
                "volume_name": None,
                "issue_id": None,
                "issue_image_url": None,
                "confidence": 0.0,
                "search_query": search_query,
                "api_query": api_query,
                "results_count": len(volume_results_for_picker),
                "results_sample": results_sample_json,
            }
        return None


async def _match_file_to_library(
    file_path: Path,
    stem: str,
    series_name: str | None,
    issue_number: str | None,
    session: SQLModelAsyncSession,
) -> tuple[str | None, str | None, float]:
    """Match a file to existing library issues.

    Returns:
        Tuple of (matched_volume_id, matched_issue_id, confidence)
    """
    if not series_name:
        logger.debug("No series name for library matching", file_name=file_path.name)
        return None, None, 0.0

    if not issue_number:
        logger.debug(
            "No issue number for library matching",
            file_name=file_path.name,
            series_name=series_name,
        )
        return None, None, 0.0

    issue_numeric = normalize_issue_number(issue_number)
    if issue_numeric is None:
        logger.debug(
            "Could not normalize issue number", file_name=file_path.name, issue_number=issue_number
        )
        return None, None, 0.0

    logger.debug(
        "Attempting library match",
        file_name=file_path.name,
        series_name=series_name,
        issue_number=issue_number,
        normalized_issue_number=issue_numeric,
    )

    # Get all library issues
    issues_result = await session.exec(
        select(LibraryIssue).where(col(LibraryIssue.number).isnot(None))
    )
    all_issues = issues_result.all()

    logger.debug("Library issues loaded", total_issues=len(all_issues))

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
            "No issues found with matching number",
            file_name=file_path.name,
            normalized_issue_number=issue_numeric,
            available_numbers=list(issue_index.keys())[:10],  # Log first 10 for debugging
        )
        return None, None, 0.0

    logger.debug(
        "Found issues with matching number", count=len(matching_issues), issue_number=issue_numeric
    )

    # Score matches by series name similarity
    best_match = None
    best_confidence = 0.0

    series_name_lower = _simplify_label(series_name)

    for issue in matching_issues:
        volume_result = await session.exec(
            select(LibraryVolume).where(LibraryVolume.id == issue.volume_id)
        )
        volume = volume_result.one_or_none()
        if not volume:
            continue

        volume_title_simplified = _simplify_label(volume.title)

        # Exact match
        if volume_title_simplified == series_name_lower:
            logger.info(
                "Exact library match found",
                file_name=file_path.name,
                series_name=series_name,
                volume_title=volume.title,
                volume_id=volume.id,
                issue_id=issue.id,
            )
            return issue.volume_id, issue.id, 1.0

        # Check if series name is contained in volume title or vice versa
        confidence = 0.0
        match_reason = ""
        if (
            series_name_lower in volume_title_simplified
            or volume_title_simplified in series_name_lower
        ):
            confidence = 0.8
            match_reason = "substring match"
        else:
            # Fuzzy match - check word overlap
            series_words = set(series_name_lower.split()) if series_name_lower else set()
            title_words = set(volume_title_simplified.split()) if volume_title_simplified else set()
            if series_words and title_words:
                overlap = len(series_words & title_words) / max(len(series_words), len(title_words))
                confidence = overlap * 0.6
                match_reason = f"word overlap: {overlap:.2%}"

        logger.debug(
            "Library match candidate",
            file_name=file_path.name,
            volume_title=volume.title,
            volume_id=volume.id,
            confidence=confidence,
            reason=match_reason,
        )

        if confidence > best_confidence:
            best_confidence = confidence
            best_match = issue

    if best_match and best_confidence >= 0.3:
        logger.info(
            "Library match found",
            file_name=file_path.name,
            series_name=series_name,
            volume_id=best_match.volume_id,
            issue_id=best_match.id,
            confidence=best_confidence,
        )
        return best_match.volume_id, best_match.id, best_confidence

    logger.debug(
        "No library match found",
        file_name=file_path.name,
        series_name=series_name,
        best_confidence=best_confidence if best_match else 0.0,
    )
    return None, None, 0.0


async def scan_folder_for_import(
    folder_path: Path,
    import_job_id: str,
    session: SQLModelAsyncSession,
    scanning_job_id: str | None = None,
    update_progress: bool = True,
) -> int:
    """Scan a folder for comic files and create ImportPendingFile records.

    Args:
        folder_path: Folder path to scan
        import_job_id: Import job ID
        session: Database session

    Returns:
        Number of files found and added as pending files
    """
    # Collect files
    files = await asyncio.to_thread(_collect_comic_files, folder_path)
    count = 0

    # Build index of existing file paths to skip duplicates
    # Get all library issues with file paths to check against
    existing_file_paths: set[str] = set()

    # Get library root to resolve relative paths
    import_job_result = await session.exec(select(ImportJob).where(ImportJob.id == import_job_id))
    import_job = import_job_result.one_or_none()
    if import_job:
        library_result = await session.exec(
            select(Library).where(Library.id == import_job.library_id)
        )
        library = library_result.one_or_none()
        if library:
            library_root = Path(library.library_root)
            # Get all issues in this library that have file paths
            # First get all volumes in this library
            volumes_result = await session.exec(
                select(LibraryVolume).where(LibraryVolume.library_id == import_job.library_id)
            )
            library_volumes = volumes_result.all()
            volume_ids = [vol.id for vol in library_volumes]

            if volume_ids:
                # Then get all issues in those volumes that have file paths
                issues_result = await session.exec(
                    select(LibraryIssue).where(
                        col(LibraryIssue.volume_id).in_(volume_ids),
                        col(LibraryIssue.file_path).isnot(None),
                    )
                )
                library_issues = issues_result.all()
            else:
                library_issues = []

            for issue in library_issues:
                if issue.file_path:
                    try:
                        # Resolve the file path (could be relative or absolute)
                        issue_file_path = Path(issue.file_path)
                        if not issue_file_path.is_absolute():
                            issue_file_path = library_root / issue_file_path
                        existing_file_paths.add(str(issue_file_path.resolve()))
                    except (ValueError, OSError):
                        # Skip invalid paths
                        pass

    for file_path in files:
        file_path_resolved = str(file_path.resolve())

        # Skip if already in library
        if file_path_resolved in existing_file_paths:
            logger.debug(
                "File already in library, skipping",
                file_path=file_path_resolved,
            )
            continue

        # Get file metadata
        try:
            file_size = file_path.stat().st_size
        except OSError:
            continue

        # Check for suspiciously small files (likely corrupted)
        from comicarr.core.utils import MIN_COMIC_FILE_SIZE

        is_suspicious = file_size < MIN_COMIC_FILE_SIZE
        if is_suspicious:
            logger.warning(
                "Suspiciously small file detected (likely corrupted)",
                file_path=str(file_path),
                file_size=file_size,
                min_size=MIN_COMIC_FILE_SIZE,
            )

        file_name = file_path.name
        file_ext = file_path.suffix.lower()
        stem = file_path.stem

        # Extract metadata from filename
        series_name, issue_number, year, month, volume = _extract_series_from_filename(file_name)

        # Try to match to existing library
        matched_volume_id, matched_issue_id, confidence = await _match_file_to_library(
            file_path, stem, series_name, issue_number, session
        )

        # If we matched to library, check if issue already has a file - if so, skip entirely
        if matched_volume_id and matched_issue_id:
            issue_has_file = await _issue_has_file(matched_issue_id, session)
            if issue_has_file:
                # Issue already has a file, skip creating ImportPendingFile entry entirely
                logger.debug(
                    "Issue already has a file, skipping import entry",
                    issue_id=matched_issue_id,
                    file_path=str(file_path),
                    file_name=file_name,
                )
                continue  # Skip to next file without creating ImportPendingFile

        # Search ComicVine if no library match
        comicvine_data = None
        if not matched_volume_id and series_name:
            comicvine_data = await _search_comicvine_for_file(
                series_name, issue_number, year, session
            )

        # Create pending file
        try:
            # Add warning note for suspicious files
            notes = None
            if is_suspicious:
                notes = f"⚠️ File size ({file_size:,} bytes) is suspiciously small (< 1MB). File may be corrupted or incomplete."

            pending_file = ImportPendingFile(
                import_job_id=import_job_id,
                file_path=file_path_resolved,
                file_name=file_name,
                file_size=file_size,
                file_extension=file_ext,
                extracted_series=series_name,
                extracted_issue_number=issue_number,
                extracted_year=year,
                extracted_month=month,
                extracted_volume=volume,
                notes=notes,
            )

            # Handle matching and approval logic
            if matched_volume_id and matched_issue_id:
                # Issue exists in library but has no file yet - auto-approve to add the file
                # This is a high-confidence match since we matched to an existing library issue
                # (We already skipped if issue has a file, so we know it doesn't)
                pending_file.matched_volume_id = matched_volume_id
                pending_file.matched_issue_id = matched_issue_id
                pending_file.matched_confidence = confidence

                # Auto-approve if not suspicious (file size warning, etc.)
                if not is_suspicious:
                    pending_file.status = "import"
                    logger.debug(
                        "Issue exists but has no file - auto-approving",
                        issue_id=matched_issue_id,
                        file_path=pending_file.file_path,
                    )
                else:
                    # If suspicious, mark as pending so user can review
                    pending_file.status = "pending"
                    logger.debug(
                        "Issue exists but has no file - matched but not auto-approved due to warnings",
                        issue_id=matched_issue_id,
                        file_path=pending_file.file_path,
                        warnings="suspicious file size",
                    )
            elif is_suspicious:
                # Files with warnings are skipped by default
                pending_file.status = "skipped"
                pending_file.action = "skip"
            elif comicvine_data:
                # If we have ComicVine data (even if no match), store it
                comicvine_confidence = comicvine_data.get("confidence", 0.0)
                comicvine_volume_id = comicvine_data.get("volume_id")

                pending_file.comicvine_volume_id = comicvine_volume_id
                pending_file.comicvine_issue_id = comicvine_data.get("issue_id")
                pending_file.comicvine_volume_name = comicvine_data.get("volume_name")
                pending_file.comicvine_issue_name = comicvine_data.get("issue_name")
                pending_file.comicvine_issue_image = comicvine_data.get("issue_image_url")
                pending_file.comicvine_confidence = comicvine_confidence
                pending_file.cv_search_query = comicvine_data.get("search_query")
                pending_file.cv_results_count = comicvine_data.get("results_count", 0)
                # Store ComicVine candidates for volume picker - ensure it's always a valid JSON string
                results_sample = comicvine_data.get("results_sample")
                if results_sample is None:
                    results_sample = "[]"  # Default to empty array if not provided
                pending_file.cv_results_sample = results_sample

                if comicvine_volume_id:
                    # Has ComicVine match - mark as auto-matched
                    pending_file.comicvine_match_type = "auto"
                    # Auto-approve high confidence ComicVine matches (>= 0.7 for substring matches) ONLY if no warnings
                    if comicvine_confidence >= 0.7 and not is_suspicious:
                        pending_file.status = "import"
                    else:
                        pending_file.status = "pending"
                else:
                    # Has ComicVine results but no good match
                    pending_file.comicvine_match_type = None
                    pending_file.status = "pending"

                # Debug logging
                try:
                    parsed_results = json.loads(results_sample) if results_sample else []
                    logger.debug(
                        "Stored ComicVine results sample",
                        pending_file_id=pending_file.id,
                        file_name=pending_file.file_name,
                        results_count=(
                            len(parsed_results) if isinstance(parsed_results, list) else 0
                        ),
                        has_volume_id=bool(comicvine_volume_id),
                        results_sample_preview=results_sample[:200] if results_sample else None,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to parse results_sample for logging",
                        pending_file_id=pending_file.id,
                        error=str(e),
                        results_sample_preview=results_sample[:100] if results_sample else None,
                    )
            else:
                # No matches found
                pending_file.comicvine_match_type = None
                pending_file.status = "pending"

            session.add(pending_file)
            count += 1

            # Update progress every 10 files
            if update_progress and count % 10 == 0:
                if scanning_job_id:
                    # Update ImportScanningJob progress
                    from comicarr.core.database import retry_db_operation
                    from comicarr.db.models import ImportScanningJob

                    scanning_job_result = await session.exec(
                        select(ImportScanningJob).where(ImportScanningJob.id == scanning_job_id)
                    )
                    scanning_job = scanning_job_result.one_or_none()
                    if scanning_job:
                        scanning_job.progress_current = count
                        scanning_job.updated_at = int(time.time())
                        await retry_db_operation(
                            lambda: session.commit(),
                            session=session,
                            operation_type="update_scanning_progress",
                        )
                else:
                    # Fallback to old ImportJob progress tracking
                    job_result = await session.exec(
                        select(ImportJob).where(ImportJob.id == import_job_id)
                    )
                    job = job_result.one_or_none()
                    if job:
                        job.scanned_files = count
                        job.updated_at = int(time.time())
                        session.add(job)
                        await session.commit()
                        await session.refresh(job)
        except Exception as pending_file_exc:
            logger.warning(
                "Failed to create import pending file",
                file_name=file_name,
                error=str(pending_file_exc),
                exc_info=True,
            )
            continue

    await session.commit()
    return count
