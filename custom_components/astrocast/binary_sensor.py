"""Binary sensors for AstroCast."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .coordinator import AstroCastConfigEntry, AstroCastCoordinator
from .engine.planner import Forecast
from .engine.timeutil import iso
from .entity import AstroCastEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AstroCastConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities([AstronomicalNightSensor(coordinator), GoodConditionsSensor(coordinator)])


def _dark_intervals(forecast: Forecast) -> list[tuple[datetime, datetime]]:
    intervals = []
    for night in forecast.nights:
        ephem = night.ephem
        dusk, dawn = ephem.astro_dusk, ephem.astro_dawn
        if dusk is None and dawn is None:
            # Either no astronomical night at all, or a polar night.
            if float(ephem.sun_alt.max()) < -18.0:
                intervals.append((ephem.start, ephem.end))
            continue
        intervals.append((dusk or ephem.start, dawn or ephem.end))
    return intervals


class AstronomicalNightSensor(AstroCastEntity, BinarySensorEntity):
    """On while the Sun is more than 18° below the horizon.

    State changes are scheduled at the exact twilight instants rather than at
    the next coordinator refresh, so automations (e.g. switching outdoor
    lights off) trigger on time.
    """

    _attr_translation_key = "astronomical_night"

    def __init__(self, coordinator: AstroCastCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "astronomical_night")
        self._unsub: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        """Schedule the next transition."""
        await super().async_added_to_hass()
        self._schedule()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel timers."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        await super().async_will_remove_from_hass()

    def _intervals(self) -> list[tuple[datetime, datetime]]:
        forecast = self.coordinator.data
        return _dark_intervals(forecast) if forecast else []

    @property
    def is_on(self) -> bool | None:
        """Whether it is astronomical night."""
        if self.coordinator.data is None:
            return None
        now = dt_util.utcnow()
        # No interval at all (e.g. summer at high latitude) simply means "off".
        return any(start <= now < end for start, end in self._intervals())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Next start and end of astronomical night."""
        now = dt_util.utcnow()
        upcoming = [(s, e) for s, e in self._intervals() if e > now]
        if not upcoming:
            return {}
        start, end = upcoming[0]
        return {"start": iso(start), "end": iso(end)}

    @callback
    def _schedule(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        now = dt_util.utcnow()
        moments = sorted(m for interval in self._intervals() for m in interval if m > now)
        if moments:
            self._unsub = async_track_point_in_utc_time(self.hass, self._transition, moments[0])

    @callback
    def _transition(self, _now: datetime) -> None:
        self._unsub = None
        self.async_write_ha_state()
        self._schedule()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule()
        super()._handle_coordinator_update()


class GoodConditionsSensor(AstroCastEntity, BinarySensorEntity):
    """On when current conditions reach the configured score threshold."""

    _attr_translation_key = "good_conditions"

    def __init__(self, coordinator: AstroCastCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "good_conditions")

    @property
    def _threshold(self) -> int:
        return self.coordinator.site.threshold

    @property
    def is_on(self) -> bool | None:
        """Whether any profile reaches the threshold now."""
        forecast = self.coordinator.data
        if forecast is None:
            return None
        scores = [s for s in forecast.now.scores.values() if s is not None]
        if not scores:
            return None
        return max(scores) >= self._threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Per-profile details."""
        forecast = self.coordinator.data
        if forecast is None:
            return {}
        scores = forecast.now.scores
        return {
            "threshold": self._threshold,
            "deep_sky": (scores.get("deep_sky") or 0) >= self._threshold,
            "planetary": (scores.get("planetary") or 0) >= self._threshold,
            "deep_sky_score": scores.get("deep_sky"),
            "planetary_score": scores.get("planetary"),
        }
