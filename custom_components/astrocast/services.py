"""Actions (services) exposed by AstroCast."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DAYS,
    ATTR_OBJECT,
    CONF_FAVORITES,
    DOMAIN,
    SERVICE_ADD_FAVORITE,
    SERVICE_GET_FORECAST,
    SERVICE_GET_OBJECT,
    SERVICE_REMOVE_FAVORITE,
)
from .coordinator import AstroCastCoordinator
from .engine.ephemeris import PLANETS
from .engine.timeutil import iso
from .serialize import (
    event_to_dict,
    now_to_dict,
    object_name,
    profile_to_dict,
    summary_to_dict,
)

ENTRY_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})
FORECAST_SCHEMA = ENTRY_SCHEMA.extend(
    {vol.Optional(ATTR_DAYS, default=7): vol.All(vol.Coerce(int), vol.Range(min=1, max=16))}
)
OBJECT_SCHEMA = ENTRY_SCHEMA.extend({vol.Required(ATTR_OBJECT): cv.string})


def get_coordinator(hass: HomeAssistant, entry_id: str) -> AstroCastCoordinator:
    """Return the coordinator of a loaded AstroCast entry."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_entry",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
    return entry.runtime_data


def resolve_object(coordinator: AstroCastCoordinator, query: str) -> str:
    """Resolve a user-provided object name to a stable identifier."""
    key = query.strip()
    lowered = key.lower()
    if lowered in PLANETS or lowered == "moon":
        return lowered
    from .i18n import STRINGS  # noqa: PLC0415

    for table in STRINGS.values():
        for body in (*PLANETS, "moon"):
            if table.get(body, "").lower() == lowered:
                return body
    if (obj := coordinator.shared.catalog.get(key)) is not None:
        return obj.id
    for elements in (*coordinator.shared.comets, *coordinator.shared.asteroids):
        if (
            lowered in (elements.id.lower(), elements.name.lower())
            or lowered in elements.name.lower()
        ):
            return elements.id
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_object",
        translation_placeholders={"object": query},
    )


def object_visibility(coordinator: AstroCastCoordinator, object_id: str) -> dict[str, Any]:
    """Visibility of any object over the forecast nights (computed on demand)."""
    from .engine.catalog import Catalog  # noqa: PLC0415
    from .engine.objects import (  # noqa: PLC0415
        NightContext,
        evaluate_catalog,
        evaluate_planet,
        evaluate_small_body,
    )
    from .engine.planner import WEATHER_NIGHTS  # noqa: PLC0415
    from .engine.scoring import sample_weather  # noqa: PLC0415
    from .serialize import _night_span, object_to_dict  # noqa: PLC0415

    forecast = coordinator.data
    language = coordinator.hass.config.language
    site = coordinator.site
    catalog = coordinator.shared.catalog
    observer = site.location.observer
    nights = []
    tonight_detail = None
    for index, night in enumerate(forecast.nights[:WEATHER_NIGHTS]):
        weather = sample_weather(forecast.timeline, night.ephem)
        ctx = NightContext.build(
            night.ephem,
            weather,
            site.sky_brightness,
            site.min_altitude,
            site.equipment,
            site.latitude,
            site.horizon,
        )
        if object_id in PLANETS:
            obj = evaluate_planet(ctx, night.ephem.planets[object_id])
        elif object_id == "moon":
            obj = evaluate_planet(ctx, night.ephem.moon)
        elif (dso := catalog.get(object_id)) is not None:
            obj = evaluate_catalog(ctx, Catalog([dso]))[0]
        else:
            elements = next(
                (
                    e
                    for e in (*coordinator.shared.comets, *coordinator.shared.asteroids)
                    if e.id == object_id
                ),
                None,
            )
            obj = evaluate_small_body(ctx, elements, observer, force=True) if elements else None
        if obj is None:
            continue
        if index == 0:
            tonight_detail = object_to_dict(obj, language, _night_span(night.ephem))
            tonight_detail["samples_start"] = iso(night.ephem.times[_night_span(night.ephem)[0]])
        nights.append(
            {
                "date": night.ephem.night.isoformat(),
                "score": obj.best_score,
                "best_time": iso(obj.best_time),
                "window_start": iso(obj.window_start),
                "window_end": iso(obj.window_end),
                "max_altitude": obj.max_alt,
                "visible_hours": obj.hours_visible,
                "transit": iso(obj.transit),
                "weather": ctx.has_weather,
            }
        )
    name = tonight_detail["name"] if tonight_detail else object_id
    best = max((n for n in nights if n["weather"]), key=lambda n: n["score"], default=None)
    return {
        "object": object_id,
        "name": name,
        "tonight": tonight_detail,
        "best_night": best,
        "nights": nights,
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register services."""

    async def get_forecast(call: ServiceCall) -> ServiceResponse:
        coordinator = get_coordinator(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        forecast = coordinator.data
        language = hass.config.language
        days = call.data[ATTR_DAYS]
        best = forecast.best_night()
        return {
            "site": coordinator.site.name,
            "generated": iso(forecast.generated),
            "now": now_to_dict(forecast),
            "best_night": best.ephem.night.isoformat() if best else None,
            "nights": [
                {
                    "date": n.ephem.night.isoformat(),
                    "deep_sky": profile_to_dict(n.deep_sky),
                    "planetary": profile_to_dict(n.planetary),
                    "narrowband": profile_to_dict(n.narrowband),
                    "moon_illumination": round(n.ephem.moon_illumination * 100),
                    "astronomical_dusk": iso(n.ephem.astro_dusk),
                    "astronomical_dawn": iso(n.ephem.astro_dawn),
                    "summary": summary_to_dict(n.summary),
                    "top_objects": [object_name(o, language) for o in n.objects[:5]],
                }
                for n in forecast.nights[:days]
            ],
            "events": [
                event_to_dict(e, language, coordinator.site.name)
                for e in forecast.events
                if e.importance >= 2
            ][:20],
        }

    async def get_object(call: ServiceCall) -> ServiceResponse:
        coordinator = get_coordinator(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        object_id = resolve_object(coordinator, call.data[ATTR_OBJECT])
        return await hass.async_add_executor_job(object_visibility, coordinator, object_id)

    async def set_favorite(call: ServiceCall, add: bool) -> None:
        coordinator = get_coordinator(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        object_id = resolve_object(coordinator, call.data[ATTR_OBJECT])
        await async_set_favorite(hass, coordinator, object_id, add)

    async def add_favorite(call: ServiceCall) -> None:
        await set_favorite(call, True)

    async def remove_favorite(call: ServiceCall) -> None:
        await set_favorite(call, False)

    hass.services.async_register(
        DOMAIN, SERVICE_GET_FORECAST, get_forecast, FORECAST_SCHEMA, SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_OBJECT, get_object, OBJECT_SCHEMA, SupportsResponse.ONLY
    )
    hass.services.async_register(DOMAIN, SERVICE_ADD_FAVORITE, add_favorite, OBJECT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_FAVORITE, remove_favorite, OBJECT_SCHEMA)


async def async_set_favorite(
    hass: HomeAssistant, coordinator: AstroCastCoordinator, object_id: str, add: bool
) -> list[str]:
    """Add or remove a favourite (updates options, which reloads the entry)."""
    entry = coordinator.config_entry
    favorites = list(entry.options.get(CONF_FAVORITES, []))
    if add and object_id not in favorites:
        favorites.append(object_id)
    elif not add and object_id in favorites:
        favorites.remove(object_id)
    else:
        return favorites
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_FAVORITES: favorites}
    )
    return favorites
