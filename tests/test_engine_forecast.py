"""Weather parsing/fusion, scoring, catalog and the planner."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from custom_components.astrocast.engine import scoring, weather as w
from custom_components.astrocast.engine.catalog import load_catalog
from custom_components.astrocast.engine.ephemeris import Location, compute_night
from custom_components.astrocast.engine.horizon import (
    HorizonError,
    altitude_limit,
    format_horizon,
    parse_horizon,
)
from custom_components.astrocast.engine.planner import Planner, SiteConfig
from custom_components.astrocast.engine.smallbodies import parse_sbdb
from custom_components.astrocast.providers import metno, open_meteo, seventimer
from custom_components.astrocast.providers.base import ProviderError, ProviderStatus

from .conftest import LATITUDE, LONGITUDE, NOW, load_fixture


def _series() -> dict[str, w.WeatherSeries]:
    return {
        "7timer": seventimer.parse(load_fixture("7timer_astro.json"), NOW),
        "open_meteo": open_meteo.parse_hourly(
            load_fixture("open_meteo_forecast.json"),
            open_meteo.FORECAST_VARIABLES,
            "open_meteo",
            NOW,
        ),
        "ensemble": open_meteo.parse_ensemble(load_fixture("open_meteo_ensemble.json"), NOW),
        "cams": open_meteo.parse_hourly(
            load_fixture("open_meteo_air_quality.json"),
            {"aerosol_optical_depth": w.AOD, "dust": w.DUST},
            "cams",
            NOW,
        ),
    }


# --- providers -----------------------------------------------------------------


def test_parse_7timer() -> None:
    series = seventimer.parse(load_fixture("7timer_astro.json"), NOW)
    assert series.model_run == datetime(2026, 10, 13, 12, tzinfo=UTC)
    assert len(series.times) == 24
    assert (series.times[1] - series.times[0]) == 3 * 3600
    seeing = [v for v in series.fields[w.SEEING] if v is not None]
    assert seeing and all(0.3 < v < 3.0 for v in seeing)
    assert all(0 <= v <= 100 for v in series.fields[w.CLOUD] if v is not None)


def test_parse_7timer_handles_missing_values() -> None:
    payload = {
        "init": "2026101312",
        "dataseries": [
            {
                "timepoint": 3,
                "cloudcover": -9999,
                "seeing": -9999,
                "transparency": 2,
                "lifted_index": -9999,
                "rh2m": 30,
                "wind10m": {},
                "temp2m": -9999,
                "prec_type": "rain",
            }
        ],
    }
    series = seventimer.parse(payload, NOW)
    assert series.fields[w.CLOUD] == [None]
    assert series.fields[w.SEEING] == [None]
    assert series.fields[w.TRANSPARENCY] == [0.35]
    assert series.fields[w.HUMIDITY] == [None]
    assert series.fields[w.PRECIP_TYPE] == [1.0]
    with pytest.raises(ProviderError):
        seventimer.parse({"init": "x"}, NOW)


def test_parse_open_meteo_and_ensemble() -> None:
    series = _series()
    forecast = series["open_meteo"]
    assert len(forecast.times) > 300
    assert set(forecast.fields) >= {w.CLOUD, w.JET, w.HUMIDITY, w.DEW_POINT}
    ensemble = series["ensemble"]
    assert ensemble.members is not None
    assert all(len(m) >= 5 for m in ensemble.members)
    with pytest.raises(ProviderError):
        open_meteo.parse_hourly({"error": True, "reason": "nope"}, {}, "open_meteo", NOW)


def test_parse_metno() -> None:
    series = metno.parse(load_fixture("metno_complete.json"), NOW)
    assert len(series.times) > 50
    assert series.fields[w.WIND][0] is not None
    # m/s converted to km/h
    raw = load_fixture("metno_complete.json")["properties"]["timeseries"][0]
    assert series.fields[w.WIND][0] == pytest.approx(
        raw["data"]["instant"]["details"]["wind_speed"] * 3.6
    )


def test_provider_status_backoff() -> None:
    status = ProviderStatus("x", timedelta(hours=1))
    assert status.due(NOW)
    status.record_failure(NOW, "boom")
    assert not status.due(NOW + timedelta(minutes=4))
    assert status.due(NOW + timedelta(minutes=6))
    status.record_failure(NOW, "boom")
    assert status.next_attempt == NOW + timedelta(minutes=10)
    status.record_success(NOW)
    assert not status.due(NOW + timedelta(minutes=30))
    assert status.due(NOW + timedelta(hours=1))
    assert status.failures == 0


# --- timeline ------------------------------------------------------------------


def test_timeline_merge_and_tiers() -> None:
    timeline = w.build_timeline(_series(), NOW, 100)
    assert timeline.hours[0].time == NOW - timedelta(hours=2)
    first = timeline.at(NOW + timedelta(hours=1))
    assert first.sources[w.CLOUD] == "open_meteo"
    assert first.sources[w.SEEING] == "7timer"
    assert first.sources[w.TRANSPARENCY] == "cams"
    assert first.tier == "detailed"
    assert first.clear_probability is not None
    later = timeline.at(NOW + timedelta(days=5))
    assert later.tier == "forecast"
    assert later.sources[w.SEEING] == "jetstream"
    far = timeline.at(NOW + timedelta(days=10))
    assert far.tier == "trend"
    assert far.confidence < first.confidence


def test_timeline_fallback_to_metno() -> None:
    series = {"met_no": metno.parse(load_fixture("metno_complete.json"), NOW)}
    timeline = w.build_timeline(series, NOW, 100)
    hour = timeline.at(NOW + timedelta(hours=3))
    assert hour.sources[w.CLOUD] == "met_no"
    assert w.SEEING not in hour.values  # no seeing forecast available


def test_series_roundtrip() -> None:
    series = _series()["ensemble"]
    restored = w.WeatherSeries.from_dict(series.as_dict())
    assert restored.times == series.times
    assert restored.members == series.members


def test_seeing_proxy_monotonic() -> None:
    values = [w.seeing_from_jetstream(v) for v in (0, 40, 80, 120, 200, 400)]
    assert values == sorted(values)


# --- scoring -------------------------------------------------------------------


def test_factor_curves() -> None:
    clouds = scoring.cloud_factor(np.array([0, 25, 50, 100]), scoring.DEEP_SKY)
    assert clouds[0] == 1 and clouds[-1] == 0 and np.all(np.diff(clouds) < 0)
    assert scoring.cloud_factor(50, scoring.PLANETARY) > scoring.cloud_factor(50, scoring.DEEP_SKY)
    dark = scoring.darkness_factor(np.array([5, -10, -15, -20]), scoring.DEEP_SKY)
    assert list(dark[[0, 3]]) == [0, 1]
    planetary = scoring.darkness_factor(np.array([-10.0]), scoring.PLANETARY)
    assert planetary[0] == 1
    assert scoring.moon_factor(np.array([0.0]))[0] == 1
    assert scoring.moon_factor(np.array([2.5]))[0] == pytest.approx(10**-0.5)
    seeing = scoring.seeing_factor(np.array([0.7, 1.5, 3.5]), scoring.PLANETARY)
    assert np.all(np.diff(seeing) < 0)
    assert scoring.seeing_factor(np.array([3.0]), scoring.DEEP_SKY)[0] > seeing[2]
    rain = scoring.precipitation_factor(np.array([90.0]), np.array([1.0]), np.array([1.0]))
    assert rain[0] == 0
    assert scoring.rating(80) == "excellent"
    assert scoring.rating(10) == "bad"
    assert scoring.rating(None) is None
    assert scoring.dew_risk(10, 9) == "high"
    assert scoring.dew_risk(10, 3) == "low"


def _synthetic_weather(ephem, cloud: float, seeing: float = 1.0) -> scoring.NightWeather:
    n = len(ephem.times)
    values = {name: np.full(n, np.nan) for name in scoring.SAMPLED_FIELDS}
    values[w.CLOUD][:] = cloud
    values[w.SEEING][:] = seeing
    values[w.TRANSPARENCY][:] = 0.2
    values[w.HUMIDITY][:] = 60
    values[w.WIND][:] = 5
    return scoring.NightWeather(
        values=values,
        has_weather=np.ones(n, dtype=bool),
        tier=["detailed"] * n,
        confidence=np.full(n, 0.9),
        clear_probability=np.full(n, np.nan),
        members=[None] * n,
        sources={},
    )


def test_profiles_react_to_clouds_and_moon() -> None:
    site = Location(LATITUDE, LONGITUDE, 100)
    new_moon = compute_night(site, date(2026, 11, 9), with_planets=False)
    full_moon = compute_night(site, date(2026, 10, 26), with_planets=False)

    clear_dark = scoring.analyse_profile(
        new_moon, _synthetic_weather(new_moon, 0), "deep_sky", 21.4
    )
    overcast = scoring.analyse_profile(
        new_moon, _synthetic_weather(new_moon, 100), "deep_sky", 21.4
    )
    clear_full = scoring.analyse_profile(
        full_moon, _synthetic_weather(full_moon, 0), "deep_sky", 21.4
    )
    planetary_full = scoring.analyse_profile(
        full_moon, _synthetic_weather(full_moon, 0), "planetary", 21.4
    )

    assert clear_dark.score >= 80 and clear_dark.rating == "excellent"
    assert clear_dark.window_start is not None and clear_dark.window_end > clear_dark.window_start
    assert overcast.score == 0 and overcast.window_start is None
    assert overcast.limiting == "clouds"
    assert clear_full.score < clear_dark.score - 25
    assert clear_full.limiting == "moon"
    assert planetary_full.score >= 80  # the Moon does not spoil planetary observing


def test_trend_uses_ensemble_expectation() -> None:
    site = Location(LATITUDE, LONGITUDE, 100)
    ephem = compute_night(site, date(2026, 11, 9), with_planets=False)
    weather = _synthetic_weather(ephem, 100)
    weather.tier = ["trend"] * len(ephem.times)
    weather.members = [[0.0] * 5 + [100.0] * 5] * len(ephem.times)
    result = scoring.analyse_profile(ephem, weather, "deep_sky", 21.4)
    # Half of the members are clear: the expected score is about half the potential.
    assert 0.35 * result.potential < result.score < 0.65 * result.potential
    assert result.tier == "trend"


def test_no_weather_gives_potential_only() -> None:
    site = Location(LATITUDE, LONGITUDE, 100)
    ephem = compute_night(site, date(2026, 11, 9), with_planets=False)
    result = scoring.analyse_profile(ephem, scoring.sample_weather(None, ephem), "deep_sky", 21.4)
    assert result.score is None
    assert result.potential is not None and result.potential > 70


# --- catalog -------------------------------------------------------------------


def test_catalog_contents_and_search() -> None:
    catalog = load_catalog()
    assert len(catalog) > 600
    messier = {o.messier for o in catalog.objects if o.messier}
    assert messier == set(range(1, 111)) - {102}
    caldwell = {o.caldwell for o in catalog.objects if o.caldwell}
    assert caldwell == set(range(1, 110))
    assert catalog.get("M 31").id == "M31"
    assert catalog.get("NGC 224").id == "M31"
    assert catalog.get("andromeda galaxy").id == "M31"
    assert catalog.get("Galaxie d'Andromède").id == "M31"
    assert catalog.get("C 20").id == "NGC7000"
    assert catalog.get("nothing here") is None
    results = catalog.search("veil")
    assert {"NGC6960", "NGC6992"} <= {o.id for o in results}
    assert catalog.by_id["M42"].label("fr") == "M 42 – Grande nébuleuse d'Orion"


# --- planner -------------------------------------------------------------------


@pytest.fixture(scope="module")
def forecast():
    site = SiteConfig("Test", LATITUDE, LONGITUDE, 100, bortle=4, min_altitude=20)
    planner = Planner(site, load_catalog())
    timeline = w.build_timeline(_series(), NOW, 100)
    comets = parse_sbdb(load_fixture("jpl_comets.json"), "comet")
    asteroids = parse_sbdb(load_fixture("jpl_asteroids.json"), "asteroid")
    return planner.compute(NOW, timeline, comets, asteroids, ["M31", "saturn", "comet:2026 A2"])


def test_planner_nights(forecast) -> None:
    assert len(forecast.nights) == 30
    assert forecast.tonight.ephem.night == date(2026, 10, 13)
    covered = [n for n in forecast.nights if n.has_weather]
    assert 12 <= len(covered) <= 16
    assert all(not n.has_weather for n in forecast.nights[17:])
    assert forecast.nights[20].deep_sky.potential is not None
    best = forecast.best_night()
    assert best is not None and best.deep_sky.score == max(n.deep_sky.score or 0 for n in covered)
    tonight = forecast.tonight.deep_sky
    assert tonight.score is not None and tonight.window_start is not None


def test_planner_objects(forecast) -> None:
    ids = [o.id for o in forecast.tonight.objects]
    assert "M31" in ids[:10]
    assert all(o.recommended for o in forecast.tonight.objects)
    assert ids == [o.id for o in sorted(forecast.tonight.objects, key=lambda o: -o.interest)]
    planets = {p.id: p for p in forecast.tonight.planets}
    assert set(planets) == {
        "mercury",
        "venus",
        "mars",
        "jupiter",
        "saturn",
        "uranus",
        "neptune",
        "moon",
    }
    assert planets["saturn"].best_score > 40
    assert {"key": "near_opposition"} in planets["saturn"].reasons
    assert planets["venus"].best_score == 0  # lost in the twilight


def test_planner_favorites(forecast) -> None:
    favorites = {f.id: f for f in forecast.favorites}
    assert set(favorites) == {"M31", "saturn", "comet:2026 A2"}
    m31 = favorites["M31"]
    assert m31.tonight is not None
    assert len(m31.nights) == 16
    assert m31.next_good is not None and m31.next_good.best_score >= 60
    comet = favorites["comet:2026 A2"]
    assert comet.tonight is not None  # forced even though faint
    assert comet.tonight.extra["estimated_magnitude"] is True


def test_planner_now(forecast) -> None:
    now = forecast.now
    assert now.is_dark
    assert now.scores["deep_sky"] is not None
    assert now.tier == "detailed"
    assert now.moonset is not None and now.moonrise is not None


# --- horizon profile -------------------------------------------------------------


def test_parse_horizon() -> None:
    points = parse_horizon("0:15, 90:30, 180:10, 270:25")
    assert points == ((0.0, 15.0), (90.0, 30.0), (180.0, 10.0), (270.0, 25.0))
    assert format_horizon(points) == "0:15, 90:30, 180:10, 270:25"
    assert parse_horizon("45=12,5; 200/8") == ((45.0, 12.5), (200.0, 8.0))
    assert parse_horizon("") == ()
    for bad in ("abc", "0:95", "10"):
        with pytest.raises(HorizonError):
            parse_horizon(bad)
    limits = altitude_limit(points, np.array([0.0, 45.0, 135.0, 315.0]), 20.0)
    np.testing.assert_allclose(limits, [20.0, 22.5, 20.0, 20.0])


def test_horizon_hides_objects() -> None:
    timeline = w.build_timeline(_series(), NOW, 100)
    catalog = load_catalog()
    open_sky = Planner(SiteConfig("Open", LATITUDE, LONGITUDE, 100), catalog).compute(NOW, timeline)
    walled = Planner(
        SiteConfig(
            "Walled", LATITUDE, LONGITUDE, 100, horizon=parse_horizon("0:75, 90:75, 180:75, 270:75")
        ),
        catalog,
    ).compute(NOW, timeline)
    assert any(o.max_alt < 75 for o in open_sky.tonight.objects)
    assert walled.tonight.objects
    assert all(o.max_alt >= 75 for o in walled.tonight.objects)
    saturn = {p.id: p for p in walled.tonight.planets}["saturn"]
    assert saturn.best_score == 0
    # The sky itself is unchanged: only object visibility depends on the horizon.
    assert walled.tonight.deep_sky.score == open_sky.tonight.deep_sky.score
