"""7Timer! ASTRO product (https://www.7timer.info).

7Timer! is a free numerical forecast service operated by Ye Quanzhi, based on
NOAA GFS. The ASTRO product gives 3-hourly forecasts for 72 h of cloud cover,
astronomical seeing, transparency, instability (lifted index), humidity, wind,
temperature and precipitation type. Values are classes; they are converted to
physical units using the class mid-points documented by 7Timer!.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from ..engine import weather as w
from .base import ProviderError, fetch_json

URL = "https://www.7timer.info/bin/api.pl"

# Class mid-points.
CLOUD_PCT = {1: 3.0, 2: 12.5, 3: 25.0, 4: 37.5, 5: 50.0, 6: 62.5, 7: 75.0, 8: 87.5, 9: 97.0}
SEEING_ARCSEC = {1: 0.4, 2: 0.625, 3: 0.875, 4: 1.125, 5: 1.375, 6: 1.75, 7: 2.25, 8: 2.75}
TRANSPARENCY_K = {1: 0.25, 2: 0.35, 3: 0.45, 4: 0.55, 5: 0.65, 6: 0.775, 7: 0.925, 8: 1.1}
WIND_KMH = {1: 0.5, 2: 6.7, 3: 20.5, 4: 33.8, 5: 50.4, 6: 75.1, 7: 102.8, 8: 125.0}
PRECIP_TYPES = {"none": 0.0, "rain": 1.0, "snow": 2.0, "frzr": 3.0, "icep": 4.0}


def _rh(value: int) -> float | None:
    if value < -4 or value > 16:
        return None
    if value == 16:
        return 100.0
    if value == 15:
        return 97.0
    return (value + 4) * 5.0 + 2.5


def _cls(table: dict[int, float], value: Any) -> float | None:
    try:
        return table.get(int(value))
    except (TypeError, ValueError):
        return None


def parse(payload: dict[str, Any], fetched: datetime) -> w.WeatherSeries:
    """Parse the JSON response of the ASTRO product."""
    try:
        init = datetime.strptime(str(payload["init"]), "%Y%m%d%H").replace(tzinfo=UTC)
        rows = payload["dataseries"]
    except (KeyError, ValueError) as err:
        raise ProviderError(f"unexpected 7Timer! payload: {err}") from err
    times: list[float] = []
    fields: dict[str, list[float | None]] = {
        w.CLOUD: [],
        w.SEEING: [],
        w.TRANSPARENCY: [],
        w.LIFTED: [],
        w.HUMIDITY: [],
        w.WIND: [],
        w.TEMPERATURE: [],
        w.PRECIP_TYPE: [],
    }
    for row in rows:
        try:
            moment = init + timedelta(hours=int(row["timepoint"]))
        except (KeyError, TypeError, ValueError):
            continue
        times.append(moment.timestamp())
        fields[w.CLOUD].append(_cls(CLOUD_PCT, row.get("cloudcover")))
        fields[w.SEEING].append(_cls(SEEING_ARCSEC, row.get("seeing")))
        fields[w.TRANSPARENCY].append(_cls(TRANSPARENCY_K, row.get("transparency")))
        lifted = row.get("lifted_index")
        fields[w.LIFTED].append(
            float(lifted) if isinstance(lifted, (int, float)) and lifted > -100 else None
        )
        rh = row.get("rh2m")
        fields[w.HUMIDITY].append(_rh(int(rh)) if isinstance(rh, (int, float)) else None)
        wind = row.get("wind10m") or {}
        fields[w.WIND].append(_cls(WIND_KMH, wind.get("speed")))
        temp = row.get("temp2m")
        fields[w.TEMPERATURE].append(
            float(temp) if isinstance(temp, (int, float)) and temp > -100 else None
        )
        fields[w.PRECIP_TYPE].append(PRECIP_TYPES.get(str(row.get("prec_type"))))
    if not times:
        raise ProviderError("7Timer! returned no data")
    return w.WeatherSeries(
        source="7timer", fetched=fetched, times=times, fields=fields, model_run=init
    )


async def fetch(
    session: aiohttp.ClientSession,
    latitude: float,
    longitude: float,
    fetched: datetime,
    headers: dict[str, str],
) -> w.WeatherSeries:
    """Fetch and parse the ASTRO forecast."""
    payload = await fetch_json(
        session,
        URL,
        {
            "lon": f"{longitude:.3f}",
            "lat": f"{latitude:.3f}",
            "product": "astro",
            "ac": "0",
            "unit": "metric",
            "output": "json",
            "tzshift": "0",
        },
        timeout=45.0,
        headers=headers,
        retries=1,
    )
    return parse(payload, fetched)
