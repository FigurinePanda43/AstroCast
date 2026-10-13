"""MET Norway Locationforecast 2.0 (https://api.met.no) — fallback weather.

Free, keyless, CC BY 4.0. The terms of service require an identifying
User-Agent and at most 4 decimals for coordinates; responses are only
re-requested once per hour.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiohttp

from ..engine import weather as w
from .base import ProviderError, fetch_json

URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"


def parse(payload: dict[str, Any], fetched: datetime) -> w.WeatherSeries:
    """Parse a Locationforecast ``complete`` document."""
    try:
        timeseries = payload["properties"]["timeseries"]
    except (KeyError, TypeError) as err:
        raise ProviderError(f"unexpected MET Norway payload: {err}") from err
    times: list[float] = []
    fields: dict[str, list[float | None]] = {
        w.CLOUD: [],
        w.CLOUD_LOW: [],
        w.CLOUD_MID: [],
        w.CLOUD_HIGH: [],
        w.HUMIDITY: [],
        w.DEW_POINT: [],
        w.TEMPERATURE: [],
        w.WIND: [],
        w.GUST: [],
        w.FOG: [],
        w.PRECIP: [],
        w.PRECIP_PROB: [],
    }
    for entry in timeseries:
        try:
            moment = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
            details = entry["data"]["instant"]["details"]
        except (KeyError, TypeError, ValueError):
            continue
        times.append(moment.timestamp())
        nxt = entry["data"].get("next_1_hours") or entry["data"].get("next_6_hours") or {}
        nxt_details = nxt.get("details") or {}

        def get(key: str, src: dict[str, Any] = details) -> float | None:
            value = src.get(key)
            return float(value) if isinstance(value, (int, float)) else None

        wind = get("wind_speed")
        gust = get("wind_speed_of_gust")
        fields[w.CLOUD].append(get("cloud_area_fraction"))
        fields[w.CLOUD_LOW].append(get("cloud_area_fraction_low"))
        fields[w.CLOUD_MID].append(get("cloud_area_fraction_medium"))
        fields[w.CLOUD_HIGH].append(get("cloud_area_fraction_high"))
        fields[w.HUMIDITY].append(get("relative_humidity"))
        fields[w.DEW_POINT].append(get("dew_point_temperature"))
        fields[w.TEMPERATURE].append(get("air_temperature"))
        fields[w.WIND].append(wind * 3.6 if wind is not None else None)
        fields[w.GUST].append(gust * 3.6 if gust is not None else None)
        fields[w.FOG].append(get("fog_area_fraction"))
        fields[w.PRECIP].append(get("precipitation_amount", nxt_details))
        fields[w.PRECIP_PROB].append(get("probability_of_precipitation", nxt_details))
    if not times:
        raise ProviderError("MET Norway returned no data")
    return w.WeatherSeries(source="met_no", fetched=fetched, times=times, fields=fields)


async def fetch(
    session: aiohttp.ClientSession,
    latitude: float,
    longitude: float,
    elevation: float,
    fetched: datetime,
    headers: dict[str, str],
) -> w.WeatherSeries:
    """Fetch and parse the forecast."""
    payload = await fetch_json(
        session,
        URL,
        {
            "lat": f"{latitude:.4f}",
            "lon": f"{longitude:.4f}",
            "altitude": f"{max(0, elevation):.0f}",
        },
        timeout=30.0,
        headers=headers,
    )
    return parse(payload, fetched)
