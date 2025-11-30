"""ReadComicsOnline weekly releases service.

Fetches weekly comic releases from readcomicsonline.ru/news/weekly-comic-upload-{date}.
These pages are organized by week and contain individual comic issues.
"""

from __future__ import annotations

import datetime
import re

import httpx
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger("comicarr.weekly_releases.readcomicsonline")

READCOMICSONLINE_BASE_URL = "https://readcomicsonline.ru"
READCOMICSONLINE_NEWS_BASE = f"{READCOMICSONLINE_BASE_URL}/news"
USER_AGENT = "Comicarr/0.1 (+https://github.com/agnlopes/comicarr)"

# Pattern to match date in URL: weekly-comic-upload-nov-26th-2025
# Matches: month (jan-dec), day (1-31) with optional suffix (st, nd, rd, th), year (4 digits)
DATE_IN_URL_PATTERN = re.compile(
    r"weekly-comic-upload-([a-z]+)-(\d+)(?:st|nd|rd|th)?-(\d{4})",
    flags=re.IGNORECASE,
)

# Month name to number mapping
MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def parse_date_from_url(url: str) -> datetime.date | None:
    """Parse date from URL like 'weekly-comic-upload-nov-26th-2025'."""
    match = DATE_IN_URL_PATTERN.search(url)
    if match:
        month_name, day, year = match.groups()
        month = MONTH_MAP.get(month_name.lower())
        if month:
            try:
                return datetime.date(int(year), month, int(day))
            except ValueError:
                return None
    return None


def format_date_for_url(date: datetime.date) -> str:
    """Format date for URL: nov-26th-2025."""
    month_names = {
        1: "jan",
        2: "feb",
        3: "mar",
        4: "apr",
        5: "may",
        6: "jun",
        7: "jul",
        8: "aug",
        9: "sep",
        10: "oct",
        11: "nov",
        12: "dec",
    }
    month = month_names.get(date.month, "jan")
    day = date.day
    # Add ordinal suffix
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{month}-{day}{suffix}-{date.year}"


def get_wednesday_for_date(date: datetime.date) -> datetime.date:
    """Get the Wednesday of the week for a given date.

    If date is Monday or Tuesday, returns previous Wednesday.
    Otherwise, returns the Wednesday of the same week.
    """
    weekday = date.weekday()  # 0 = Monday, 1 = Tuesday, 2 = Wednesday, etc.

    if weekday < 2:  # Monday or Tuesday
        days_to_subtract = weekday + 5  # Mon: 0+5=5, Tue: 1+5=6
    else:  # Wednesday or later
        days_to_subtract = weekday - 2  # Wed: 2-2=0, Thu: 3-2=1, etc.

    wednesday = date - datetime.timedelta(days=days_to_subtract)
    return wednesday


async def fetch_readcomicsonline_releases(
    week_start: datetime.date | None = None,
) -> list[dict]:
    """Fetch weekly comic releases from ReadComicsOnline weekly-comic-upload pages.

    Args:
        week_start: Target week start date (Wednesday). If None, uses current week's Wednesday.

    Returns:
        List of parsed release dictionaries with 'title', 'publisher', 'release_date', 'url'.
    """
    # If no week_start provided, calculate current week's Wednesday
    if week_start is None:
        today = datetime.date.today()
        weekday = today.weekday()  # 0 = Monday, 1 = Tuesday, etc.
        days_until_wednesday = (2 - weekday) % 7
        if days_until_wednesday == 0 and weekday != 2:
            days_until_wednesday = 7
        week_start = today + datetime.timedelta(days=days_until_wednesday)

    # Construct URL for the weekly upload page
    # Use the Wednesday date to format the URL
    date_str = format_date_for_url(week_start)
    url = f"{READCOMICSONLINE_NEWS_BASE}/weekly-comic-upload-{date_str}"

    logger.info("Fetching ReadComicsOnline releases", url=url, week_start=week_start.isoformat())

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.warning(
                "Weekly upload page not found for date", url=url, week_start=week_start.isoformat()
            )
            return []  # Return empty list if page doesn't exist
        logger.error(
            "HTTP error fetching ReadComicsOnline", status_code=exc.response.status_code, url=url
        )
        raise RuntimeError(
            f"Failed to fetch ReadComicsOnline: HTTP {exc.response.status_code}"
        ) from exc
    except Exception as exc:
        logger.exception("Failed to fetch ReadComicsOnline", error=str(exc), url=url)
        raise RuntimeError(f"Failed to fetch ReadComicsOnline: {exc}") from exc

    if not html:
        raise RuntimeError("ReadComicsOnline returned empty response")

    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")

    releases = []
    seen_titles: set[str] = set()

    # Find main content container - look for div with class 'list-container'
    list_container = soup.find("div", class_=lambda x: x and "list" in str(x).lower())
    if not list_container:
        # Fallback to other containers
        list_container = (
            soup.find("div", class_=lambda x: x and "container" in str(x).lower())
            or soup.find("article")
            or soup.find("main")
            or soup.find("body")
            or soup
        )

    # Publisher header pattern
    publisher_pattern = re.compile(
        r"^(DC COMICS?|MARVEL COMICS?|IMAGE COMICS?|DARK HORSE|IDW|DYNAMITE|BOOM|ONI PRESS|VALIANT|"
        r"AFTERSHOCK|BLACK MASK|VAULT|AWA|AHOY|ARCHIE|ASPEN|AVATAR|BLACK HAMMER):?$",
        re.IGNORECASE,
    )

    # Publisher name normalization map
    publisher_map = {
        "DC COMICS": "DC Comics",
        "DC COMIC": "DC Comics",
        "MARVEL COMICS": "Marvel Comics",
        "MARVEL COMIC": "Marvel Comics",
        "IMAGE COMICS": "Image Comics",
        "IMAGE COMIC": "Image Comics",
    }

    # Find all ul lists in the container
    ul_lists = list_container.find_all("ul")
    logger.info("Found ul lists", count=len(ul_lists), url=url)

    # Process each ul list
    for ul in ul_lists:
        # Find the publisher header that precedes this ul
        # Search backwards through previous siblings
        current_publisher: str | None = None

        # Check previous siblings
        prev = ul.previous_sibling
        while prev:
            if hasattr(prev, "find_all"):
                # Check for publisher headers in this element
                headers = prev.find_all(["strong", "u", "p"])
                for header in headers:
                    header_text = header.get_text(strip=True)
                    if publisher_pattern.match(header_text):
                        pub_match = publisher_pattern.match(header_text)
                        if pub_match:
                            pub_name = pub_match.group(1).upper()
                            current_publisher = publisher_map.get(pub_name, pub_name.title())
                            break
                if current_publisher:
                    break
            elif isinstance(prev, str) and prev.strip():
                # Check if this text node is a publisher header
                if publisher_pattern.match(prev.strip()):
                    pub_match = publisher_pattern.match(prev.strip())
                    if pub_match:
                        pub_name = pub_match.group(1).upper()
                        current_publisher = publisher_map.get(pub_name, pub_name.title())
                        break
            prev = prev.previous_sibling

        # If not found in siblings, check parent's previous siblings
        if not current_publisher:
            parent = ul.parent
            if parent:
                prev = parent.previous_sibling
                while prev and not current_publisher:
                    if hasattr(prev, "find_all"):
                        headers = prev.find_all(["strong", "u", "p"])
                        for header in headers:
                            header_text = header.get_text(strip=True)
                            if publisher_pattern.match(header_text):
                                pub_match = publisher_pattern.match(header_text)
                                if pub_match:
                                    pub_name = pub_match.group(1).upper()
                                    current_publisher = publisher_map.get(
                                        pub_name, pub_name.title()
                                    )
                                    break
                    prev = prev.previous_sibling if hasattr(prev, "previous_sibling") else None

        # Process each li in the ul
        for li in ul.find_all("li"):
            # Get all text from the li
            li_text = li.get_text(separator=" ", strip=True)

            # Find "Read Online" link (preferred) or "Download" link
            read_online_link = li.find("a", string=lambda text: text and text.strip().lower() == "read online")  # type: ignore[arg-type]
            download_link = li.find("a", string=lambda text: text and text.strip().lower() == "download")  # type: ignore[arg-type]

            link = read_online_link or download_link
            if not link:
                continue

            # Extract title - it's the text before the links
            # The pattern is: "Title #number : Download | Read Online"
            # So we need to get text before "Download" or "Read Online"
            link_text = link.get_text(strip=True)
            link_pos = li_text.lower().find(link_text.lower())

            if link_pos == -1:
                # Try alternative: get all text and remove link texts
                title = li_text
                for link_elem in li.find_all("a"):
                    link_text_to_remove = link_elem.get_text(strip=True)
                    title = title.replace(link_text_to_remove, "").strip()
            else:
                title = li_text[:link_pos].strip()

            # Clean up title - remove patterns like ": Download |", ": Download|", " : Download |", etc.
            # Remove trailing colons, "Download", "|", and extra whitespace
            title = re.sub(r":\s*Download\s*\|\s*$", "", title, flags=re.IGNORECASE)
            title = re.sub(r":\s*Download\s*$", "", title, flags=re.IGNORECASE)
            title = re.sub(r":\s*$", "", title).strip()

            # Skip if title is too short or looks like a publisher header
            if not title or len(title) < 3 or publisher_pattern.match(title):
                continue

            # Skip duplicates
            title_lower = title.lower().strip()
            if title_lower in seen_titles:
                continue
            seen_titles.add(title_lower)

            # Get the URL
            href = link.get("href", "")
            if href:
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = f"{READCOMICSONLINE_BASE_URL}{href}"
                else:
                    full_url = f"{READCOMICSONLINE_BASE_URL}/{href}"
            else:
                full_url = None

            releases.append(
                {
                    "title": title,
                    "publisher": current_publisher,
                    "release_date": week_start.isoformat(),
                    "url": full_url,
                }
            )

    logger.info(
        "Parsed ReadComicsOnline releases",
        count=len(releases),
        week_start=week_start.isoformat(),
        url=url,
    )

    return releases
