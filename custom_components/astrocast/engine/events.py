"""Astronomical events computed locally for an observing site."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
from typing import Any

import astronomy
import numpy as np

from .ephemeris import BODIES, KM_PER_AU, RADIUS_KM, Location, horizontal
from .meteors import SHOWERS, hourly_rate, limiting_magnitude, peak_time
from .smallbodies import OrbitalElements, position
from .timeutil import from_astro, to_astro, utc

# Bright stars and clusters close to the ecliptic that the Moon can approach
# or occult (J2000 coordinates: RA hours, Dec degrees, magnitude).
ECLIPTIC_STARS: dict[str, tuple[float, float, float]] = {
    "aldebaran": (4.598677, 16.509301, 0.87),
    "regulus": (10.139532, 11.967207, 1.36),
    "spica": (13.419883, -11.161319, 0.97),
    "antares": (16.490128, -26.432003, 1.06),
    "pleiades": (3.783, 24.117, 1.6),
    "beehive": (8.670, 19.983, 3.7),
}

BRIGHT_PLANETS = ("mercury", "venus", "mars", "jupiter", "saturn")
OUTER_PLANETS = ("mars", "jupiter", "saturn", "uranus", "neptune")
QUARTER_KEYS = ("new_moon", "first_quarter", "full_moon", "last_quarter")
SUPERMOON_KM = 360_000.0


@dataclass(slots=True)
class AstroEvent:
    """An astronomical event."""

    id: str
    type: str
    start: datetime
    end: datetime | None = None
    importance: int = 1  # 1 = minor, 2 = notable, 3 = major
    visible: bool | None = None
    best_time: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)


# --- generic geometry helpers ------------------------------------------------


def _unit(vec: astronomy.Vector) -> np.ndarray:
    arr = np.array([vec.x, vec.y, vec.z], dtype=float)
    return arr / np.linalg.norm(arr)


def _star_unit(ra_hours: float, dec: float) -> np.ndarray:
    ra = math.radians(ra_hours * 15.0)
    de = math.radians(dec)
    return np.array([math.cos(de) * math.cos(ra), math.cos(de) * math.sin(ra), math.sin(de)])


def geocentric_unit(target: str, time: astronomy.Time) -> np.ndarray:
    """Geocentric J2000 unit vector of a body or ecliptic star."""
    if target == "moon":
        return _unit(astronomy.GeoMoon(time))
    if target in ECLIPTIC_STARS:
        ra, dec, _ = ECLIPTIC_STARS[target]
        return _star_unit(ra, dec)
    return _unit(astronomy.GeoVector(BODIES[target], time, True))


def target_horizontal(
    target: str, time: astronomy.Time, observer: astronomy.Observer
) -> tuple[float, float]:
    """Topocentric refracted altitude/azimuth of a body or ecliptic star."""
    if target in ECLIPTIC_STARS:
        ra, dec, _ = ECLIPTIC_STARS[target]
        vec = astronomy.Vector(*_star_unit(ra, dec), time)
        date_vec = astronomy.RotateVector(astronomy.Rotation_EQJ_EQD(time), vec)
        sph = astronomy.EquatorFromVector(date_vec)
        hor = astronomy.Horizon(time, observer, sph.ra, sph.dec, astronomy.Refraction.Normal)
        return hor.altitude, hor.azimuth
    return horizontal(BODIES[target], time, observer)


def _separation(u1: np.ndarray, u2: np.ndarray) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u1, u2))))))


def _golden_minimum(
    func: Callable[[float], float], lo: float, hi: float, tol: float = 1.0 / 1440.0
) -> tuple[float, float]:
    """Golden-section search of a unimodal function on [lo, hi] (days)."""
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = hi - ratio * (hi - lo)
    d = lo + ratio * (hi - lo)
    fc, fd = func(c), func(d)
    while hi - lo > tol:
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - ratio * (hi - lo)
            fc = func(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + ratio * (hi - lo)
            fd = func(d)
    mid = (lo + hi) / 2.0
    return mid, func(mid)


def best_viewing(
    targets: Iterable[str],
    center: datetime,
    observer: astronomy.Observer,
    span_hours: float = 14.0,
    sun_limit: float = -6.0,
    min_alt: float = 5.0,
) -> tuple[datetime | None, float]:
    """Find when all ``targets`` are highest in a dark-enough sky around ``center``.

    Returns (best time, lowest altitude among targets at that time).
    """
    targets = tuple(targets)
    best: tuple[datetime | None, float] = (None, -90.0)
    steps = int(span_hours * 3)
    for k in range(-steps, steps + 1):
        moment = center + timedelta(minutes=20 * k)
        time = to_astro(moment)
        if horizontal(astronomy.Body.Sun, time, observer)[0] > sun_limit:
            continue
        low = min(target_horizontal(t, time, observer)[0] for t in targets)
        if low >= min_alt and low > best[1]:
            best = (moment, low)
    return best


# --- event finders -------------------------------------------------------------


def moon_phases(start: datetime, end: datetime) -> list[AstroEvent]:
    """Principal lunar phases, flagging supermoons."""
    events: list[AstroEvent] = []
    quarter = astronomy.SearchMoonQuarter(to_astro(start))
    while True:
        moment = from_astro(quarter.time)
        if moment > end:
            break
        key = QUARTER_KEYS[quarter.quarter]
        distance = astronomy.GeoMoon(quarter.time).Length() * KM_PER_AU
        data: dict[str, Any] = {"phase": key, "distance_km": round(distance)}
        importance = 1
        if key == "full_moon" and distance < SUPERMOON_KM:
            data["supermoon"] = True
            importance = 2
        events.append(
            AstroEvent(
                id=f"{key}-{moment:%Y%m%d}",
                type="moon_phase",
                start=moment,
                importance=importance,
                data=data,
            )
        )
        quarter = astronomy.NextMoonQuarter(quarter)
    return events


def lunar_eclipses(
    start: datetime, end: datetime, observer: astronomy.Observer
) -> list[AstroEvent]:
    """Lunar eclipses with local visibility."""
    events: list[AstroEvent] = []
    info = astronomy.SearchLunarEclipse(to_astro(start))
    while from_astro(info.peak) <= end:
        peak = from_astro(info.peak)
        kind = info.kind.name.lower()
        begin = peak - timedelta(minutes=info.sd_penum)
        finish = peak + timedelta(minutes=info.sd_penum)
        samples = [begin + (finish - begin) * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
        moon_alts = [
            horizontal(astronomy.Body.Moon, to_astro(s), observer)[0] for s in samples
        ]
        visible = max(moon_alts) > 0.0
        peak_alt = horizontal(astronomy.Body.Moon, info.peak, observer)[0]
        data: dict[str, Any] = {
            "kind": kind,
            "obscuration": round(info.obscuration, 3),
            "peak_altitude": round(peak_alt, 1),
            "partial_begin": None,
            "partial_end": None,
            "total_begin": None,
            "total_end": None,
        }
        if info.sd_partial > 0:
            data["partial_begin"] = peak - timedelta(minutes=info.sd_partial)
            data["partial_end"] = peak + timedelta(minutes=info.sd_partial)
        if info.sd_total > 0:
            data["total_begin"] = peak - timedelta(minutes=info.sd_total)
            data["total_end"] = peak + timedelta(minutes=info.sd_total)
        if kind == "penumbral" or not visible:
            importance = 1
        elif peak_alt < 0.0 or info.obscuration < 0.2:
            importance = 2
        else:
            importance = 3
        events.append(
            AstroEvent(
                id=f"lunar_eclipse-{peak:%Y%m%d}",
                type="lunar_eclipse",
                start=begin,
                end=finish,
                importance=importance,
                visible=visible,
                best_time=peak,
                data=data,
            )
        )
        info = astronomy.NextLunarEclipse(info.peak)
    return events


def solar_eclipses(
    start: datetime, end: datetime, observer: astronomy.Observer
) -> list[AstroEvent]:
    """Solar eclipses seen from the site (partial phases included)."""
    events: list[AstroEvent] = []
    info = astronomy.SearchLocalSolarEclipse(to_astro(start), observer)
    while from_astro(info.peak.time) <= end:
        peak = from_astro(info.peak.time)
        alts = [info.partial_begin.altitude, info.peak.altitude, info.partial_end.altitude]
        visible = max(alts) > 0.0
        kind = info.kind.name.lower()
        if visible:
            importance = 3 if kind in ("total", "annular") or info.obscuration > 0.5 else 2
            if info.peak.altitude < 5.0:
                importance = 2
            data: dict[str, Any] = {
                "kind": kind,
                "obscuration": round(info.obscuration, 3),
                "peak_altitude": round(info.peak.altitude, 1),
            }
            if info.total_begin is not None:
                data["total_begin"] = from_astro(info.total_begin.time)
                data["total_end"] = from_astro(info.total_end.time)
            events.append(
                AstroEvent(
                    id=f"solar_eclipse-{peak:%Y%m%d}",
                    type="solar_eclipse",
                    start=from_astro(info.partial_begin.time),
                    end=from_astro(info.partial_end.time),
                    importance=importance,
                    visible=True,
                    best_time=peak,
                    data=data,
                )
            )
        info = astronomy.NextLocalSolarEclipse(info.peak.time, observer)
    return events


def oppositions(
    start: datetime, end: datetime, observer: astronomy.Observer
) -> list[AstroEvent]:
    """Oppositions of the superior planets.

    astronomy-engine measures the heliocentric longitude of the planet relative
    to the Earth: 0° is an opposition for a superior planet.
    """
    events: list[AstroEvent] = []
    for key in OUTER_PLANETS:
        body = BODIES[key]
        time = astronomy.SearchRelativeLongitude(body, 0.0, to_astro(start))
        moment = from_astro(time)
        if moment > end:
            continue
        illum = astronomy.Illumination(body, time)
        equ = astronomy.Equator(body, time, observer, False, True)
        importance = 3 if key in ("mars", "jupiter", "saturn") else 2
        events.append(
            AstroEvent(
                id=f"opposition-{key}-{moment:%Y%m%d}",
                type="opposition",
                start=moment,
                importance=importance,
                visible=True,
                data={
                    "body": key,
                    "mag": round(illum.mag, 1),
                    "distance_au": round(illum.geo_dist, 3),
                    "constellation": astronomy.Constellation(equ.ra, equ.dec).symbol,
                },
            )
        )
    return events


def elongations(
    start: datetime, end: datetime, observer: astronomy.Observer
) -> list[AstroEvent]:
    """Greatest elongations of Mercury and Venus (best inner-planet views)."""
    events: list[AstroEvent] = []
    for key in ("mercury", "venus"):
        body = BODIES[key]
        cursor = to_astro(start)
        while True:
            found = astronomy.SearchMaxElongation(body, cursor)
            if found is None:
                break
            moment = from_astro(found.time)
            if moment > end:
                break
            side = "evening" if found.visibility == astronomy.Visibility.Evening else "morning"
            best_time, best_alt = best_viewing((key,), moment, observer, span_hours=14, sun_limit=-6)
            illum = astronomy.Illumination(body, found.time)
            events.append(
                AstroEvent(
                    id=f"elongation-{key}-{moment:%Y%m%d}",
                    type="greatest_elongation",
                    start=moment,
                    importance=2,
                    visible=best_time is not None,
                    best_time=best_time,
                    data={
                        "body": key,
                        "elongation": round(found.elongation, 1),
                        "side": side,
                        "mag": round(illum.mag, 1),
                        "altitude": round(best_alt, 1) if best_time else None,
                    },
                )
            )
            cursor = found.time.AddDays(10)
    return events


def seasons(start: datetime, end: datetime) -> list[AstroEvent]:
    """Equinoxes and solstices."""
    events: list[AstroEvent] = []
    for year in range(start.year, end.year + 1):
        info = astronomy.Seasons(year)
        for key, time in (
            ("march_equinox", info.mar_equinox),
            ("june_solstice", info.jun_solstice),
            ("september_equinox", info.sep_equinox),
            ("december_solstice", info.dec_solstice),
        ):
            moment = from_astro(time)
            if start <= moment <= end:
                events.append(
                    AstroEvent(
                        id=f"{key}-{year}",
                        type="season",
                        start=moment,
                        importance=1,
                        data={"season": key},
                    )
                )
    return events


def meteor_showers(
    start: datetime,
    end: datetime,
    location: Location,
    sqm: float,
) -> list[AstroEvent]:
    """Meteor shower maxima with the expected local rate on the best night."""
    observer = location.observer
    events: list[AstroEvent] = []
    for year in range(start.year, end.year + 1):
        for shower in SHOWERS:
            peak = peak_time(shower, year)
            if peak is None or not (start - timedelta(days=1) <= peak <= end):
                continue
            best: tuple[float, datetime | None, float, float] = (0.0, None, 0.0, 0.0)
            # Scan the 36 hours centred on the peak for the best dark hour.
            for k in range(-36, 37):
                moment = peak + timedelta(minutes=30 * k)
                time = to_astro(moment)
                if horizontal(astronomy.Body.Sun, time, observer)[0] > -12.0:
                    continue
                vec = astronomy.Vector(*_star_unit(shower.radiant_ra / 15.0, shower.radiant_dec), time)
                sph = astronomy.EquatorFromVector(
                    astronomy.RotateVector(astronomy.Rotation_EQJ_EQD(time), vec)
                )
                rad_alt = astronomy.Horizon(
                    time, observer, sph.ra, sph.dec, astronomy.Refraction.Normal
                ).altitude
                moon_alt = horizontal(astronomy.Body.Moon, time, observer)[0]
                sky = sqm
                if moon_alt > 0:
                    illum = astronomy.Illumination(astronomy.Body.Moon, time)
                    # Moonlight brightens the whole sky; use the zenith value.
                    from .skyglow import moon_brightening_mag  # noqa: PLC0415

                    sky = sqm - float(
                        moon_brightening_mag(sqm, illum.phase_angle, 90.0 - moon_alt, moon_alt, 90.0)
                    )
                lm = limiting_magnitude(sky)
                rate = hourly_rate(shower, rad_alt, lm)
                # Prefer times close to the peak (activity profile ~1 day wide).
                weight = rate * math.exp(-((k / 2.0) / 24.0) ** 2)
                if weight > best[0]:
                    best = (weight, moment, rate, rad_alt)
            illum_frac = astronomy.Illumination(astronomy.Body.Moon, to_astro(peak)).phase_fraction
            if shower.zhr >= 50:
                importance = 3 if best[2] >= 10 else 2
            elif shower.zhr >= 15:
                importance = 2 if best[2] >= 5 else 1
            else:
                importance = 1
            events.append(
                AstroEvent(
                    id=f"meteor-{shower.code}-{year}",
                    type="meteor_shower",
                    start=peak,
                    importance=importance,
                    visible=best[1] is not None and best[2] >= 1.0,
                    best_time=best[1],
                    data={
                        "code": shower.code,
                        "zhr": shower.zhr,
                        "rate": round(best[2]) if best[1] else 0,
                        "radiant_altitude": round(best[3], 1) if best[1] else None,
                        "moon_illumination": round(illum_frac * 100),
                        "velocity": shower.velocity,
                        "variable": shower.variable,
                        "active_from": f"{shower.start[0]:02d}-{shower.start[1]:02d}",
                        "active_to": f"{shower.end[0]:02d}-{shower.end[1]:02d}",
                    },
                )
            )
    return events


def _pair_minima(
    first: str,
    seconds: Iterable[str],
    start: datetime,
    end: datetime,
    step_hours: float,
    threshold: float,
) -> list[tuple[str, datetime, float]]:
    """Times of minimum geocentric separation below ``threshold`` (deg)."""
    seconds = tuple(seconds)
    n = int((end - start).total_seconds() / 3600.0 / step_hours) + 1
    times = [to_astro(start + timedelta(hours=step_hours * i)) for i in range(n)]
    first_u = [geocentric_unit(first, t) for t in times]
    found: list[tuple[str, datetime, float]] = []
    for other in seconds:
        seps = np.array([_separation(first_u[i], geocentric_unit(other, t)) for i, t in enumerate(times)])
        for i in range(1, n - 1):
            if seps[i] <= seps[i - 1] and seps[i] < seps[i + 1] and seps[i] < threshold + 2.0:
                t0 = times[i].ut - step_hours / 24.0
                t1 = times[i].ut + step_hours / 24.0

                def func(ut: float, other: str = other) -> float:
                    time = astronomy.Time(ut)
                    return _separation(geocentric_unit(first, time), geocentric_unit(other, time))

                ut, sep = _golden_minimum(func, t0, t1)
                if sep < threshold:
                    found.append((other, from_astro(astronomy.Time(ut)), sep))
    return found


def _occultation(
    target: str, around: datetime, observer: astronomy.Observer
) -> tuple[datetime, float, bool] | None:
    """Check whether the Moon occults ``target`` from the site near ``around``.

    Returns (time of minimum topocentric separation, separation in arcmin,
    occultation flag) or None.
    """

    def topo_sep(ut: float) -> float:
        time = astronomy.Time(ut)
        moon = astronomy.Equator(astronomy.Body.Moon, time, observer, False, True)
        if target in ECLIPTIC_STARS:
            ra, dec, _ = ECLIPTIC_STARS[target]
        else:
            equ = astronomy.Equator(BODIES[target], time, observer, False, True)
            ra, dec = equ.ra, equ.dec
        return _separation(_star_unit(moon.ra, moon.dec), _star_unit(ra, dec))

    center = to_astro(around).ut
    # Coarse scan (10 min) over ±5 h then refine.
    grid = [center + k / 144.0 for k in range(-30, 31)]
    values = [topo_sep(ut) for ut in grid]
    idx = int(np.argmin(values))
    lo = grid[max(0, idx - 1)]
    hi = grid[min(len(grid) - 1, idx + 1)]
    ut, sep = _golden_minimum(topo_sep, lo, hi, tol=1.0 / 8640.0)
    time = astronomy.Time(ut)
    moon_dist_km = astronomy.Equator(astronomy.Body.Moon, time, observer, False, True).dist * KM_PER_AU
    moon_radius = math.degrees(math.asin(RADIUS_KM["moon"] / moon_dist_km))
    target_radius = 0.0
    if target in RADIUS_KM:
        dist = astronomy.Equator(BODIES[target], time, observer, False, True).dist * KM_PER_AU
        target_radius = math.degrees(math.atan(RADIUS_KM[target] / dist))
    if target == "pleiades":
        target_radius = 0.5  # the cluster's bright core
    return from_astro(time), sep * 60.0, sep < moon_radius + target_radius


def conjunctions(
    start: datetime, end_moon: datetime, end_planets: datetime, observer: astronomy.Observer
) -> list[AstroEvent]:
    """Close approaches: Moon–planet, Moon–bright star/cluster, planet–planet."""
    events: list[AstroEvent] = []
    moon_targets = (*BRIGHT_PLANETS, "uranus", "neptune", *ECLIPTIC_STARS)
    for target, moment, sep in _pair_minima("moon", moon_targets, start, end_moon, 3.0, 4.0):
        visible_time, alt = best_viewing(("moon", target), moment, observer, span_hours=12)
        data: dict[str, Any] = {
            "bodies": ["moon", target],
            "separation": round(sep, 2),
            "altitude": round(alt, 1) if visible_time else None,
        }
        importance = 1
        event_type = "conjunction"
        if sep < 1.5:
            occ = _occultation(target, moment, observer)
            if occ is not None and occ[2]:
                occ_time = occ[0]
                moon_alt = target_horizontal("moon", to_astro(occ_time), observer)[0]
                if moon_alt > 0:
                    event_type = "occultation"
                    moment = occ_time
                    data["altitude"] = round(moon_alt, 1)
                    sun_alt = horizontal(astronomy.Body.Sun, to_astro(occ_time), observer)[0]
                    data["daylight"] = sun_alt > -6.0
                    visible_time = occ_time
                    importance = 3
        if event_type == "conjunction":
            if target in ("uranus", "neptune", "beehive") and sep > 1.0:
                continue
            if sep < 1.0 and visible_time:
                importance = 2
            elif sep < 2.5 and visible_time and target in ("venus", "jupiter", "pleiades"):
                importance = 2
        events.append(
            AstroEvent(
                id=f"{event_type}-moon-{target}-{moment:%Y%m%d}",
                type=event_type,
                start=moment,
                importance=importance,
                visible=visible_time is not None,
                best_time=visible_time,
                data=data,
            )
        )

    planets = (*BRIGHT_PLANETS, "uranus", "neptune")
    for i, first in enumerate(planets):
        others = planets[i + 1 :]
        for target, moment, sep in _pair_minima(first, others, start, end_planets, 24.0, 3.0):
            if (first in ("uranus", "neptune") or target in ("uranus", "neptune")) and sep > 1.0:
                continue
            sun_sep = min(
                _separation(geocentric_unit(b, to_astro(moment)), geocentric_unit("sun", to_astro(moment)))
                for b in (first, target)
            )
            if sun_sep < 12.0:
                continue  # lost in the Sun's glare
            visible_time, alt = best_viewing((first, target), moment, observer, span_hours=14)
            importance = 3 if sep < 1.0 and visible_time else 2 if visible_time else 1
            events.append(
                AstroEvent(
                    id=f"conjunction-{first}-{target}-{moment:%Y%m%d}",
                    type="conjunction",
                    start=moment,
                    importance=importance,
                    visible=visible_time is not None,
                    best_time=visible_time,
                    data={
                        "bodies": [first, target],
                        "separation": round(sep, 2),
                        "altitude": round(alt, 1) if visible_time else None,
                    },
                )
            )
    return events


def comet_events(
    comets: Iterable[OrbitalElements],
    start: datetime,
    end: datetime,
    observer: astronomy.Observer,
    max_mag: float = 10.0,
) -> list[AstroEvent]:
    """Perihelion passages of comets expected to become bright."""
    events: list[AstroEvent] = []
    for comet in comets:
        perihelion = from_astro(astronomy.Time(comet.tp - 2451545.0))
        if not start - timedelta(days=30) <= perihelion <= end:
            continue
        # Estimated peak brightness over ±60 days around perihelion.
        mags = []
        for k in range(-60, 61, 5):
            moment = perihelion + timedelta(days=k)
            pos = position(comet, moment, None)
            if pos.mag is not None:
                mags.append((pos.mag, moment, pos.elongation))
        if not mags:
            continue
        mag, when, elong = min(mags)
        if mag > max_mag:
            continue
        events.append(
            AstroEvent(
                id=f"comet-{comet.id}-{perihelion:%Y%m%d}",
                type="comet",
                start=perihelion,
                importance=3 if mag < 6 else 2,
                visible=None,
                best_time=when,
                data={
                    "name": comet.name,
                    "object_id": comet.id,
                    "peak_mag": round(mag, 1),
                    "peak_time": when,
                    "elongation": round(elong),
                    "q": round(comet.q, 3),
                },
            )
        )
    del observer
    return events


def compute_events(
    location: Location,
    now: datetime,
    sqm: float,
    comets: Iterable[OrbitalElements] = (),
    horizon_days: int = 365,
    near_days: int = 60,
) -> list[AstroEvent]:
    """Compute every event between ``now`` and the horizon, sorted by date."""
    now = utc(now)
    observer = location.observer
    end = now + timedelta(days=horizon_days)
    near = now + timedelta(days=near_days)
    start = now - timedelta(days=1)
    events: list[AstroEvent] = []
    events += moon_phases(start, now + timedelta(days=120))
    events += lunar_eclipses(start, now + timedelta(days=3 * 365), observer)
    events += solar_eclipses(start, now + timedelta(days=3 * 365), observer)
    events += oppositions(start, end, observer)
    events += elongations(start, end, observer)
    events += seasons(start, end)
    events += meteor_showers(start, end, location, sqm)
    events += conjunctions(start, near, now + timedelta(days=180), observer)
    events += comet_events(comets, start, end, observer)
    events.sort(key=lambda e: e.start)
    return events
