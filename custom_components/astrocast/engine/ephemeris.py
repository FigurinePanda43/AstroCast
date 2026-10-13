"""Sun, Moon and planet ephemerides organised per night.

All positions come from astronomy-engine (Don Cross, MIT licence), whose
accuracy is better than one arcminute against JPL DE ephemerides. Topocentric
coordinates include parallax, aberration, nutation and standard refraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import math

import astronomy
import numpy as np

from .timeutil import from_astro, night_window, to_astro

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


def _search_altitude(
    observer: astronomy.Observer,
    direction: astronomy.Direction,
    start: astronomy.Time,
    end: datetime,
    altitude: float,
) -> datetime | None:
    found = astronomy.SearchAltitude(
        astronomy.Body.Sun, observer, direction, start, 1.0, altitude
    )
    if found is None:
        return None
    moment = from_astro(found)
    return moment if moment < end else None


def _search_rise_set(
    body: astronomy.Body,
    observer: astronomy.Observer,
    direction: astronomy.Direction,
    start: astronomy.Time,
    end: datetime,
) -> datetime | None:
    found = astronomy.SearchRiseSet(body, observer, direction, start, 1.0)
    if found is None:
        return None
    moment = from_astro(found)
    return moment if moment < end else None


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


def _body_track(
    key: str,
    observer: astronomy.Observer,
    times: list[astronomy.Time],
    midnight: astronomy.Time,
    window_start: astronomy.Time,
    window_end: datetime,
) -> BodyTrack:
    body = BODIES[key]
    alt = np.empty(len(times))
    az = np.empty(len(times))
    for i, time in enumerate(times):
        alt[i], az[i] = horizontal(body, time, observer)

    equ = astronomy.Equator(body, midnight, observer, True, True)
    equ_j2000 = astronomy.Equator(body, midnight, observer, False, True)
    constellation = astronomy.Constellation(equ_j2000.ra, equ_j2000.dec).symbol
    diameter = 2.0 * math.atan(RADIUS_KM[key] / (equ.dist * KM_PER_AU)) * ARCSEC_PER_RAD

    track = BodyTrack(
        key=key,
        alt=alt,
        az=az,
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
    track.rise = _search_rise_set(
        body, observer, astronomy.Direction.Rise, window_start, window_end
    )
    track.set = _search_rise_set(
        body, observer, astronomy.Direction.Set, window_start, window_end
    )
    transit = astronomy.SearchHourAngle(body, observer, 0.0, window_start, 1)
    transit_time = from_astro(transit.time)
    if transit_time < window_end:
        track.transit = transit_time
        track.transit_alt = transit.hor.altitude
    return track


def compute_night(location: Location, night: date, with_planets: bool = True) -> NightEphemeris:
    """Compute the ephemeris of a night (local noon to local noon)."""
    observer = location.observer
    start, end = night_window(night, location.longitude)
    times = [start + timedelta(minutes=STEP_MINUTES * i) for i in range(SAMPLES_PER_NIGHT)]
    atimes = [to_astro(t) for t in times]
    n = len(times)

    sun_alt = np.empty(n)
    moon_alt = np.empty(n)
    moon_az = np.empty(n)
    moon_illum = np.empty(n)
    moon_pa = np.empty(n)
    lst = np.empty(n)
    for i, time in enumerate(atimes):
        sun_alt[i] = horizontal(astronomy.Body.Sun, time, observer)[0]
        moon_alt[i], moon_az[i] = horizontal(astronomy.Body.Moon, time, observer)
        lst[i] = local_sidereal_deg(time, location.longitude)
    # Lunar illumination changes slowly: evaluate every 3 hours and interpolate.
    coarse = list(range(0, n, 12)) + [n - 1]
    coarse_illum = []
    coarse_pa = []
    for idx in coarse:
        illum = astronomy.Illumination(astronomy.Body.Moon, atimes[idx])
        coarse_illum.append(illum.phase_fraction)
        coarse_pa.append(illum.phase_angle)
    moon_illum[:] = np.interp(np.arange(n), coarse, coarse_illum)
    moon_pa[:] = np.interp(np.arange(n), coarse, coarse_pa)

    astart = atimes[0]
    midnight = to_astro(start + timedelta(hours=12))
    moon_track = _body_track("moon", observer, [], midnight, astart, end)
    moon_track.alt = moon_alt
    moon_track.az = moon_az

    ephem = NightEphemeris(
        night=night,
        start=start,
        end=end,
        times=times,
        unix=np.array([t.timestamp() for t in times]),
        sun_alt=sun_alt,
        moon_alt=moon_alt,
        moon_az=moon_az,
        moon_illum=moon_illum,
        moon_phase_angle=moon_pa,
        lst_deg=lst,
        precession=precession_matrix(midnight),
        sunset=_search_rise_set(
            astronomy.Body.Sun, observer, astronomy.Direction.Set, astart, end
        ),
        sunrise=None,
        civil_dusk=_search_altitude(observer, astronomy.Direction.Set, astart, end, CIVIL),
        civil_dawn=None,
        nautical_dusk=_search_altitude(
            observer, astronomy.Direction.Set, astart, end, NAUTICAL
        ),
        nautical_dawn=None,
        astro_dusk=_search_altitude(
            observer, astronomy.Direction.Set, astart, end, ASTRONOMICAL
        ),
        astro_dawn=None,
        moonrise=moon_track.rise,
        moonset=moon_track.set,
        moon_phase=astronomy.MoonPhase(midnight),
        moon_illumination=astronomy.Illumination(astronomy.Body.Moon, midnight).phase_fraction,
        moon=moon_track,
    )
    # Morning events are searched from the evening event (or the window start)
    # so that a morning event is always paired with the right evening.
    ephem.sunrise = _search_rise_set(
        astronomy.Body.Sun,
        observer,
        astronomy.Direction.Rise,
        to_astro(ephem.sunset) if ephem.sunset else astart,
        end,
    )
    for dusk_attr, dawn_attr, limit in (
        ("civil_dusk", "civil_dawn", CIVIL),
        ("nautical_dusk", "nautical_dawn", NAUTICAL),
        ("astro_dusk", "astro_dawn", ASTRONOMICAL),
    ):
        dusk = getattr(ephem, dusk_attr)
        setattr(
            ephem,
            dawn_attr,
            _search_altitude(
                observer,
                astronomy.Direction.Rise,
                to_astro(dusk) if dusk else astart,
                end,
                limit,
            ),
        )

    if with_planets:
        night_idx = [i for i in range(n) if sun_alt[i] < 0.0]
        for key in PLANETS:
            track = _body_track(key, observer, [], midnight, astart, end)
            alt = np.full(n, -90.0)
            az = np.zeros(n)
            for i in night_idx:
                alt[i], az[i] = horizontal(BODIES[key], atimes[i], observer)
            track.alt = alt
            track.az = az
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
    moon = astronomy.Horizon(
        time, observer, moon_equ.ra, moon_equ.dec, astronomy.Refraction.Normal
    )
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
