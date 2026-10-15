"""Explainable observing-quality scores.

A score (0-100) is the product of independent factors in [0, 1], one per
physical limitation. A single fatal limitation (overcast, daylight, rain)
therefore drives the score to zero, and the smallest factor is reported as the
"limiting factor" so that every score can be explained in plain words.

Three profiles are computed:

* ``deep_sky``  — faint extended objects, visual or imaging. Dominated by
  clouds, darkness, moonlight (Krisciunas & Schaefer sky-brightness model) and
  transparency. Seeing and wind matter less.
* ``planetary`` — Moon, planets, double stars. Dominated by clouds and seeing;
  twilight and moonlight barely matter.
* ``narrowband`` — emission nebulae imaged through narrowband filters (Hα,
  OIII, SII). Like deep sky, but a 3–7 nm filter rejects most moonlight and
  light pollution, so the Moon and nautical twilight weigh much less.

The score of a night rewards long sessions: it is the best mean score over a
contiguous window multiplied by a duration factor (a 2-hour clearing is not a
good night for long exposures). Dew on unprotected optics ends a session, so
from the predicted onset the rest of the night is heavily penalised.

See docs/methodology.md for the rationale and the exact curves.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
import itertools
import math

import numpy as np

from . import weather as w
from .ephemeris import STEP_MINUTES, NightEphemeris
from .skyglow import moon_brightening_mag

DEEP_SKY = "deep_sky"
PLANETARY = "planetary"
NARROWBAND = "narrowband"
PROFILES = (DEEP_SKY, PLANETARY, NARROWBAND)

FACTORS = (
    "clouds",
    "precipitation",
    "darkness",
    "moon",
    "transparency",
    "seeing",
    "wind",
    "humidity",
    "dew",
)

RATINGS: tuple[tuple[int, str], ...] = (
    (75, "excellent"),
    (55, "good"),
    (35, "fair"),
    (15, "poor"),
    (0, "bad"),
)

DEFAULT_SEEING = 1.75  # arcsec, typical mid-latitude site
DEFAULT_EXTINCTION = 0.25  # mag/airmass when no transparency forecast exists

CLOUD_EXPONENT = {DEEP_SKY: 1.6, PLANETARY: 1.1, NARROWBAND: 1.6}
SEEING_TABLE = (
    (0.8, 1.0),
    (1.0, 0.93),
    (1.5, 0.78),
    (2.0, 0.6),
    (2.5, 0.43),
    (3.0, 0.3),
    (4.0, 0.15),
)
SEEING_EXPONENT = {DEEP_SKY: 0.35, PLANETARY: 1.0, NARROWBAND: 0.35}
WIND_TABLE = ((12.0, 1.0), (20.0, 0.9), (30.0, 0.7), (40.0, 0.45), (55.0, 0.22), (70.0, 0.1))
WIND_EXPONENT = {DEEP_SKY: 1.0, PLANETARY: 0.8, NARROWBAND: 1.0}
HUMIDITY_TABLE = ((85.0, 1.0), (90.0, 0.93), (95.0, 0.82), (100.0, 0.68))
TRANSPARENCY_EXPONENT = {DEEP_SKY: 1.0, PLANETARY: 0.4, NARROWBAND: 0.8}
DARKNESS_TABLE = {
    DEEP_SKY: ((-18.0, 1.0), (-15.0, 0.55), (-12.0, 0.0)),
    PLANETARY: ((-8.0, 1.0), (-4.0, 0.5), (-1.0, 0.0)),
    NARROWBAND: ((-15.0, 1.0), (-12.0, 0.6), (-10.0, 0.0)),
}
# Exponent applied to the moonlight brightening (Δm). A 3–7 nm filter passes the
# emission lines but only a small slice of the moonlit sky continuum.
MOON_SENSITIVITY = {DEEP_SKY: 1.0, PLANETARY: 0.0, NARROWBAND: 0.25}
# Session length (h) → factor. Long exposures need long windows; planetary
# imaging and observing are done in shorter runs.
DURATION_TABLE = {
    DEEP_SKY: (
        (0.0, 0.0),
        (1.0, 0.35),
        (2.0, 0.6),
        (3.0, 0.78),
        (4.0, 0.9),
        (5.0, 0.97),
        (6.0, 1.0),
    ),
    PLANETARY: ((0.0, 0.0), (0.5, 0.45), (1.0, 0.7), (2.0, 0.92), (3.0, 1.0)),
    NARROWBAND: (
        (0.0, 0.0),
        (1.0, 0.35),
        (2.0, 0.6),
        (3.0, 0.78),
        (4.0, 0.9),
        (5.0, 0.97),
        (6.0, 1.0),
    ),
}
# Dew: optics cool below the air by radiation under a clear, calm sky.
DEW_COOLING = 2.0  # °C under a clear sky without wind
DEW_CALM_WIND = 15.0  # km/h from which wind prevents radiative cooling
DEW_ONSET_MARGIN = 0.5  # °C: dew forms on unprotected optics below this margin
DEW_WET = 0.3  # factor once unprotected optics are wet (rest of the night)
DEW_TABLE = ((0.5, 0.8), (1.0, 0.9), (2.0, 0.97), (3.0, 1.0))
DEW_TABLE_HEATED = ((-2.0, 0.85), (0.0, 0.95), (1.0, 1.0))


def rating(score: float | None) -> str | None:
    """Qualitative rating for a score."""
    if score is None:
        return None
    for threshold, label in RATINGS:
        if score >= threshold:
            return label
    return "bad"


def _table(x: np.ndarray, table: Sequence[tuple[float, float]]) -> np.ndarray:
    xs = np.array([p[0] for p in table])
    ys = np.array([p[1] for p in table])
    return np.interp(x, xs, ys)


def cloud_factor(cloud_pct: np.ndarray | float, profile: str) -> np.ndarray:
    """Fraction of usable sky: (1 − c)^γ."""
    c = np.clip(np.asarray(cloud_pct, dtype=float), 0.0, 100.0) / 100.0
    return (1.0 - c) ** CLOUD_EXPONENT[profile]


def expected_cloud_factor(members: Sequence[float], profile: str) -> float:
    """Expectation of the cloud factor over ensemble members."""
    return float(np.mean(cloud_factor(np.asarray(members, dtype=float), profile)))


def precipitation_factor(
    probability: np.ndarray, amount: np.ndarray, precip_type: np.ndarray
) -> np.ndarray:
    """1 when dry, 0 when it rains; intermediate with the rain probability."""
    prob = np.nan_to_num(np.asarray(probability, dtype=float), nan=0.0)
    amt = np.nan_to_num(np.asarray(amount, dtype=float), nan=0.0)
    ptype = np.nan_to_num(np.asarray(precip_type, dtype=float), nan=0.0)
    factor = 1.0 - 0.8 * np.clip((prob - 20.0) / 60.0, 0.0, 1.0)
    factor = np.where(amt >= 0.2, 0.0, np.where(amt >= 0.05, factor * 0.5, factor))
    return np.where(ptype > 0, np.minimum(factor, 0.15), factor)


def darkness_factor(sun_alt: np.ndarray, profile: str) -> np.ndarray:
    """Sky darkness from the Sun's altitude."""
    return _table(np.asarray(sun_alt, dtype=float), DARKNESS_TABLE[profile])


def moon_factor(delta_mag: np.ndarray, sensitivity: float | np.ndarray = 1.0) -> np.ndarray:
    """Relative signal-to-noise ratio under moonlight: 10^(−0.2 Δm).

    For a sky-limited observation the SNR at fixed exposure scales with
    sqrt(B_dark / B_total).
    """
    return 10.0 ** (-0.2 * np.asarray(delta_mag, dtype=float) * sensitivity)


def transparency_factor(extinction: np.ndarray, profile: str) -> np.ndarray:
    """Light loss from extinction above an excellent 0.15 mag/airmass at X=1.3."""
    k = np.asarray(extinction, dtype=float)
    base = 10.0 ** (-0.4 * np.maximum(0.0, k - 0.15) * 1.3)
    return base ** TRANSPARENCY_EXPONENT[profile]


def seeing_factor(arcsec: np.ndarray, profile: str) -> np.ndarray:
    """Image sharpness from the seeing FWHM (arcsec)."""
    return _table(np.asarray(arcsec, dtype=float), SEEING_TABLE) ** SEEING_EXPONENT[profile]


def wind_factor(speed: np.ndarray, gust: np.ndarray, profile: str) -> np.ndarray:
    """Mount stability / shake from wind (km/h)."""
    s = np.nan_to_num(np.asarray(speed, dtype=float), nan=0.0)
    g = np.nan_to_num(np.asarray(gust, dtype=float), nan=0.0)
    effective = np.maximum(s, 0.6 * g)
    return _table(effective, WIND_TABLE) ** WIND_EXPONENT[profile]


def humidity_factor(rh: np.ndarray, fog: np.ndarray) -> np.ndarray:
    """Haze, dew and fog risk."""
    r = np.nan_to_num(np.asarray(rh, dtype=float), nan=0.0)
    f = np.nan_to_num(np.asarray(fog, dtype=float), nan=0.0)
    factor = _table(r, HUMIDITY_TABLE)
    return factor * (1.0 - 0.8 * np.clip(f / 50.0, 0.0, 1.0))


def profile_moon_factor(delta_mag: np.ndarray, profile: str) -> np.ndarray:
    """Moonlight factor of a profile (neutral for planetary observing)."""
    sensitivity = MOON_SENSITIVITY[profile]
    if sensitivity <= 0.0:
        return np.ones(np.shape(delta_mag))
    return moon_factor(delta_mag, sensitivity)


def dew_margin(
    temperature: np.ndarray, dew_point: np.ndarray, cloud: np.ndarray, wind: np.ndarray
) -> np.ndarray:
    """Margin (°C) between the optics' temperature and the dew point.

    Optics exposed to a clear, calm sky cool about 2 °C below the air by
    radiation; clouds and wind reduce that cooling. NaN where unknown.
    """
    t = np.asarray(temperature, dtype=float)
    td = np.asarray(dew_point, dtype=float)
    clear = 1.0 - np.clip(np.nan_to_num(np.asarray(cloud, dtype=float), nan=50.0), 0, 100) / 100
    calm = np.clip(
        1.0 - np.nan_to_num(np.asarray(wind, dtype=float), nan=0.0) / DEW_CALM_WIND, 0, 1
    )
    return (t - td) - DEW_COOLING * clear * calm


def dew_onset_index(margin: np.ndarray, active: np.ndarray) -> int | None:
    """First sample (within ``active``) where dew forms on unprotected optics."""
    hits = np.flatnonzero(active & ~np.isnan(margin) & (margin <= DEW_ONSET_MARGIN))
    return int(hits[0]) if hits.size else None


def dew_factor(margin: np.ndarray, heaters: bool, onset: int | None = None) -> np.ndarray:
    """Dew factor from the optics margin.

    Without heaters, optics stay wet once dew has formed: every sample from
    ``onset`` on gets :data:`DEW_WET`. Heaters keep the optics clear, only
    saturated air (haze) still costs a little.
    """
    m = np.asarray(margin, dtype=float)
    if heaters:
        return np.where(np.isnan(m), 1.0, _table(m, DEW_TABLE_HEATED))
    factor = np.where(np.isnan(m), 1.0, _table(m, DEW_TABLE))
    factor = np.where(~np.isnan(m) & (m <= DEW_ONSET_MARGIN), DEW_WET, factor)
    if onset is not None:
        factor[onset:] = DEW_WET
    return factor


def dew_risk_level(margin: float | None) -> str | None:
    """Dew risk on unprotected optics: low, moderate or high."""
    if margin is None or math.isnan(margin):
        return None
    if margin <= DEW_ONSET_MARGIN:
        return "high"
    if margin <= 2.0:
        return "moderate"
    return "low"


def duration_factor(hours: float, profile: str) -> float:
    """Value of a session of ``hours`` hours for a profile (0–1)."""
    return float(_table(np.array([hours]), DURATION_TABLE[profile])[0])


@dataclass(slots=True)
class NightWeather:
    """Weather interpolated on the 15-minute grid of a night."""

    values: dict[str, np.ndarray]
    has_weather: np.ndarray
    tier: list[str | None]
    confidence: np.ndarray
    clear_probability: np.ndarray
    members: list[list[float] | None]
    sources: dict[str, str]
    in_range: np.ndarray | None = None

    def __post_init__(self) -> None:
        """Default: every sample may be covered."""
        if self.in_range is None:
            self.in_range = np.ones(len(self.has_weather), dtype=bool)

    def get(self, name: str) -> np.ndarray:
        """Array of a quantity (NaN where unknown)."""
        return self.values[name]


SAMPLED_FIELDS = (
    w.CLOUD,
    w.CLOUD_LOW,
    w.CLOUD_MID,
    w.CLOUD_HIGH,
    w.HUMIDITY,
    w.DEW_POINT,
    w.TEMPERATURE,
    w.WIND,
    w.GUST,
    w.PRECIP_PROB,
    w.PRECIP,
    w.PRECIP_TYPE,
    w.SEEING,
    w.TRANSPARENCY,
    w.AOD,
    w.FOG,
)


def sample_weather(timeline: w.Timeline | None, ephem: NightEphemeris) -> NightWeather:
    """Interpolate the merged hourly timeline onto the night's sample grid."""
    n = len(ephem.times)
    values = {name: np.full(n, np.nan) for name in SAMPLED_FIELDS}
    has = np.zeros(n, dtype=bool)
    tiers: list[str | None] = [None] * n
    conf = np.full(n, np.nan)
    clear = np.full(n, np.nan)
    members: list[list[float] | None] = [None] * n
    sources: dict[str, str] = {}
    if timeline is None or not timeline.hours:
        return NightWeather(values, has, tiers, conf, clear, members, sources)
    start = timeline.start.timestamp()
    end = timeline.end.timestamp()
    # Samples before the first hour with cloud data (the past, for providers
    # that do not return it) cannot be covered.
    first_cloud = next(
        (h.time.timestamp() for h in timeline.hours if h.values.get(w.CLOUD) is not None), end
    )
    in_range = ephem.unix >= first_cloud
    for i, ts in enumerate(ephem.unix):
        if ts < start or ts > end:
            continue
        hour = timeline.at(ephem.times[i])
        if hour is None:
            continue
        for name in SAMPLED_FIELDS:
            value = timeline.interpolate(name, float(ts))
            if value is not None:
                values[name][i] = value
        has[i] = not math.isnan(values[w.CLOUD][i])
        tiers[i] = hour.tier
        conf[i] = hour.confidence
        if hour.clear_probability is not None:
            clear[i] = hour.clear_probability
        members[i] = hour.members
        for name, source in hour.sources.items():
            sources.setdefault(name, source)
    return NightWeather(values, has, tiers, conf, clear, members, sources, in_range)


def zenith_moon_brightening(
    ephem: NightEphemeris, sqm: float, extinction: np.ndarray
) -> np.ndarray:
    """Moonlight brightening (mag/arcsec²) at the zenith for every sample."""
    return moon_brightening_mag(
        sqm,
        ephem.moon_phase_angle,
        90.0 - ephem.moon_alt,
        ephem.moon_alt,
        np.full(len(ephem.times), 90.0),
        extinction,
    )


def night_dew_margin(ephem: NightEphemeris, weather: NightWeather) -> np.ndarray:
    """Optics dew margin (°C) on the night grid."""
    return dew_margin(
        weather.get(w.TEMPERATURE),
        weather.get(w.DEW_POINT),
        weather.get(w.CLOUD),
        weather.get(w.WIND),
    )


def night_dew_onset(ephem: NightEphemeris, weather: NightWeather) -> int | None:
    """Sample at which dew forms on unprotected optics after sunset, if any."""
    active = (ephem.sun_alt < 0.0) & weather.has_weather
    return dew_onset_index(night_dew_margin(ephem, weather), active)


def sky_factors(
    ephem: NightEphemeris,
    weather: NightWeather,
    profile: str,
    sqm: float,
    assume_clear: bool = False,
    dew_heaters: bool = False,
) -> dict[str, np.ndarray]:
    """All factors for a profile on the night grid.

    With ``assume_clear`` the weather factors are neutral (clear, typical
    transparency/seeing): the result is the astronomical potential of the night.
    """
    n = len(ephem.times)
    ones = np.ones(n)
    extinction = weather.get(w.TRANSPARENCY)
    extinction = np.where(np.isnan(extinction), DEFAULT_EXTINCTION, extinction)
    factors: dict[str, np.ndarray] = {"darkness": darkness_factor(ephem.sun_alt, profile)}
    if MOON_SENSITIVITY[profile] > 0.0:
        factors["moon"] = profile_moon_factor(
            zenith_moon_brightening(ephem, sqm, extinction), profile
        )
    else:
        factors["moon"] = ones.copy()
    if assume_clear:
        factors["clouds"] = ones.copy()
        factors["precipitation"] = ones.copy()
        factors["transparency"] = transparency_factor(np.full(n, DEFAULT_EXTINCTION), profile)
        factors["seeing"] = seeing_factor(np.full(n, DEFAULT_SEEING), profile)
        factors["wind"] = ones.copy()
        factors["humidity"] = ones.copy()
        factors["dew"] = ones.copy()
        return factors

    cloud = cloud_factor(np.nan_to_num(weather.get(w.CLOUD), nan=100.0), profile)
    for i, tier in enumerate(weather.tier):
        if tier == "trend" and weather.members[i]:
            cloud[i] = expected_cloud_factor(weather.members[i], profile)
    factors["clouds"] = np.where(weather.has_weather, cloud, 0.0)
    factors["precipitation"] = precipitation_factor(
        weather.get(w.PRECIP_PROB), weather.get(w.PRECIP), weather.get(w.PRECIP_TYPE)
    )
    factors["transparency"] = transparency_factor(extinction, profile)
    seeing = weather.get(w.SEEING)
    factors["seeing"] = seeing_factor(np.where(np.isnan(seeing), DEFAULT_SEEING, seeing), profile)
    factors["wind"] = wind_factor(weather.get(w.WIND), weather.get(w.GUST), profile)
    factors["humidity"] = humidity_factor(weather.get(w.HUMIDITY), weather.get(w.FOG))
    margin = night_dew_margin(ephem, weather)
    onset = None if dew_heaters else night_dew_onset(ephem, weather)
    factors["dew"] = dew_factor(margin, dew_heaters, onset)
    return factors


def combine(factors: dict[str, np.ndarray]) -> np.ndarray:
    """Product of factors, scaled to 0-100."""
    result: np.ndarray | None = None
    for name in FACTORS:
        if name in factors:
            result = factors[name] if result is None else result * factors[name]
    assert result is not None
    return np.clip(result * 100.0, 0.0, 100.0)


def limiting_factor(factors: dict[str, np.ndarray], mask: np.ndarray) -> str | None:
    """Name of the factor with the lowest mean over ``mask``."""
    if not np.any(mask):
        return None
    means = {name: float(np.mean(values[mask])) for name, values in factors.items()}
    name, value = min(means.items(), key=lambda kv: kv[1])
    return name if value < 0.97 else None


@dataclass(slots=True)
class ProfileNight:
    """Night analysis for one profile."""

    profile: str
    scores: np.ndarray
    factors: dict[str, np.ndarray]
    potential_scores: np.ndarray
    score: int | None = None
    potential: int | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    window_score: int | None = None
    window_quality: int | None = None
    window_hours: float = 0.0
    duration_factor: float | None = None
    peak_time: datetime | None = None
    peak_score: int | None = None
    good_hours: float = 0.0
    usable_hours: float = 0.0
    limiting: str | None = None
    confidence: float | None = None
    tier: str | None = None
    factor_means: dict[str, float] = field(default_factory=dict)

    @property
    def rating(self) -> str | None:
        """Qualitative rating of the night."""
        return rating(self.score)


@dataclass(slots=True, frozen=True)
class Session:
    """Best contiguous observing session of a night."""

    start: int
    end: int  # exclusive
    quality: float  # mean score over the session
    duration: float  # factor for the session length
    value: float  # quality × duration


SESSION_FLOOR = 0.5  # fraction of the night's best level a session sample must reach
SESSION_MIN_FLOOR = 20.0
SESSION_MAX_GAP = 2  # samples (30 min)


def _decent_samples(scores: np.ndarray, usable: np.ndarray) -> np.ndarray:
    """Usable samples good enough to belong to a session (short dips bridged)."""
    level = float(np.percentile(scores[usable], 90))
    floor = max(SESSION_MIN_FLOOR, SESSION_FLOOR * level)
    decent = usable & (scores >= floor)
    if not np.any(decent):
        return usable  # a uniformly bad night: its (low) mean is the answer
    idx = np.flatnonzero(decent)
    for a, b in itertools.pairwise(idx):
        if 1 < b - a <= SESSION_MAX_GAP + 1 and np.all(usable[a:b]):
            decent[a:b] = True
    return decent


def best_session(
    scores: np.ndarray,
    usable: np.ndarray,
    profile: str,
    step_hours: float,
    reference_hours: float | None = None,
) -> Session | None:
    """Window maximising mean score × duration factor within ``usable``.

    A session only spans decent samples (at least half the night's best level),
    so it cannot buy duration with clouded or dewed-up hours; dips of up to
    :data:`SESSION_MAX_GAP` samples (a passing cloud) are tolerated.

    ``reference_hours`` normalises the duration factor when only part of the
    night can be known (end of the forecast range): a window covering all the
    known hours is then not penalised for the unknown remainder.
    """
    n = len(scores)
    if n == 0 or not np.any(usable):
        return None
    usable = _decent_samples(scores, usable)
    values = np.where(usable, scores, 0.0)
    csum = np.concatenate(([0.0], np.cumsum(values)))
    ucount = np.concatenate(([0], np.cumsum(usable.astype(int))))
    starts = np.arange(n)[:, None]
    ends = np.arange(1, n + 1)[None, :]
    length = ends - starts
    valid = (length > 0) & ((ucount[ends] - ucount[starts]) == length)
    if not np.any(valid):
        return None
    safe = np.where(valid, length, 1)
    mean = (csum[ends] - csum[starts]) / safe
    hours = length * step_hours
    table = DURATION_TABLE[profile]
    duration = np.interp(hours, [p[0] for p in table], [p[1] for p in table])
    if reference_hours is not None and reference_hours > 0:
        full = duration_factor(reference_hours, profile)
        if full > 0:
            duration = np.minimum(1.0, duration / full)
    value = np.where(valid, mean * duration, -1.0)
    flat = int(np.argmax(value))
    i, j = divmod(flat, n)
    return Session(
        start=i,
        end=j + 1,
        quality=float(mean[i, j]),
        duration=float(duration[i, j]),
        value=float(value[i, j]),
    )


def analyse_profile(
    ephem: NightEphemeris,
    weather: NightWeather,
    profile: str,
    sqm: float,
    good_threshold: float = 55.0,
    dew_heaters: bool = False,
) -> ProfileNight:
    """Score a night for a profile: best session, window, limiting factor."""
    factors = sky_factors(ephem, weather, profile, sqm, dew_heaters=dew_heaters)
    scores = combine(factors)
    potential_scores = combine(sky_factors(ephem, weather, profile, sqm, assume_clear=True))
    usable = factors["darkness"] > 0.3
    step_h = STEP_MINUTES / 60.0
    result = ProfileNight(profile, scores, factors, potential_scores)
    result.usable_hours = float(np.count_nonzero(usable)) * step_h

    pot = best_session(potential_scores, usable, profile, step_h)
    if pot is not None:
        result.potential = int(round(pot.value))

    covered = usable & weather.has_weather
    expected = usable & weather.in_range
    if not np.any(expected) or np.count_nonzero(covered) < 0.5 * np.count_nonzero(expected):
        return result  # outside the weather forecast range: potential only

    # Hours that cannot be known (beyond the forecast, or the past without
    # data) must not count as a short window.
    reference = None
    if np.count_nonzero(covered) < np.count_nonzero(usable):
        reference = float(np.count_nonzero(covered)) * step_h
    session = best_session(np.where(covered, scores, 0.0), covered, profile, step_h, reference)
    if session is None:
        return result
    result.score = int(round(session.value))
    peak = int(np.argmax(np.where(usable, scores, -1.0)))
    result.peak_time = ephem.times[peak]
    result.peak_score = int(round(scores[peak]))
    result.good_hours = float(np.count_nonzero(usable & (scores >= good_threshold))) * step_h

    focus = np.zeros(len(scores), dtype=bool)
    if session.quality >= 35.0:
        lo, hi = session.start, session.end
        result.window_start = ephem.times[lo]
        result.window_end = ephem.times[hi - 1] + (ephem.times[1] - ephem.times[0])
        result.window_score = result.score
        result.window_quality = int(round(session.quality))
        result.window_hours = round((hi - lo) * step_h, 2)
        result.duration_factor = round(session.duration, 3)
        focus[lo:hi] = True
    else:
        focus = usable

    result.limiting = limiting_factor(factors, focus & usable)
    result.factor_means = {
        name: round(float(np.mean(values[focus & usable])), 3) for name, values in factors.items()
    }
    if result.duration_factor is not None and result.duration_factor < 0.97:
        result.factor_means["duration"] = result.duration_factor
        lowest = min(result.factor_means.values())
        if result.duration_factor <= lowest:
            result.limiting = "duration"
    conf = weather.confidence[focus & usable]
    conf = conf[~np.isnan(conf)]
    result.confidence = round(float(np.min(conf)), 2) if conf.size else None
    tiers = [t for t, m in zip(weather.tier, focus & usable, strict=False) if m and t]
    if tiers:
        order = {"detailed": 0, "forecast": 1, "trend": 2}
        result.tier = max(tiers, key=lambda t: order.get(t, 3))
    return result
