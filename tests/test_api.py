"""Services, websocket API, diagnostics and resilience."""

from __future__ import annotations

from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.astrocast.const import CONF_FAVORITES, DOMAIN
from custom_components.astrocast.diagnostics import async_get_config_entry_diagnostics

from .conftest import LATITUDE, LONGITUDE, NOW, load_fixture


async def test_get_forecast_service(hass: HomeAssistant, setup_integration) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "get_forecast",
        {"config_entry_id": setup_integration.entry_id, "days": 3},
        blocking=True,
        return_response=True,
    )
    assert response["site"] == "Jardin"
    assert len(response["nights"]) == 3
    assert response["nights"][0]["deep_sky"]["score"] is not None
    assert response["nights"][0]["top_objects"]
    assert response["events"]


@pytest.mark.parametrize("query", ["Jupiter", "M42", "orion nebula", "NGC 1976"])
async def test_get_object_service(hass: HomeAssistant, setup_integration, query: str) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "get_object_visibility",
        {"config_entry_id": setup_integration.entry_id, "object": query},
        blocking=True,
        return_response=True,
    )
    assert len(response["nights"]) == 16
    assert response["tonight"]["max_alt"] > 20
    assert response["best_night"] is not None


async def test_service_errors(hass: HomeAssistant, setup_integration) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "get_object_visibility",
            {"config_entry_id": setup_integration.entry_id, "object": "Planet X"},
            blocking=True,
            return_response=True,
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "get_forecast",
            {"config_entry_id": "nope"},
            blocking=True,
            return_response=True,
        )


async def test_favorite_services(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    await hass.services.async_call(
        DOMAIN,
        "add_favorite",
        {"config_entry_id": entry.entry_id, "object": "Saturne"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "saturn" in entry.options[CONF_FAVORITES]
    await hass.services.async_call(
        DOMAIN,
        "remove_favorite",
        {"config_entry_id": entry.entry_id, "object": "M 31"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "M31" not in entry.options[CONF_FAVORITES]
    registry = er.async_get(hass)
    assert any(e.unique_id.endswith("_favorite_saturn") for e in registry.entities.values())


async def test_websocket_api(hass: HomeAssistant, setup_integration, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "astrocast/sites"})
    msg = await client.receive_json()
    assert msg["result"] == [{"entry_id": setup_integration.entry_id, "title": "Jardin"}]

    await client.send_json({"id": 2, "type": "astrocast/forecast", "language": "fr"})
    msg = await client.receive_json()
    payload = msg["result"]
    assert payload["language"] == "fr"
    assert payload["health"] == "ok"
    assert len(payload["nights"]) == 30
    assert payload["nights"][0]["samples"]["deep_sky"]
    assert payload["nights"][0]["objects"][0]["alt"]
    assert any(e["title"].startswith(("Pleine Lune", "Nouvelle Lune")) for e in payload["events"])
    assert {f["id"] for f in payload["favorites"]} == {"M31", "jupiter"}

    await client.send_json({"id": 3, "type": "astrocast/search", "query": "veil"})
    msg = await client.receive_json()
    assert {"NGC6960", "NGC6992"} <= {r["id"] for r in msg["result"]}

    await client.send_json({"id": 4, "type": "astrocast/object", "object_id": "saturn"})
    msg = await client.receive_json()
    assert msg["result"]["tonight"]["kind"] == "planet"

    await client.send_json(
        {"id": 5, "type": "astrocast/favorite", "object_id": "M45", "favorite": True}
    )
    msg = await client.receive_json()
    assert msg["success"]
    assert "M45" in msg["result"]["favorites"]

    await client.send_json({"id": 6, "type": "astrocast/forecast", "entry_id": "missing"})
    msg = await client.receive_json()
    assert not msg["success"]


async def test_websocket_subscription(
    hass: HomeAssistant, setup_integration, hass_ws_client
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "astrocast/subscribe"})
    msg = await client.receive_json()
    assert msg["success"]
    msg = await client.receive_json()
    assert msg["type"] == "event"
    assert msg["event"]["site"]["name"] == "Jardin"
    # A coordinator refresh pushes a new payload.
    await setup_integration.runtime_data.async_refresh()
    msg = await client.receive_json()
    assert msg["type"] == "event"


async def test_diagnostics(hass: HomeAssistant, setup_integration) -> None:
    result = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert result["entry"]["data"]["latitude"] == round(LATITUDE, 1)
    assert result["health"] == "ok"
    assert result["series"]["ensemble"]["members"] >= 5
    assert result["catalog_objects"] > 600
    assert result["forecast"]["nights"]


async def test_degraded_when_7timer_fails(
    hass: HomeAssistant,
    frozen_now,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """A failing provider degrades the data but never breaks the integration."""
    aioclient_mock.get("https://www.7timer.info/bin/api.pl", exc=aiohttp.ClientError("down"))
    aioclient_mock.get(
        "https://api.open-meteo.com/v1/forecast", json=load_fixture("open_meteo_forecast.json")
    )
    aioclient_mock.get("https://ensemble-api.open-meteo.com/v1/ensemble", status=500)
    aioclient_mock.get(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        json=load_fixture("open_meteo_air_quality.json"),
    )
    aioclient_mock.get("https://ssd-api.jpl.nasa.gov/sbdb_query.api", status=503)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data
    assert coordinator.health() == "degraded"
    report = coordinator.provider_report()
    assert report["7timer"]["failures"] == 1
    assert report["ensemble"]["active"] is False
    forecast = coordinator.data
    hour = forecast.timeline.at(NOW + timedelta(hours=2))
    assert hour.sources["seeing"] == "jetstream"
    assert forecast.tonight.deep_sky.score is not None


async def test_works_without_any_weather(
    hass: HomeAssistant,
    frozen_now,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """With every API down, astronomy (moon, objects potential, events) still works."""
    for url in (
        "https://www.7timer.info/bin/api.pl",
        "https://api.open-meteo.com/v1/forecast",
        "https://ensemble-api.open-meteo.com/v1/ensemble",
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        "https://api.met.no/weatherapi/locationforecast/2.0/complete",
        "https://ssd-api.jpl.nasa.gov/sbdb_query.api",
    ):
        aioclient_mock.get(url, exc=TimeoutError())
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    coordinator = config_entry.runtime_data
    assert coordinator.health() == "unavailable"
    forecast = coordinator.data
    assert forecast.tonight.deep_sky.score is None
    assert forecast.tonight.deep_sky.potential is not None
    assert forecast.events
    registry = er.async_get(hass)
    entity = next(e for e in registry.entities.values() if e.unique_id.endswith("_moon_phase"))
    assert hass.states.get(entity.entity_id).state == "waxing_crescent"


async def test_metno_fallback(
    hass: HomeAssistant,
    frozen_now,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get("https://www.7timer.info/bin/api.pl", text="{}")
    aioclient_mock.get("https://api.open-meteo.com/v1/forecast", status=429)
    aioclient_mock.get("https://ensemble-api.open-meteo.com/v1/ensemble", status=429)
    aioclient_mock.get("https://air-quality-api.open-meteo.com/v1/air-quality", status=429)
    aioclient_mock.get(
        "https://api.met.no/weatherapi/locationforecast/2.0/complete",
        json=load_fixture("metno_complete.json"),
    )
    aioclient_mock.get("https://ssd-api.jpl.nasa.gov/sbdb_query.api", status=503)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data
    assert "met_no" in coordinator.series
    assert coordinator.data.tonight.deep_sky.score is not None
    assert coordinator.provider_report()["open_meteo"]["last_error"].startswith("rate limited")


async def test_cache_survives_restart(
    hass: HomeAssistant, setup_integration, aioclient_mock: AiohttpClientMocker, freezer
) -> None:
    """Fresh cached data is reused after a reload instead of calling the APIs again."""
    entry = setup_integration
    freezer.tick(timedelta(seconds=40))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()  # flush the delayed storage write
    calls = aioclient_mock.call_count
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == calls
    assert entry.runtime_data.data.tonight.deep_sky.score is not None


async def test_two_sites(hass: HomeAssistant, setup_integration, hass_ws_client) -> None:
    second = MockConfigEntry(
        domain=DOMAIN,
        title="Montagne",
        unique_id="44.5000_6.0000",
        data={"latitude": 44.5, "longitude": 6.0, "elevation": 1500.0},
        options={
            "bortle": 2,
            "equipment": "binoculars",
            "min_altitude": 15,
            "threshold": 60,
            "favorites": [],
            "show_panel": True,
        },
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "astrocast/sites"})
    msg = await client.receive_json()
    assert {s["title"] for s in msg["result"]} == {"Jardin", "Montagne"}
    assert second.runtime_data.shared is setup_integration.runtime_data.shared
    assert second.data["longitude"] != LONGITUDE
