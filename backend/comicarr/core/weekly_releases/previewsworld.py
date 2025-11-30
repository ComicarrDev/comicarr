"""PreviewsWorld weekly releases service.

Fetches and parses the PreviewsWorld new releases text feed.
"""

from __future__ import annotations

import datetime
import warnings

import httpx
import structlog

logger = structlog.get_logger("comicarr.weekly_releases.previewsworld")

PREVIEWSWORLD_BASE_URL = "https://www.previewsworld.com/NewReleases/Export"
USER_AGENT = "Comicarr/0.1 (+https://github.com/agnlopes/comicarr)"


def parse_release_date(header_line: str) -> datetime.date | None:
    """Parse release date from header line like 'SERVICING FOR RELEASE DATE 12/11/2024'."""
    if "SERVICING FOR RELEASE DATE" not in header_line.upper():
        return None

    parts = header_line.split()
    if not parts:
        return None

    date_str = parts[-1]
    try:
        return datetime.datetime.strptime(date_str, "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_release_line(line: str) -> dict | None:
    """Parse a release line like 'PUBLISHER - TITLE (FORMAT) #ISSUE'."""
    line = line.strip()
    if not line or " - " not in line:
        return None

    # Skip section headers
    upper_line = line.upper()
    section_headers = (
        "PREVIEWS PUBLICATIONS",
        "COMICS",
        "GRAPHIC NOVELS",
        "MAGAZINES",
        "MERCHANDISE",
        "COLLECTIBLES & NOVELTIES",
        "BOOKS",
    )
    if any(upper_line.startswith(header) for header in section_headers):
        return None

    publisher_part, remainder = line.split(" - ", 1)
    publisher = publisher_part.strip()
    title = remainder.strip()

    if not publisher or not title:
        return None

    return {
        "title": title,
        "publisher": publisher,
    }


async def fetch_previewsworld_releases(
    week_start: datetime.date | None = None,
) -> list[dict]:
    """Fetch and parse releases from PreviewsWorld.

    Args:
        week_start: Target week start date (Wednesday). If None, uses current week's Wednesday.

    Returns:
        List of parsed release dictionaries with 'title', 'publisher', 'release_date'.
    """
    # If no week_start provided, calculate current week's Wednesday
    if week_start is None:
        today = datetime.date.today()
        # Calculate days since Monday (0 = Monday, 1 = Tuesday, etc.)
        days_since_monday = today.weekday()
        # Wednesday is 2 days after Monday
        days_until_wednesday = (2 - days_since_monday) % 7
        if days_until_wednesday == 0 and today.weekday() != 2:
            # If today is not Wednesday, go to next Wednesday
            days_until_wednesday = 7
        week_start = today + datetime.timedelta(days=days_until_wednesday)

    # Format date as MM/DD/YYYY for the URL
    date_str = week_start.strftime("%m/%d/%Y")
    # URL encode the date parameter
    from urllib.parse import quote

    encoded_date = quote(date_str, safe="")
    url = f"{PREVIEWSWORLD_BASE_URL}?format=txt&releaseDate={encoded_date}"

    logger.info("Fetching PreviewsWorld releases", url=url, week_start=week_start.isoformat())

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
            async with httpx.AsyncClient(
                timeout=20.0,
                headers={"User-Agent": USER_AGENT},
                verify=False,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                text = response.text
    except Exception as exc:
        logger.exception("Failed to fetch PreviewsWorld feed", error=str(exc), url=url)
        raise RuntimeError(f"Failed to fetch PreviewsWorld feed: {exc}") from exc

    if not text:
        raise RuntimeError("PreviewsWorld feed was empty")

    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        raise RuntimeError("PreviewsWorld feed contained no lines")

    # Parse header for release date (fallback to week_start if header parsing fails)
    release_date = week_start
    if lines:
        header = lines[0].strip()
        parsed_date = parse_release_date(header)
        if parsed_date:
            release_date = parsed_date

    # Parse release lines
    releases = []
    for line in lines[1:]:
        parsed = parse_release_line(line)
        if parsed:
            parsed["release_date"] = release_date.isoformat() if release_date else None
            releases.append(parsed)

    logger.info(
        "Parsed PreviewsWorld releases",
        count=len(releases),
        release_date=release_date.isoformat() if release_date else None,
    )
    return releases
