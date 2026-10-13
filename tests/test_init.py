"""Integration setup tests."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.astrocast.const import DOMAIN


async def test_setup_creates_entities(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    unique = {e.unique_id.removeprefix(f"{entry.entry_id}_") for e in entities}
    assert {
        "deep_sky_tonight",
        "planetary_tonight",
        "best_night",
        "moon_phase",
        "astronomical_night",
        "good_conditions",
        "observing_windows",
        "astronomy_events",
        "favorite_M31",
        "favorite_jupiter",
    } <= unique
    for state in hass.states.async_all():
        if state.entity_id.startswith(("sensor.", "binary_sensor.", "calendar.")):
            print(state.entity_id, state.state)


async def test_unload(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert DOMAIN
