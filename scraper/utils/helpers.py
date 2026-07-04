"""Small pure helper functions shared across the project."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

_WS_RE = re.compile(r"\s+")
_NUM_CLEAN_RE = re.compile(r"[,\s%₹]|Rs\.?|Cr\.?", re.IGNORECASE)


def clean_text(value: str | None) -> str | None:
    """Normalise scraped text: unescape HTML entities, collapse whitespace.

    Returns ``None`` for empty / placeholder values so callers can treat
    "missing" uniformly.
    """
    if value is None:
        return None
    text = html.unescape(str(value))
    text = _WS_RE.sub(" ", text).strip()
    if text in ("", "-", "--", "N.A.", "NA", "null", "None"):
        return None
    return text


def parse_number(value: object) -> float | None:
    """Parse Moneycontrol-style numbers ("70,698.00", "--", 757446.62).

    Returns ``None`` when the value is missing or not numeric.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(str(value))
    if text is None:
        return None
    text = _NUM_CLEAN_RE.sub("", text)
    if text in ("", "-", "."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_PERIOD_LABEL_RE = re.compile(r"^([A-Za-z]{3})\w*\s*'?(\d{2,4})$")


def period_sort_key(label: str | None) -> tuple[int, int]:
    """Sortable (year, month) for period labels like "Mar '26" / "Dec 2025".

    Unparsable labels sort first (oldest) via ``(0, 0)`` so real data always
    outranks noise.
    """
    if not label:
        return (0, 0)
    match = _PERIOD_LABEL_RE.match(label.strip())
    if not match:
        return (0, 0)
    month = _MONTHS.get(match.group(1).lower(), 0)
    year = int(match.group(2))
    if year < 100:
        year += 2000
    return (year, month)


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string (stored in DB timestamps)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_db_timestamp(value: str | None) -> datetime | None:
    """Parse a timestamp previously written by :func:`utcnow_iso`."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
