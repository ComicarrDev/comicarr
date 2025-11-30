"""Internal dataclass models for Comicarr."""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class FormatValue:
    """Value container for filename formatting with support for numeric padding and date formatting."""

    default: str
    numeric: float | None = None
    raw: str | None = None
    date_value: datetime.datetime | None = None

    def __format__(self, format_spec: str) -> str:
        """Format the value according to the spec (e.g., '000' for zero-padding, '%Y-%m-%d' for strftime)."""
        if not format_spec:
            return self.default

        spec = format_spec.strip()
        if not spec:
            return self.default

        # Handle strftime formatting for dates
        if spec.startswith("%") and self.date_value:
            try:
                return self.date_value.strftime(spec)
            except (ValueError, TypeError):
                return self.default

        # Handle numeric padding
        if spec.isdigit():
            width = len(spec)
            if self.numeric is not None:
                if float(self.numeric).is_integer():
                    return f"{int(round(self.numeric)):0{width}d}"
                text = f"{self.numeric:.2f}".rstrip("0").rstrip(".")
                integer_part, _, decimal_part = text.partition(".")
                padded = integer_part.zfill(width)
                return f"{padded}.{decimal_part}" if decimal_part else padded
            candidate = (self.raw or "").replace(".", "")
            if candidate.isdigit():
                return candidate.zfill(width)
            return self.default

        # Try standard formatting
        try:
            if self.numeric is not None:
                return format(self.numeric, spec)
            return format(self.default, spec)
        except Exception:
            return self.default

    def __str__(self) -> str:
        """Return the default string representation."""
        return self.default
