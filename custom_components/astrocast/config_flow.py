"""Config flow for AstroCast: site on a map, then observing preferences."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ELEVATION, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
import voluptuous as vol

from .const import (
    CONF_BORTLE,
    CONF_DEW_HEATERS,
    CONF_EQUIPMENT,
    CONF_FAVORITES,
    CONF_HORIZON,
    CONF_LOCATION,
    CONF_MIN_ALTITUDE,
    CONF_SHOW_PANEL,
    CONF_SQM,
    CONF_STATION_HUMIDITY,
    CONF_STATION_TEMPERATURE,
    CONF_THRESHOLD,
    DEFAULT_BORTLE,
    DEFAULT_DEW_HEATERS,
    DEFAULT_EQUIPMENT,
    DEFAULT_MIN_ALTITUDE,
    DEFAULT_SHOW_PANEL,
    DEFAULT_THRESHOLD,
    DOMAIN,
    EQUIPMENT_OPTIONS,
)
from .coordinator import http_headers
from .engine.ephemeris import PLANETS
from .engine.horizon import HorizonError, format_horizon, parse_horizon
from .i18n import body_name, lang_of
from .providers.open_meteo import fetch_elevation


def _location_schema(
    hass: HomeAssistant,
    name: str,
    latitude: float,
    longitude: float,
    elevation: float | None,
) -> vol.Schema:
    elevation_key = (
        vol.Optional(CONF_ELEVATION, description={"suggested_value": elevation})
        if elevation is not None
        else vol.Optional(CONF_ELEVATION)
    )
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=name): TextSelector(),
            vol.Required(
                CONF_LOCATION, default={CONF_LATITUDE: latitude, CONF_LONGITUDE: longitude}
            ): LocationSelector(LocationSelectorConfig(radius=False, icon="mdi:telescope")),
            elevation_key: NumberSelector(
                NumberSelectorConfig(
                    min=-500, max=9000, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="m"
                )
            ),
        }
    )


def _preferences_schema(options: dict[str, Any]) -> dict[Any, Any]:
    return {
        vol.Required(
            CONF_BORTLE, default=str(options.get(CONF_BORTLE, DEFAULT_BORTLE))
        ): SelectSelector(
            SelectSelectorConfig(
                options=[str(i) for i in range(1, 10)],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="bortle",
            )
        ),
        vol.Required(
            CONF_EQUIPMENT, default=options.get(CONF_EQUIPMENT, DEFAULT_EQUIPMENT)
        ): SelectSelector(
            SelectSelectorConfig(
                options=EQUIPMENT_OPTIONS,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="equipment",
            )
        ),
        vol.Required(
            CONF_MIN_ALTITUDE, default=options.get(CONF_MIN_ALTITUDE, DEFAULT_MIN_ALTITUDE)
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=60, step=5, mode=NumberSelectorMode.SLIDER, unit_of_measurement="°"
            )
        ),
        vol.Required(
            CONF_THRESHOLD, default=options.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)
        ): NumberSelector(
            NumberSelectorConfig(min=30, max=90, step=5, mode=NumberSelectorMode.SLIDER)
        ),
        vol.Required(
            CONF_DEW_HEATERS, default=options.get(CONF_DEW_HEATERS, DEFAULT_DEW_HEATERS)
        ): BooleanSelector(),
    }


def _valid_coordinates(latitude: float, longitude: float) -> bool:
    return (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90.0 <= latitude <= 90.0
        and -180.0 <= longitude <= 180.0
    )


async def _resolve_elevation(
    hass: HomeAssistant, latitude: float, longitude: float, value: Any
) -> float:
    """Use the entered elevation, the home elevation or the Copernicus DEM."""
    if value is not None and value != "":
        return float(value)
    if (
        abs(latitude - hass.config.latitude) < 1e-4
        and abs(longitude - hass.config.longitude) < 1e-4
        and hass.config.elevation
    ):
        return float(hass.config.elevation)
    found = await fetch_elevation(
        async_get_clientsession(hass), latitude, longitude, http_headers()
    )
    if found is not None:
        return round(found)
    return float(hass.config.elevation or 0)


STATION_PAIRS = (
    (CONF_STATION_TEMPERATURE, CONF_STATION_HUMIDITY),
    (CONF_STATION_HUMIDITY, CONF_STATION_TEMPERATURE),
)


def _normalise_options(user_input: dict[str, Any]) -> dict[str, Any]:
    options = dict(user_input)
    options[CONF_BORTLE] = int(options[CONF_BORTLE])
    options[CONF_MIN_ALTITUDE] = int(options[CONF_MIN_ALTITUDE])
    options[CONF_THRESHOLD] = int(options[CONF_THRESHOLD])
    if options.get(CONF_SQM) in (None, "", 0):
        options.pop(CONF_SQM, None)
    return options


class AstroCastConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an observing site."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._site: dict[str, Any] = {}
        self._name = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose the site on a map."""
        errors: dict[str, str] = {}
        if user_input is not None:
            location = user_input[CONF_LOCATION]
            latitude = float(location[CONF_LATITUDE])
            longitude = float(location[CONF_LONGITUDE])
            if not _valid_coordinates(latitude, longitude):
                errors[CONF_LOCATION] = "invalid_location"
            else:
                await self.async_set_unique_id(f"{latitude:.4f}_{longitude:.4f}")
                self._abort_if_unique_id_configured()
                self._name = user_input[CONF_NAME].strip() or self.hass.config.location_name
                self._site = {
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                    CONF_ELEVATION: await _resolve_elevation(
                        self.hass, latitude, longitude, user_input.get(CONF_ELEVATION)
                    ),
                }
                return await self.async_step_observing()

        return self.async_show_form(
            step_id="user",
            data_schema=_location_schema(
                self.hass,
                self.hass.config.location_name,
                self.hass.config.latitude,
                self.hass.config.longitude,
                None,
            ),
            errors=errors,
        )

    async def async_step_observing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Observing preferences."""
        if user_input is not None:
            options = _normalise_options(user_input)
            options[CONF_FAVORITES] = []
            options[CONF_SHOW_PANEL] = DEFAULT_SHOW_PANEL
            return self.async_create_entry(title=self._name, data=self._site, options=options)
        return self.async_show_form(
            step_id="observing",
            data_schema=vol.Schema(_preferences_schema({})),
            description_placeholders={"elevation": f"{self._site.get(CONF_ELEVATION, 0):.0f}"},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Move or rename an existing site."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            location = user_input[CONF_LOCATION]
            latitude = float(location[CONF_LATITUDE])
            longitude = float(location[CONF_LONGITUDE])
            if not _valid_coordinates(latitude, longitude):
                errors[CONF_LOCATION] = "invalid_location"
            else:
                await self.async_set_unique_id(f"{latitude:.4f}_{longitude:.4f}")
                if self.unique_id != entry.unique_id:
                    self._abort_if_unique_id_configured()
                elevation = user_input.get(CONF_ELEVATION)
                moved = (
                    abs(latitude - entry.data[CONF_LATITUDE]) > 1e-4
                    or abs(longitude - entry.data[CONF_LONGITUDE]) > 1e-4
                )
                previous = entry.data.get(CONF_ELEVATION)
                # The form pre-fills the old elevation: once the marker has moved,
                # an unchanged value means "look it up again".
                if (
                    moved
                    and elevation is not None
                    and previous is not None
                    and abs(float(elevation) - float(previous)) < 0.5
                ):
                    elevation = None
                if elevation is None and not moved:
                    elevation = previous
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=self.unique_id,
                    title=user_input[CONF_NAME].strip() or entry.title,
                    data={
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                        CONF_ELEVATION: await _resolve_elevation(
                            self.hass, latitude, longitude, elevation
                        ),
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_location_schema(
                self.hass,
                entry.title,
                entry.data[CONF_LATITUDE],
                entry.data[CONF_LONGITUDE],
                entry.data.get(CONF_ELEVATION),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AstroCastOptionsFlow:
        """Options flow."""
        return AstroCastOptionsFlow()


def favorite_options(hass: HomeAssistant, current: list[str]) -> list[SelectOptionDict]:
    """Selectable favourites: Moon, planets, catalog objects, tracked small bodies."""
    from . import DATA_SHARED  # noqa: PLC0415

    language = lang_of(hass.config.language)
    options: list[SelectOptionDict] = [
        SelectOptionDict(value=key, label=body_name(language, key)) for key in ("moon", *PLANETS)
    ]
    shared = hass.data.get(DATA_SHARED)
    if shared is not None:
        options += [
            SelectOptionDict(value=obj.id, label=obj.label(language))
            for obj in shared.catalog.objects
        ]
        options += [
            SelectOptionDict(value=e.id, label=e.name) for e in (*shared.comets, *shared.asteroids)
        ]
    known = {o["value"] for o in options}
    options += [SelectOptionDict(value=fid, label=fid) for fid in current if fid not in known]
    return options


class AstroCastOptionsFlow(OptionsFlow):
    """Observing preferences and favourites."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage options."""
        options = dict(self.config_entry.options)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _normalise_options(user_input)
            try:
                horizon = parse_horizon(data.get(CONF_HORIZON))
            except HorizonError:
                errors[CONF_HORIZON] = "invalid_horizon"
            else:
                if horizon:
                    data[CONF_HORIZON] = format_horizon(horizon)
                else:
                    data.pop(CONF_HORIZON, None)
            # The station needs both sensors (the dew point uses both).
            for key, other in STATION_PAIRS:
                if not data.get(key) and data.get(other):
                    errors[key] = "station_incomplete"
            if not errors:
                return self.async_create_entry(data=data)
            options.update(user_input)
        favorites = list(options.get(CONF_FAVORITES, []))
        sqm = options.get(CONF_SQM)
        schema: dict[Any, Any] = _preferences_schema(options)
        schema[vol.Optional(CONF_SQM, description={"suggested_value": sqm} if sqm else None)] = (
            NumberSelector(
                NumberSelectorConfig(
                    min=16.0,
                    max=22.5,
                    step=0.05,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="mag/arcsec²",
                )
            )
        )
        for key, device_class in (
            (CONF_STATION_TEMPERATURE, SensorDeviceClass.TEMPERATURE),
            (CONF_STATION_HUMIDITY, SensorDeviceClass.HUMIDITY),
        ):
            current = options.get(key)
            schema[
                vol.Optional(key, description={"suggested_value": current} if current else None)
            ] = EntitySelector(EntitySelectorConfig(domain="sensor", device_class=device_class))
        horizon = options.get(CONF_HORIZON)
        schema[
            vol.Optional(
                CONF_HORIZON, description={"suggested_value": horizon} if horizon else None
            )
        ] = TextSelector()
        schema[vol.Optional(CONF_FAVORITES, default=favorites)] = SelectSelector(
            SelectSelectorConfig(
                options=favorite_options(self.hass, favorites),
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
                sort=False,
            )
        )
        schema[
            vol.Required(CONF_SHOW_PANEL, default=options.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL))
        ] = BooleanSelector()
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
