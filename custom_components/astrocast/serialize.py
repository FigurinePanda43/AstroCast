"""JSON serialisation of forecasts for the dashboard, services and diagnostics."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any

import numpy as np

from .engine import weather as w
from .engine.catalog import Catalog
from .engine.ephemeris import STEP_MINUTES, NightEphemeris, moon_phase_name
from .engine.events import AstroEvent
from .engine.objects import ObjectNight
from .engine.planner import FavoriteForecast, Forecast, NightForecast
from .engine.scoring import ProfileNight
from .engine.timeutil import iso
from .i18n import body_name, event_description, event_title, lang_of

SAMPLE_NIGHTS = 2  # nights with full 15-minute curves
CURVE_NIGHTS = 7  # nights with hourly curves
TONIGHT_OBJECTS = 20  # objects sent for tonight (with altitude curves for the first 12)
LATER_OBJECTS = 8  # compact objects sent for the following nights


def _round(value: Any, digits: int = 1) -> Any:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        if math.isnan(value):
            return None
        return round(float(value), digits)
    return value


def _array(values: np.ndarray, digits: int = 1) -> list[float | None]:
    return [None if math.isnan(v) else round(float(v), digits) for v in values]


def _night_span(ephem: NightEphemeris, margin_samples: int = 4) -> tuple[int, int]:
    """Sample range covering the night (Sun below +2°) plus a margin."""
    idx = np.flatnonzero(ephem.sun_alt < 2.0)
    if idx.size == 0:
        mid = len(ephem.times) // 2
        return max(0, mid - 8), min(len(ephem.times), mid + 8)
    return max(0, int(idx[0]) - margin_samples), min(
        len(ephem.times), int(idx[-1]) + 1 + margin_samples
    )


def profile_to_dict(profile: ProfileNight) -> dict[str, Any]:
    """Serialise a profile analysis."""
    return {
        "score": profile.score,
        "rating": profile.rating,
        "potential": profile.potential,
        "window_start": iso(profile.window_start),
        "window_end": iso(profile.window_end),
        "window_score": profile.window_score,
        "peak_time": iso(profile.peak_time),
        "peak_score": profile.peak_score,
        "good_hours": profile.good_hours,
        "usable_hours": profile.usable_hours,
        "limiting": profile.limiting,
        "confidence": profile.confidence,
        "tier": profile.tier,
        "factors": profile.factor_means,
    }


def object_name(obj: ObjectNight, language: str, catalog: Catalog | None = None) -> str:
    """Localised display name of an object."""
    lang = lang_of(language)
    if obj.kind in ("planet", "moon"):
        return body_name(lang, obj.id)
    name = obj.names.get(lang) or obj.names.get("en")
    if obj.kind == "dso":
        return f"{obj.designation} – {name}" if name else obj.designation
    return name or obj.designation


def object_to_dict(
    obj: ObjectNight,
    language: str,
    span: tuple[int, int] | None = None,
    favorites: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Serialise an object's visibility."""
    data: dict[str, Any] = {
        "id": obj.id,
        "kind": obj.kind,
        "type": obj.type,
        "name": object_name(obj, language),
        "common_name": obj.names.get(lang_of(language)) or obj.names.get("en"),
        "designation": obj.designation if obj.kind not in ("planet", "moon") else None,
        "constellation": obj.constellation,
        "mag": _round(obj.mag),
        "size": _round(obj.size),
        "max_alt": _round(obj.max_alt),
        "max_alt_time": iso(obj.max_alt_time),
        "transit": iso(obj.transit),
        "rise": iso(obj.rise),
        "set": iso(obj.set),
        "hours_visible": obj.hours_visible,
        "best_time": iso(obj.best_time),
        "best_score": obj.best_score,
        "window_start": iso(obj.window_start),
        "window_end": iso(obj.window_end),
        "interest": obj.interest,
        "recommended": obj.recommended,
        "moon_separation": obj.moon_separation,
        "reasons": obj.reasons,
        "extra": obj.extra,
        "favorite": obj.id in favorites,
    }
    if span is not None and obj.altitudes is not None:
        start, end = span
        data["alt"] = [round(float(a)) for a in obj.altitudes[start:end]]
        if obj.azimuths is not None:
            data["az"] = [round(float(a)) for a in obj.azimuths[start:end]]
        if obj.scores is not None:
            data["scores"] = [round(float(s)) for s in obj.scores[start:end]]
    return data


def object_brief(
    obj: ObjectNight, language: str, favorites: set[str] | frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Compact object summary (later nights, lists)."""
    return {
        "id": obj.id,
        "kind": obj.kind,
        "type": obj.type,
        "name": object_name(obj, language),
        "mag": _round(obj.mag),
        "max_alt": _round(obj.max_alt),
        "best_time": iso(obj.best_time),
        "best_score": obj.best_score,
        "window_start": iso(obj.window_start),
        "window_end": iso(obj.window_end),
        "hours_visible": obj.hours_visible,
        "interest": obj.interest,
        "favorite": obj.id in favorites,
    }


def _samples(night: NightForecast, span: tuple[int, int], step: int, full: bool) -> dict[str, Any]:
    ephem = night.ephem
    start, end = span
    sl = slice(start, end, step)
    weather = night.weather
    data: dict[str, Any] = {
        "start": iso(ephem.times[start]),
        "step_minutes": STEP_MINUTES * step,
        "sun_alt": _array(ephem.sun_alt[sl], 0),
        "moon_alt": _array(ephem.moon_alt[sl], 0),
        "moon_az": _array(ephem.moon_az[sl], 0),
        # Unknown (not zero) where no weather forecast covers the sample.
        "deep_sky": _array(np.where(weather.has_weather, night.deep_sky.scores, np.nan)[sl], 0),
        "planetary": _array(np.where(weather.has_weather, night.planetary.scores, np.nan)[sl], 0),
        "cloud": _array(weather.get(w.CLOUD)[sl], 0),
        "clear_probability": _array(weather.clear_probability[sl], 0),
    }
    if full:
        data.update(
            {
                "deep_sky_potential": _array(night.deep_sky.potential_scores[sl], 0),
                "cloud_low": _array(weather.get(w.CLOUD_LOW)[sl], 0),
                "cloud_mid": _array(weather.get(w.CLOUD_MID)[sl], 0),
                "cloud_high": _array(weather.get(w.CLOUD_HIGH)[sl], 0),
                "seeing": _array(weather.get(w.SEEING)[sl], 2),
                "transparency": _array(weather.get(w.TRANSPARENCY)[sl], 2),
                "humidity": _array(weather.get(w.HUMIDITY)[sl], 0),
                "wind": _array(weather.get(w.WIND)[sl], 0),
                "temperature": _array(weather.get(w.TEMPERATURE)[sl], 1),
                "dew_point": _array(weather.get(w.DEW_POINT)[sl], 1),
            }
        )
    return data


def night_to_dict(
    night: NightForecast,
    language: str,
    index: int,
    favorites: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Serialise a night."""
    ephem = night.ephem
    data: dict[str, Any] = {
        "date": ephem.night.isoformat(),
        "start": iso(ephem.start),
        "end": iso(ephem.end),
        "sunset": iso(ephem.sunset),
        "sunrise": iso(ephem.sunrise),
        "civil_dusk": iso(ephem.civil_dusk),
        "civil_dawn": iso(ephem.civil_dawn),
        "nautical_dusk": iso(ephem.nautical_dusk),
        "nautical_dawn": iso(ephem.nautical_dawn),
        "astro_dusk": iso(ephem.astro_dusk),
        "astro_dawn": iso(ephem.astro_dawn),
        "moonrise": iso(ephem.moonrise),
        "moonset": iso(ephem.moonset),
        "moon_illumination": round(ephem.moon_illumination * 100),
        "moon_phase": moon_phase_name(ephem.moon_phase),
        "moon_phase_angle": round(ephem.moon_phase, 1),
        "dark_hours": ephem.dark_hours,
        "moonless_dark_hours": ephem.moonless_dark_hours,
        "has_weather": night.has_weather,
        "deep_sky": profile_to_dict(night.deep_sky),
        "planetary": profile_to_dict(night.planetary),
        "summary": night.summary,
    }
    if (index < CURVE_NIGHTS and night.has_weather) or index < SAMPLE_NIGHTS:
        span = _night_span(ephem)
        step = 1 if index < SAMPLE_NIGHTS else 4
        data["samples"] = _samples(night, span, step, full=index < SAMPLE_NIGHTS)
        if index == 0:
            data["objects"] = [
                object_to_dict(o, language, span if i < 12 else None, favorites)
                for i, o in enumerate(night.objects[:TONIGHT_OBJECTS])
            ]
            data["planets"] = [object_to_dict(p, language, span, favorites) for p in night.planets]
        else:
            if night.objects:
                data["objects"] = [
                    object_brief(o, language, favorites) for o in night.objects[:LATER_OBJECTS]
                ]
            if night.planets:
                data["planets"] = [object_brief(p, language, favorites) for p in night.planets]
    return data


def event_to_dict(event: AstroEvent, language: str, site: str) -> dict[str, Any]:
    """Serialise an event with localised texts."""
    data = {
        key: (iso(value) if isinstance(value, datetime) else value)
        for key, value in event.data.items()
    }
    return {
        "id": event.id,
        "type": event.type,
        "start": iso(event.start),
        "end": iso(event.end),
        "importance": event.importance,
        "visible": event.visible,
        "best_time": iso(event.best_time),
        "title": event_title(event, language),
        "description": event_description(event, language, site),
        "data": data,
    }


def favorite_to_dict(fav: FavoriteForecast, language: str, catalog: Catalog) -> dict[str, Any]:
    """Serialise a favourite's opportunities."""
    tonight = fav.tonight
    name = fav.id
    if tonight is not None:
        name = object_name(tonight, language)
    elif (obj := catalog.get(fav.id)) is not None:
        name = obj.label(lang_of(language))
    return {
        "id": fav.id,
        "name": name,
        "tonight": object_to_dict(tonight, language) if tonight else None,
        "next_good": _fav_night(fav.next_good) if fav.next_good else None,
        "nights": [_fav_night(n) for n in fav.nights],
    }


def _fav_night(night: Any) -> dict[str, Any]:
    return {
        "date": night.night.isoformat(),
        "best_time": iso(night.best_time),
        "best_score": night.best_score,
        "window_start": iso(night.window_start),
        "window_end": iso(night.window_end),
        "max_alt": night.max_alt,
        "has_weather": night.has_weather,
    }


def now_to_dict(forecast: Forecast) -> dict[str, Any]:
    """Serialise current conditions."""
    now = forecast.now
    snap = now.snapshot
    return {
        "time": iso(now.time),
        "sun_alt": round(snap.sun_alt, 1),
        "sun_az": round(snap.sun_az, 1),
        "moon_alt": round(snap.moon_alt, 1),
        "moon_az": round(snap.moon_az, 1),
        "moon_illumination": round(snap.moon_illumination * 100),
        "moon_phase": now.moon_phase_name,
        "moon_phase_angle": round(snap.moon_phase, 1),
        "moon_distance_km": round(snap.moon_distance_km),
        "is_dark": now.is_dark,
        "scores": now.scores,
        "limiting": now.limiting,
        "factors": now.factors,
        "weather": now.weather,
        "sources": now.sources,
        "tier": now.tier,
        "confidence": now.confidence,
        "clear_probability": now.clear_probability,
        "dew_risk": now.dew_risk,
        "planets": {k: [round(v[0], 1), round(v[1], 1)] for k, v in snap.bodies.items()},
    }


def forecast_to_dict(
    forecast: Forecast,
    language: str,
    catalog: Catalog,
    favorites: list[str],
    providers: dict[str, Any],
    nights: int = 30,
) -> dict[str, Any]:
    """Full payload for the dashboard."""
    fav_set = set(favorites)
    site = forecast.site
    best = forecast.best_night()
    best_planetary = forecast.best_night("planetary")
    return {
        "version": 1,
        "generated": iso(forecast.generated),
        "language": lang_of(language),
        "site": {
            "name": site.name,
            "latitude": round(site.latitude, 4),
            "longitude": round(site.longitude, 4),
            "elevation": round(site.elevation),
            "bortle": site.bortle,
            "sqm": round(site.sky_brightness, 2),
            "min_altitude": site.min_altitude,
            "equipment": site.equipment,
            "threshold": site.threshold,
        },
        "now": now_to_dict(forecast),
        "best_night": best.ephem.night.isoformat() if best else None,
        "best_planetary_night": best_planetary.ephem.night.isoformat() if best_planetary else None,
        "nights": [
            night_to_dict(n, language, i, fav_set) for i, n in enumerate(forecast.nights[:nights])
        ],
        "events": [
            event_to_dict(e, language, site.name)
            for e in forecast.events
            if e.importance >= 2
            or e.type in ("moon_phase", "season", "meteor_shower")
            or (e.visible and e.type in ("conjunction", "occultation"))
        ],
        "favorites": [favorite_to_dict(f, language, catalog) for f in forecast.favorites],
        "providers": providers,
    }
