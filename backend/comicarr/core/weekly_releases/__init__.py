"""Weekly releases services for fetching comic releases from external sources."""

from comicarr.core.weekly_releases.comicgeeks import fetch_comicgeeks_releases
from comicarr.core.weekly_releases.matching import (
    deduplicate_week_by_comicvine,
    match_week_to_comicvine,
    match_week_to_library,
    match_weekly_release_to_comicvine,
    match_weekly_release_to_library,
)
from comicarr.core.weekly_releases.previewsworld import fetch_previewsworld_releases
from comicarr.core.weekly_releases.readcomicsonline import fetch_readcomicsonline_releases
from comicarr.core.weekly_releases.storage import (
    build_issue_key,
    get_or_create_week,
    parse_issue_from_title,
    store_releases,
)

__all__ = [
    "fetch_comicgeeks_releases",
    "fetch_previewsworld_releases",
    "fetch_readcomicsonline_releases",
    "build_issue_key",
    "get_or_create_week",
    "parse_issue_from_title",
    "store_releases",
    "match_week_to_comicvine",
    "match_week_to_library",
    "match_weekly_release_to_comicvine",
    "match_weekly_release_to_library",
    "deduplicate_week_by_comicvine",
]
