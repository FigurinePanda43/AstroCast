"""Explainable observing-quality scores.

A score (0-100) is the product of independent factors in [0, 1], one per
physical limitation. A single fatal limitation (overcast, daylight, rain)
therefore drives the score to zero, and the smallest factor is reported as the
"limiting factor" so that every score can be explained in plain words.

Two profiles are computed:

* ``deep_sky``  — faint extended objects, visual or imaging. Dominated by
  clouds, darkness, moonlight (Krisciunas & Schaefer sky-brightness model) and
  transparency. Seeing and wind matter less.
* ``planetary`` — Moon, planets, double stars. Dominated by clouds and seeing;
  twilight and moonlight barely matter.

See docs/methodology.md for the rationale and the exact curves.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
import math

import numpy as np

from . import weather as w
from .ephemeris import STEP_MINUTES, NightEphemeris
from .skyglow import moon_brightening_mag

DEEP_SKY = "deep_sky"
PLANETARY = "planetary"
PROFILES = (DEEP_SKY, PLANETARY)

FACTORS = (
    "clouds",
    "precipitation",
    "darkness",
    "moon",
    "transparency",
    "seeing",
    "wind",
    "humidity",
)

RATINGS: tuple[tuple[int, str], ...] = (
    (75, "excellent"),
    (55, "good"),
    (35, "fair"),
    (15, "poor"),
    (0, "bad"),
)

SESSION_HOURS = 3.0
DEFAULT_SEEING = 1.75  # arcsec, typical mid-latitude site
DEFAULT_EXTINCTION = 0.25  # mag/airmass when no transparency forecast exists

CLOUD_EXPONENT = {DEEP_SKY: 1.6, PLANETARY: 1.1}
SEEING_TABLE = ((0.8, 1.0), (1.0, 0.93), (1.5, 0.78), (2.0, 0.6), (2.5, 0.43), (3.0, 0.3), (4.0, 0.15))
SEEING_EXPONENT = {DEEP_SKY: 0.35, PLANETARY: 1.0}
WIND_TABLE = ((12.0, 1.0), (20.0, 0.9), (30.0, 0.7), (40.0, 0.45), (55.0, 0.22), (70.0, 0.1))
WIND_EXPONENT = {DEEP_SKY: 1.0, PLANETARY: 0.8}
HUMIDITY_TABLE = ((85.0, 1.0), (90.0, 0.93), (95.0, 0.82), (100.0, 0.68))
TRANSPARENCY_EXPONENT = {DEEP_SKY: 1.0, PLANETARY: 0.4}
DARKNESS_TABLE = {
    DEEP_SKY: ((-18.0, 1.0), (-15.0, 0.55), (-12.0, 0.0)),
    PLANETARY: ((-8.0, 1.0), (-4.0, 0.5), (-1.0, 0.0)),
}


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
    return NightWeather(values, has, tiers, conf, clear, members, sources)


def zenith_moon_brightening(ephem: NightEphemeris, sqm: float, extinction: np.ndarray) -> np.ndarray:
    """Moonlight brightening (mag/arcsec²) at the zenith for every sample."""
    return moon_brightening_mag(
        sqm,
        ephem.moon_phase_angle,
        90.0 - ephem.moon_alt,
        ephem.moon_alt,
        np.full(len(ephem.times), 90.0),
        extinction,
    )


def sky_factors(
    ephem: NightEphemeris,
    weather: NightWeather,
    profile: str,
    sqm: float,
    assume_clear: bool = False,
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
    if profile == DEEP_SKY:
        factors["moon"] = moon_factor(zenith_moon_brightening(ephem, sqm, extinction))
    else:
        factors["moon"] = ones.copy()
    if assume_clear:
        factors["clouds"] = ones.copy()
        factors["precipitation"] = ones.copy()
        factors["transparency"] = transparency_factor(np.full(n, DEFAULT_EXTINCTION), profile)
        factors["seeing"] = seeing_factor(np.full(n, DEFAULT_SEEING), profile)
        factors["wind"] = ones.copy()
        factors["humidity"] = ones.copy()
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


def _best_block(scores: np.ndarray, usable: np.ndarray, length: int) -> tuple[int, int, float] | None:
    """Best contiguous block of ``length`` samples within the usable mask."""
    idx = np.flatnonzero(usable)
    if idx.size == 0:
        return None
    length = max(1, min(length, idx.size))
    best: tuple[int, int, float] | None = None
    values = np.where(usable, scores, 0.0)
    csum = np.concatenate(([0.0], np.cumsum(values)))
    for start in range(int(idx[0]), int(idx[-1]) - length + 2):
        mean = (csum[start + length] - csum[start]) / length
        if best is None or mean > best[2] + 1e-9:
            best = (start, start + length, mean)
    return best


def analyse_profile(
    ephem: NightEphemeris,
    weather: NightWeather,
    profile: str,
    sqm: float,
    good_threshold: float = 55.0,
) -> ProfileNight:
    """Score a night for a profile: best session, window, limiting factor."""
    factors = sky_factors(ephem, weather, profile, sqm)
    scores = combine(factors)
    potential_scores = combine(sky_factors(ephem, weather, profile, sqm, assume_clear=True))
    usable = factors["darkness"] > 0.3
    step_h = STEP_MINUTES / 60.0
    result = ProfileNight(profile, scores, factors, potential_scores)
    result.usable_hours = float(np.count_nonzero(usable)) * step_h
    block_len = int(round(SESSION_HOURS / step_h))

    pot = _best_block(potential_scores, usable, block_len)
    if pot is not None:
        result.potential = int(round(pot[2]))

    covered = usable & weather.has_weather
    if not np.any(usable) or np.count_nonzero(covered) < 0.5 * np.count_nonzero(usable):
        return result  # outside the weather forecast range: potential only

    block = _best_block(scores, usable, block_len)
    if block is None:
        return result
    start, end, mean = block
    result.score = int(round(mean))
    peak = int(np.argmax(np.where(usable, scores, -1.0)))
    result.peak_time = ephem.times[peak]
    result.peak_score = int(round(scores[peak]))
    result.good_hours = float(np.count_nonzero(usable & (scores >= good_threshold))) * step_h

    if mean >= 35.0:
        threshold = max(35.0, 0.8 * mean)
        lo, hi = start, end - 1
        while lo > 0 and usable[lo - 1] and scores[lo - 1] >= threshold:
            lo -= 1
        while hi < len(scores) - 1 and usable[hi + 1] and scores[hi + 1] >= threshold:
            hi += 1
        result.window_start = ephem.times[lo]
        result.window_end = ephem.times[hi] + (ephem.times[1] - ephem.times[0])
        result.window_score = int(round(float(np.mean(scores[lo : hi + 1]))))
        focus = np.zeros(len(scores), dtype=bool)
        focus[lo : hi + 1] = True
    else:
        focus = usable

    result.limiting = limiting_factor(factors, focus & usable)
    result.factor_means = {
        name: round(float(np.mean(values[focus & usable])), 3) for name, values in factors.items()
    }
    conf = weather.confidence[focus & usable]
    conf = conf[~np.isnan(conf)]
    result.confidence = round(float(np.min(conf)), 2) if conf.size else None
    tiers = [t for t, m in zip(weather.tier, focus & usable, strict=False) if m and t]
    if tiers:
        order = {"detailed": 0, "forecast": 1, "trend": 2}
        result.tier = max(tiers, key=lambda t: order.get(t, 3))
    return result


def dew_risk(temperature: float | None, dew_point: float | None) -> str | None:
    """Dew/frost risk on optics from the temperature–dew point spread."""
    if temperature is None or dew_point is None:
        return None
    spread = temperature - dew_point
    if spread <= 2.0:
        return "high"
    if spread <= 4.0:
        return "moderate"
    return "low"
