"""Sensors for AstroCast."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_FAVORITES
from .coordinator import AstroCastConfigEntry, AstroCastCoordinator
from .engine import weather as w
from .engine.ephemeris import moon_phase_name
from .engine.planner import Forecast, NightForecast
from .engine.scoring import ProfileNight, rating
from .engine.timeutil import iso
from .entity import AstroCastEntity
from .i18n import confidence_label, event_title
from .serialize import object_name

MOON_PHASES = [
    "new_moon",
    "waxing_crescent",
    "first_quarter",
    "waxing_gibbous",
    "full_moon",
    "waning_gibbous",
    "last_quarter",
    "waning_crescent",
]
DATA_HEALTH = ["ok", "degraded", "unavailable"]
DEW_RISKS = ["low", "moderate", "high"]

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AstroCastSensorDescription(SensorEntityDescription):
    """Describes an AstroCast sensor."""

    value_fn: Callable[[AstroCastCoordinator, Forecast], Any]
    attrs_fn: Callable[[AstroCastCoordinator, Forecast], dict[str, Any]] | None = None


def _profile_attrs(night: NightForecast, profile: ProfileNight, language: str) -> dict[str, Any]:
    ephem = night.ephem
    return {
        "night": ephem.night.isoformat(),
        "rating": profile.rating,
        "window_start": iso(profile.window_start),
        "window_end": iso(profile.window_end),
        "window_score": profile.window_score,
        "window_quality": profile.window_quality,
        "window_hours": profile.window_hours,
        "duration_factor": profile.duration_factor,
        "peak_time": iso(profile.peak_time),
        "good_hours": profile.good_hours,
        "usable_hours": profile.usable_hours,
        "limiting_factor": profile.limiting,
        "confidence": confidence_label(language, profile.confidence),
        "forecast_tier": profile.tier,
        "factors": profile.factor_means,
        "cloud_cover": night.summary.get("cloud_cover"),
        "clear_probability": night.summary.get("clear_probability"),
        "seeing": night.summary.get("seeing"),
        "transparency": night.summary.get("transparency"),
        "dew_risk": night.summary.get("dew_risk"),
        "dew_onset": iso(night.summary.get("dew_onset")),
        "moon_illumination": round(ephem.moon_illumination * 100),
        "astronomical_dusk": iso(ephem.astro_dusk),
        "astronomical_dawn": iso(ephem.astro_dawn),
        "dark_hours": ephem.dark_hours,
        "moonless_dark_hours": ephem.moonless_dark_hours,
    }


def _now_attrs(profile: str) -> Callable[[AstroCastCoordinator, Forecast], dict[str, Any]]:
    def attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
        now = forecast.now
        score = now.scores.get(profile)
        return {
            "rating": rating(score),
            "limiting_factor": now.limiting.get(profile),
            "factors": now.factors.get(profile, {}),
            "forecast_tier": now.tier,
            "confidence": confidence_label(coordinator.hass.config.language, now.confidence),
        }

    return attrs


def _best_night_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    best = forecast.best_night()
    nights = [
        {
            "date": n.ephem.night.isoformat(),
            "deep_sky": n.deep_sky.score,
            "planetary": n.planetary.score,
            "narrowband": n.narrowband.score,
            "rating": n.deep_sky.rating,
            "window_start": iso(n.deep_sky.window_start),
            "window_end": iso(n.deep_sky.window_end),
            "window_hours": n.deep_sky.window_hours,
            "dew_onset": iso(n.summary.get("dew_onset")),
            "moon": round(n.ephem.moon_illumination * 100),
            "tier": n.deep_sky.tier,
            "clear_probability": n.summary.get("clear_probability"),
        }
        for n in forecast.nights
        if n.has_weather
    ]
    attrs: dict[str, Any] = {"nights": nights}
    if best is not None:
        attrs.update(
            {
                "date": best.ephem.night.isoformat(),
                "score": best.deep_sky.score,
                "rating": best.deep_sky.rating,
                "window_end": iso(best.deep_sky.window_end),
                "confidence": confidence_label(
                    coordinator.hass.config.language, best.deep_sky.confidence
                ),
            }
        )
    best_pl = forecast.best_night("planetary")
    if best_pl is not None:
        attrs["best_planetary_date"] = best_pl.ephem.night.isoformat()
        attrs["best_planetary_score"] = best_pl.planetary.score
    best_nb = forecast.best_night("narrowband")
    if best_nb is not None:
        attrs["best_narrowband_date"] = best_nb.ephem.night.isoformat()
        attrs["best_narrowband_score"] = best_nb.narrowband.score
    return attrs


def _best_night_value(coordinator: AstroCastCoordinator, forecast: Forecast) -> datetime | None:
    best = forecast.best_night()
    if best is None:
        return None
    return best.deep_sky.window_start or best.ephem.astro_dusk or best.ephem.sunset


def _weather_now(name: str, digits: int = 1) -> Callable[[AstroCastCoordinator, Forecast], Any]:
    def value(coordinator: AstroCastCoordinator, forecast: Forecast) -> Any:
        v = forecast.now.weather.get(name)
        return round(v, digits) if v is not None else None

    return value


def _cloud_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    now = forecast.now
    return {
        "low": now.weather.get(w.CLOUD_LOW),
        "mid": now.weather.get(w.CLOUD_MID),
        "high": now.weather.get(w.CLOUD_HIGH),
        "clear_probability": now.clear_probability,
        "source": now.sources.get(w.CLOUD),
        "forecast_tier": now.tier,
    }


def _seeing_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    now = forecast.now
    return {
        "source": now.sources.get(w.SEEING),
        "jet_stream_wind": now.weather.get(w.JET),
        "estimate": True,
    }


def _transparency_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    now = forecast.now
    return {
        "source": now.sources.get(w.TRANSPARENCY),
        "aerosol_optical_depth": now.weather.get(w.AOD),
        "dust": now.weather.get(w.DUST),
        "humidity": now.weather.get(w.HUMIDITY),
        "dew_risk": now.dew_risk,
        "estimate": True,
    }


def _dew_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    now = forecast.now
    temperature = now.weather.get(w.TEMPERATURE)
    dew_point = now.weather.get(w.DEW_POINT)
    summary = forecast.tonight.summary
    return {
        "optics_margin": now.dew_margin,
        "temperature": temperature,
        "dew_point": dew_point,
        "spread": round(temperature - dew_point, 1)
        if temperature is not None and dew_point is not None
        else None,
        "humidity": now.weather.get(w.HUMIDITY),
        "tonight_risk": summary.get("dew_risk"),
        "tonight_onset": iso(summary.get("dew_onset")),
        "dew_heaters": coordinator.site.dew_heaters,
        "estimate": True,
    }


def _dew_onset_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    summary = forecast.tonight.summary
    return {
        "expected": summary.get("dew_onset") is not None,
        "night": forecast.tonight.ephem.night.isoformat(),
        "risk": summary.get("dew_risk"),
        "lowest_optics_margin": summary.get("dew_margin_min"),
        "dew_heaters": coordinator.site.dew_heaters,
    }


def _moon_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    snap = forecast.now.snapshot
    tonight = forecast.tonight.ephem
    return {
        "illumination": round(snap.moon_illumination * 100, 1),
        "phase_angle": round(snap.moon_phase, 1),
        "altitude": round(snap.moon_alt, 1),
        "azimuth": round(snap.moon_az, 1),
        "distance_km": round(snap.moon_distance_km),
        "moonrise_tonight": iso(tonight.moonrise),
        "moonset_tonight": iso(tonight.moonset),
    }


def _next_moon(event: str) -> Callable[[AstroCastCoordinator, Forecast], datetime | None]:
    def value(coordinator: AstroCastCoordinator, forecast: Forecast) -> datetime | None:
        return forecast.now.moonrise if event == "rise" else forecast.now.moonset

    return value


def _next_event(coordinator: AstroCastCoordinator, forecast: Forecast) -> datetime | None:
    now = dt_util.utcnow()
    for event in forecast.events:
        if event.importance >= 2 and (event.end or event.start) >= now:
            return event.start
    return None


def _next_event_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    language = coordinator.hass.config.language
    now = dt_util.utcnow()
    upcoming = [e for e in forecast.events if e.importance >= 2 and (e.end or e.start) >= now]
    attrs: dict[str, Any] = {
        "upcoming": [
            {
                "start": iso(e.start),
                "title": event_title(e, language),
                "type": e.type,
                "importance": e.importance,
                "visible": e.visible,
            }
            for e in upcoming[:15]
        ]
    }
    if upcoming:
        first = upcoming[0]
        attrs.update(
            {
                "title": event_title(first, language),
                "type": first.type,
                "end": iso(first.end),
                "best_time": iso(first.best_time),
                "importance": first.importance,
                "visible": first.visible,
            }
        )
    return attrs


def _top_object(coordinator: AstroCastCoordinator, forecast: Forecast) -> str | None:
    objects = forecast.tonight.objects
    if not objects:
        return None
    return object_name(objects[0], coordinator.hass.config.language)[:255]


def _top_object_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    language = coordinator.hass.config.language
    return {
        "objects": [
            {
                "id": o.id,
                "name": object_name(o, language),
                "type": o.type,
                "magnitude": o.mag,
                "best_time": iso(o.best_time),
                "max_altitude": o.max_alt,
                "score": o.best_score,
                "interest": o.interest,
            }
            for o in forecast.tonight.objects[:10]
        ]
    }


def _visible_planets(coordinator: AstroCastCoordinator, forecast: Forecast) -> int:
    return sum(
        1
        for p in forecast.tonight.planets
        if p.kind == "planet" and p.hours_visible > 0 and p.appeal > 0
    )


def _planet_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    language = coordinator.hass.config.language
    return {
        "planets": [
            {
                "id": p.id,
                "name": object_name(p, language),
                "magnitude": p.mag,
                "visible_hours": p.hours_visible,
                "max_altitude": p.max_alt,
                "best_time": iso(p.best_time),
                "score": p.best_score,
                "rise": iso(p.rise),
                "set": iso(p.set),
                "constellation": p.constellation,
            }
            for p in forecast.tonight.planets
            if p.kind == "planet" and p.hours_visible > 0 and p.appeal > 0
        ]
    }


def _health(coordinator: AstroCastCoordinator, forecast: Forecast) -> str:
    return coordinator.health()


def _health_attrs(coordinator: AstroCastCoordinator, forecast: Forecast) -> dict[str, Any]:
    return {"providers": coordinator.provider_report(), "generated": iso(forecast.generated)}


SENSORS: tuple[AstroCastSensorDescription, ...] = (
    AstroCastSensorDescription(
        key="deep_sky_tonight",
        translation_key="deep_sky_tonight",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c, f: f.tonight.deep_sky.score,
        attrs_fn=lambda c, f: _profile_attrs(f.tonight, f.tonight.deep_sky, c.hass.config.language),
    ),
    AstroCastSensorDescription(
        key="planetary_tonight",
        translation_key="planetary_tonight",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c, f: f.tonight.planetary.score,
        attrs_fn=lambda c, f: _profile_attrs(
            f.tonight, f.tonight.planetary, c.hass.config.language
        ),
    ),
    AstroCastSensorDescription(
        key="narrowband_tonight",
        translation_key="narrowband_tonight",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c, f: f.tonight.narrowband.score,
        attrs_fn=lambda c, f: _profile_attrs(
            f.tonight, f.tonight.narrowband, c.hass.config.language
        ),
    ),
    AstroCastSensorDescription(
        key="deep_sky_now",
        translation_key="deep_sky_now",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c, f: f.now.scores.get("deep_sky"),
        attrs_fn=_now_attrs("deep_sky"),
    ),
    AstroCastSensorDescription(
        key="planetary_now",
        translation_key="planetary_now",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c, f: f.now.scores.get("planetary"),
        attrs_fn=_now_attrs("planetary"),
    ),
    AstroCastSensorDescription(
        key="narrowband_now",
        translation_key="narrowband_now",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c, f: f.now.scores.get("narrowband"),
        attrs_fn=_now_attrs("narrowband"),
    ),
    AstroCastSensorDescription(
        key="best_night",
        translation_key="best_night",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_best_night_value,
        attrs_fn=_best_night_attrs,
    ),
    AstroCastSensorDescription(
        key="cloud_cover",
        translation_key="cloud_cover",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_weather_now(w.CLOUD, 0),
        attrs_fn=_cloud_attrs,
    ),
    AstroCastSensorDescription(
        key="seeing",
        translation_key="seeing",
        native_unit_of_measurement="″",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=_weather_now(w.SEEING, 2),
        attrs_fn=_seeing_attrs,
    ),
    AstroCastSensorDescription(
        key="transparency",
        translation_key="transparency",
        native_unit_of_measurement="mag/airmass",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=_weather_now(w.TRANSPARENCY, 2),
        attrs_fn=_transparency_attrs,
    ),
    AstroCastSensorDescription(
        key="dew_risk",
        translation_key="dew_risk",
        device_class=SensorDeviceClass.ENUM,
        options=DEW_RISKS,
        value_fn=lambda c, f: f.now.dew_risk,
        attrs_fn=_dew_attrs,
    ),
    AstroCastSensorDescription(
        key="dew_onset",
        translation_key="dew_onset",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c, f: f.tonight.summary.get("dew_onset"),
        attrs_fn=_dew_onset_attrs,
    ),
    AstroCastSensorDescription(
        key="moon_phase",
        translation_key="moon_phase",
        device_class=SensorDeviceClass.ENUM,
        options=MOON_PHASES,
        value_fn=lambda c, f: moon_phase_name(f.now.snapshot.moon_phase),
        attrs_fn=_moon_attrs,
    ),
    AstroCastSensorDescription(
        key="moon_illumination",
        translation_key="moon_illumination",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda c, f: round(f.now.snapshot.moon_illumination * 100, 1),
    ),
    AstroCastSensorDescription(
        key="moonrise",
        translation_key="moonrise",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=_next_moon("rise"),
    ),
    AstroCastSensorDescription(
        key="moonset",
        translation_key="moonset",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=_next_moon("set"),
    ),
    AstroCastSensorDescription(
        key="astronomical_dusk",
        translation_key="astronomical_dusk",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c, f: f.tonight.ephem.astro_dusk,
    ),
    AstroCastSensorDescription(
        key="astronomical_dawn",
        translation_key="astronomical_dawn",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c, f: f.tonight.ephem.astro_dawn,
    ),
    AstroCastSensorDescription(
        key="next_event",
        translation_key="next_event",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_event,
        attrs_fn=_next_event_attrs,
    ),
    AstroCastSensorDescription(
        key="top_object",
        translation_key="top_object",
        value_fn=_top_object,
        attrs_fn=_top_object_attrs,
    ),
    AstroCastSensorDescription(
        key="visible_planets",
        translation_key="visible_planets",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_visible_planets,
        attrs_fn=_planet_attrs,
    ),
    AstroCastSensorDescription(
        key="data_sources",
        translation_key="data_sources",
        device_class=SensorDeviceClass.ENUM,
        options=DATA_HEALTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_health,
        attrs_fn=_health_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AstroCastConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    coordinator.add_sensor_entities = async_add_entities
    entities: list[SensorEntity] = [AstroCastSensor(coordinator, d) for d in SENSORS]
    entities += [
        FavoriteSensor(coordinator, object_id)
        for object_id in entry.options.get(CONF_FAVORITES, [])
    ]
    async_add_entities(entities)


class AstroCastSensor(AstroCastEntity, SensorEntity):
    """A sensor driven by an entity description."""

    entity_description: AstroCastSensorDescription
    # Large or fast-changing attributes are kept out of the recorder. Home
    # Assistant merges this set once per class, so it must be declared here.
    _unrecorded_attributes = frozenset(
        {"factors", "nights", "upcoming", "objects", "planets", "providers", "generated"}
    )

    def __init__(
        self, coordinator: AstroCastCoordinator, description: AstroCastSensorDescription
    ) -> None:
        """Initialise."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._update_from_data()

    def _update_from_data(self) -> None:
        forecast = self.coordinator.data
        if forecast is None:
            return
        description = self.entity_description
        self._attr_native_value = description.value_fn(self.coordinator, forecast)
        if description.attrs_fn is not None:
            self._attr_extra_state_attributes = description.attrs_fn(self.coordinator, forecast)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_data()
        super()._handle_coordinator_update()


class FavoriteSensor(AstroCastEntity, SensorEntity):
    """Next favourable observing window for a favourite object."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "favorite"
    _unrecorded_attributes = frozenset({"nights"})

    def __init__(self, coordinator: AstroCastCoordinator, object_id: str) -> None:
        """Initialise."""
        super().__init__(coordinator, f"favorite_{object_id}")
        self.object_id = object_id
        catalog = coordinator.shared.catalog
        language = coordinator.hass.config.language
        obj = catalog.get(object_id)
        if obj is not None:
            label = obj.label(language)
        else:
            from .i18n import body_name  # noqa: PLC0415

            label = (
                body_name(language, object_id)
                if ":" not in object_id
                else object_id.split(":", 1)[1]
            )
        self._attr_translation_placeholders = {"object": label}
        self._update_from_data()

    def _update_from_data(self) -> None:
        forecast = self.coordinator.data
        if forecast is None:
            return
        fav = next((f for f in forecast.favorites if f.id == self.object_id), None)
        if fav is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {"object_id": self.object_id}
            return
        nxt = fav.next_good
        self._attr_native_value = nxt.window_start or nxt.best_time if nxt else None
        tonight = fav.tonight
        attrs: dict[str, Any] = {
            "object_id": self.object_id,
            "next_window_end": iso(nxt.window_end) if nxt else None,
            "next_window_score": nxt.best_score if nxt else None,
            "next_night": nxt.night.isoformat() if nxt else None,
            "nights": [
                {
                    "date": n.night.isoformat(),
                    "score": n.best_score,
                    "best_time": iso(n.best_time),
                    "window_start": iso(n.window_start),
                    "window_end": iso(n.window_end),
                    "max_altitude": n.max_alt,
                    "weather": n.has_weather,
                }
                for n in fav.nights
            ],
        }
        if tonight is not None:
            attrs.update(
                {
                    "tonight_score": tonight.best_score,
                    "tonight_best_time": iso(tonight.best_time),
                    "tonight_max_altitude": tonight.max_alt,
                    "tonight_visible_hours": tonight.hours_visible,
                    "transit": iso(tonight.transit),
                    "magnitude": tonight.mag,
                    "constellation": tonight.constellation,
                }
            )
        self._attr_extra_state_attributes = attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_data()
        super()._handle_coordinator_update()
