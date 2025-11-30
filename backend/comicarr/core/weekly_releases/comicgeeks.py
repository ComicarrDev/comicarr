"""League of Comic Geeks weekly releases service.

Fetches and parses releases from League of Comic Geeks new comics page.
"""

from __future__ import annotations

import asyncio
import datetime
import re

import cloudscraper
import httpx
import requests
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger("comicarr.weekly_releases.comicgeeks")

COMICGEEKS_BASE_URL = "https://leagueofcomicgeeks.com"
COMICGEEKS_NEW_COMICS_URL = f"{COMICGEEKS_BASE_URL}/comics/new-comics"
USER_AGENT = "Comicarr/0.1 (+https://github.com/agnlopes/comicarr)"

# Publisher pattern for extraction
PUBLISHER_PATTERN = re.compile(
    r"\b(DC Comics|Marvel Comics|Image Comics|Dark Horse|IDW|Dynamite|Boom|Oni Press|Valiant|"
    r"Aftershock|Black Mask|Vault|AWA|Ahoy|Archie|Aspen|Avatar|Black Hammer|Boom! Studios|"
    r"Catalyst|Comixology|Dynamite Entertainment|Fantagraphics|First Second|Heavy Metal|"
    r"Humanoids|Icon|IDW Publishing|Insight Editions|Legendary|Lion Forge|Mad Cave|"
    r"Magnetic Press|Papercutz|Rebellion|Red 5|Scout|Skybound|Titan|Top Cow|Vertigo|Viz|Yen Press)\b",
    flags=re.IGNORECASE,
)

# Date pattern: "Nov 5th, 2025" or "Nov 5, 2025"
DATE_PATTERN = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+)(?:th|st|nd|rd)?,?\s+(\d{4})",
    flags=re.IGNORECASE,
)


def parse_date_from_text(text: str) -> datetime.date | None:
    """Parse date from text like 'Nov 5th, 2025' or 'Nov 5, 2025'."""
    match = DATE_PATTERN.search(text)
    if match:
        month_name, day, year = match.groups()
        month_map = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        try:
            month = month_map[month_name.lower()]
            return datetime.date(int(year), month, int(day))
        except (ValueError, KeyError):
            return None
    return None


def current_week_wednesday(date: datetime.datetime | None = None) -> datetime.date:
    """Calculate the Wednesday of the week for a given date.

    Wednesday is the standard release day for comics.
    If the date is Monday or Tuesday, returns the previous Wednesday.
    Otherwise, returns the Wednesday of the same week.
    """
    base = date or datetime.datetime.now(datetime.UTC)
    weekday = base.weekday()  # 0 = Monday, 1 = Tuesday, 2 = Wednesday, etc.

    if weekday < 2:  # Monday or Tuesday
        days_to_subtract = weekday + 5  # Mon: 0+5=5, Tue: 1+5=6
    else:  # Wednesday or later
        days_to_subtract = weekday - 2  # Wed: 2-2=0, Thu: 3-2=1, etc.

    wednesday = base - datetime.timedelta(days=days_to_subtract)
    return wednesday.date()


async def fetch_comicgeeks_releases(
    week_start: datetime.date | None = None,
) -> list[dict]:
    """Fetch and parse releases from League of Comic Geeks.

    Args:
        week_start: Optional target week start date (Wednesday). If None, uses previous week.

    Returns:
        List of parsed release dictionaries with 'title', 'publisher', 'release_date', 'url'.
    """
    # Comics are released on Wednesdays
    # League of Comic Geeks URL uses Tuesday (day before release), but we store Wednesday
    if week_start is None:
        # Default to previous week for consistency
        base_date = datetime.datetime.now(datetime.UTC) + datetime.timedelta(weeks=-1)
        week_start = current_week_wednesday(base_date)

    target_date = week_start - datetime.timedelta(days=1)  # Tuesday for URL

    url = f"{COMICGEEKS_NEW_COMICS_URL}/{target_date.year}/{target_date.month:02d}/{target_date.day:02d}"
    logger.info("Fetching ComicGeeks releases", url=url, week_start=week_start.isoformat())

    html: str | None = None

    # Use cloudscraper to bypass Cloudflare
    try:

        def fetch_with_cloudscraper() -> str:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "darwin", "desktop": True}
            )
            response = scraper.get(url, timeout=30)
            response.raise_for_status()
            return response.text

        loop = asyncio.get_event_loop()
        html = await loop.run_in_executor(None, fetch_with_cloudscraper)
    except requests.exceptions.RequestException:
        # Fallback to httpx if cloudscraper fails
        logger.warning("cloudscraper failed, falling back to httpx", url=url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers=headers,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error fetching ComicGeeks", status_code=exc.response.status_code, url=url
            )
            raise RuntimeError(
                f"Failed to fetch ComicGeeks: HTTP {exc.response.status_code}"
            ) from exc

    if not html:
        raise RuntimeError("ComicGeeks returned empty response")

    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")
    comic_links = soup.find_all("a", href=re.compile(r"/comic/\d+"))

    releases = []
    seen_titles: set[str] = set()

    for link in comic_links:
        href = link.get("href", "")
        title = link.get_text(strip=True)

        if not title or not title.strip():
            continue

        # Skip invalid titles
        title_lower = title.lower().strip()
        invalid_titles = {"untitled release", "untitled", "tba", "tbd", "to be announced"}
        if title_lower in invalid_titles or any(
            title_lower.startswith(inv) for inv in invalid_titles
        ):
            continue

        # Skip variant covers
        if (href and "variant=" in href) or "Cover" in title:
            continue

        # Skip duplicates
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        # Find parent list item for publisher extraction
        li = link.find_parent("li")
        if not li:
            continue

        full_text = li.get_text()

        # Extract publisher
        publisher_match = PUBLISHER_PATTERN.search(full_text)
        if not publisher_match:
            continue

        publisher = publisher_match.group(1)

        # Extract date from text or use target_date
        release_date = parse_date_from_text(full_text) or target_date

        # Build full URL
        if href and isinstance(href, str) and href.startswith("http"):
            full_url = href
        else:
            full_url = f"{COMICGEEKS_BASE_URL}{href}"

        releases.append(
            {
                "title": title,
                "publisher": publisher,
                "release_date": release_date.isoformat(),
                "url": full_url,
            }
        )

    logger.info(
        "Parsed ComicGeeks releases", count=len(releases), week_start=week_start.isoformat()
    )
    return releases
