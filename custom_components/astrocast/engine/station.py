"""Local weather station: measured temperature and humidity.

A station measures the air where the telescope stands, which weather models
(grid cells of 1–10 km) cannot know: gardens, lawns and valley bottoms are
often 1–3 °C cooler and moister at night than the forecast, and dew is decided
by those few degrees. AstroCast uses the measurement for the current
conditions and corrects the forecast temperature and dew point of the next
hours by the current error, fading out with an e-folding time of
:data:`FADE_HOURS` (the model takes over again).

A station disagreeing with the forecast by more than :data:`MAX_OFFSET`
(a sensor in the sun, next to a wall or indoors) is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from .timeutil import utc
from .weather import DEW_POINT, HUMIDITY, TEMPERATURE, Timeline

# Magnus coefficients over water (Alduchov & Eskridge 1996).
MAGNUS_A = 17.625
MAGNUS_B = 243.04
FADE_HOURS = 6.0
MAX_OFFSET = 8.0  # °C
STATION = "station"


def dew_point(temperature: float, humidity: float) -> float:
    """Dew point (°C) from the air temperature (°C) and relative humidity (%)."""
    rh = min(100.0, max(1.0, humidity))
    gamma = math.log(rh / 100.0) + MAGNUS_A * temperature / (MAGNUS_B + temperature)
    return MAGNUS_B * gamma / (MAGNUS_A - gamma)


def relative_humidity(temperature: float, dew_point_c: float) -> float:
    """Relative humidity (%) from the air temperature and the dew point (°C)."""
    ratio = math.exp(
        MAGNUS_A * dew_point_c / (MAGNUS_B + dew_point_c)
        - MAGNUS_A * temperature / (MAGNUS_B + temperature)
    )
    return min(100.0, max(1.0, 100.0 * ratio))


@dataclass(slots=True, frozen=True)
class StationReading:
    """Latest measurement of the local station."""

    time: datetime
    temperature: float  # °C
    humidity: float  # %

    @property
    def dew_point(self) -> float:
        """Dew point (°C)."""
        return dew_point(self.temperature, self.humidity)


@dataclass(slots=True, frozen=True)
class StationCorrection:
    """How the station corrected the forecast."""

    reading: StationReading
    temperature_offset: float | None  # measured − forecast now (°C)
    dew_point_offset: float | None
    accepted: bool = True


def apply_station(timeline: Timeline, reading: StationReading, now: datetime) -> StationCorrection:
    """Correct the forecast temperature and dew point with the station (in place).

    The current error (measurement − forecast) is added to every hour from the
    one containing ``now``, weighted by exp(−Δt / FADE_HOURS); the humidity is
    recomputed from the corrected values so that all three stay consistent.
    """
    ts_now = utc(now).timestamp()
    forecast_t = timeline.interpolate(TEMPERATURE, ts_now)
    forecast_td = timeline.interpolate(DEW_POINT, ts_now)
    if forecast_t is None or forecast_td is None:
        # Nothing to correct: the measurement still describes "now".
        return StationCorrection(reading, None, None)
    dt = reading.temperature - forecast_t
    dtd = reading.dew_point - forecast_td
    if abs(dt) > MAX_OFFSET or abs(dtd) > MAX_OFFSET:
        return StationCorrection(reading, round(dt, 1), round(dtd, 1), accepted=False)
    first = math.floor(ts_now / 3600.0) * 3600.0
    for hour in timeline.hours:
        hour_ts = hour.time.timestamp()
        if hour_ts < first:
            continue
        weight = math.exp(-max(0.0, hour_ts - ts_now) / 3600.0 / FADE_HOURS)
        t = hour.values.get(TEMPERATURE)
        td = hour.values.get(DEW_POINT)
        if t is None or td is None:
            continue
        t += dt * weight
        td = min(t, td + dtd * weight)
        hour.values[TEMPERATURE] = round(t, 2)
        hour.values[DEW_POINT] = round(td, 2)
        hour.values[HUMIDITY] = round(relative_humidity(t, td), 1)
        if weight >= 0.05:
            for name in (TEMPERATURE, DEW_POINT, HUMIDITY):
                source = hour.sources.get(name)
                hour.sources[name] = f"{source}+{STATION}" if source else STATION
    return StationCorrection(reading, round(dt, 1), round(dtd, 1))
