"""
==========================================================
Flowering Synchronisation Analysis Tool
utils.py - Date parsing, validation, small helpers
==========================================================
"""

import datetime
import pandas as pd


# ── All supported date formats (label → strptime format string) ───────────────
DATE_FORMATS = {
    "DD/MM/YYYY  (e.g. 25/07/2024)": "%d/%m/%Y",
    "DD-MM-YYYY  (e.g. 25-07-2024)": "%d-%m-%Y",
    "DD.MM.YYYY  (e.g. 25.07.2024)": "%d.%m.%Y",
    "MM/DD/YYYY  (e.g. 07/25/2024)": "%m/%d/%Y",
    "MM-DD-YYYY  (e.g. 07-25-2024)": "%m-%d-%Y",
    "MM.DD.YYYY  (e.g. 07.25.2024)": "%m.%d.%Y",
    "YYYY/MM/DD  (e.g. 2024/07/25)": "%Y/%m/%d",
    "YYYY-MM-DD  (e.g. 2024-07-25)": "%Y-%m-%d",
    "YYYY.MM.DD  (e.g. 2024.07.25)": "%Y.%m.%d",
    "DD/MM/YY    (e.g. 25/07/24)":   "%d/%m/%y",
    "DD-MM-YY    (e.g. 25-07-24)":   "%d-%m-%y",
    "MM/DD/YY    (e.g. 07/25/24)":   "%m/%d/%y",
}

# Default format shown in the UI on first load
DEFAULT_DATE_FORMAT_LABEL = "DD/MM/YYYY  (e.g. 25/07/2024)"


def parse_date(value, primary_fmt=None):
    """
    Parse a date value coming from a shapefile attribute field.

    Parameters
    ----------
    value       : raw value from the GeoDataFrame cell
    primary_fmt : strptime format string to try FIRST (from user selection),
                  e.g. '%d/%m/%Y'.  If None, the legacy auto-detect list is used.

    Returns datetime.date or None.
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

    # Numeric → could be an Excel serial date
    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return None
            base = datetime.date(1899, 12, 30)          # Excel epoch
            return base + datetime.timedelta(days=float(value))
        except Exception:
            return None

    # String parsing
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.lower() in ("nan", "none", "nat"):
            return None

        # Build the ordered list of formats to try:
        #   1. User-selected format first (highest priority)
        #   2. All other known formats as fallback
        all_fmt_values = list(DATE_FORMATS.values())
        if primary_fmt and primary_fmt in all_fmt_values:
            fmt_order = [primary_fmt] + [f for f in all_fmt_values if f != primary_fmt]
        else:
            fmt_order = all_fmt_values

        for fmt in fmt_order:
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue

        # Last resort: let pandas try (dayfirst honours common non-US convention)
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
