"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import pytest

from homeassistant.const import CONF_ELEVATION, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.astrocast.const import (
    CONF_BORTLE,
    CONF_EQUIPMENT,
    CONF_FAVORITES,
    CONF_MIN_ALTITUDE,
    CONF_SHOW_PANEL,
    CONF_THRESHOLD,
    DOMAIN,
)

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 13, 19, 0, tzinfo=UTC)
LATITUDE = 48.84
LONGITUDE = 2.34

pytest_plugins = "pytest_homeassistant_custom_component"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> Generator[None]:
    """Enable custom integrations in every test."""
    return


@pytest.fixture
def frozen_now(freezer: Any) -> datetime:
    """Freeze time at the moment the fixtures were recorded."""
    freezer.move_to(NOW)
    return NOW


@pytest.fixture
def mock_providers(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Serve every external API from recorded responses."""
    aioclient_mock.get(
        "https://www.7timer.info/bin/api.pl", text=json.dumps(load_fixture("7timer_astro.json"))
    )
    aioclient_mock.get(
        "https://api.open-meteo.com/v1/forecast", json=load_fixture("open_meteo_forecast.json")
    )
    aioclient_mock.get(
        "https://ensemble-api.open-meteo.com/v1/ensemble",
        json=load_fixture("open_meteo_ensemble.json"),
    )
    aioclient_mock.get(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        json=load_fixture("open_meteo_air_quality.json"),
    )
    aioclient_mock.get(
        "https://api.met.no/weatherapi/locationforecast/2.0/complete",
        json=load_fixture("metno_complete.json"),
    )
    aioclient_mock.get(
        "https://api.open-meteo.com/v1/elevation", json={"elevation": [63.0]}
    )

    aioclient_mock.get(
        "https://ssd-api.jpl.nasa.gov/sbdb_query.api?sb-kind=c", json=load_fixture("jpl_comets.json")
    )
    aioclient_mock.get(
        "https://ssd-api.jpl.nasa.gov/sbdb_query.api?sb-kind=a",
        json=load_fixture("jpl_asteroids.json"),
    )
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """An observing site."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Jardin",
        unique_id=f"{LATITUDE:.4f}_{LONGITUDE:.4f}",
        data={CONF_LATITUDE: LATITUDE, CONF_LONGITUDE: LONGITUDE, CONF_ELEVATION: 100.0},
        options={
            CONF_BORTLE: 4,
            CONF_EQUIPMENT: "small_telescope",
            CONF_MIN_ALTITUDE: 20,
            CONF_THRESHOLD: 60,
            CONF_FAVORITES: ["M31", "jupiter"],
            CONF_SHOW_PANEL: True,
        },
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    frozen_now: datetime,
    mock_providers: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Set up the integration with recorded data."""
    hass.config.latitude = LATITUDE
    hass.config.longitude = LONGITUDE
    hass.config.elevation = 100
    hass.config.language = "en"
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
