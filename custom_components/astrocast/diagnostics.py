"""Diagnostics support for AstroCast."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .coordinator import AstroCastConfigEntry
from .engine.timeutil import iso


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AstroCastConfigEntry
) -> dict[str, Any]:
    """Return diagnostics (coordinates are rounded to ~10 km for privacy)."""
    coordinator = entry.runtime_data
    data = dict(entry.data)
    for key in (CONF_LATITUDE, CONF_LONGITUDE):
        if key in data:
            data[key] = round(float(data[key]), 1)
    forecast = coordinator.data
    result: dict[str, Any] = {
        "entry": {"data": data, "options": dict(entry.options)},
        "health": coordinator.health(),
        "providers": coordinator.provider_report(),
        "series": {
            name: {
                "points": len(series.times),
                "fields": sorted(series.fields),
                "fetched": series.fetched.isoformat(),
                "members": len(series.members[0]) if series.members else None,
            }
            for name, series in coordinator.series.items()
        },
        "catalog_objects": len(coordinator.shared.catalog),
        "comets": len(coordinator.shared.comets),
        "asteroids": len(coordinator.shared.asteroids),
    }
    if forecast is not None:
        result["forecast"] = {
            "generated": iso(forecast.generated),
            "timeline_hours": len(forecast.timeline.hours),
            "now": {"scores": forecast.now.scores, "tier": forecast.now.tier},
            "nights": [
                {
                    "date": n.ephem.night.isoformat(),
                    "deep_sky": n.deep_sky.score,
                    "planetary": n.planetary.score,
                    "narrowband": n.narrowband.score,
                    "window_hours": n.deep_sky.window_hours,
                    "tier": n.deep_sky.tier,
                }
                for n in forecast.nights
            ],
            "events": len(forecast.events),
        }
    return result
