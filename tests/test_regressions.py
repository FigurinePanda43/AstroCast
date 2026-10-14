"""Regression tests for issues found during code review."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
import json
import math
from pathlib import Path

import pytest

from custom_components.astrocast.engine import weather as w
from custom_components.astrocast.engine.catalog import load_catalog
from custom_components.astrocast.engine.ephemeris import Location, compute_night
from custom_components.astrocast.engine.planner import Planner, SiteConfig
from custom_components.astrocast.engine.smallbodies import (
    GAUSS_K,
    OrbitalElements,
    heliocentric_ecliptic,
)
from custom_components.astrocast.engine.timeutil import night_date_for, night_window

from .conftest import LATITUDE, LONGITUDE, NOW
from .test_engine_forecast import _series


def test_planner_keeps_working_day_after_day() -> None:
    """Nights first cached without planets get them once they enter the window."""
    planner = Planner(SiteConfig("Test", LATITUDE, LONGITUDE, 100), load_catalog())
    for day in range(20):
        moment = NOW + timedelta(days=day)
        forecast = planner.compute(moment, None, favorites=["jupiter", "M31"])
        for night in forecast.nights[:16]:
            assert night.ephem.planets, (day, night.ephem.night)
        assert forecast.favorites[0].nights


def test_tonight_keeps_its_score_after_midnight() -> None:
    """Past samples of the current night must not make it look uncovered."""
    series = _series()
    planner = Planner(SiteConfig("Test", LATITUDE, LONGITUDE, 100), load_catalog())
    # Up to 05:00 UTC on the 14th: sunrise is at 05:53 UTC.
    for hour in (20, 23, 26, 28, 29):
        moment = datetime(2026, 10, 13, tzinfo=UTC) + timedelta(hours=hour)
        night_start = night_window(date(2026, 10, 13), LONGITUDE)[0]
        timeline = w.build_timeline(series, moment, 100, start=night_start)
        forecast = planner.compute(moment, timeline)
        assert forecast.tonight.ephem.night == date(2026, 10, 13)
        assert forecast.tonight.has_weather, hour
        assert forecast.tonight.deep_sky.score is not None, hour


def test_tonight_is_the_coming_night_after_sunrise() -> None:
    """From sunrise to local noon, "tonight" is the coming night, not the past one."""
    series = _series()
    planner = Planner(SiteConfig("Test", LATITUDE, LONGITUDE, 100), load_catalog())
    sunrise = compute_night(planner.site.location, date(2026, 10, 13), with_planets=False).sunrise
    assert sunrise is not None
    noon = night_window(date(2026, 10, 14), LONGITUDE)[0]
    assert sunrise < noon
    expected = (
        (sunrise - timedelta(minutes=5), date(2026, 10, 13)),
        (sunrise + timedelta(minutes=5), date(2026, 10, 14)),
        (noon - timedelta(minutes=5), date(2026, 10, 14)),
        (noon + timedelta(minutes=5), date(2026, 10, 14)),
    )
    for moment, night in expected:
        # Timeline built as the coordinator does (from the noon-based night).
        start = night_window(night_date_for(moment, LONGITUDE), LONGITUDE)[0]
        timeline = w.build_timeline(series, moment, 100, start=start)
        forecast = planner.compute(moment, timeline)
        assert forecast.tonight.ephem.night == night, moment
        assert forecast.tonight.has_weather, moment
        assert forecast.tonight.deep_sky.score is not None, moment
        assert forecast.tonight.ephem.planets, moment
        dates = [n.ephem.night for n in forecast.nights]
        assert dates == [night + timedelta(days=i) for i in range(len(dates))]


def test_tonight_keeps_noon_boundary_without_sunrise() -> None:
    """Polar day: no sunrise, so the night still changes at local noon."""
    planner = Planner(SiteConfig("Polar", 78.0, 15.0, 0), load_catalog())
    morning = datetime(2026, 6, 21, 8, tzinfo=UTC)  # 09:00 local mean solar time
    assert planner.compute(morning, None).tonight.ephem.night == date(2026, 6, 20)
    afternoon = datetime(2026, 6, 21, 13, tzinfo=UTC)
    assert planner.compute(afternoon, None).tonight.ephem.night == date(2026, 6, 21)


def _reference_position(q: float, e: float, dt: float) -> tuple[float, float]:
    """In-plane position from the classical elliptic Kepler equation (bisection)."""
    a = q / (1 - e)
    n = GAUSS_K / a**1.5
    period = 2 * math.pi / n
    dt = (dt + period / 2) % period - period / 2
    mean = n * dt
    lo, hi = -math.pi, math.pi
    for _ in range(200):
        mid = (lo + hi) / 2
        if mid - e * math.sin(mid) - mean > 0:
            hi = mid
        else:
            lo = mid
    ecc = (lo + hi) / 2
    return a * (math.cos(ecc) - e), a * math.sqrt(1 - e * e) * math.sin(ecc)


@pytest.mark.parametrize(
    ("q", "e", "dt"),
    [
        (0.1, 0.99, 150.0),
        (0.1, 0.99, -150.0),
        (0.1, 0.98, -225.0),
        (0.01, 0.999, 10.0),
        (0.005, 0.9999, 300.0),
        (1.0, 0.5, 400.0),
        (2.5, 0.08, -380.0),
    ],
)
def test_kepler_solver_high_eccentricity(q: float, e: float, dt: float) -> None:
    elements = OrbitalElements("t", "t", "comet", q, e, 0.0, 0.0, 0.0, 2461000.0, 2461000.0)
    x, y, z = heliocentric_ecliptic(elements, 2461000.0 + dt)
    rx, ry = _reference_position(q, e, dt)
    assert z == pytest.approx(0.0, abs=1e-9)
    assert math.hypot(x - rx, y - ry) < 1e-6 * max(1.0, math.hypot(rx, ry))


def _unbound_reference(q: float, e: float, dt: float) -> tuple[float, float]:
    """Hyperbolic Kepler equation, or Barker's equation for a parabola."""
    if e == 1.0:
        target = math.sqrt(GAUSS_K**2 / (2 * q**3)) * dt
        lo, hi = -1e3, 1e3
        for _ in range(300):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if mid**3 / 3 + mid - target > 0 else (mid, hi)
        tan_half = (lo + hi) / 2
        r = q * (1 + tan_half**2)
        nu = 2 * math.atan(tan_half)
        return r * math.cos(nu), r * math.sin(nu)
    a = q / (e - 1)
    mean = GAUSS_K / a**1.5 * dt
    lo, hi = -50.0, 50.0
    for _ in range(300):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if e * math.sinh(mid) - mid - mean > 0 else (mid, hi)
    anomaly = (lo + hi) / 2
    return a * (e - math.cosh(anomaly)), a * math.sqrt(e * e - 1) * math.sinh(anomaly)


@pytest.mark.parametrize("e", [1.0, 1.0007, 1.2, 3.0])
@pytest.mark.parametrize("dt", [-400.0, -30.0, 0.5, 60.0, 400.0])
def test_kepler_solver_unbound_orbits(e: float, dt: float) -> None:
    elements = OrbitalElements("t", "t", "comet", 0.8, e, 0.0, 0.0, 0.0, 2461000.0, 2461000.0)
    x, y, _ = heliocentric_ecliptic(elements, 2461000.0 + dt)
    rx, ry = _unbound_reference(0.8, e, dt)
    assert math.hypot(x - rx, y - ry) < 1e-9


def test_compute_night_unchanged_by_cache() -> None:
    location = Location(LATITUDE, LONGITUDE, 100)
    a = compute_night(location, date(2026, 10, 20), with_planets=False)
    b = compute_night(location, date(2026, 10, 20), with_planets=True)
    assert a.astro_dusk == b.astro_dusk
    assert b.planets and not a.planets


# --- Home Assistant level -------------------------------------------------------

from homeassistant.const import (  # noqa: E402
    CONF_ELEVATION,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.astrocast.const import CONF_LOCATION, DOMAIN  # noqa: E402
from custom_components.astrocast.sensor import AstroCastSensor  # noqa: E402


def test_large_attributes_are_not_recorded() -> None:
    combined = AstroCastSensor._Entity__combined_unrecorded_attributes
    assert {"nights", "upcoming", "objects", "planets", "providers", "factors"} <= combined


async def test_astronomical_night_off_without_darkness(
    hass: HomeAssistant, freezer, mock_providers
) -> None:
    """London in June has no astronomical night: the sensor is off, not unknown."""
    freezer.move_to(datetime(2026, 6, 21, 23, 0, tzinfo=UTC))
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="London",
        unique_id="51.5000_-0.1200",
        data={CONF_LATITUDE: 51.5, CONF_LONGITUDE: -0.12, CONF_ELEVATION: 20.0},
        options={"favorites": []},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity = next(
        e for e in registry.entities.values() if e.unique_id.endswith("_astronomical_night")
    )
    assert hass.states.get(entity.entity_id).state == "off"


async def test_reconfigure_with_prefilled_elevation_looks_it_up(
    hass: HomeAssistant, setup_integration
) -> None:
    entry = setup_integration
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Ailleurs",
            CONF_LOCATION: {CONF_LATITUDE: 44.6, CONF_LONGITUDE: 5.9},
            CONF_ELEVATION: entry.data[CONF_ELEVATION],  # value pre-filled by the form
        },
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_ELEVATION] == 63


async def test_dashboard_updated_after_options_reload(
    hass: HomeAssistant, setup_integration, hass_ws_client
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "astrocast/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["site"]["equipment"] == "small_telescope"
    hass.config_entries.async_update_entry(
        setup_integration,
        options={**setup_integration.options, "equipment": "binoculars"},
    )
    await hass.async_block_till_done()
    msg = await asyncio.wait_for(client.receive_json(), 10)
    assert msg["event"]["site"]["equipment"] == "binoculars"


async def test_storage_removed_with_entry(
    hass: HomeAssistant, setup_integration, hass_storage, freezer
) -> None:
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    entry = setup_integration
    key = f"{DOMAIN}.{entry.entry_id}"
    freezer.tick(timedelta(seconds=40))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert key in hass_storage
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


def test_card_version_matches_manifest() -> None:
    """The version printed by the card follows the integration version."""
    root = Path(__file__).parent.parent / "custom_components" / "astrocast"
    version = json.loads((root / "manifest.json").read_text())["version"]
    card = (root / "frontend" / "astrocast-card.js").read_text()
    assert f'const VERSION = "{version}";' in card
