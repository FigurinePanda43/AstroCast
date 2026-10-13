"""Constants for AstroCast."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "astrocast"
NAME: Final = "AstroCast"
VERSION: Final = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]

PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

# Config entry data
CONF_LOCATION: Final = "location"

# Options
CONF_BORTLE: Final = "bortle"
CONF_SQM: Final = "sqm"
CONF_MIN_ALTITUDE: Final = "min_altitude"
CONF_EQUIPMENT: Final = "equipment"
CONF_THRESHOLD: Final = "threshold"
CONF_FAVORITES: Final = "favorites"
CONF_SHOW_PANEL: Final = "show_panel"

DEFAULT_BORTLE: Final = 4
DEFAULT_MIN_ALTITUDE: Final = 20
DEFAULT_EQUIPMENT: Final = "small_telescope"
DEFAULT_THRESHOLD: Final = 60
DEFAULT_SHOW_PANEL: Final = True

EQUIPMENT_OPTIONS: Final = [
    "naked_eye",
    "binoculars",
    "small_telescope",
    "medium_telescope",
    "large_telescope",
    "astrophotography",
]

UPDATE_INTERVAL: Final = timedelta(minutes=15)

# Provider refresh intervals.
TTL_7TIMER: Final = timedelta(hours=3)
TTL_OPEN_METEO: Final = timedelta(hours=1)
TTL_ENSEMBLE: Final = timedelta(hours=6)
TTL_AIR_QUALITY: Final = timedelta(hours=6)
TTL_MET_NO: Final = timedelta(hours=1)
TTL_SMALL_BODIES: Final = timedelta(hours=24)

# Data older than this is dropped rather than shown as a forecast.
MAX_AGE: Final = {
    "7timer": timedelta(hours=24),
    "open_meteo": timedelta(hours=24),
    "met_no": timedelta(hours=24),
    "ensemble": timedelta(hours=36),
    "cams": timedelta(hours=36),
}

STORAGE_VERSION: Final = 1

URL_BASE: Final = "/astrocast_static"
CARD_FILENAME: Final = "astrocast-card.js"
PANEL_URL: Final = "astrocast"
PANEL_COMPONENT: Final = "astrocast-panel"

SERVICE_GET_FORECAST: Final = "get_forecast"
SERVICE_GET_OBJECT: Final = "get_object_visibility"
SERVICE_ADD_FAVORITE: Final = "add_favorite"
SERVICE_REMOVE_FAVORITE: Final = "remove_favorite"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_OBJECT: Final = "object"
ATTR_DAYS: Final = "days"

ATTRIBUTION: Final = (
    "Weather: 7Timer!, Open-Meteo (CC BY 4.0), MET Norway (CC BY 4.0), CAMS; "
    "orbits: NASA/JPL SBDB; deep-sky catalog: OpenNGC (CC BY-SA 4.0)"
)
