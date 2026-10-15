"""Sensors, binary sensors, calendars and favourites."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.astrocast.const import CONF_FAVORITES

from .conftest import NOW


def _state(hass: HomeAssistant, key: str):
    registry = er.async_get(hass)
    entry = next(e for e in registry.entities.values() if e.unique_id.endswith(f"_{key}"))
    return hass.states.get(entry.entity_id)


async def test_score_sensors(hass: HomeAssistant, setup_integration) -> None:
    tonight = _state(hass, "deep_sky_tonight")
    assert 0 <= int(tonight.state) <= 100
    attrs = tonight.attributes
    assert attrs["night"] == "2026-10-13"
    assert attrs["rating"] in ("excellent", "good", "fair", "poor", "bad")
    assert attrs["window_start"] < attrs["window_end"]
    assert attrs["forecast_tier"] == "detailed"
    assert attrs["unit_of_measurement"] == "%"
    assert int(_state(hass, "planetary_tonight").state) > 0
    now = _state(hass, "deep_sky_now")
    assert now.attributes["limiting_factor"] in (None, "wind", "clouds", "seeing", "transparency")


async def test_other_sensors(hass: HomeAssistant, setup_integration) -> None:
    assert _state(hass, "moon_phase").state == "waxing_crescent"
    assert 5 < float(_state(hass, "moon_illumination").state) < 20
    assert _state(hass, "astronomical_dusk").state.startswith("2026-10-13T18:")
    assert _state(hass, "astronomical_dawn").state.startswith("2026-10-14T04:")
    best = _state(hass, "best_night")
    assert best.attributes["nights"]
    assert best.attributes["date"] >= "2026-10-13"
    assert _state(hass, "top_object").state.startswith("M ")
    assert int(_state(hass, "visible_planets").state) >= 3
    event = _state(hass, "next_event")
    assert event.attributes["title"]
    assert _state(hass, "data_sources").state == "ok"
    assert float(_state(hass, "cloud_cover").state) >= 0
    # Disabled by default.
    registry = er.async_get(hass)
    seeing = next(e for e in registry.entities.values() if e.unique_id.endswith("_seeing"))
    assert seeing.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_narrowband_and_session_attributes(hass: HomeAssistant, setup_integration) -> None:
    narrow = _state(hass, "narrowband_tonight")
    assert 0 <= int(narrow.state) <= 100
    assert narrow.attributes["night"] == "2026-10-13"
    assert 0 <= int(_state(hass, "narrowband_now").state) <= 100
    deep = _state(hass, "deep_sky_tonight").attributes
    assert deep["window_hours"] > 0
    assert 0 < deep["duration_factor"] <= 1
    assert deep["window_quality"] >= int(_state(hass, "deep_sky_tonight").state)
    best = _state(hass, "best_night").attributes
    assert "narrowband" in best["nights"][0]
    assert "best_narrowband_date" in best


async def test_dew_sensors(hass: HomeAssistant, setup_integration) -> None:
    risk = _state(hass, "dew_risk")
    assert risk.state in ("low", "moderate", "high")
    assert risk.attributes["optics_margin"] is not None
    assert risk.attributes["dew_heaters"] is False
    onset = _state(hass, "dew_onset")
    # The recorded forecast saturates the air late in the evening of the 13th.
    assert onset.attributes["expected"] is True
    assert onset.state.startswith("2026-10-13T2")
    assert risk.attributes["tonight_onset"] == onset.state
    assert _state(hass, "deep_sky_tonight").attributes["dew_onset"] == onset.state


async def test_favorite_sensors(hass: HomeAssistant, setup_integration) -> None:
    m31 = _state(hass, "favorite_M31")
    assert m31.attributes["friendly_name"].endswith("M 31 – Andromeda Galaxy next window")
    assert m31.state.startswith("2026-10-13")
    assert len(m31.attributes["nights"]) == 16
    assert m31.attributes["tonight_score"] > 60


async def test_favorites_update_without_reload(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    coordinator = entry.runtime_data
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_FAVORITES: ["M31", "NGC7000"]}
    )
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is coordinator  # no reload
    assert _state(hass, "favorite_NGC7000") is not None
    registry = er.async_get(hass)
    assert not any(e.unique_id.endswith("_favorite_jupiter") for e in registry.entities.values())
    assert {f.id for f in coordinator.data.favorites} == {"M31", "NGC7000"}


async def test_other_options_reload(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    coordinator = entry.runtime_data
    hass.config_entries.async_update_entry(entry, options={**entry.options, "threshold": 70})
    await hass.async_block_till_done()
    assert entry.runtime_data is not coordinator
    assert entry.runtime_data.site.threshold == 70


async def test_binary_sensors(hass: HomeAssistant, setup_integration, freezer) -> None:
    night = _state(hass, "astronomical_night")
    assert night.state == STATE_ON  # 19:00 UTC, astronomical dusk was 18:35
    dawn = dt_util.parse_datetime(night.attributes["end"])
    assert dawn.hour == 4
    good = _state(hass, "good_conditions")
    assert good.state in (STATE_ON, STATE_OFF)
    assert good.attributes["threshold"] == 60
    # The state flips exactly at astronomical dawn, without waiting for a refresh.
    freezer.move_to(dawn + timedelta(seconds=1))
    async_fire_time_changed(hass, dawn + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert _state(hass, "astronomical_night").state == STATE_OFF


async def test_calendars(hass: HomeAssistant, setup_integration) -> None:
    registry = er.async_get(hass)
    windows = next(
        e for e in registry.entities.values() if e.unique_id.endswith("_observing_windows")
    )
    events_cal = next(
        e for e in registry.entities.values() if e.unique_id.endswith("_astronomy_events")
    )
    response = await hass.services.async_call(
        CALENDAR_DOMAIN,
        "get_events",
        {
            "entity_id": [windows.entity_id, events_cal.entity_id],
            "start_date_time": NOW.isoformat(),
            "end_date_time": (NOW + timedelta(days=60)).isoformat(),
        },
        blocking=True,
        return_response=True,
    )
    windows_events = response[windows.entity_id]["events"]
    assert windows_events
    assert any("Deep-sky window" in e["summary"] for e in windows_events)
    assert all("/100" in e["summary"] for e in windows_events)
    assert all("Session of" in e["description"] for e in windows_events)
    astro = response[events_cal.entity_id]["events"]
    titles = [e["summary"] for e in astro]
    assert any("meteor shower" in t for t in titles)
    assert any(t == "Full Moon" for t in titles)
    state = hass.states.get(windows.entity_id)
    assert state.attributes["message"]
