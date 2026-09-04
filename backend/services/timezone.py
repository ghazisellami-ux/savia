"""Application timezone policy.

The browser owns presentation time for each user. Server-side business work
uses the timezone of the first configured country so schedules and generated
documents are consistent for the company, even when the server runs in UTC.
"""

import os
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Africa/Tunis"

# Countries currently available in the SAVIA location catalogue.  These are
# IANA timezone names, so daylight-saving rules remain correct where they
# apply. Countries with multiple zones should eventually expose an explicit
# timezone override; the selected country is still a sensible default.
COUNTRY_TIMEZONES = {
    "TN": "Africa/Tunis",
    "DZ": "Africa/Algiers",
    "MA": "Africa/Casablanca",
    "SN": "Africa/Dakar",
    "FR": "Europe/Paris",
    "US": "America/New_York",
    "QA": "Asia/Qatar",
    "SA": "Asia/Riyadh",
}


def _first_country(value: object) -> str:
    return str(value or "").split(",", 1)[0].strip().upper()


def timezone_name_for_country(country: object) -> str:
    """Return the IANA timezone for a country code."""
    code = _first_country(country)
    return COUNTRY_TIMEZONES.get(code, "UTC" if code == "OTHER" else DEFAULT_TIMEZONE)


def configured_timezone_name() -> str:
    """Read the current company timezone from the selected country setting."""
    try:
        # Imported lazily to avoid a database import cycle during startup.
        from db_engine import get_config
        return timezone_name_for_country(get_config("pays", "TN"))
    except Exception:
        return DEFAULT_TIMEZONE


def configure_process_timezone() -> str:
    """Align Python's local clock with the configured business timezone."""
    timezone_name = configured_timezone_name()
    os.environ["TZ"] = timezone_name
    # tzset is available in the Linux containers. Keep the fallback for local
    # development platforms where Python does not expose it.
    if hasattr(time, "tzset"):
        time.tzset()
    return timezone_name


def business_timezone() -> ZoneInfo:
    """Return the configured business timezone as an IANA ZoneInfo object."""
    return ZoneInfo(configured_timezone_name())


def business_now() -> datetime:
    return datetime.now(business_timezone())


def business_today() -> date:
    return business_now().date()


def _safe_zoneinfo(name: object, fallback: str = "UTC") -> ZoneInfo:
    try:
        return ZoneInfo(str(name or fallback).strip())
    except Exception:
        return ZoneInfo(fallback)


def now_in_timezone(name: object) -> datetime:
    """Return the current instant rendered in a validated IANA timezone."""
    return datetime.now(timezone.utc).astimezone(_safe_zoneinfo(name))


def utc_bounds_for_local_date(value: object, timezone_name: object = "UTC", end: bool = False) -> datetime:
    """Convert a local calendar date boundary to a UTC naive database value."""
    local_date = datetime.strptime(str(value), "%Y-%m-%d").date()
    if end:
        local_date += timedelta(days=1)
    local_boundary = datetime.combine(local_date, datetime.min.time(), tzinfo=_safe_zoneinfo(timezone_name))
    return local_boundary.astimezone(timezone.utc).replace(tzinfo=None)


def format_utc_timestamp(value: object, timezone_name: object = "UTC", fmt: str = "%d/%m/%Y %H:%M:%S") -> str:
    """Format a UTC database timestamp in the requested display timezone."""
    if value in (None, ""):
        return ""
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(_safe_zoneinfo(timezone_name)).strftime(fmt)
    except (TypeError, ValueError):
        return str(value)


__all__ = [
    "COUNTRY_TIMEZONES",
    "DEFAULT_TIMEZONE",
    "business_now",
    "business_timezone",
    "business_today",
    "configure_process_timezone",
    "configured_timezone_name",
    "format_utc_timestamp",
    "now_in_timezone",
    "timezone_name_for_country",
    "utc_bounds_for_local_date",
]
