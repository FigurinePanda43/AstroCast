"""Normalised weather series and their fusion into one hourly timeline.

Each provider returns a :class:`WeatherSeries` (possibly 3- or 6-hourly). The
timeline merges them hour by hour with an explicit priority per quantity and
records where every value comes from, its forecast tier and a confidence
estimate, so that nothing is ever presented as more precise than it is.

Forecast tiers:
* ``detailed`` — lead time ≤ 72 h (7Timer! ASTRO and high-resolution models).
* ``forecast`` — lead time ≤ 7 days (deterministic global models).
* ``trend``    — beyond 7 days: ensemble statistics (probabilities, not values).
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import math
from typing import Any

from .skyglow import extinction_from_aod

# Field names shared by all providers.
CLOUD = "cloud_cover"
CLOUD_LOW = "cloud_low"
CLOUD_MID = "cloud_mid"
CLOUD_HIGH = "cloud_high"
HUMIDITY = "humidity"
DEW_POINT = "dew_point"
TEMPERATURE = "temperature"
WIND = "wind_speed"
GUST = "wind_gust"
PRECIP_PROB = "precip_probability"
PRECIP = "precipitation"
VISIBILITY = "visibility"
JET = "jet_wind"
LIFTED = "lifted_index"
SEEING = "seeing"
TRANSPARENCY = "transparency"
AOD = "aod"
DUST = "dust"
FOG = "fog"
PRECIP_TYPE = "precip_type"

DETAILED_HOURS = 72
FORECAST_HOURS = 168
CLEAR_THRESHOLD = 25.0  # % cloud cover below which an ensemble member is "clear"

# Merge priority per quantity (first available wins).
PRIORITY: dict[str, tuple[str, ...]] = {
    CLOUD: ("open_meteo", "met_no", "7timer"),
    CLOUD_LOW: ("open_meteo", "met_no"),
    CLOUD_MID: ("open_meteo", "met_no"),
    CLOUD_HIGH: ("open_meteo", "met_no"),
    HUMIDITY: ("open_meteo", "met_no", "7timer"),
    DEW_POINT: ("open_meteo", "met_no"),
    TEMPERATURE: ("open_meteo", "met_no", "7timer"),
    WIND: ("open_meteo", "met_no", "7timer"),
    GUST: ("open_meteo", "met_no"),
    PRECIP_PROB: ("open_meteo", "met_no"),
    PRECIP: ("open_meteo", "met_no"),
    VISIBILITY: ("open_meteo",),
    JET: ("open_meteo",),
    LIFTED: ("7timer", "open_meteo"),
    FOG: ("met_no",),
    AOD: ("cams",),
    DUST: ("cams",),
}

# Maximum gap (h) across which a series may be interpolated.
MAX_GAP_HOURS: dict[str, float] = {
    "open_meteo": 1.5,
    "met_no": 6.5,
    "7timer": 3.5,
    "cams": 1.5,
    "ensemble": 6.5,
}


@dataclass(slots=True)
class WeatherSeries:
    """A provider's time series (UTC timestamps, possibly irregular)."""

    source: str
    fetched: datetime
    times: list[float]
    fields: dict[str, list[float | None]]
    model_run: datetime | None = None
    members: list[list[float]] | None = None  # ensemble only, per time step

    def value(self, name: str, ts: float) -> float | None:
        """Linearly interpolated value at ``ts`` (None if unavailable)."""
        values = self.fields.get(name)
        if not values or not self.times:
            return None
        idx = bisect_left(self.times, ts)
        if idx < len(self.times) and self.times[idx] == ts:
            return values[idx]
        if idx == 0 or idx >= len(self.times):
            return None
        t0, t1 = self.times[idx - 1], self.times[idx]
        if (t1 - t0) / 3600.0 > MAX_GAP_HOURS.get(self.source, 1.5):
            return None
        v0, v1 = values[idx - 1], values[idx]
        if v0 is None or v1 is None:
            return v0 if ts - t0 < t1 - ts else v1
        frac = (ts - t0) / (t1 - t0)
        return v0 + (v1 - v0) * frac

    def nearest_members(self, ts: float) -> list[float] | None:
        """Ensemble members at the nearest time step (within the max gap)."""
        if not self.members or not self.times:
            return None
        idx = bisect_left(self.times, ts)
        candidates = [i for i in (idx - 1, idx) if 0 <= i < len(self.times)]
        if not candidates:
            return None
        best = min(candidates, key=lambda i: abs(self.times[i] - ts))
        if abs(self.times[best] - ts) / 3600.0 > MAX_GAP_HOURS["ensemble"] / 2:
            return None
        return self.members[best] or None

    @property
    def end(self) -> float | None:
        """Last timestamp."""
        return self.times[-1] if self.times else None

    def as_dict(self) -> dict[str, Any]:
        """Serialise for persistent storage."""
        return {
            "source": self.source,
            "fetched": self.fetched.isoformat(),
            "model_run": self.model_run.isoformat() if self.model_run else None,
            "times": self.times,
            "fields": self.fields,
            "members": self.members,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeatherSeries:
        """Restore from storage."""
        return cls(
            source=data["source"],
            fetched=datetime.fromisoformat(data["fetched"]),
            model_run=datetime.fromisoformat(data["model_run"]) if data.get("model_run") else None,
            times=list(data["times"]),
            fields={k: list(v) for k, v in data["fields"].items()},
            members=data.get("members"),
        )


@dataclass(slots=True)
class HourlyWeather:
    """Merged weather for one hour."""

    time: datetime
    lead_hours: float
    tier: str
    confidence: float
    values: dict[str, float | None] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    clear_probability: float | None = None
    ensemble_mean: float | None = None
    ensemble_spread: float | None = None
    members: list[float] | None = None

    def get(self, name: str) -> float | None:
        """Return a merged value."""
        return self.values.get(name)


@dataclass(slots=True)
class Timeline:
    """Hourly merged weather."""

    hours: list[HourlyWeather]
    sources: dict[str, WeatherSeries]
    _index: dict[float, int] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        """Index by timestamp."""
        self._index = {h.time.timestamp(): i for i, h in enumerate(self.hours)}

    @property
    def start(self) -> datetime | None:
        """First hour."""
        return self.hours[0].time if self.hours else None

    @property
    def end(self) -> datetime | None:
        """Last hour."""
        return self.hours[-1].time if self.hours else None

    def at(self, moment: datetime) -> HourlyWeather | None:
        """Hour containing ``moment``."""
        ts = moment.replace(minute=0, second=0, microsecond=0).timestamp()
        idx = self._index.get(ts)
        return self.hours[idx] if idx is not None else None

    def interpolate(self, name: str, ts: float) -> float | None:
        """Interpolate a merged quantity at an arbitrary timestamp."""
        if not self.hours:
            return None
        base = math.floor(ts / 3600.0) * 3600.0
        i0 = self._index.get(base)
        if i0 is None:
            return None
        v0 = self.hours[i0].values.get(name)
        i1 = self._index.get(base + 3600.0)
        v1 = self.hours[i1].values.get(name) if i1 is not None else None
        if v0 is None:
            return v1 if v1 is not None and ts - base > 1800 else None
        if v1 is None:
            return v0
        return v0 + (v1 - v0) * (ts - base) / 3600.0


def seeing_from_jetstream(jet_kmh: float) -> float:
    """Rough seeing estimate (arcsec) from the 250 hPa wind speed.

    Strong jet-stream winds are the main source of high-altitude turbulence.
    This empirical proxy is only used when no dedicated seeing forecast is
    available, and is flagged as such.
    """
    table = ((0.0, 1.0), (50.0, 1.2), (90.0, 1.6), (130.0, 2.1), (180.0, 2.6), (250.0, 3.2))
    return _interp_table(jet_kmh, table)


def _interp_table(x: float, table: tuple[tuple[float, float], ...]) -> float:
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:], strict=False):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def _confidence(lead_hours: float, spread: float | None, tier: str) -> float:
    base = max(0.25, 1.0 - lead_hours / (16 * 24) * 0.75)
    if spread is not None:
        base *= 1.0 - min(spread, 45.0) / 90.0
    if tier == "trend":
        base = min(base, 0.5)
    return round(max(0.05, min(1.0, base)), 2)


def tier_for(lead_hours: float) -> str:
    """Forecast tier for a lead time."""
    if lead_hours <= DETAILED_HOURS:
        return "detailed"
    if lead_hours <= FORECAST_HOURS:
        return "forecast"
    return "trend"


def build_timeline(
    series: dict[str, WeatherSeries],
    now: datetime,
    elevation: float,
    max_days: int = 16,
) -> Timeline:
    """Merge provider series into an hourly timeline starting just before ``now``."""
    now = now.astimezone(UTC)
    start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    ends = [s.end for s in series.values() if s.end is not None]
    if not ends:
        return Timeline([], series)
    last = min(max(ends), (start + timedelta(days=max_days)).timestamp())
    hours: list[HourlyWeather] = []
    ensemble = series.get("ensemble")
    seven = series.get("7timer")
    ts = start.timestamp()
    while ts <= last:
        moment = datetime.fromtimestamp(ts, tz=UTC)
        lead = (ts - now.timestamp()) / 3600.0
        tier = tier_for(max(0.0, lead))
        hour = HourlyWeather(time=moment, lead_hours=round(lead, 1), tier=tier, confidence=1.0)
        for name, sources in PRIORITY.items():
            for source in sources:
                provider = series.get(source)
                if provider is None:
                    continue
                value = provider.value(name, ts)
                if value is not None:
                    hour.values[name] = value
                    hour.sources[name] = source
                    break

        # Seeing: 7Timer! ASTRO forecast, else jet-stream proxy.
        seeing = seven.value(SEEING, ts) if seven else None
        if seeing is not None:
            hour.values[SEEING] = seeing
            hour.sources[SEEING] = "7timer"
        elif (jet := hour.values.get(JET)) is not None:
            hour.values[SEEING] = round(seeing_from_jetstream(jet), 2)
            hour.sources[SEEING] = "jetstream"

        # Transparency (V extinction): CAMS aerosols, else 7Timer! class.
        if (aod := hour.values.get(AOD)) is not None:
            hour.values[TRANSPARENCY] = round(extinction_from_aod(aod, elevation), 3)
            hour.sources[TRANSPARENCY] = "cams"
        elif seven and (k := seven.value(TRANSPARENCY, ts)) is not None:
            hour.values[TRANSPARENCY] = k
            hour.sources[TRANSPARENCY] = "7timer"

        # Ensemble statistics.
        if ensemble is not None and (members := ensemble.nearest_members(ts)):
            mean = sum(members) / len(members)
            spread = math.sqrt(sum((m - mean) ** 2 for m in members) / len(members))
            hour.ensemble_mean = round(mean, 1)
            hour.ensemble_spread = round(spread, 1)
            hour.clear_probability = round(
                100.0 * sum(1 for m in members if m < CLEAR_THRESHOLD) / len(members)
            )
            hour.members = members
            if CLOUD not in hour.values:
                hour.values[CLOUD] = round(mean, 1)
                hour.sources[CLOUD] = "ensemble"

        if not hour.values:
            ts += 3600.0
            continue
        hour.confidence = _confidence(max(0.0, lead), hour.ensemble_spread, tier)
        hours.append(hour)
        ts += 3600.0
    return Timeline(hours, series)
