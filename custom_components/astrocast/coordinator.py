"""Data coordinators for AstroCast."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ELEVATION, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BORTLE,
    CONF_DEW_HEATERS,
    CONF_EQUIPMENT,
    CONF_FAVORITES,
    CONF_HORIZON,
    CONF_MIN_ALTITUDE,
    CONF_SQM,
    CONF_THRESHOLD,
    DEFAULT_BORTLE,
    DEFAULT_DEW_HEATERS,
    DEFAULT_EQUIPMENT,
    DEFAULT_MIN_ALTITUDE,
    DEFAULT_THRESHOLD,
    DOMAIN,
    MAX_AGE,
    STORAGE_VERSION,
    TTL_7TIMER,
    TTL_AIR_QUALITY,
    TTL_ENSEMBLE,
    TTL_MET_NO,
    TTL_OPEN_METEO,
    TTL_SMALL_BODIES,
    UPDATE_INTERVAL,
    VERSION,
)
from .engine.catalog import Catalog, load_catalog
from .engine.horizon import HorizonError, parse_horizon
from .engine.planner import Forecast, Planner, SiteConfig
from .engine.smallbodies import OrbitalElements
from .engine.timeutil import night_date_for, night_window
from .engine.weather import WeatherSeries, build_timeline
from .providers import jpl, metno, open_meteo, seventimer
from .providers.base import USER_AGENT, ProviderError, ProviderStatus

_LOGGER = logging.getLogger(__name__)

type AstroCastConfigEntry = ConfigEntry[AstroCastCoordinator]


def signal_update(entry_id: str) -> str:
    """Dispatcher signal sent after every successful forecast update."""
    return f"{DOMAIN}_update_{entry_id}"


def http_headers() -> dict[str, str]:
    """Identifying headers (required by MET Norway's terms of service)."""
    return {"User-Agent": USER_AGENT.format(version=VERSION), "Accept": "application/json"}


def _elements_to_dict(items: list[OrbitalElements]) -> list[dict[str, Any]]:
    return [
        {
            "id": e.id,
            "name": e.name,
            "kind": e.kind,
            "q": e.q,
            "e": e.e,
            "i": e.i,
            "node": e.node,
            "peri": e.peri,
            "tp": e.tp,
            "epoch": e.epoch,
            "h": e.h,
            "g": e.g,
        }
        for e in items
    ]


def _elements_from_dict(items: list[dict[str, Any]]) -> list[OrbitalElements]:
    return [OrbitalElements(**item) for item in items]


@dataclass
class AstroCastShared:
    """Resources shared by every observing site."""

    hass: HomeAssistant
    catalog: Catalog
    comets: list[OrbitalElements] = field(default_factory=list)
    asteroids: list[OrbitalElements] = field(default_factory=list)
    status: ProviderStatus = field(
        default_factory=lambda: ProviderStatus("jpl_sbdb", TTL_SMALL_BODIES)
    )
    store: Store | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    loaded: bool = False
    panel_registered: bool = False

    @classmethod
    async def async_create(cls, hass: HomeAssistant) -> AstroCastShared:
        """Load the catalog and the cached small-body orbits."""
        catalog = await hass.async_add_executor_job(load_catalog)
        shared = cls(hass=hass, catalog=catalog)
        shared.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.small_bodies")
        return shared

    async def async_small_bodies(
        self, now: datetime
    ) -> tuple[list[OrbitalElements], list[OrbitalElements]]:
        """Return comet and asteroid orbits, refreshing them once a day."""
        async with self.lock:
            if not self.loaded and self.store is not None:
                self.loaded = True
                stored = await self.store.async_load()
                if stored:
                    try:
                        self.comets = _elements_from_dict(stored.get("comets", []))
                        self.asteroids = _elements_from_dict(stored.get("asteroids", []))
                        fetched = stored.get("fetched")
                        if fetched:
                            self.status.last_success = datetime.fromisoformat(fetched)
                    except (TypeError, ValueError):
                        _LOGGER.debug("Ignoring invalid cached orbits")
            if self.status.due(now):
                session = async_get_clientsession(self.hass)
                try:
                    comets = await jpl.fetch_comets(session, now, http_headers())
                    asteroids = await jpl.fetch_asteroids(session, http_headers())
                except ProviderError as err:
                    self.status.record_failure(now, str(err))
                    _LOGGER.info("JPL small-body database unavailable: %s", err)
                else:
                    self.comets, self.asteroids = comets, asteroids
                    self.status.record_success(now)
                    if self.store is not None:
                        self.store.async_delay_save(
                            lambda: {
                                "fetched": now.isoformat(),
                                "comets": _elements_to_dict(self.comets),
                                "asteroids": _elements_to_dict(self.asteroids),
                            },
                            5,
                        )
            return self.comets, self.asteroids


def site_config(entry: ConfigEntry) -> SiteConfig:
    """Build the engine configuration from a config entry."""
    options = entry.options
    sqm = options.get(CONF_SQM)
    try:
        horizon = parse_horizon(options.get(CONF_HORIZON))
    except HorizonError:
        _LOGGER.warning("Ignoring invalid horizon profile for %s", entry.title)
        horizon = ()
    return SiteConfig(
        name=entry.title,
        latitude=float(entry.data[CONF_LATITUDE]),
        longitude=float(entry.data[CONF_LONGITUDE]),
        elevation=float(entry.data.get(CONF_ELEVATION) or 0.0),
        bortle=int(options.get(CONF_BORTLE, DEFAULT_BORTLE)),
        sqm=float(sqm) if sqm else None,
        min_altitude=float(options.get(CONF_MIN_ALTITUDE, DEFAULT_MIN_ALTITUDE)),
        equipment=str(options.get(CONF_EQUIPMENT, DEFAULT_EQUIPMENT)),
        threshold=int(options.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)),
        horizon=horizon,
        dew_heaters=bool(options.get(CONF_DEW_HEATERS, DEFAULT_DEW_HEATERS)),
    )


class AstroCastCoordinator(DataUpdateCoordinator[Forecast]):
    """Fetches weather for one site and computes its forecast."""

    config_entry: AstroCastConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, shared: AstroCastShared) -> None:
        """Initialise."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.shared = shared
        self.site = site_config(entry)
        self.planner = Planner(self.site, shared.catalog)
        self.series: dict[str, WeatherSeries] = {}
        self.statuses: dict[str, ProviderStatus] = {
            "7timer": ProviderStatus("7timer", TTL_7TIMER),
            "open_meteo": ProviderStatus("open_meteo", TTL_OPEN_METEO),
            "ensemble": ProviderStatus("ensemble", TTL_ENSEMBLE),
            "cams": ProviderStatus("cams", TTL_AIR_QUALITY),
            "met_no": ProviderStatus("met_no", TTL_MET_NO),
        }
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.options_snapshot: dict[str, Any] = dict(entry.options)
        self.add_sensor_entities: Callable[[list[Any]], None] | None = None
        self._restored = False
        self._compute_lock = asyncio.Lock()

    @property
    def favorites(self) -> list[str]:
        """Favourite object ids."""
        return list(self.config_entry.options.get(CONF_FAVORITES, []))

    async def _async_restore(self) -> None:
        """Restore cached weather series (avoids refetching after a restart)."""
        self._restored = True
        stored = await self._store.async_load()
        if not stored:
            return
        key = f"{self.site.latitude:.4f},{self.site.longitude:.4f}"
        if stored.get("location") != key:
            return
        for name, payload in (stored.get("series") or {}).items():
            try:
                series = WeatherSeries.from_dict(payload)
            except (KeyError, TypeError, ValueError):
                continue
            self.series[name] = series
            if name in self.statuses:
                self.statuses[name].last_success = series.fetched

    def _save(self) -> None:
        key = f"{self.site.latitude:.4f},{self.site.longitude:.4f}"
        self._store.async_delay_save(
            lambda: {
                "location": key,
                "series": {name: s.as_dict() for name, s in self.series.items()},
            },
            30,
        )

    async def _fetch(
        self,
        name: str,
        now: datetime,
        factory: Callable[[], Awaitable[WeatherSeries]],
    ) -> bool:
        status = self.statuses[name]
        try:
            series = await factory()
        except ProviderError as err:
            status.record_failure(now, str(err))
            _LOGGER.debug("%s unavailable: %s", name, err)
            return False
        except Exception as err:
            status.record_failure(now, f"{type(err).__name__}: {err}")
            _LOGGER.warning("Unexpected error from %s: %s", name, err, exc_info=True)
            return False
        self.series[name] = series
        status.record_success(now)
        return True

    async def _async_refresh_weather(self, now: datetime) -> None:
        session = async_get_clientsession(self.hass)
        site = self.site
        headers = http_headers()
        jobs: dict[str, Callable[[], Awaitable[WeatherSeries]]] = {
            "7timer": lambda: seventimer.fetch(
                session, site.latitude, site.longitude, now, headers
            ),
            "open_meteo": lambda: open_meteo.fetch_forecast(
                session, site.latitude, site.longitude, site.elevation, now, headers
            ),
            "ensemble": lambda: open_meteo.fetch_ensemble(
                session, site.latitude, site.longitude, now, headers
            ),
            "cams": lambda: open_meteo.fetch_air_quality(
                session, site.latitude, site.longitude, now, headers
            ),
        }
        due = [name for name in jobs if self.statuses[name].due(now)]
        results = await asyncio.gather(*(self._fetch(n, now, jobs[n]) for n in due))
        changed = any(results)

        # MET Norway is only used when Open-Meteo's deterministic forecast is missing.
        om_status = self.statuses["open_meteo"]
        if (om_status.last_error or "open_meteo" not in self.series) and self.statuses[
            "met_no"
        ].due(now):
            changed |= await self._fetch(
                "met_no",
                now,
                lambda: metno.fetch(
                    session, site.latitude, site.longitude, site.elevation, now, headers
                ),
            )
        elif "open_meteo" in self.series and not om_status.last_error:
            self.series.pop("met_no", None)

        for name in list(self.series):
            if now - self.series[name].fetched > MAX_AGE.get(name, timedelta(hours=24)):
                _LOGGER.debug("Dropping stale %s data", name)
                del self.series[name]
                changed = True
        if changed:
            self._save()

    async def _async_update_data(self) -> Forecast:
        """Fetch what is due and recompute the forecast."""
        now = dt_util.utcnow()
        if not self._restored:
            await self._async_restore()
        await self._async_refresh_weather(now)
        comets, asteroids = await self.shared.async_small_bodies(now)
        night_start = night_window(night_date_for(now, self.site.longitude), self.site.longitude)[0]
        timeline = build_timeline(self.series, now, self.site.elevation, start=night_start)
        async with self._compute_lock:
            try:
                return await self.hass.async_add_executor_job(
                    self.planner.compute, now, timeline, comets, asteroids, self.favorites
                )
            except Exception as err:
                _LOGGER.exception("AstroCast computation failed")
                raise UpdateFailed(f"Computation failed: {err}") from err

    def provider_report(self) -> dict[str, Any]:
        """Health of every data source."""
        now = dt_util.utcnow()
        report: dict[str, Any] = {}
        for name, status in (*self.statuses.items(), ("jpl_sbdb", self.shared.status)):
            item = status.as_dict()
            series = self.series.get(name)
            item["active"] = series is not None
            item["stale"] = status.stale(now)
            if series is not None:
                item["data_until"] = datetime.fromtimestamp(
                    series.times[-1], tz=now.tzinfo
                ).isoformat()
                if series.model_run:
                    item["model_run"] = series.model_run.isoformat()
            report[name] = item
        report["jpl_sbdb"]["active"] = bool(self.shared.comets or self.shared.asteroids)
        report["met_no"]["role"] = "fallback"
        return report

    def health(self) -> str:
        """Overall data health: ok, degraded or unavailable."""
        has_weather = "open_meteo" in self.series or "met_no" in self.series
        if not has_weather and "7timer" not in self.series:
            return "unavailable"
        problems = [
            name
            for name in ("7timer", "open_meteo", "ensemble", "cams")
            if name not in self.series or self.statuses[name].failures
        ]
        return "degraded" if problems else "ok"
