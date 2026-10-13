"""Orchestration: from site settings, weather and ephemerides to a forecast."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import Any

import numpy as np

from . import scoring
from . import weather as w
from .catalog import Catalog
from .ephemeris import (
    ASTRONOMICAL,
    PLANETS,
    Location,
    NightEphemeris,
    Snapshot,
    compute_night,
    moon_phase_name,
    next_rise_set,
    snapshot,
)
from .events import AstroEvent, compute_events
from .objects import (
    NightContext,
    ObjectNight,
    evaluate_catalog,
    evaluate_planet,
    evaluate_small_body,
)
from .skyglow import bortle_to_sqm, moon_brightening_mag
from .smallbodies import OrbitalElements
from .timeutil import night_date_for, utc

_LOGGER = logging.getLogger(__name__)

WEATHER_NIGHTS = 16  # nights evaluated against the weather forecast
TOTAL_NIGHTS = 30  # nights evaluated astronomically (moon, darkness)
OBJECT_NIGHTS = 7  # nights with full object recommendations
TOP_OBJECTS = 25


@dataclass(slots=True, frozen=True)
class SiteConfig:
    """User settings for an observing site."""

    name: str
    latitude: float
    longitude: float
    elevation: float = 0.0
    bortle: int = 4
    sqm: float | None = None
    min_altitude: float = 20.0
    equipment: str = "small_telescope"
    threshold: int = 60

    @property
    def location(self) -> Location:
        """Geographic location."""
        return Location(self.latitude, self.longitude, self.elevation)

    @property
    def sky_brightness(self) -> float:
        """Zenith sky brightness without Moon (mag/arcsec²)."""
        return self.sqm if self.sqm else bortle_to_sqm(self.bortle)


@dataclass(slots=True)
class NightForecast:
    """A night: ephemeris, weather and both profile analyses."""

    ephem: NightEphemeris
    weather: scoring.NightWeather
    deep_sky: scoring.ProfileNight
    planetary: scoring.ProfileNight
    summary: dict[str, Any] = field(default_factory=dict)
    objects: list[ObjectNight] = field(default_factory=list)
    planets: list[ObjectNight] = field(default_factory=list)

    @property
    def has_weather(self) -> bool:
        """Whether a weather forecast covers this night."""
        return self.deep_sky.score is not None or self.planetary.score is not None

    def profile(self, name: str) -> scoring.ProfileNight:
        """Return a profile analysis."""
        return self.deep_sky if name == scoring.DEEP_SKY else self.planetary


@dataclass(slots=True)
class NowConditions:
    """Current conditions."""

    time: datetime
    snapshot: Snapshot
    is_dark: bool
    scores: dict[str, int | None]
    factors: dict[str, dict[str, float]]
    limiting: dict[str, str | None]
    weather: dict[str, float | None]
    sources: dict[str, str]
    tier: str | None
    confidence: float | None
    clear_probability: float | None
    dew_risk: str | None
    moonrise: datetime | None = None
    moonset: datetime | None = None

    @property
    def moon_phase_name(self) -> str:
        """Lunar phase name."""
        return moon_phase_name(self.snapshot.moon_phase)


@dataclass(slots=True)
class FavoriteNight:
    """Best opportunity for a favourite object in one night."""

    night: date
    best_time: datetime | None
    best_score: int
    window_start: datetime | None
    window_end: datetime | None
    max_alt: float
    has_weather: bool


@dataclass(slots=True)
class FavoriteForecast:
    """Upcoming opportunities for a favourite object."""

    id: str
    tonight: ObjectNight | None
    nights: list[FavoriteNight]
    next_good: FavoriteNight | None


@dataclass(slots=True)
class Forecast:
    """Complete result for a site."""

    generated: datetime
    site: SiteConfig
    now: NowConditions
    nights: list[NightForecast]
    events: list[AstroEvent]
    favorites: list[FavoriteForecast]
    timeline: w.Timeline

    @property
    def tonight(self) -> NightForecast:
        """The current or upcoming night."""
        return self.nights[0]

    def best_night(self, profile: str = scoring.DEEP_SKY) -> NightForecast | None:
        """Night with the highest score for a profile (weather-covered nights)."""
        candidates = [n for n in self.nights if n.profile(profile).score is not None]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda n: (n.profile(profile).score or 0, n.profile(profile).good_hours),
        )


def _nanmean(values: np.ndarray) -> float | None:
    values = values[~np.isnan(values)]
    return round(float(np.mean(values)), 2) if values.size else None


def _nanmax(values: np.ndarray) -> float | None:
    values = values[~np.isnan(values)]
    return round(float(np.max(values)), 2) if values.size else None


def _night_summary(ephem: NightEphemeris, weather: scoring.NightWeather) -> dict[str, Any]:
    dark = ephem.sun_alt < -12.0
    if not np.any(dark):
        dark = ephem.sun_alt < 0.0
    summary: dict[str, Any] = {
        "cloud_cover": _nanmean(weather.get(w.CLOUD)[dark]),
        "seeing": _nanmean(weather.get(w.SEEING)[dark]),
        "transparency": _nanmean(weather.get(w.TRANSPARENCY)[dark]),
        "humidity": _nanmean(weather.get(w.HUMIDITY)[dark]),
        "wind_max": _nanmax(weather.get(w.WIND)[dark]),
        "temperature_min": None,
        "clear_probability": _nanmean(weather.clear_probability[dark]),
        "precip_probability_max": _nanmax(weather.get(w.PRECIP_PROB)[dark]),
        "aod": _nanmean(weather.get(w.AOD)[dark]),
        "dew_risk": None,
    }
    temps = weather.get(w.TEMPERATURE)[dark]
    temps = temps[~np.isnan(temps)]
    if temps.size:
        summary["temperature_min"] = round(float(np.min(temps)), 1)
    spread = weather.get(w.TEMPERATURE)[dark] - weather.get(w.DEW_POINT)[dark]
    spread = spread[~np.isnan(spread)]
    if spread.size:
        smallest = float(np.min(spread))
        summary["dew_risk"] = "high" if smallest <= 2 else "moderate" if smallest <= 4 else "low"
    return summary


class Planner:
    """Stateful planner for one site (caches ephemerides and events)."""

    def __init__(self, site: SiteConfig, catalog: Catalog) -> None:
        """Initialise."""
        self.site = site
        self.catalog = catalog
        self._nights: dict[date, NightEphemeris] = {}
        self._events: tuple[date, list[AstroEvent]] | None = None

    def nights_for(self, now: datetime, count: int = TOTAL_NIGHTS) -> list[NightEphemeris]:
        """Ephemerides of the next ``count`` nights (cached)."""
        first = night_date_for(now, self.site.longitude)
        wanted = [first + timedelta(days=i) for i in range(count)]
        for night in list(self._nights):
            if night < first:
                del self._nights[night]
        location = self.site.location
        for i, night in enumerate(wanted):
            if night not in self._nights:
                self._nights[night] = compute_night(location, night, with_planets=i < WEATHER_NIGHTS)
        return [self._nights[n] for n in wanted]

    def events(self, now: datetime, comets: Sequence[OrbitalElements]) -> list[AstroEvent]:
        """Events (recomputed once per day)."""
        today = utc(now).date()
        if self._events is None or self._events[0] != today:
            self._events = (
                today,
                compute_events(self.site.location, now, self.site.sky_brightness, comets),
            )
        horizon = utc(now) - timedelta(hours=12)
        return [e for e in self._events[1] if (e.end or e.start) >= horizon]

    def compute(
        self,
        now: datetime,
        timeline: w.Timeline | None,
        comets: Sequence[OrbitalElements] = (),
        asteroids: Sequence[OrbitalElements] = (),
        favorites: Iterable[str] = (),
    ) -> Forecast:
        """Compute a complete forecast (CPU bound: run in an executor)."""
        now = utc(now)
        site = self.site
        sqm = site.sky_brightness
        if timeline is None:
            timeline = w.Timeline([], {})
        ephemerides = self.nights_for(now)
        favorites = list(dict.fromkeys(favorites))
        observer = site.location.observer
        nights: list[NightForecast] = []
        fav_nights: dict[str, list[FavoriteNight]] = {fid: [] for fid in favorites}
        fav_tonight: dict[str, ObjectNight] = {}

        for index, ephem in enumerate(ephemerides):
            weather = scoring.sample_weather(timeline, ephem)
            night = NightForecast(
                ephem=ephem,
                weather=weather,
                deep_sky=scoring.analyse_profile(ephem, weather, scoring.DEEP_SKY, sqm, site.threshold),
                planetary=scoring.analyse_profile(
                    ephem, weather, scoring.PLANETARY, sqm, site.threshold
                ),
                summary=_night_summary(ephem, weather),
            )
            nights.append(night)
            if index >= WEATHER_NIGHTS:
                continue
            ctx = NightContext.build(
                ephem, weather, sqm, site.min_altitude, site.equipment, site.latitude
            )
            by_id: dict[str, ObjectNight] = {}
            if index < OBJECT_NIGHTS:
                dso = evaluate_catalog(ctx, self.catalog)
                by_id.update({o.id: o for o in dso})
                bodies: list[ObjectNight] = []
                for elements in (*comets, *asteroids):
                    try:
                        item = evaluate_small_body(
                            ctx, elements, observer, force=elements.id in favorites
                        )
                    except (ValueError, ZeroDivisionError, OverflowError):
                        _LOGGER.debug("Could not evaluate %s", elements.id, exc_info=True)
                        continue
                    if item is not None:
                        bodies.append(item)
                        by_id[item.id] = item
                planets = [evaluate_planet(ctx, ephem.planets[k]) for k in PLANETS]
                moon = evaluate_planet(ctx, ephem.moon)
                by_id.update({p.id: p for p in planets})
                by_id["moon"] = moon
                night.planets = [*planets, moon]
                ranked = sorted(
                    (o for o in (*dso, *bodies) if o.recommended),
                    key=lambda o: o.interest,
                    reverse=True,
                )
                night.objects = ranked[:TOP_OBJECTS]
            else:
                wanted = [fid for fid in favorites if self.catalog.get(fid)]
                if wanted:
                    subset = Catalog([self.catalog.get(fid) for fid in wanted])  # type: ignore[misc]
                    by_id.update({o.id: o for o in evaluate_catalog(ctx, subset)})
                for key in PLANETS:
                    if key in favorites:
                        by_id[key] = evaluate_planet(ctx, ephem.planets[key])
                if "moon" in favorites:
                    by_id["moon"] = evaluate_planet(ctx, ephem.moon)
                for elements in (*comets, *asteroids):
                    if elements.id in favorites:
                        item = evaluate_small_body(ctx, elements, observer, force=True)
                        if item is not None:
                            by_id[item.id] = item

            for fid in favorites:
                obj = by_id.get(fid)
                if obj is None:
                    resolved = self.catalog.get(fid)
                    obj = by_id.get(resolved.id) if resolved else None
                if obj is None:
                    continue
                if index == 0:
                    fav_tonight[fid] = obj
                fav_nights[fid].append(
                    FavoriteNight(
                        night=ephem.night,
                        best_time=obj.best_time,
                        best_score=obj.best_score,
                        window_start=obj.window_start,
                        window_end=obj.window_end,
                        max_alt=obj.max_alt,
                        has_weather=ctx.has_weather,
                    )
                )

        favorite_results = []
        for fid in favorites:
            items = fav_nights[fid]
            next_good = next(
                (
                    n
                    for n in items
                    if n.has_weather
                    and n.best_score >= site.threshold
                    and n.window_end is not None
                    and n.window_end > now
                ),
                None,
            )
            favorite_results.append(
                FavoriteForecast(id=fid, tonight=fav_tonight.get(fid), nights=items, next_good=next_good)
            )

        return Forecast(
            generated=now,
            site=site,
            now=self._now(now, timeline, sqm),
            nights=nights,
            events=self.events(now, comets),
            favorites=favorite_results,
            timeline=timeline,
        )

    def _now(self, now: datetime, timeline: w.Timeline, sqm: float) -> NowConditions:
        """Instantaneous conditions."""
        snap = snapshot(self.site.location, now)
        hour = timeline.at(now)
        values: dict[str, float | None] = {}
        sources: dict[str, str] = {}
        if hour is not None:
            for name in (*scoring.SAMPLED_FIELDS, w.JET, w.VISIBILITY, w.LIFTED, w.DUST):
                value = timeline.interpolate(name, now.timestamp())
                values[name] = round(value, 2) if value is not None else None
            sources = dict(hour.sources)
        scores: dict[str, int | None] = {}
        factors_out: dict[str, dict[str, float]] = {}
        limiting: dict[str, str | None] = {}

        def arr(name: str) -> np.ndarray:
            value = values.get(name)
            return np.array([np.nan if value is None else value])

        for profile in scoring.PROFILES:
            if hour is None or values.get(w.CLOUD) is None:
                scores[profile] = None
                limiting[profile] = None
                continue
            ext = arr(w.TRANSPARENCY)
            ext = np.where(np.isnan(ext), scoring.DEFAULT_EXTINCTION, ext)
            seeing = arr(w.SEEING)
            factors = {
                "darkness": scoring.darkness_factor(np.array([snap.sun_alt]), profile),
                "clouds": scoring.cloud_factor(arr(w.CLOUD), profile),
                "precipitation": scoring.precipitation_factor(
                    arr(w.PRECIP_PROB), arr(w.PRECIP), arr(w.PRECIP_TYPE)
                ),
                "transparency": scoring.transparency_factor(ext, profile),
                "seeing": scoring.seeing_factor(
                    np.where(np.isnan(seeing), scoring.DEFAULT_SEEING, seeing), profile
                ),
                "wind": scoring.wind_factor(arr(w.WIND), arr(w.GUST), profile),
                "humidity": scoring.humidity_factor(arr(w.HUMIDITY), arr(w.FOG)),
            }
            if profile == scoring.DEEP_SKY:
                delta = moon_brightening_mag(
                    sqm, snap.moon_phase_angle, 90.0 - snap.moon_alt, snap.moon_alt, 90.0, ext
                )
                factors["moon"] = scoring.moon_factor(np.atleast_1d(delta))
            else:
                factors["moon"] = np.ones(1)
            score = scoring.combine(factors)
            scores[profile] = int(round(float(score[0])))
            factors_out[profile] = {k: round(float(v[0]), 3) for k, v in factors.items()}
            limiting[profile] = scoring.limiting_factor(factors, np.array([True]))

        moonrise, moonset = next_rise_set(self.site.location, "moon", now)
        return NowConditions(
            moonrise=moonrise,
            moonset=moonset,
            time=now,
            snapshot=snap,
            is_dark=snap.sun_alt < ASTRONOMICAL,
            scores=scores,
            factors=factors_out,
            limiting=limiting,
            weather=values,
            sources=sources,
            tier=hour.tier if hour else None,
            confidence=hour.confidence if hour else None,
            clear_probability=hour.clear_probability if hour else None,
            dew_risk=scoring.dew_risk(values.get(w.TEMPERATURE), values.get(w.DEW_POINT)),
        )
