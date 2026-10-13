"""AstroCast: astronomy and astrophotography forecasts for Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_FILENAME,
    CONF_FAVORITES,
    CONF_SHOW_PANEL,
    DEFAULT_SHOW_PANEL,
    DOMAIN,
    NAME,
    PANEL_COMPONENT,
    PANEL_URL,
    PLATFORMS,
    URL_BASE,
    VERSION,
)
from .coordinator import (
    AstroCastConfigEntry,
    AstroCastCoordinator,
    AstroCastShared,
    signal_update,
)
from .services import async_setup_services
from .websocket import async_setup_websocket

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
DATA_SHARED = f"{DOMAIN}_shared"
CARD_URL = f"{URL_BASE}/{CARD_FILENAME}?v={VERSION}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the frontend resources, services and websocket commands."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                URL_BASE, str(Path(__file__).parent / "frontend"), cache_headers=False
            )
        ]
    )
    # The card is loaded on every dashboard so it appears in the card picker
    # without any manual resource configuration.
    frontend.add_extra_js_url(hass, CARD_URL)
    async_setup_services(hass)
    async_setup_websocket(hass)
    return True


async def async_get_shared(hass: HomeAssistant) -> AstroCastShared:
    """Shared resources (catalog, small bodies), created on first use."""
    shared: AstroCastShared | None = hass.data.get(DATA_SHARED)
    if shared is None:
        shared = await AstroCastShared.async_create(hass)
        hass.data[DATA_SHARED] = shared
    return shared


async def async_setup_entry(hass: HomeAssistant, entry: AstroCastConfigEntry) -> bool:
    """Set up an observing site."""
    shared = await async_get_shared(hass)
    coordinator = AstroCastCoordinator(hass, entry, shared)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_stale_favorite_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(
        coordinator.async_add_listener(
            lambda: async_dispatcher_send(hass, signal_update(entry.entry_id))
        )
    )
    await _async_update_panel(hass, current=entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AstroCastConfigEntry) -> bool:
    """Unload an observing site."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await _async_update_panel(hass, removing=entry.entry_id)
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: AstroCastConfigEntry) -> None:
    """Apply option changes.

    Favourites are applied in place (no reload: the weather cache, timers and
    dashboard subscriptions stay alive); any other change reloads the entry.
    """
    coordinator = entry.runtime_data
    previous = coordinator.options_snapshot
    current = dict(entry.options)
    coordinator.options_snapshot = current
    changed = {k for k in {*previous, *current} if previous.get(k) != current.get(k)}
    if changed and changed <= {CONF_FAVORITES}:
        await _async_apply_favorites(hass, entry, previous.get(CONF_FAVORITES, []))
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_apply_favorites(
    hass: HomeAssistant, entry: AstroCastConfigEntry, previous: list[str]
) -> None:
    coordinator = entry.runtime_data
    current = list(entry.options.get(CONF_FAVORITES, []))
    _remove_stale_favorite_entities(hass, entry)
    added = [fid for fid in current if fid not in previous]
    if added and coordinator.add_sensor_entities is not None:
        from .sensor import FavoriteSensor  # noqa: PLC0415

        coordinator.add_sensor_entities([FavoriteSensor(coordinator, fid) for fid in added])
    await coordinator.async_refresh()


def _remove_stale_favorite_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove favourite sensors whose object is no longer a favourite."""
    registry = er.async_get(hass)
    favorites = set(entry.options.get(CONF_FAVORITES, []))
    prefix = f"{entry.entry_id}_favorite_"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id.startswith(prefix):
            object_id = entity.unique_id[len(prefix) :]
            if object_id not in favorites:
                registry.async_remove(entity.entity_id)


async def _async_update_panel(
    hass: HomeAssistant,
    current: ConfigEntry | None = None,
    removing: str | None = None,
) -> None:
    """Show the sidebar panel when at least one loaded site enables it."""
    shared: AstroCastShared | None = hass.data.get(DATA_SHARED)
    if shared is None:
        return
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != removing
        and (entry.state is ConfigEntryState.LOADED or entry is current)
    ]
    wanted = any(entry.options.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL) for entry in entries)
    if wanted and not shared.panel_registered:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_COMPONENT,
            sidebar_title=NAME,
            sidebar_icon="mdi:telescope",
            module_url=CARD_URL,
            embed_iframe=False,
            require_admin=False,
        )
        shared.panel_registered = True
    elif not wanted and shared.panel_registered:
        frontend.async_remove_panel(hass, PANEL_URL)
        shared.panel_registered = False
