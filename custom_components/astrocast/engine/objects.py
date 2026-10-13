"""Visibility and recommendation of celestial objects for a night.

An object is *recommended* only when it is both well placed (high enough,
during darkness, for long enough) **and** worth observing under the expected
conditions (sky score at its position, moonlight at its position, brightness
compared with what the chosen equipment can show). Every recommendation comes
with machine-readable reasons that the UI translates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Any

import numpy as np

from . import scoring
from .catalog import Catalog, DeepSkyObject
from .ephemeris import STEP_MINUTES, BodyTrack, NightEphemeris
from .horizon import altitude_limit
from .positions import altaz, angular_separation, precess
from .skyglow import airmass, moon_brightening_mag
from .smallbodies import OrbitalElements, position
from .timeutil import to_astro

EQUIPMENT_LIMIT = {
    "naked_eye": 6.0,
    "binoculars": 9.5,
    "small_telescope": 11.5,
    "medium_telescope": 12.8,
    "large_telescope": 14.0,
    "astrophotography": 15.0,
}

# How much each object type suits a kind of equipment (0-1).
AFFINITY: dict[str, dict[str, float]] = {
    "naked_eye": {
        "open_cluster": 1.0,
        "asterism": 1.0,
        "galaxy": 0.7,
        "globular_cluster": 0.6,
        "cluster_nebula": 0.8,
        "emission_nebula": 0.5,
        "nebula": 0.5,
        "planetary_nebula": 0.2,
        "reflection_nebula": 0.3,
        "supernova_remnant": 0.2,
        "dark_nebula": 0.3,
        "galaxy_group": 0.1,
        "double_star": 0.3,
    },
    "binoculars": {
        "open_cluster": 1.0,
        "asterism": 1.0,
        "galaxy": 0.8,
        "globular_cluster": 0.85,
        "cluster_nebula": 0.95,
        "emission_nebula": 0.75,
        "nebula": 0.7,
        "planetary_nebula": 0.5,
        "reflection_nebula": 0.5,
        "supernova_remnant": 0.5,
        "dark_nebula": 0.5,
        "galaxy_group": 0.3,
        "double_star": 0.6,
    },
    "telescope": {
        "open_cluster": 0.85,
        "asterism": 0.6,
        "galaxy": 1.0,
        "globular_cluster": 1.0,
        "cluster_nebula": 1.0,
        "emission_nebula": 0.9,
        "nebula": 0.9,
        "planetary_nebula": 1.0,
        "reflection_nebula": 0.8,
        "supernova_remnant": 0.8,
        "dark_nebula": 0.4,
        "galaxy_group": 0.85,
        "double_star": 0.9,
    },
    "astrophotography": {
        "open_cluster": 0.6,
        "asterism": 0.4,
        "galaxy": 1.0,
        "globular_cluster": 0.85,
        "cluster_nebula": 1.0,
        "emission_nebula": 1.0,
        "nebula": 1.0,
        "planetary_nebula": 0.85,
        "reflection_nebula": 1.0,
        "supernova_remnant": 1.0,
        "dark_nebula": 0.9,
        "galaxy_group": 0.9,
        "double_star": 0.2,
    },
}

# Diffuse objects look fainter than their integrated magnitude suggests.
DIFFUSE_PENALTY = {
    "open_cluster": -0.5,
    "asterism": -0.5,
    "globular_cluster": 0.5,
    "planetary_nebula": 0.3,
    "emission_nebula": 1.0,
    "nebula": 1.0,
    "reflection_nebula": 1.2,
    "supernova_remnant": 1.5,
    "cluster_nebula": 0.5,
    "dark_nebula": 2.0,
    "galaxy_group": 1.0,
    "double_star": 0.0,
}

# Sensitivity of an object type to moonlight (exponent of the moon factor).
MOON_SENSITIVITY = {
    "galaxy": 1.0,
    "galaxy_group": 1.0,
    "emission_nebula": 1.0,
    "nebula": 1.0,
    "reflection_nebula": 1.0,
    "supernova_remnant": 1.0,
    "dark_nebula": 1.0,
    "cluster_nebula": 0.8,
    "planetary_nebula": 0.6,
    "globular_cluster": 0.7,
    "open_cluster": 0.45,
    "asterism": 0.4,
    "double_star": 0.2,
    "comet": 1.0,
    "asteroid": 0.5,
}

PLANET_NAMES = ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")


def affinity_group(equipment: str) -> str:
    """Map an equipment preset to an affinity table."""
    if equipment in ("small_telescope", "medium_telescope", "large_telescope"):
        return "telescope"
    return equipment if equipment in AFFINITY else "telescope"


def limiting_magnitude(equipment: str, sqm: float) -> float:
    """Practical limiting magnitude for extended objects with this equipment."""
    base = EQUIPMENT_LIMIT.get(equipment, 12.0)
    return base - 0.8 * max(0.0, 21.5 - sqm)


@dataclass(slots=True)
class ObjectNight:
    """Visibility of one object during one night."""

    id: str
    kind: str  # dso, planet, moon, comet, asteroid
    type: str
    names: dict[str, str | None]
    designation: str
    constellation: str
    mag: float | None
    size: float | None = None  # arcmin (dso) or arcsec (planets)
    max_alt: float = -90.0
    max_alt_time: datetime | None = None
    transit: datetime | None = None
    rise: datetime | None = None
    set: datetime | None = None
    hours_visible: float = 0.0
    best_time: datetime | None = None
    best_score: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None
    interest: int = 0
    appeal: float = 0.0
    moon_separation: float | None = None
    reasons: list[dict[str, Any]] = field(default_factory=list)
    altitudes: np.ndarray | None = None
    azimuths: np.ndarray | None = None
    scores: np.ndarray | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def recommended(self) -> bool:
        """Worth observing tonight."""
        return self.interest >= 30 and self.best_score >= 35


def _window(
    scores: np.ndarray, times: list[datetime]
) -> tuple[datetime | None, datetime | None, int, int]:
    if scores.size == 0 or float(np.max(scores)) <= 0:
        return None, None, 0, -1
    best = int(np.argmax(scores))
    peak = float(scores[best])
    threshold = max(35.0, 0.8 * peak) if peak >= 35 else peak * 0.8
    lo = hi = best
    while lo > 0 and scores[lo - 1] >= threshold:
        lo -= 1
    while hi < len(scores) - 1 and scores[hi + 1] >= threshold:
        hi += 1
    step = times[1] - times[0]
    return times[lo], times[hi] + step, int(round(peak)), best


@dataclass(slots=True)
class NightContext:
    """Shared inputs for object evaluation in one night."""

    ephem: NightEphemeris
    weather: scoring.NightWeather
    sqm: float
    min_alt: float
    equipment: str
    latitude: float
    has_weather: bool
    deep: dict[str, np.ndarray]
    planetary: dict[str, np.ndarray]
    extinction: np.ndarray
    seeing: np.ndarray
    horizon: tuple[tuple[float, float], ...] = ()

    @classmethod
    def build(
        cls,
        ephem: NightEphemeris,
        weather: scoring.NightWeather,
        sqm: float,
        min_alt: float,
        equipment: str,
        latitude: float,
        horizon: tuple[tuple[float, float], ...] = (),
    ) -> NightContext:
        """Pre-compute sky factors for the night."""
        usable = ephem.sun_alt < -12.0
        has_weather = bool(np.any(weather.has_weather[usable])) if np.any(usable) else False
        deep = scoring.sky_factors(
            ephem, weather, scoring.DEEP_SKY, sqm, assume_clear=not has_weather
        )
        planetary = scoring.sky_factors(
            ephem, weather, scoring.PLANETARY, sqm, assume_clear=not has_weather
        )
        ext = weather.get("transparency")
        ext = np.where(np.isnan(ext), scoring.DEFAULT_EXTINCTION, ext)
        seeing = weather.get("seeing")
        seeing = np.where(np.isnan(seeing), scoring.DEFAULT_SEEING, seeing)
        return cls(
            ephem,
            weather,
            sqm,
            min_alt,
            equipment,
            latitude,
            has_weather,
            deep,
            planetary,
            ext,
            seeing,
            horizon,
        )

    def limit(self, az: np.ndarray, floor: float | None = None) -> np.ndarray:
        """Lowest usable altitude at the given azimuths (horizon profile)."""
        return altitude_limit(self.horizon, az, self.min_alt if floor is None else floor)

    def deep_base(self) -> np.ndarray:
        """Deep-sky sky factors except the (object-specific) moon factor."""
        f = self.deep
        return (
            f["clouds"]
            * f["precipitation"]
            * f["darkness"]
            * f["transparency"]
            * f["seeing"]
            * f["wind"]
            * f["humidity"]
        )

    def planetary_base(self) -> np.ndarray:
        """Planetary sky factors except seeing (altitude-dependent)."""
        f = self.planetary
        return (
            f["clouds"]
            * f["precipitation"]
            * f["darkness"]
            * f["transparency"]
            * f["wind"]
            * f["humidity"]
        )


def _altitude_factor(
    alt: np.ndarray, extinction: np.ndarray, min_alt: float | np.ndarray
) -> np.ndarray:
    """Extinction loss with airmass, and the user's horizon limit."""
    x = airmass(alt)
    loss = 10.0 ** (-0.2 * (extinction + 0.1) * (x - 1.0))
    return np.where(alt >= min_alt, loss, 0.0)


def evaluate_catalog(
    ctx: NightContext, catalog: Catalog, language: str = "en"
) -> list[ObjectNight]:
    """Evaluate every deep-sky object of the catalog (vectorised)."""
    ephem = ctx.ephem
    ra, dec = precess(catalog.vectors, ephem.precession)
    alt, az = altaz(ra, dec, ephem.lst_deg, ctx.latitude)
    moon_sep = angular_separation(alt, az, ephem.moon_alt[None, :], ephem.moon_az[None, :])
    delta = moon_brightening_mag(
        ctx.sqm,
        ephem.moon_phase_angle[None, :],
        moon_sep,
        ephem.moon_alt[None, :],
        alt,
        ctx.extinction[None, :],
    )
    sens = np.array([MOON_SENSITIVITY.get(o.type, 1.0) for o in catalog.objects])[:, None]
    f_moon = scoring.moon_factor(delta, sens)
    limit = ctx.limit(az)
    f_alt = _altitude_factor(alt, ctx.extinction[None, :], limit)
    scores = 100.0 * ctx.deep_base()[None, :] * f_moon * f_alt
    dark = ctx.deep["darkness"] > 0.5
    return [
        _summarise_dso(
            ctx, obj, alt[i], az[i], scores[i], moon_sep[i], dark, f_moon[i], limit[i], language
        )
        for i, obj in enumerate(catalog.objects)
    ]


def _summarise_dso(
    ctx: NightContext,
    obj: DeepSkyObject,
    alt: np.ndarray,
    az: np.ndarray,
    scores: np.ndarray,
    moon_sep: np.ndarray,
    dark: np.ndarray,
    f_moon: np.ndarray,
    limit: np.ndarray,
    language: str,
) -> ObjectNight:
    ephem = ctx.ephem
    result = ObjectNight(
        id=obj.id,
        kind="dso",
        type=obj.type,
        names={"en": obj.name_en, "fr": obj.name_fr},
        designation=obj.aliases[0] if obj.aliases else obj.id,
        constellation=obj.constellation,
        mag=obj.mag,
        size=obj.size,
    )
    _fill_visibility(result, ephem, alt, dark, limit, az)
    start, end, best_score, best = _window(scores, ephem.times)
    result.window_start, result.window_end, result.best_score = start, end, best_score
    if best >= 0:
        result.best_time = ephem.times[best]
        if ephem.moon_alt[best] > 0:
            result.moon_separation = round(float(moon_sep[best]), 1)
    lm = limiting_magnitude(ctx.equipment, ctx.sqm)
    mag_eff = obj.effective_mag + DIFFUSE_PENALTY.get(obj.type, 0.5)
    if obj.surface_brightness is not None and obj.type == "galaxy":
        mag_eff = obj.effective_mag + max(0.0, obj.surface_brightness - 22.0) * 0.7
    brightness = float(np.clip((lm - mag_eff + 1.0) / 4.0, 0.0, 1.0))
    affinity = AFFINITY[affinity_group(ctx.equipment)].get(obj.type, 0.8)
    fame = 1.0 if (obj.messier or obj.caldwell) else 0.95 if obj.name_en else 0.75
    size_fit = 1.0
    if obj.size and ctx.equipment in ("medium_telescope", "large_telescope") and obj.size > 120:
        size_fit = 0.75
    if obj.size and obj.size < 0.5 and ctx.equipment in ("naked_eye", "binoculars"):
        size_fit = 0.5
    result.appeal = round(brightness * affinity * fame * size_fit, 3)
    good = float(np.count_nonzero(scores >= max(35.0, 0.8 * best_score))) * STEP_MINUTES / 60.0
    duration = min(1.0, good / 1.5) ** 0.5 if best_score > 0 else 0.0
    result.interest = int(round(best_score * result.appeal * duration))

    reasons = result.reasons
    if obj.messier or obj.caldwell or obj.name_en:
        reasons.append({"key": "showpiece"})
    if result.max_alt >= 60:
        reasons.append({"key": "high_altitude", "alt": round(result.max_alt)})
    elif 0 < result.max_alt < ctx.min_alt + 10:
        reasons.append({"key": "low_altitude", "alt": round(result.max_alt)})
    if best >= 0:
        if ephem.moon_alt[best] <= 0:
            reasons.append({"key": "moon_down"})
        elif f_moon[best] < 0.6:
            reasons.append({"key": "moon_interference", "sep": round(float(moon_sep[best]))})
        elif moon_sep[best] >= 90:
            reasons.append({"key": "moon_far", "sep": round(float(moon_sep[best]))})
    if brightness < 0.4:
        reasons.append({"key": "faint_for_equipment"})
    if 0 < result.hours_visible < 1.5:
        reasons.append({"key": "short_window", "hours": round(result.hours_visible, 1)})
    del language
    return result


def _fill_visibility(
    result: ObjectNight,
    ephem: NightEphemeris,
    alt: np.ndarray,
    dark: np.ndarray,
    min_alt: float | np.ndarray,
    az: np.ndarray | None = None,
) -> None:
    visible = dark & (alt >= min_alt)
    result.hours_visible = float(np.count_nonzero(visible)) * STEP_MINUTES / 60.0
    if np.any(dark):
        idx = int(np.argmax(np.where(dark, alt, -999.0)))
        result.max_alt = round(float(alt[idx]), 1)
        result.max_alt_time = ephem.times[idx]
    peak = int(np.argmax(alt))
    if 0 < peak < len(alt) - 1:
        result.transit = ephem.times[peak]
    result.altitudes = alt
    result.azimuths = az


def evaluate_planet(ctx: NightContext, track: BodyTrack) -> ObjectNight:
    """Evaluate the Moon or a planet with the planetary profile."""
    ephem = ctx.ephem
    alt = track.alt
    x = airmass(alt)
    eff_seeing = ctx.seeing * x**0.6
    f_seeing = scoring.seeing_factor(eff_seeing, scoring.PLANETARY)
    limit = ctx.limit(track.az, max(ctx.min_alt, 5.0) if track.key == "moon" else None)
    f_alt = _altitude_factor(alt, ctx.extinction, limit)
    scores = 100.0 * ctx.planetary_base() * f_seeing * f_alt
    kind = "moon" if track.key == "moon" else "planet"
    result = ObjectNight(
        id=track.key,
        kind=kind,
        type=kind,
        names={"en": None, "fr": None},
        designation=track.key,
        constellation=track.constellation,
        mag=round(track.mag, 2) if track.mag is not None else None,
        size=round(track.diameter_arcsec, 1),
        rise=track.rise,
        set=track.set,
    )
    dark = ctx.planetary["darkness"] > 0.5
    _fill_visibility(result, ephem, alt, dark, limit, track.az)
    result.transit = track.transit
    start, end, best_score, best = _window(scores, ephem.times)
    result.window_start, result.window_end, result.best_score = start, end, best_score
    if best >= 0:
        result.best_time = ephem.times[best]

    mag = track.mag if track.mag is not None else 6.0
    lm = limiting_magnitude(ctx.equipment, ctx.sqm)
    if kind == "moon":
        illum = track.phase_fraction or 0.0
        appeal = 0.95 if 0.15 <= illum <= 0.85 else 0.7 if illum > 0.85 else 0.4
        result.extra["illumination"] = round(illum * 100)
    else:
        appeal = 1.0 if mag <= 0 else 0.92 if mag <= 2 else 0.6 if mag <= 6 else 0.45
        if mag > lm:
            appeal = 0.0
        elif track.key in ("uranus", "neptune") and ctx.equipment == "naked_eye":
            appeal = 0.15
    result.appeal = appeal
    good = float(np.count_nonzero(scores >= max(35.0, 0.8 * best_score))) * STEP_MINUTES / 60.0
    duration = min(1.0, good / 1.0) ** 0.5 if best_score > 0 else 0.0
    result.interest = int(round(best_score * appeal * duration))

    reasons = result.reasons
    if track.elongation is not None:
        result.extra["elongation"] = round(track.elongation, 1)
        if abs(track.elongation) >= 150 and track.key not in ("mercury", "venus"):
            reasons.append({"key": "near_opposition"})
        if track.key in ("mercury", "venus") and abs(track.elongation) >= 15:
            reasons.append(
                {
                    "key": "evening_sky" if track.elongation > 0 else "morning_sky",
                    "elong": round(abs(track.elongation)),
                }
            )
    if track.phase_fraction is not None and track.key in ("moon", "venus", "mercury"):
        result.extra["phase"] = round(track.phase_fraction * 100)
    if track.ring_tilt is not None:
        result.extra["ring_tilt"] = round(track.ring_tilt, 1)
    result.extra["diameter"] = round(track.diameter_arcsec, 1)
    result.extra["distance_au"] = round(track.distance_au, 4)
    if result.max_alt >= 50:
        reasons.append({"key": "high_altitude", "alt": round(result.max_alt)})
    elif 0 < result.max_alt < 20:
        reasons.append({"key": "low_altitude", "alt": round(result.max_alt)})
    if best >= 0 and ctx.seeing[best] <= 1.2 and ctx.has_weather:
        reasons.append({"key": "good_seeing", "seeing": round(float(ctx.seeing[best]), 1)})
    return result


_POSITION_CACHE: dict[tuple[str, float, float, float, float], Any] = {}


def _cached_position(elements: OrbitalElements, moment: datetime, observer: Any) -> Any:
    """Small-body positions only depend on the date: cache them per night."""
    key = (elements.id, elements.tp, moment.timestamp(), observer.latitude, observer.longitude)
    found = _POSITION_CACHE.get(key)
    if found is None:
        if len(_POSITION_CACHE) > 20000:
            _POSITION_CACHE.clear()
        found = _POSITION_CACHE[key] = position(elements, moment, observer)
    return found


def evaluate_small_body(
    ctx: NightContext, elements: OrbitalElements, observer: Any, force: bool = False
) -> ObjectNight | None:
    """Evaluate a comet or an asteroid (position at local midnight).

    Bodies too faint for the equipment are skipped unless ``force`` is set
    (favourites are always evaluated).
    """
    ephem = ctx.ephem
    pos = _cached_position(elements, ephem.midnight, observer)
    if pos.mag is None:
        return None
    lm = limiting_magnitude(ctx.equipment, ctx.sqm)
    is_comet = elements.kind == "comet"
    mag_eff = pos.mag + (1.5 if is_comet else 0.0)
    if not force and (mag_eff > lm + 1.0 or pos.elongation < 20):
        return None
    ra = np.array([math.radians(pos.ra_hours * 15.0)])
    dec = np.array([math.radians(pos.dec)])
    alt, az = altaz(ra, dec, ephem.lst_deg, ctx.latitude)
    alt, az = alt[0], az[0]
    moon_sep = angular_separation(alt, az, ephem.moon_alt, ephem.moon_az)
    delta = moon_brightening_mag(
        ctx.sqm, ephem.moon_phase_angle, moon_sep, ephem.moon_alt, alt, ctx.extinction
    )
    f_moon = scoring.moon_factor(delta, MOON_SENSITIVITY["comet" if is_comet else "asteroid"])
    limit = ctx.limit(az)
    scores = 100.0 * ctx.deep_base() * f_moon * _altitude_factor(alt, ctx.extinction, limit)
    result = ObjectNight(
        id=elements.id,
        kind=elements.kind,
        type=elements.kind,
        names={"en": elements.name, "fr": elements.name},
        designation=elements.name,
        constellation=pos.constellation,
        mag=round(pos.mag, 1),
    )
    dark = ctx.deep["darkness"] > 0.5
    _fill_visibility(result, ephem, alt, dark, limit, az)
    start, end, best_score, best = _window(scores, ephem.times)
    result.window_start, result.window_end, result.best_score = start, end, best_score
    if best >= 0:
        result.best_time = ephem.times[best]
    brightness = float(np.clip((lm - mag_eff + 1.0) / 4.0, 0.0, 1.0))
    result.appeal = round(brightness * (1.0 if is_comet else 0.7), 3)
    good = float(np.count_nonzero(scores >= max(35.0, 0.8 * best_score))) * STEP_MINUTES / 60.0
    duration = min(1.0, good / 1.5) ** 0.5 if best_score > 0 else 0.0
    result.interest = int(round(best_score * result.appeal * duration))
    result.extra.update(
        {
            "distance_au": round(pos.distance_au, 3),
            "sun_distance_au": round(pos.sun_distance_au, 3),
            "elongation": round(pos.elongation),
            "ra": round(pos.ra_j2000_hours, 4),
            "dec": round(pos.dec_j2000, 3),
            "estimated_magnitude": True,
        }
    )
    if is_comet:
        result.reasons.append({"key": "comet_estimate"})
    if abs(elements.epoch - (to_astro(ephem.midnight).tt + 2451545.0)) > 365:
        result.extra["old_orbit"] = True
    return result
