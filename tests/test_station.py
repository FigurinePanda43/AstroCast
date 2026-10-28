"""Local weather station: measured temperature and humidity."""

from __future__ import annotations

from datetime import timedelta
import math

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.astrocast.const import (
    CONF_SHOW_PANEL,
    CONF_STATION_HUMIDITY,
    CONF_STATION_TEMPERATURE,
)
from custom_components.astrocast.engine import weather as w
from custom_components.astrocast.engine.catalog import load_catalog
from custom_components.astrocast.engine.planner import Planner, SiteConfig
from custom_components.astrocast.engine.station import (
    FADE_HOURS,
    StationReading,
    apply_station,
    dew_point,
    relative_humidity,
)
from custom_components.astrocast.engine.timeutil import night_date_for, night_window

from .conftest import LATITUDE, LONGITUDE, NOW
from .test_config_flow import PREFERENCES
from .test_engine_forecast import _series

TEMPERATURE_ID = "sensor.garden_temperature"
HUMIDITY_ID = "sensor.garden_humidity"


def _timeline() -> w.Timeline:
    start = night_window(night_date_for(NOW, LONGITUDE), LONGITUDE)[0]
    return w.build_timeline(_series(), NOW, 100, start=start)


def _reading(timeline: w.Timeline, dt: float, dtd: float) -> StationReading:
    """A measurement differing from the forecast at NOW by (dt, dtd) °C."""
    ts = NOW.timestamp()
    t = timeline.interpolate(w.TEMPERATURE, ts) + dt
    td = timeline.interpolate(w.DEW_POINT, ts) + dtd
    return StationReading(NOW, t, relative_humidity(t, td))


def test_dew_point_formula() -> None:
    assert dew_point(20.0, 50.0) == pytest.approx(9.26, abs=0.05)
    assert dew_point(10.0, 100.0) == pytest.approx(10.0, abs=0.01)
    assert dew_point(-5.0, 80.0) == pytest.approx(-7.9, abs=0.1)
    assert relative_humidity(18.0, dew_point(18.0, 65.0)) == pytest.approx(65.0, abs=0.01)


def test_correction_fades_out() -> None:
    reference = _timeline()
    timeline = _timeline()
    correction = apply_station(timeline, _reading(timeline, -2.0, 1.5), NOW)
    assert correction.accepted
    assert correction.temperature_offset == pytest.approx(-2.0, abs=0.05)
    assert correction.dew_point_offset == pytest.approx(1.5, abs=0.05)
    for before, after in zip(reference.hours, timeline.hours, strict=True):
        lead = (after.time - NOW).total_seconds() / 3600.0
        t0, t1 = before.values.get(w.TEMPERATURE), after.values.get(w.TEMPERATURE)
        if t0 is None:
            continue
        if lead < 0:
            assert t1 == t0  # the past is not rewritten
            continue
        expected = t0 - 2.0 * math.exp(-lead / FADE_HOURS)
        assert t1 == pytest.approx(expected, abs=0.02), lead
        td = after.values[w.DEW_POINT]
        assert td <= t1
        assert after.values[w.HUMIDITY] == pytest.approx(relative_humidity(t1, td), abs=0.1)
        if lead <= 12:
            assert after.sources[w.TEMPERATURE].endswith("+station")
    # Measured value at NOW.
    assert timeline.interpolate(w.TEMPERATURE, NOW.timestamp()) == pytest.approx(
        reference.interpolate(w.TEMPERATURE, NOW.timestamp()) - 2.0, abs=0.05
    )


def test_implausible_station_is_ignored() -> None:
    reference = _timeline()
    timeline = _timeline()
    correction = apply_station(timeline, _reading(timeline, 12.0, 0.0), NOW)
    assert not correction.accepted
    assert [h.values for h in timeline.hours] == [h.values for h in reference.hours]


def test_planner_uses_the_station() -> None:
    """A moister garden than forecast: dew comes earlier, "now" is measured."""
    planner = Planner(SiteConfig("Test", LATITUDE, LONGITUDE, 100), load_catalog())
    plain = planner.compute(NOW, _timeline())
    timeline = _timeline()
    reading = _reading(timeline, -1.5, 3.0)
    measured = planner.compute(NOW, timeline, station=reading)
    now = measured.now
    assert now.station is not None and now.station.accepted
    assert now.weather[w.TEMPERATURE] == pytest.approx(reading.temperature, abs=0.01)
    assert now.weather[w.DEW_POINT] == pytest.approx(reading.dew_point, abs=0.01)
    assert now.sources[w.DEW_POINT] == "station"
    assert now.dew_margin < plain.now.dew_margin
    onset_plain = plain.tonight.summary["dew_onset"]
    onset = measured.tonight.summary["dew_onset"]
    assert onset is not None
    assert onset_plain is None or onset <= onset_plain


def _set_station(
    hass: HomeAssistant, temperature: str, humidity: str = "97", unit: str = "°C"
) -> None:
    hass.states.async_set(
        TEMPERATURE_ID,
        temperature,
        {"unit_of_measurement": unit, "device_class": "temperature"},
    )
    hass.states.async_set(
        HUMIDITY_ID, humidity, {"unit_of_measurement": "%", "device_class": "humidity"}
    )


def _dew_risk(hass: HomeAssistant):
    registry = er.async_get(hass)
    entity = next(e for e in registry.entities.values() if e.unique_id.endswith("_dew_risk"))
    return hass.states.get(entity.entity_id)


async def _configure(hass: HomeAssistant, entry, **station: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**PREFERENCES, CONF_SHOW_PANEL: True, **station}
    )
    await hass.async_block_till_done()
    return result


def _forecast_now(entry) -> float:
    """Forecast temperature now (the station must stay within 8 °C of it)."""
    return round(entry.runtime_data.data.now.weather[w.TEMPERATURE], 1)


async def test_station_options_and_sensors(hass: HomeAssistant, setup_integration) -> None:
    entry = setup_integration
    measured = _forecast_now(entry) - 2.0
    _set_station(hass, str(measured))
    result = await _configure(hass, entry, **{CONF_STATION_TEMPERATURE: TEMPERATURE_ID})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_STATION_HUMIDITY: "station_incomplete"}

    result = await _configure(
        hass,
        entry,
        **{CONF_STATION_TEMPERATURE: TEMPERATURE_ID, CONF_STATION_HUMIDITY: HUMIDITY_ID},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    attrs = _dew_risk(hass).attributes
    assert attrs["station"] == "ok"
    assert attrs["source"] == "station"
    assert attrs["estimate"] is False
    assert attrs["station_temperature"] == measured
    assert attrs["station_dew_point"] == pytest.approx(dew_point(measured, 97.0), abs=0.1)
    assert attrs["forecast_error_temperature"] == pytest.approx(-2.0, abs=0.1)
    now = entry.runtime_data.data.now
    assert now.weather[w.TEMPERATURE] == measured

    # A sensor far from the forecast (in the sun, indoors…) is ignored.
    _set_station(hass, str(measured + 14.0))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _dew_risk(hass).attributes["station"] == "rejected"
    assert _dew_risk(hass).attributes["source"] != "station"


async def test_station_units_and_staleness(hass: HomeAssistant, setup_integration, freezer) -> None:
    entry = setup_integration
    celsius = _forecast_now(entry) - 1.0
    _set_station(hass, f"{celsius * 9 / 5 + 32:.2f}", unit="°F")
    await _configure(
        hass,
        entry,
        **{CONF_STATION_TEMPERATURE: TEMPERATURE_ID, CONF_STATION_HUMIDITY: HUMIDITY_ID},
    )
    coordinator = entry.runtime_data
    assert coordinator.data.now.station.reading.temperature == pytest.approx(celsius, abs=0.01)

    # The sensors stop reporting: after 90 minutes the station is ignored.
    freezer.tick(timedelta(hours=2))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.station_status["state"] == "stale"
    assert coordinator.data.now.station is None
    assert _dew_risk(hass).attributes["source"] != "station"

    # Back online.
    _set_station(hass, f"{celsius:.1f}")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.station_status["state"] == "ok"
    assert _dew_risk(hass).attributes["station_temperature"] == round(celsius, 1)

    # Unavailable sensor.
    hass.states.async_set(TEMPERATURE_ID, "unavailable")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.station_status["state"] == "unavailable"
