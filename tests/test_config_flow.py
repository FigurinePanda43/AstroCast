"""Config, reconfigure and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_ELEVATION, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.astrocast.const import (
    CONF_BORTLE,
    CONF_EQUIPMENT,
    CONF_FAVORITES,
    CONF_HORIZON,
    CONF_LOCATION,
    CONF_MIN_ALTITUDE,
    CONF_SHOW_PANEL,
    CONF_SQM,
    CONF_THRESHOLD,
    DOMAIN,
)

from .conftest import LATITUDE, LONGITUDE

PREFERENCES = {
    CONF_BORTLE: "3",
    CONF_EQUIPMENT: "astrophotography",
    CONF_MIN_ALTITUDE: 25,
    CONF_THRESHOLD: 65,
}


async def _start(hass: HomeAssistant):
    hass.config.latitude = LATITUDE
    hass.config.longitude = LONGITUDE
    hass.config.elevation = 120
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_home_location(hass: HomeAssistant, mock_providers) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Jardin", CONF_LOCATION: {CONF_LATITUDE: LATITUDE, CONF_LONGITUDE: LONGITUDE}},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "observing"
    assert result["description_placeholders"]["elevation"] == "120"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PREFERENCES)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jardin"
    assert result["data"] == {
        CONF_LATITUDE: LATITUDE,
        CONF_LONGITUDE: LONGITUDE,
        CONF_ELEVATION: 120.0,
    }
    assert result["options"][CONF_BORTLE] == 3
    assert result["options"][CONF_EQUIPMENT] == "astrophotography"
    assert result["options"][CONF_FAVORITES] == []
    assert result["options"][CONF_SHOW_PANEL] is True
    assert result["result"].unique_id == f"{LATITUDE:.4f}_{LONGITUDE:.4f}"


async def test_user_flow_custom_location_looks_up_elevation(
    hass: HomeAssistant, mock_providers
) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Montagne", CONF_LOCATION: {CONF_LATITUDE: 44.1, CONF_LONGITUDE: 5.2}},
    )
    assert result["step_id"] == "observing"
    assert result["description_placeholders"]["elevation"] == "63"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PREFERENCES)
    assert result["data"][CONF_ELEVATION] == 63


async def test_user_flow_explicit_elevation(hass: HomeAssistant, mock_providers) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Pic",
            CONF_LOCATION: {CONF_LATITUDE: 42.94, CONF_LONGITUDE: 0.14},
            CONF_ELEVATION: 2877,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], PREFERENCES)
    assert result["data"][CONF_ELEVATION] == 2877


async def test_duplicate_site_aborts(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Again", CONF_LOCATION: {CONF_LATITUDE: LATITUDE, CONF_LONGITUDE: LONGITUDE}},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_moves_site(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Nouveau site", CONF_LOCATION: {CONF_LATITUDE: 44.5, CONF_LONGITUDE: 5.5}},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Nouveau site"
    assert entry.data[CONF_LATITUDE] == 44.5
    assert entry.data[CONF_ELEVATION] == 63  # looked up again after moving
    assert entry.unique_id == "44.5000_5.5000"


async def test_options_flow(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema_keys = {str(k) for k in result["data_schema"].schema}
    assert {CONF_BORTLE, CONF_SQM, CONF_FAVORITES, CONF_SHOW_PANEL} <= schema_keys
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **PREFERENCES,
            CONF_SQM: 21.2,
            CONF_FAVORITES: ["M42", "saturn"],
            CONF_SHOW_PANEL: False,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SQM] == 21.2
    assert entry.options[CONF_BORTLE] == 3
    assert entry.options[CONF_FAVORITES] == ["M42", "saturn"]
    assert entry.runtime_data.site.sky_brightness == 21.2
    assert entry.runtime_data.site.equipment == "astrophotography"


async def test_options_flow_horizon(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**PREFERENCES, CONF_HORIZON: "north is blocked", CONF_SHOW_PANEL: True},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HORIZON: "invalid_horizon"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**PREFERENCES, CONF_HORIZON: "0=20; 180=5,5", CONF_SHOW_PANEL: True},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_HORIZON] == "0:20, 180:5.5"
    assert entry.runtime_data.site.horizon == ((0.0, 20.0), (180.0, 5.5))
