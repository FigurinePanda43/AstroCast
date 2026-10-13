"""Time helpers shared by the engine."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import astronomy

# 2000-01-01T12:00:00Z expressed as a Unix timestamp (astronomy-engine epoch).
J2000_UNIX = 946728000.0


def utc(dt: datetime) -> datetime:
    """Return ``dt`` as an aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_astro(dt: datetime) -> astronomy.Time:
    """Convert a datetime to an astronomy-engine ``Time``."""
    return astronomy.Time((utc(dt).timestamp() - J2000_UNIX) / 86400.0)


def from_astro(time: astronomy.Time) -> datetime:
    """Convert an astronomy-engine ``Time`` to an aware UTC datetime."""
    return datetime.fromtimestamp(time.ut * 86400.0 + J2000_UNIX, tz=UTC)


def floor_hour(dt: datetime) -> datetime:
    """Truncate to the start of the hour (UTC)."""
    return utc(dt).replace(minute=0, second=0, microsecond=0)


def solar_offset(longitude: float) -> timedelta:
    """Offset of local mean solar time from UTC for a longitude (east positive)."""
    return timedelta(hours=longitude / 15.0)


def night_date_for(moment: datetime, longitude: float) -> date:
    """Return the date of the evening that starts the night containing ``moment``.

    A "night" runs from local mean solar noon to the next local mean solar noon,
    which keeps the definition valid everywhere on Earth (including polar
    regions) and independent of political time zones.
    """
    local = utc(moment) + solar_offset(longitude) - timedelta(hours=12)
    return local.date()


def night_window(night: date, longitude: float) -> tuple[datetime, datetime]:
    """Return the UTC [noon, next noon) window of a night (local mean solar time)."""
    start = datetime(night.year, night.month, night.day, 12, tzinfo=UTC) - solar_offset(longitude)
    return start, start + timedelta(days=1)


def iso(dt: datetime | None) -> str | None:
    """Serialise an optional datetime to ISO 8601 (UTC)."""
    if dt is None:
        return None
    return utc(dt).isoformat(timespec="seconds")
