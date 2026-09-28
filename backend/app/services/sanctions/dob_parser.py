"""Best-effort parsing of OFAC's free-text date of birth strings.

OFAC dates of birth are not a fixed format: exact dates ("19 Jun 1951"), year-only
("1965"), circa years ("circa 1965") and ranges ("1965 to 1967") all appear. When an
exact date cannot be determined, the year is still captured for coarse comparison.
"""

from __future__ import annotations

import datetime as dt
import re

_MONTHS = {
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

_EXACT_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})\s*$")
_YEAR_RE = re.compile(r"(\d{4})")


def parse_dob(raw: str | None) -> tuple[dt.date | None, int | None]:
    """Return (exact_date, year) for a raw OFAC date-of-birth string."""
    if not raw:
        return None, None

    exact_match = _EXACT_RE.match(raw)
    if exact_match:
        day, month_name, year = exact_match.groups()
        month = _MONTHS.get(month_name[:3].lower())
        if month:
            try:
                return dt.date(int(year), month, int(day)), int(year)
            except ValueError:
                pass

    year_match = _YEAR_RE.search(raw)
    if year_match:
        return None, int(year_match.group(1))

    return None, None
