"""Night scores: session length, dew and the narrowband profile."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import itertools

import numpy as np
import pytest

from custom_components.astrocast.engine import scoring, weather as w
from custom_components.astrocast.engine.ephemeris import Location, NightEphemeris, compute_night

from .conftest import LATITUDE, LONGITUDE

SITE = Location(LATITUDE, LONGITUDE, 100)
SQM = 21.3  # Bortle 4
NEW_MOON_NIGHT = date(2026, 10, 10)
FULL_MOON_NIGHT = date(2026, 10, 25)


def _night(night: date) -> NightEphemeris:
    return compute_night(SITE, night, with_planets=False)


def _weather(
    ephem: NightEphemeris,
    clear: tuple[datetime, datetime] | None = None,
    dew_from: datetime | None = None,
) -> scoring.NightWeather:
    """Synthetic forecast: clear inside ``clear`` (whole night if None), dry air.

    From ``dew_from`` on the air is saturated (dew point = temperature).
    """
    n = len(ephem.times)
    values = {name: np.full(n, np.nan) for name in scoring.SAMPLED_FIELDS}
    times = np.array([t.timestamp() for t in ephem.times])
    cloud = np.zeros(n)
    if clear is not None:
        inside = (times >= clear[0].timestamp()) & (times < clear[1].timestamp())
        cloud = np.where(inside, 0.0, 100.0)
    values[w.CLOUD] = cloud
    values[w.TEMPERATURE] = np.full(n, 12.0)
    values[w.DEW_POINT] = np.full(n, 2.0)
    if dew_from is not None:
        values[w.DEW_POINT] = np.where(times >= dew_from.timestamp(), 12.0, 2.0)
    values[w.HUMIDITY] = np.full(n, 50.0)
    values[w.WIND] = np.full(n, 5.0)
    return scoring.NightWeather(
        values=values,
        has_weather=np.ones(n, dtype=bool),
        tier=["detailed"] * n,
        confidence=np.full(n, 0.9),
        clear_probability=np.full(n, 90.0),
        members=[None] * n,
        sources={},
    )


def _analyse(ephem, weather, profile=scoring.DEEP_SKY, heaters=False):
    return scoring.analyse_profile(ephem, weather, profile, SQM, dew_heaters=heaters)


def test_short_clearing_is_not_a_good_night() -> None:
    """Two clear hours (e.g. 21h–23h) score far below a clear night."""
    ephem = _night(NEW_MOON_NIGHT)
    assert ephem.astro_dusk is not None
    start = ephem.astro_dusk + timedelta(minutes=30)
    full = _analyse(ephem, _weather(ephem))
    short = _analyse(ephem, _weather(ephem, (start, start + timedelta(hours=2))))
    assert full.score is not None and full.score >= 75
    assert full.window_hours >= 6
    assert short.score is not None
    assert short.score <= 0.65 * full.score
    assert short.window_hours == pytest.approx(2.0)
    assert short.window_quality is not None and short.window_quality >= 75
    assert short.limiting == "duration"
    # A longer clearing scores higher than a shorter one of the same quality.
    longer = _analyse(ephem, _weather(ephem, (start, start + timedelta(hours=4))))
    assert short.score < longer.score < full.score


def test_planetary_sessions_can_be_shorter() -> None:
    """Planetary observing loses much less with a 2-hour window."""
    ephem = _night(NEW_MOON_NIGHT)
    start = ephem.astro_dusk + timedelta(minutes=30)
    full = _analyse(ephem, _weather(ephem), scoring.PLANETARY)
    short = _analyse(ephem, _weather(ephem, (start, start + timedelta(hours=2))), scoring.PLANETARY)
    assert short.score >= 0.85 * full.score


def test_dew_ends_the_session_without_heaters() -> None:
    """Saturated air two hours after dusk ruins unprotected optics."""
    ephem = _night(NEW_MOON_NIGHT)
    onset = ephem.astro_dusk + timedelta(hours=2)
    weather = _weather(ephem, dew_from=onset)
    index = scoring.night_dew_onset(ephem, weather)
    assert index is not None
    assert abs((ephem.times[index] - onset).total_seconds()) <= 15 * 60
    dry = _analyse(ephem, _weather(ephem))
    wet = _analyse(ephem, weather)
    heated = _analyse(ephem, weather, heaters=True)
    assert wet.score <= 0.75 * dry.score
    assert wet.window_end is not None and wet.window_end <= onset + timedelta(minutes=15)
    assert wet.limiting in ("dew", "duration")
    assert heated.score >= 0.85 * dry.score
    assert heated.score > wet.score


def test_partial_forecast_is_not_penalised_as_short() -> None:
    """Unknown hours at the end of the forecast range are not a short window."""
    ephem = _night(NEW_MOON_NIGHT)
    weather = _weather(ephem)
    known = np.array([t <= ephem.midnight for t in ephem.times])
    weather.has_weather = known
    weather.values[w.CLOUD] = np.where(known, 0.0, np.nan)
    partial = _analyse(ephem, weather)
    full = _analyse(ephem, _weather(ephem))
    assert partial.score is not None
    assert partial.score >= 0.9 * full.score


def test_narrowband_tolerates_the_moon() -> None:
    """Under a full Moon, narrowband imaging stays workable, broadband does not."""
    ephem = _night(FULL_MOON_NIGHT)
    assert ephem.moon_illumination > 0.95
    weather = _weather(ephem)
    deep = _analyse(ephem, weather, scoring.DEEP_SKY)
    narrow = _analyse(ephem, weather, scoring.NARROWBAND)
    assert narrow.score >= deep.score + 20
    assert narrow.score >= 50
    # Without the Moon both profiles agree closely.
    dark = _night(NEW_MOON_NIGHT)
    clear = _weather(dark)
    assert abs(_analyse(dark, clear, scoring.NARROWBAND).score - _analyse(dark, clear).score) <= 10


def test_duration_factor_is_monotonic() -> None:
    for profile in scoring.PROFILES:
        values = [scoring.duration_factor(h / 4, profile) for h in range(40)]
        assert values[0] == 0
        assert all(b >= a for a, b in itertools.pairwise(values))
        assert values[-1] == 1
