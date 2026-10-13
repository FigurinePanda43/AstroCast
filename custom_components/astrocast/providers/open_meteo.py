"""Open-Meteo APIs (https://open-meteo.com) — free, keyless, CC BY 4.0 data.

* Forecast API: hourly variables up to 16 days from the best available models
  for the location (e.g. Météo-France AROME/ARPEGE, DWD ICON, ECMWF IFS, GFS).
* Ensemble API: ECMWF IFS 0.25° ensemble (51 members, 15 days), used for the
  probability of clear sky and the reliability of long-range forecasts.
* Air-quality API: CAMS aerosol optical depth at 550 nm (5 days), the best
  freely available predictor of atmospheric transparency (dust, smoke, haze).
* Elevation API: Copernicus GLO-90 digital elevation model.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

import aiohttp

from ..engine import weather as w
from .base import ProviderError, fetch_json

_LOGGER = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

FORECAST_VARIABLES: dict[str, str] = {
    "cloud_cover": w.CLOUD,
    "cloud_cover_low": w.CLOUD_LOW,
    "cloud_cover_mid": w.CLOUD_MID,
    "cloud_cover_high": w.CLOUD_HIGH,
    "relative_humidity_2m": w.HUMIDITY,
    "dew_point_2m": w.DEW_POINT,
    "temperature_2m": w.TEMPERATURE,
    "wind_speed_10m": w.WIND,
    "wind_gusts_10m": w.GUST,
    "precipitation_probability": w.PRECIP_PROB,
    "precipitation": w.PRECIP,
    "visibility": w.VISIBILITY,
    "wind_speed_250hPa": w.JET,
    "lifted_index": w.LIFTED,
}
# Variables that some model combinations may not provide.
OPTIONAL_VARIABLES = ("wind_speed_250hPa", "lifted_index", "visibility")

ENSEMBLE_MODELS = ("ecmwf_ifs025", "gfs025")


def _common_params(latitude: float, longitude: float) -> dict[str, Any]:
    return {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "timeformat": "unixtime",
        "timezone": "GMT",
    }


def parse_hourly(
    payload: dict[str, Any],
    mapping: dict[str, str],
    source: str,
    fetched: datetime,
) -> w.WeatherSeries:
    """Parse an Open-Meteo ``hourly`` block into a series."""
    if payload.get("error"):
        raise ProviderError(str(payload.get("reason", "Open-Meteo error")))
    hourly = payload.get("hourly") or {}
    times = [float(t) for t in hourly.get("time") or []]
    if not times:
        raise ProviderError("Open-Meteo returned no hourly data")
    fields: dict[str, list[float | None]] = {}
    for api_name, name in mapping.items():
        values = hourly.get(api_name)
        if values is None:
            continue
        fields[name] = [None if v is None else float(v) for v in values]
    return w.WeatherSeries(source=source, fetched=fetched, times=times, fields=fields)


def parse_ensemble(payload: dict[str, Any], fetched: datetime) -> w.WeatherSeries:
    """Parse an ensemble response (control + members) for cloud cover."""
    if payload.get("error"):
        raise ProviderError(str(payload.get("reason", "Open-Meteo error")))
    hourly = payload.get("hourly") or {}
    times = [float(t) for t in hourly.get("time") or []]
    keys = [k for k in hourly if k == "cloud_cover" or k.startswith("cloud_cover_member")]
    if not times or not keys:
        raise ProviderError("Open-Meteo ensemble returned no cloud cover")
    members: list[list[float]] = []
    kept_times: list[float] = []
    for i, ts in enumerate(times):
        values = [float(hourly[k][i]) for k in keys if hourly[k][i] is not None]
        if len(values) >= 5:
            members.append(values)
            kept_times.append(ts)
    if not kept_times:
        raise ProviderError("Open-Meteo ensemble returned empty members")
    means = [sum(m) / len(m) for m in members]
    return w.WeatherSeries(
        source="ensemble",
        fetched=fetched,
        times=kept_times,
        fields={w.CLOUD: means},
        members=members,
    )


async def fetch_forecast(
    session: aiohttp.ClientSession,
    latitude: float,
    longitude: float,
    elevation: float,
    fetched: datetime,
    headers: dict[str, str],
) -> w.WeatherSeries:
    """Fetch the deterministic forecast (16 days, hourly)."""
    variables = list(FORECAST_VARIABLES)
    params = {
        **_common_params(latitude, longitude),
        "elevation": f"{elevation:.0f}",
        "forecast_days": "16",
        "past_days": "1",
        "wind_speed_unit": "kmh",
        "hourly": ",".join(variables),
    }
    try:
        payload = await fetch_json(session, FORECAST_URL, params, timeout=30.0, headers=headers)
    except ProviderError as err:
        if "HTTP 400" not in str(err):
            raise
        # Retry without the variables that a model mix might not support.
        _LOGGER.debug("Open-Meteo rejected optional variables (%s), retrying", err)
        variables = [v for v in variables if v not in OPTIONAL_VARIABLES]
        params["hourly"] = ",".join(variables)
        payload = await fetch_json(session, FORECAST_URL, params, timeout=30.0, headers=headers)
    return parse_hourly(payload, FORECAST_VARIABLES, "open_meteo", fetched)


async def fetch_ensemble(
    session: aiohttp.ClientSession,
    latitude: float,
    longitude: float,
    fetched: datetime,
    headers: dict[str, str],
) -> w.WeatherSeries:
    """Fetch ensemble cloud cover (falls back to GFS ensemble)."""
    last_error: ProviderError | None = None
    for model in ENSEMBLE_MODELS:
        params = {
            **_common_params(latitude, longitude),
            "hourly": "cloud_cover",
            "models": model,
            "forecast_days": "16" if model.startswith("gfs") else "15",
        }
        try:
            payload = await fetch_json(session, ENSEMBLE_URL, params, timeout=45.0, headers=headers)
            series = parse_ensemble(payload, fetched)
        except ProviderError as err:
            last_error = err
            continue
        return series
    raise last_error or ProviderError("ensemble unavailable")


async def fetch_air_quality(
    session: aiohttp.ClientSession,
    latitude: float,
    longitude: float,
    fetched: datetime,
    headers: dict[str, str],
) -> w.WeatherSeries:
    """Fetch CAMS aerosol optical depth and dust."""
    params = {
        **_common_params(latitude, longitude),
        "hourly": "aerosol_optical_depth,dust",
        "forecast_days": "5",
    }
    payload = await fetch_json(session, AIR_QUALITY_URL, params, timeout=30.0, headers=headers)
    return parse_hourly(
        payload,
        {"aerosol_optical_depth": w.AOD, "dust": w.DUST},
        "cams",
        fetched,
    )


async def fetch_elevation(
    session: aiohttp.ClientSession, latitude: float, longitude: float, headers: dict[str, str]
) -> float | None:
    """Ground elevation (m) from the Copernicus DEM, or None."""
    try:
        payload = await fetch_json(
            session,
            ELEVATION_URL,
            {"latitude": f"{latitude:.4f}", "longitude": f"{longitude:.4f}"},
            timeout=15.0,
            headers=headers,
            retries=0,
        )
    except ProviderError:
        return None
    values = payload.get("elevation") if isinstance(payload, dict) else None
    if values and isinstance(values[0], (int, float)):
        return float(values[0])
    return None
