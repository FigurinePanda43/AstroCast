"""Sun, Moon and planet ephemerides organised per night.

All positions come from astronomy-engine (Don Cross, MIT licence), whose
accuracy is better than one arcminute against JPL DE ephemerides. Topocentric
coordinates include parallax, aberration, nutation and standard refraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
import math

import astronomy
import numpy as np

from .skyglow import refraction_deg
from .timeutil import J2000_UNIX, from_astro, night_window, to_astro

STEP_MINUTES = 15
SAMPLES_PER_NIGHT = 24 * 60 // STEP_MINUTES

PLANETS: tuple[str, ...] = (
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
)

BODIES: dict[str, astronomy.Body] = {
    "sun": astronomy.Body.Sun,
    "moon": astronomy.Body.Moon,
    "mercury": astronomy.Body.Mercury,
    "venus": astronomy.Body.Venus,
    "mars": astronomy.Body.Mars,
    "jupiter": astronomy.Body.Jupiter,
    "saturn": astronomy.Body.Saturn,
    "uranus": astronomy.Body.Uranus,
    "neptune": astronomy.Body.Neptune,
}

# Equatorial radii in km (IAU WGCCRE).
RADIUS_KM: dict[str, float] = {
    "moon": 1737.4,
    "mercury": 2439.7,
    "venus": 6051.8,
    "mars": 3396.2,
    "jupiter": 71492.0,
    "saturn": 60268.0,
    "uranus": 25559.0,
    "neptune": 24764.0,
}

KM_PER_AU = 149_597_870.7
ARCSEC_PER_RAD = 206_264.806

# Sun altitudes defining twilight boundaries.
CIVIL = -6.0
NAUTICAL = -12.0
ASTRONOMICAL = -18.0


@dataclass(slots=True, frozen=True)
class Location:
    """Geographic position of an observing site."""

    latitude: float
    longitude: float
    elevation: float = 0.0

    @property
    def observer(self) -> astronomy.Observer:
        """Return the astronomy-engine observer."""
        return astronomy.Observer(self.latitude, self.longitude, self.elevation)


@dataclass(slots=True)
class BodyTrack:
    """Position of a solar-system body across one night."""

    key: str
    alt: np.ndarray
    az: np.ndarray
    ra_hours: float
    dec: float
    distance_au: float
    diameter_arcsec: float
    constellation: str
    mag: float | None = None
    phase_fraction: float | None = None
    elongation: float | None = None
    ring_tilt: float | None = None
    rise: datetime | None = None
    set: datetime | None = None
    transit: datetime | None = None
    transit_alt: float | None = None


@dataclass(slots=True)
class NightEphemeris:
    """Everything that depends only on astronomy for one night at one site."""

    night: date
    start: datetime
    end: datetime
    times: list[datetime]
    unix: np.ndarray
    sun_alt: np.ndarray
    moon_alt: np.ndarray
    moon_az: np.ndarray
    moon_illum: np.ndarray
    moon_phase_angle: np.ndarray
    lst_deg: np.ndarray
    precession: np.ndarray
    sunset: datetime | None
    sunrise: datetime | None
    civil_dusk: datetime | None
    civil_dawn: datetime | None
    nautical_dusk: datetime | None
    nautical_dawn: datetime | None
    astro_dusk: datetime | None
    astro_dawn: datetime | None
    moonrise: datetime | None
    moonset: datetime | None
    moon_phase: float
    moon_illumination: float
    moon: BodyTrack
    planets: dict[str, BodyTrack] = field(default_factory=dict)

    @property
    def midnight(self) -> datetime:
        """Local mean solar midnight."""
        return self.start + timedelta(hours=12)

    def mask_dark(self, sun_limit: float = ASTRONOMICAL) -> np.ndarray:
        """Boolean mask of samples with the Sun below ``sun_limit``."""
        return self.sun_alt < sun_limit

    def hours(self, mask: np.ndarray) -> float:
        """Total duration (h) of the samples selected by ``mask``."""
        return float(np.count_nonzero(mask)) * STEP_MINUTES / 60.0

    @property
    def dark_hours(self) -> float:
        """Duration of astronomical night."""
        return self.hours(self.mask_dark())

    @property
    def moonless_dark_hours(self) -> float:
        """Duration of astronomical night with the Moon below the horizon."""
        return self.hours(self.mask_dark() & (self.moon_alt < -0.5))

    def index_of(self, moment: datetime) -> int | None:
        """Return the sample index for ``moment`` or None if outside the night."""
        offset = (moment - self.start).total_seconds() / (STEP_MINUTES * 60)
        idx = int(round(offset))
        if 0 <= idx < len(self.times):
            return idx
        return None


def moon_phase_name(phase_deg: float) -> str:
    """Name of the lunar phase from the ecliptic phase angle (0 = new moon).

    Principal phases are reported for ±6° (about half a day) around the exact
    instant, consistent with Home Assistant's own ``moon`` integration.
    """
    p = phase_deg % 360.0
    if p < 6.1 or p > 353.9:
        return "new_moon"
    if p < 83.9:
        return "waxing_crescent"
    if p <= 96.1:
        return "first_quarter"
    if p < 173.9:
        return "waxing_gibbous"
    if p <= 186.1:
        return "full_moon"
    if p < 263.9:
        return "waning_gibbous"
    if p <= 276.1:
        return "last_quarter"
    return "waning_crescent"


def horizontal(
    body: astronomy.Body, time: astronomy.Time, observer: astronomy.Observer
) -> tuple[float, float]:
    """Topocentric refracted altitude/azimuth of a body (degrees)."""
    equ = astronomy.Equator(body, time, observer, True, True)
    hor = astronomy.Horizon(time, observer, equ.ra, equ.dec, astronomy.Refraction.Normal)
    return hor.altitude, hor.azimuth


def precession_matrix(time: astronomy.Time) -> np.ndarray:
    """Rotation matrix converting J2000 (EQJ) vectors to true equator of date."""
    return np.array(astronomy.Rotation_EQJ_EQD(time).rot, dtype=float).T


def local_sidereal_deg(time: astronomy.Time, longitude: float) -> float:
    """Local apparent sidereal time in degrees."""
    return (astronomy.SiderealTime(time) * 15.0 + longitude) % 360.0


SIDEREAL_RATE = 360.98564736629  # degrees of sidereal time per UT day
SUN_HORIZON = -0.8333  # refraction + solar semi-diameter (geometric altitude)
PLANET_HORIZON = -0.5667  # refraction only
MOON_HORIZON = -0.8333  # refraction + mean lunar semi-diameter (topocentric)

# Spacing of the exact ephemeris evaluations that are interpolated in between.
ANCHOR_HOURS = {"sun": 4.0, "moon": 1.0}
DEFAULT_ANCHOR_HOURS = 12.0


def equatorial_track(
    body: astronomy.Body,
    observer: astronomy.Observer,
    unix: np.ndarray,
    anchor_hours: float,
) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """Topocentric RA/Dec of date (deg) interpolated from exact anchor points.

    Bodies move smoothly: evaluating astronomy-engine every ``anchor_hours`` and
    interpolating keeps the error far below 0.05° while being an order of
    magnitude faster (important on small ARM boards).
    """
    t0, t1 = float(unix[0]), float(unix[-1])
    count = max(2, int(math.ceil((t1 - t0) / (anchor_hours * 3600.0))) + 1)
    anchors = np.linspace(t0, t1, count)
    ras: list[float] = []
    decs: list[float] = []
    dists: list[float] = []
    for ts in anchors:
        equ = astronomy.Equator(
            body, astronomy.Time((ts - J2000_UNIX) / 86400.0), observer, True, True
        )
        ras.append(equ.ra * 15.0)
        decs.append(equ.dec)
        dists.append(equ.dist)
    ra_unwrapped = np.degrees(np.unwrap(np.radians(ras)))
    ra = np.interp(unix, anchors, ra_unwrapped) % 360.0
    dec = np.interp(unix, anchors, decs)
    return ra, dec, dists


def altaz_series(
    ra_deg: np.ndarray, dec_deg: np.ndarray, lst_deg: np.ndarray, latitude: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Geometric altitude, apparent (refracted) altitude and azimuth (deg)."""
    phi = math.radians(latitude)
    ha = np.radians(lst_deg - ra_deg)
    dec = np.radians(dec_deg)
    sin_alt = math.sin(phi) * np.sin(dec) + math.cos(phi) * np.cos(dec) * np.cos(ha)
    geometric = np.degrees(np.arcsin(np.clip(sin_alt, -1.0, 1.0)))
    az = (
        np.degrees(
            np.arctan2(
                -np.sin(ha) * np.cos(dec),
                math.cos(phi) * np.sin(dec) - math.sin(phi) * np.cos(dec) * np.cos(ha),
            )
        )
        % 360.0
    )
    return geometric, geometric + refraction_deg(geometric), az


def crossings(unix: np.ndarray, values: np.ndarray, level: float) -> list[tuple[datetime, int]]:
    """Times where ``values`` crosses ``level`` (+1 rising, -1 setting)."""
    diff = values - level
    result: list[tuple[datetime, int]] = []
    for i in np.flatnonzero(np.sign(diff[:-1]) != np.sign(diff[1:])):
        d0, d1 = diff[i], diff[i + 1]
        if d0 == d1:
            continue
        frac = d0 / (d0 - d1)
        ts = unix[i] + frac * (unix[i + 1] - unix[i])
        result.append((datetime.fromtimestamp(float(ts), tz=UTC), 1 if d1 > d0 else -1))
    return result


def _first(
    events: list[tuple[datetime, int]], direction: int, after: datetime | None = None
) -> datetime | None:
    for moment, sense in events:
        if sense == direction and (after is None or moment > after):
            return moment
    return None


def _transit(unix: np.ndarray, lst: np.ndarray, ra: np.ndarray) -> datetime | None:
    """Upper culmination: hour angle crossing zero from negative to positive."""
    ha = (lst - ra + 180.0) % 360.0 - 180.0
    for i in range(len(ha) - 1):
        if ha[i] < 0 <= ha[i + 1] and ha[i + 1] - ha[i] < 90:
            frac = -ha[i] / (ha[i + 1] - ha[i])
            return datetime.fromtimestamp(float(unix[i] + frac * (unix[i + 1] - unix[i])), tz=UTC)
    return None


def _body_info(key: str, observer: astronomy.Observer, midnight: astronomy.Time) -> BodyTrack:
    """Physical data of a body at local midnight (brightness, size, elongation)."""
    body = BODIES[key]
    equ = astronomy.Equator(body, midnight, observer, True, True)
    equ_j2000 = astronomy.Equator(body, midnight, observer, False, True)
    constellation = astronomy.Constellation(equ_j2000.ra, equ_j2000.dec).symbol
    diameter = 2.0 * math.atan(RADIUS_KM[key] / (equ.dist * KM_PER_AU)) * ARCSEC_PER_RAD
    track = BodyTrack(
        key=key,
        alt=np.empty(0),
        az=np.empty(0),
        ra_hours=equ.ra,
        dec=equ.dec,
        distance_au=equ.dist,
        diameter_arcsec=diameter,
        constellation=constellation,
    )
    illum = astronomy.Illumination(body, midnight)
    track.mag = illum.mag
    track.phase_fraction = illum.phase_fraction
    if key == "saturn":
        track.ring_tilt = illum.ring_tilt
    if key != "moon":
        track.elongation = astronomy.Elongation(body, midnight).elongation
        # Positive when the body is east of the Sun (evening sky).
        if astronomy.PairLongitude(body, astronomy.Body.Sun, midnight) > 180.0:
            track.elongation = -track.elongation
    return track


def _fill_track(
    track: BodyTrack,
    observer: astronomy.Observer,
    unix: np.ndarray,
    lst: np.ndarray,
    latitude: float,
    horizon: float,
) -> None:
    ra, dec, _ = equatorial_track(
        BODIES[track.key], observer, unix, ANCHOR_HOURS.get(track.key, DEFAULT_ANCHOR_HOURS)
    )
    geometric, apparent, az = altaz_series(ra, dec, lst, latitude)
    track.alt = apparent
    track.az = az
    events = crossings(unix, geometric, horizon)
    track.rise = _first(events, 1)
    track.set = _first(events, -1)
    track.transit = _transit(unix, lst, ra)
    if track.transit is not None:
        track.transit_alt = round(
            90.0 - abs(latitude - float(np.interp(track.transit.timestamp(), unix, dec))), 2
        )


def compute_night(location: Location, night: date, with_planets: bool = True) -> NightEphemeris:
    """Compute the ephemeris of a night (local noon to local noon)."""
    observer = location.observer
    start, end = night_window(night, location.longitude)
    # Align the sampling grid on whole quarter hours (nicer times for users).
    start = start.replace(second=0, microsecond=0) - timedelta(minutes=start.minute % STEP_MINUTES)
    end = start + timedelta(days=1)
    times = [start + timedelta(minutes=STEP_MINUTES * i) for i in range(SAMPLES_PER_NIGHT)]
    unix = np.array([t.timestamp() for t in times])
    n = len(times)
    astart = to_astro(start)
    midnight = to_astro(start + timedelta(hours=12))
    lst = (
        local_sidereal_deg(astart, location.longitude) + SIDEREAL_RATE * (unix - unix[0]) / 86400.0
    ) % 360.0

    sun_ra, sun_dec, _ = equatorial_track(astronomy.Body.Sun, observer, unix, ANCHOR_HOURS["sun"])
    sun_geo, _sun_app, _ = altaz_series(sun_ra, sun_dec, lst, location.latitude)

    moon = _body_info("moon", observer, midnight)
    _fill_track(moon, observer, unix, lst, location.latitude, MOON_HORIZON)

    # Lunar illumination changes slowly: evaluate every 3 hours and interpolate.
    coarse = [*range(0, n, 12), n - 1]
    coarse_illum = []
    coarse_pa = []
    for idx in coarse:
        illum = astronomy.Illumination(astronomy.Body.Moon, to_astro(times[idx]))
        coarse_illum.append(illum.phase_fraction)
        coarse_pa.append(illum.phase_angle)

    sun_events = crossings(unix, sun_geo, SUN_HORIZON)
    sunset = _first(sun_events, -1)
    ephem = NightEphemeris(
        night=night,
        start=start,
        end=end,
        times=times,
        unix=unix,
        sun_alt=sun_geo,
        moon_alt=moon.alt,
        moon_az=moon.az,
        moon_illum=np.interp(np.arange(n), coarse, coarse_illum),
        moon_phase_angle=np.interp(np.arange(n), coarse, coarse_pa),
        lst_deg=lst,
        precession=precession_matrix(midnight),
        sunset=sunset,
        sunrise=_first(sun_events, 1, sunset),
        civil_dusk=None,
        civil_dawn=None,
        nautical_dusk=None,
        nautical_dawn=None,
        astro_dusk=None,
        astro_dawn=None,
        moonrise=moon.rise,
        moonset=moon.set,
        moon_phase=astronomy.MoonPhase(midnight),
        moon_illumination=astronomy.Illumination(astronomy.Body.Moon, midnight).phase_fraction,
        moon=moon,
    )
    # Morning events are paired with the evening event of the same night.
    for dusk_attr, dawn_attr, limit in (
        ("civil_dusk", "civil_dawn", CIVIL),
        ("nautical_dusk", "nautical_dawn", NAUTICAL),
        ("astro_dusk", "astro_dawn", ASTRONOMICAL),
    ):
        events = crossings(unix, sun_geo, limit)
        dusk = _first(events, -1)
        setattr(ephem, dusk_attr, dusk)
        setattr(ephem, dawn_attr, _first(events, 1, dusk))

    if with_planets:
        for key in PLANETS:
            track = _body_info(key, observer, midnight)
            _fill_track(track, observer, unix, lst, location.latitude, PLANET_HORIZON)
            ephem.planets[key] = track
    return ephem


@dataclass(slots=True)
class Snapshot:
    """Instantaneous positions used for "now" values."""

    time: datetime
    sun_alt: float
    sun_az: float
    moon_alt: float
    moon_az: float
    moon_illumination: float
    moon_phase: float
    moon_phase_angle: float
    moon_distance_km: float
    bodies: dict[str, tuple[float, float]]


def snapshot(location: Location, moment: datetime) -> Snapshot:
    """Positions of the Sun, Moon and planets at ``moment``."""
    observer = location.observer
    time = to_astro(moment)
    sun = horizontal(astronomy.Body.Sun, time, observer)
    moon_equ = astronomy.Equator(astronomy.Body.Moon, time, observer, True, True)
    moon = astronomy.Horizon(time, observer, moon_equ.ra, moon_equ.dec, astronomy.Refraction.Normal)
    illum = astronomy.Illumination(astronomy.Body.Moon, time)
    bodies = {key: horizontal(BODIES[key], time, observer) for key in PLANETS}
    return Snapshot(
        time=moment,
        sun_alt=sun[0],
        sun_az=sun[1],
        moon_alt=moon.altitude,
        moon_az=moon.azimuth,
        moon_illumination=illum.phase_fraction,
        moon_phase=astronomy.MoonPhase(time),
        moon_phase_angle=illum.phase_angle,
        moon_distance_km=moon_equ.dist * KM_PER_AU,
        bodies=bodies,
    )


def next_rise_set(
    location: Location, body_key: str, moment: datetime
) -> tuple[datetime | None, datetime | None]:
    """Next rise and set of a body after ``moment`` (within 2 days)."""
    observer = location.observer
    time = to_astro(moment)
    body = BODIES[body_key]
    rise = astronomy.SearchRiseSet(body, observer, astronomy.Direction.Rise, time, 2.0)
    set_ = astronomy.SearchRiseSet(body, observer, astronomy.Direction.Set, time, 2.0)
    return (
        from_astro(rise) if rise else None,
        from_astro(set_) if set_ else None,
    )


def next_sun_altitude(
    location: Location, moment: datetime, altitude: float, rising: bool
) -> datetime | None:
    """Next time the Sun crosses ``altitude`` (within 2 days)."""
    found = astronomy.SearchAltitude(
        astronomy.Body.Sun,
        location.observer,
        astronomy.Direction.Rise if rising else astronomy.Direction.Set,
        to_astro(moment),
        2.0,
        altitude,
    )
    return from_astro(found) if found else None
