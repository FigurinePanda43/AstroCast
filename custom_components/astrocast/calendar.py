"""Calendars: observing windows and astronomical events.

Calendar entities are the most convenient way to drive notifications in Home
Assistant: the calendar trigger supports offsets ("1 hour before the start of
the next observing window") and the events show up in the calendar panel.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AstroCastConfigEntry, AstroCastCoordinator
from .engine.planner import Forecast
from .engine.scoring import DEEP_SKY, PLANETARY, rating
from .entity import AstroCastEntity
from .i18n import confidence_label, event_description, event_title, text

PARALLEL_UPDATES = 0

# Events always worth a calendar entry even when classified as minor.
ALWAYS_LISTED = {"moon_phase", "season", "meteor_shower", "lunar_eclipse", "solar_eclipse"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AstroCastConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up calendars."""
    coordinator = entry.runtime_data
    async_add_entities([ObservingWindowCalendar(coordinator), AstroEventCalendar(coordinator)])


def _fmt(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}" if digits else f"{round(value)}"


def observing_windows(
    forecast: Forecast, language: str, threshold: int
) -> list[CalendarEvent]:
    """Calendar events for every forecast window above the threshold."""
    events: list[CalendarEvent] = []
    for night in forecast.nights:
        for profile_name in (DEEP_SKY, PLANETARY):
            profile = night.profile(profile_name)
            if (
                profile.window_start is None
                or profile.window_end is None
                or profile.window_score is None
                or profile.window_score < threshold
            ):
                continue
            summary = text(
                language,
                f"{profile_name}_window",
                rating=text(language, f"rating_{rating(profile.window_score) or 'bad'}"),
                score=profile.window_score,
            )
            lines = [
                text(
                    language,
                    "desc_window",
                    cloud=_fmt(night.summary.get("cloud_cover")),
                    seeing=_fmt(night.summary.get("seeing"), 1),
                    moon=round(night.ephem.moon_illumination * 100),
                    conf=confidence_label(language, profile.confidence),
                )
            ]
            if profile.limiting:
                lines.append(
                    text(language, "desc_limiting", factor=text(language, f"factor_{profile.limiting}"))
                )
            events.append(
                CalendarEvent(
                    start=profile.window_start,
                    end=profile.window_end,
                    summary=summary,
                    description="\n".join(lines),
                    location=forecast.site.name,
                    uid=f"{profile_name}-{night.ephem.night.isoformat()}",
                )
            )
    events.sort(key=lambda e: e.start)
    return events


def astro_events(forecast: Forecast, language: str) -> list[CalendarEvent]:
    """Calendar events for astronomical phenomena."""
    result: list[CalendarEvent] = []
    for event in forecast.events:
        if event.importance < 2 and event.type not in ALWAYS_LISTED:
            continue
        if event.type in ("conjunction",) and event.visible is False and event.importance < 3:
            continue
        start = event.start
        end = event.end
        if event.type == "meteor_shower" and event.best_time is not None:
            # Span the best observing night rather than the instant of maximum.
            start = event.best_time - timedelta(hours=2)
            end = event.best_time + timedelta(hours=2)
        if end is None or end <= start:
            end = start + timedelta(minutes=30)
        result.append(
            CalendarEvent(
                start=start,
                end=end,
                summary=event_title(event, language),
                description=event_description(event, language, forecast.site.name),
                location=forecast.site.name,
                uid=event.id,
            )
        )
    result.sort(key=lambda e: e.start)
    return result


class _BaseCalendar(AstroCastEntity, CalendarEntity):
    def __init__(self, coordinator: AstroCastCoordinator, key: str) -> None:
        super().__init__(coordinator, key)

    def _events(self) -> list[CalendarEvent]:
        raise NotImplementedError

    @property
    def event(self) -> CalendarEvent | None:
        """Current or next event."""
        now = dt_util.utcnow()
        for event in self._events():
            if event.end_datetime_local > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Events within a range."""
        return [
            e
            for e in self._events()
            if e.end_datetime_local > start_date and e.start_datetime_local < end_date
        ]


class ObservingWindowCalendar(_BaseCalendar):
    """Best observing windows (deep sky and planetary) above the threshold."""

    _attr_translation_key = "observing_windows"

    def __init__(self, coordinator: AstroCastCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "observing_windows")

    def _events(self) -> list[CalendarEvent]:
        forecast = self.coordinator.data
        if forecast is None:
            return []
        return observing_windows(
            forecast, self.hass.config.language, self.coordinator.site.threshold
        )


class AstroEventCalendar(_BaseCalendar):
    """Eclipses, oppositions, conjunctions, meteor showers, lunar phases..."""

    _attr_translation_key = "astronomy_events"

    def __init__(self, coordinator: AstroCastCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "astronomy_events")

    def _events(self) -> list[CalendarEvent]:
        forecast = self.coordinator.data
        if forecast is None:
            return []
        return astro_events(forecast, self.hass.config.language)
