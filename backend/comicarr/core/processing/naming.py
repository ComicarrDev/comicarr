"""Naming service for generating file and folder names from templates."""

from __future__ import annotations

import datetime
import re
from typing import Any

import structlog

from comicarr.core.models import FormatValue

logger = structlog.get_logger("comicarr.processing.naming")


FIELD_TOKEN_PATTERN = re.compile(r"\{([^{}]+)\}")


def _parse_release_datetime(value: str | None) -> datetime.datetime | None:
    """Parse release date string to datetime.

    Supports ISO format strings and common date formats.
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    candidates = [raw]
    if raw.endswith("Z"):
        candidates.append(raw[:-1] + "+00:00")

    for candidate in candidates:
        try:
            return datetime.datetime.fromisoformat(candidate)
        except ValueError:
            pass

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m",
        "%Y",
    ]
    for fmt in formats:
        try:
            parsed = datetime.datetime.strptime(raw, fmt)
            if fmt == "%Y-%m":
                parsed = parsed.replace(day=1)
            elif fmt == "%Y":
                parsed = parsed.replace(month=1, day=1)
            return parsed
        except ValueError:
            continue

    return None


class NamingService:
    """Service for rendering naming templates."""

    def __init__(self) -> None:
        """Initialize naming service."""
        self.logger = structlog.get_logger("comicarr.processing.naming")

    def render_issue_filename(
        self,
        template: str,
        volume_title: str,
        issue_number: str | None,
        ext: str = "cbz",
        release_date: str | None = None,
        volume_year: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Render issue filename from template.

        Args:
            template: Template string with {field} tokens
            volume_title: Series/volume title
            issue_number: Issue number (e.g., "1", "1.5")
            ext: File extension (without dot)
            release_date: Release date string (ISO format or YYYY-MM-DD)
            volume_year: Volume/series year (used for {Year} field)
            **kwargs: Additional template variables

        Returns:
            Rendered filename
        """
        # Clean title (move articles to end)
        cleaned_title = self._clean_series_title(volume_title)

        # Format issue number with padding
        issue_formatted = self._format_issue_number(issue_number)
        issue_numeric = None
        try:
            if issue_number:
                issue_numeric = float(issue_number)
        except (ValueError, TypeError):
            pass

        # Parse release date
        release_date_obj = _parse_release_datetime(release_date)
        release_year = str(release_date_obj.year) if release_date_obj else None

        # Series year: volume year if present, otherwise issue year from release date
        series_year = str(volume_year) if volume_year is not None else (release_year or "")

        # Build context with FormatValue objects for proper formatting
        context: dict[str, FormatValue] = {
            "Series Title": FormatValue(cleaned_title),
            "Title": FormatValue(cleaned_title),  # Alias
            "Issue Number": FormatValue(
                issue_formatted, numeric=issue_numeric, raw=issue_number or ""
            ),
            "Issue": FormatValue(
                issue_formatted, numeric=issue_numeric, raw=issue_number or ""
            ),  # Alias
            "Year": FormatValue(
                series_year
            ),  # Series year (volume year if present, otherwise issue year)
            "ext": FormatValue(ext),
            "Release Date": FormatValue(
                release_date or "",
                raw=release_date or "",
                date_value=release_date_obj,
            ),
        }

        # Add kwargs as FormatValue objects
        for key, value in kwargs.items():
            if isinstance(value, FormatValue):
                context[key] = value
            else:
                context[key] = FormatValue(str(value) if value is not None else "")

        # Render template
        filename = template
        for match in FIELD_TOKEN_PATTERN.finditer(template):
            field = match.group(1)
            # Handle formatting (e.g., {Issue Number:03d} or {Release Date:%Y-%m-%d})
            if ":" in field:
                field_name, format_spec = field.split(":", 1)
                format_value = context.get(field_name, FormatValue(""))

                # Check if this is a strftime format spec (starts with %)
                if format_spec.strip().startswith("%") and format_value.date_value:
                    try:
                        value = format_value.date_value.strftime(format_spec.strip())
                    except (ValueError, TypeError):
                        value = format_value.default
                else:
                    # Use FormatValue's __format__ method for numeric padding
                    value = format(format_value, format_spec)
            else:
                format_value = context.get(field, FormatValue(""))
                value = str(format_value)

            filename = filename.replace(match.group(0), value)

        # Sanitize filename
        return self._sanitize_filename(filename)

    def render_volume_folder(
        self,
        template: str,
        volume_title: str,
        volume_year: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Render volume folder name from template.

        Args:
            template: Template string with {field} tokens
            volume_title: Series/volume title
            volume_year: Volume/series year (used for {Year} field)
            **kwargs: Additional template variables

        Returns:
            Rendered folder name
        """
        cleaned_title = self._clean_series_title(volume_title)

        context: dict[str, FormatValue] = {
            "Series Title": FormatValue(cleaned_title),
            "Title": FormatValue(cleaned_title),
            "Year": FormatValue(str(volume_year) if volume_year is not None else ""),
        }

        # Add kwargs as FormatValue objects
        for key, value in kwargs.items():
            if isinstance(value, FormatValue):
                context[key] = value
            else:
                context[key] = FormatValue(str(value) if value is not None else "")

        folder_name = template
        for match in FIELD_TOKEN_PATTERN.finditer(template):
            field = match.group(1)
            # Handle formatting (e.g., {Release Date:%Y-%m-%d})
            if ":" in field:
                field_name, format_spec = field.split(":", 1)
                format_value = context.get(field_name, FormatValue(""))

                # Check if this is a strftime format spec (starts with %)
                if format_spec.strip().startswith("%") and format_value.date_value:
                    try:
                        value = format_value.date_value.strftime(format_spec.strip())
                    except (ValueError, TypeError):
                        value = format_value.default
                else:
                    # Use FormatValue's __format__ method for numeric padding
                    value = format(format_value, format_spec)
            else:
                format_value = context.get(field, FormatValue(""))
                value = str(format_value)

            folder_name = folder_name.replace(match.group(0), value)

        return self._sanitize_folder_name(folder_name)

    def _clean_series_title(self, title: str) -> str:
        """Clean series title by moving articles to the end."""
        lowered = title.lower()
        for prefix in ("the ", "a ", "an "):
            if lowered.startswith(prefix):
                return f"{title[len(prefix):]}, {title[:len(prefix)-1]}"
        return title

    def _format_issue_number(self, issue_number: str | None) -> str:
        """Format issue number for display."""
        if not issue_number:
            return ""
        # Try to parse as float for formatting
        try:
            num = float(issue_number)
            if num.is_integer():
                return str(int(num))
            return str(num)
        except (ValueError, TypeError):
            return str(issue_number)

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename by removing invalid characters."""
        # Remove invalid characters for filenames
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "")
        # Remove leading/trailing dots and spaces
        filename = filename.strip(". ")
        # Replace multiple spaces with single space
        filename = re.sub(r"\s+", " ", filename)
        return filename

    def _sanitize_folder_name(self, folder_name: str) -> str:
        """Sanitize folder name, preserving forward slashes for subfolders."""
        # Split by forward slash to handle subfolders
        parts = folder_name.split("/")
        sanitized_parts = []
        for part in parts:
            # Remove invalid characters but preserve forward slashes (already split)
            cleaned = re.sub(r'[<>:"\\|?*]+', "", part)
            # Remove leading/trailing dots and spaces
            cleaned = cleaned.strip(". ")
            # Replace multiple spaces with single space
            cleaned = re.sub(r"\s+", " ", cleaned)
            # Allow forward slashes, spaces, and common folder name characters
            safe = re.sub(r"[^0-9A-Za-z._\-()'# /]+", "", cleaned)
            safe = safe.strip()
            if safe:
                sanitized_parts.append(safe)  # type: ignore[arg-type]
        # Join parts with forward slash, but filter out empty parts
        result = "/".join(sanitized_parts).strip()
        # Remove any double slashes
        result = re.sub(r"/+", "/", result)
        # Remove leading/trailing slashes (but preserve internal ones)
        result = result.strip("/")
        return result or "Volume"
