"""App-wide timezone helpers for display and PSTrax fill timestamps."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "America/New_York"

TIMEZONE_CHOICES = [
    ("America/New_York", "Eastern (America/New_York)"),
    ("America/Chicago", "Central (America/Chicago)"),
    ("America/Denver", "Mountain (America/Denver)"),
    ("America/Phoenix", "Arizona (America/Phoenix)"),
    ("America/Los_Angeles", "Pacific (America/Los_Angeles)"),
    ("America/Anchorage", "Alaska (America/Anchorage)"),
    ("Pacific/Honolulu", "Hawaii (Pacific/Honolulu)"),
    ("UTC", "UTC"),
]


def normalize_timezone_name(name: str | None) -> str:
    raw = (name or "").strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(raw)
        return raw
    except ZoneInfoNotFoundError:
        return DEFAULT_TIMEZONE


def get_timezone_name() -> str:
    """Resolve configured timezone: DB setting, then env, then default."""
    try:
        from app.models import ScrapeConfig

        config = ScrapeConfig.query.first()
        if config:
            configured = getattr(config, "app_timezone", None)
            if configured:
                return normalize_timezone_name(configured)
    except Exception:
        pass

    return normalize_timezone_name(
        os.environ.get("APP_TIMEZONE") or os.environ.get("TZ") or DEFAULT_TIMEZONE
    )


def get_zoneinfo(name: str | None = None) -> ZoneInfo:
    return ZoneInfo(normalize_timezone_name(name or get_timezone_name()))


def local_now(name: str | None = None) -> datetime:
    """Current wall-clock time in the app timezone (timezone-aware)."""
    return datetime.now(get_zoneinfo(name))


def to_local(dt: datetime | None, name: str | None = None) -> datetime | None:
    """Convert a naive-UTC or aware datetime into the app timezone."""
    if dt is None:
        return None
    tz = get_zoneinfo(name)
    if dt.tzinfo is None:
        # Stored timestamps in this app are treated as UTC when naive.
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz)


def format_local(
    dt: datetime | None,
    fmt: str = "%Y-%m-%d %H:%M",
    name: str | None = None,
    empty: str = "",
) -> str:
    local_dt = to_local(dt, name)
    if local_dt is None:
        return empty
    return local_dt.strftime(fmt)
