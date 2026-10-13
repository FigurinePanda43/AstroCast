"""Websocket API used by the AstroCast dashboard card and panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
import voluptuous as vol

from .const import CONF_FAVORITES, DOMAIN
from .coordinator import AstroCastCoordinator, signal_update
from .engine.ephemeris import PLANETS
from .i18n import body_name, lang_of
from .serialize import forecast_to_dict
from .services import async_set_favorite, object_visibility, resolve_object


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    """Register websocket commands."""
    websocket_api.async_register_command(hass, ws_sites)
    websocket_api.async_register_command(hass, ws_forecast)
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_object)
    websocket_api.async_register_command(hass, ws_search)
    websocket_api.async_register_command(hass, ws_favorite)


def _loaded(hass: HomeAssistant) -> list[Any]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def _coordinator(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> AstroCastCoordinator | None:
    entries = _loaded(hass)
    entry_id = msg.get("entry_id")
    entry = next((e for e in entries if e.entry_id == entry_id), None) if entry_id else None
    if entry is None and not entry_id and entries:
        entry = entries[0]
    if entry is None:
        connection.send_error(msg["id"], "not_found", "AstroCast site not found or not loaded")
        return None
    return entry.runtime_data


def _payload(
    hass: HomeAssistant, coordinator: AstroCastCoordinator, language: str
) -> dict[str, Any]:
    payload = forecast_to_dict(
        coordinator.data,
        language,
        coordinator.shared.catalog,
        coordinator.favorites,
        coordinator.provider_report(),
    )
    payload["entry_id"] = coordinator.config_entry.entry_id
    payload["health"] = coordinator.health()
    return payload


def _language(hass: HomeAssistant, msg: dict[str, Any]) -> str:
    return lang_of(msg.get("language") or hass.config.language)


@websocket_api.websocket_command({vol.Required("type"): "astrocast/sites"})
@callback
def ws_sites(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List loaded observing sites."""
    connection.send_result(
        msg["id"],
        [{"entry_id": e.entry_id, "title": e.title} for e in _loaded(hass)],
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "astrocast/forecast",
        vol.Optional("entry_id"): str,
        vol.Optional("language"): str,
    }
)
@websocket_api.async_response
async def ws_forecast(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the full forecast of a site."""
    coordinator = _coordinator(hass, connection, msg)
    if coordinator is None:
        return
    payload = await hass.async_add_executor_job(_payload, hass, coordinator, _language(hass, msg))
    connection.send_result(msg["id"], payload)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "astrocast/subscribe",
        vol.Optional("entry_id"): str,
        vol.Optional("language"): str,
    }
)
@websocket_api.async_response
async def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the forecast now and every time it is recomputed."""
    coordinator = _coordinator(hass, connection, msg)
    if coordinator is None:
        return
    language = _language(hass, msg)
    msg_id = msg["id"]
    entry_id = coordinator.config_entry.entry_id

    async def send() -> None:
        # Look the coordinator up again: the entry may have been reloaded.
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.state not in (
            ConfigEntryState.LOADED,
            ConfigEntryState.SETUP_IN_PROGRESS,
        ):
            return
        current: AstroCastCoordinator | None = getattr(entry, "runtime_data", None)
        if current is None or current.data is None:
            return
        payload = await hass.async_add_executor_job(_payload, hass, current, language)
        connection.send_message(websocket_api.event_message(msg_id, payload))

    @callback
    def on_update() -> None:
        hass.async_create_task(send(), "astrocast websocket update")

    connection.subscriptions[msg_id] = async_dispatcher_connect(
        hass, signal_update(entry_id), on_update
    )
    connection.send_result(msg_id)
    await send()


@websocket_api.websocket_command(
    {
        vol.Required("type"): "astrocast/object",
        vol.Required("object_id"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_object(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Visibility of one object over the forecast nights."""
    coordinator = _coordinator(hass, connection, msg)
    if coordinator is None:
        return
    result = await hass.async_add_executor_job(object_visibility, coordinator, msg["object_id"])
    connection.send_result(msg["id"], result)


def search_objects(
    coordinator: AstroCastCoordinator, query: str, language: str, limit: int = 25
) -> list[dict[str, Any]]:
    """Search planets, the Moon, the deep-sky catalog and small bodies."""
    needle = query.strip().lower()
    results: list[dict[str, Any]] = []
    if not needle:
        return results
    favorites = set(coordinator.favorites)
    for key in (*PLANETS, "moon"):
        name = body_name(language, key)
        if needle in key or needle in name.lower():
            results.append(
                {
                    "id": key,
                    "kind": "moon" if key == "moon" else "planet",
                    "type": key,
                    "name": name,
                    "favorite": key in favorites,
                }
            )
    for obj in coordinator.shared.catalog.search(query, limit):
        results.append(
            {
                "id": obj.id,
                "kind": "dso",
                "type": obj.type,
                "name": obj.label(language),
                "constellation": obj.constellation,
                "mag": obj.mag,
                "favorite": obj.id in favorites,
            }
        )
    for elements in (*coordinator.shared.comets, *coordinator.shared.asteroids):
        if needle in elements.name.lower():
            results.append(
                {
                    "id": elements.id,
                    "kind": elements.kind,
                    "type": elements.kind,
                    "name": elements.name,
                    "favorite": elements.id in favorites,
                }
            )
    return results[:limit]


@websocket_api.websocket_command(
    {
        vol.Required("type"): "astrocast/search",
        vol.Required("query"): str,
        vol.Optional("entry_id"): str,
        vol.Optional("language"): str,
    }
)
@callback
def ws_search(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Search objects by name or designation."""
    coordinator = _coordinator(hass, connection, msg)
    if coordinator is None:
        return
    connection.send_result(
        msg["id"], search_objects(coordinator, msg["query"], _language(hass, msg))
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "astrocast/favorite",
        vol.Required("object_id"): str,
        vol.Required("favorite"): bool,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_favorite(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Add or remove a favourite object (administrators only)."""
    coordinator = _coordinator(hass, connection, msg)
    if coordinator is None:
        return
    object_id = msg["object_id"]
    if msg["favorite"]:
        try:
            object_id = resolve_object(coordinator, object_id)
        except ServiceValidationError:
            connection.send_error(msg["id"], "unknown_object", f"Unknown object: {object_id}")
            return
    favorites = await async_set_favorite(hass, coordinator, object_id, msg["favorite"])
    connection.send_result(msg["id"], {CONF_FAVORITES: favorites})
