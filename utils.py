"""
==========================================================
Flowering Synchronisation Analysis Tool
utils.py - Date parsing, validation, small helpers
==========================================================
"""

import datetime
import pandas as pd


def parse_date(value):
    """
    Attempt to parse a date value coming from a shapefile attribute field.
    Supports DD-MM-YYYY, YYYY-MM-DD, datetime objects, pandas Timestamps,
    and Excel-style serial numbers.

    Returns a datetime.date, or None if parsing fails.
    """
    if value is None:
        return None

    # Already a date/datetime
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value

    # Pandas Timestamp / NaT
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date()

    # Numeric -> could be an Excel serial date
    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return None
            base = datetime.date(1899, 12, 30)  # Excel epoch
            return base + datetime.timedelta(days=float(value))
        except Exception:
            return None

    # String parsing
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.lower() in ("nan", "none", "nat"):
            return None

        formats = [
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%y",
            "%d.%m.%Y",
            "%m-%d-%Y",
        ]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue

        # Last resort: let pandas try
        try:
            parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
            if pd.isna(parsed):
                return None
            return parsed.date()
        except Exception:
            return None

    return None


def safe_str(value):
    """Convert any attribute value to a clean string for comparison."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def crops_match(crop_a, crop_b):
    """Case-insensitive crop comparison."""
    return safe_str(crop_a).lower() == safe_str(crop_b).lower()


def format_date(d):
    """Format a date object as DD-MM-YYYY for display/export, or blank."""
    if d is None:
        return ""
    return d.strftime("%d-%m-%Y")
