"""JPL Small-Body Database query API (https://ssd-api.jpl.nasa.gov).

Public NASA/JPL service, no key required. Used once a day to download the
osculating orbits of comets near perihelion and of the brightest asteroids.
"""

from __future__ import annotations

from datetime import datetime
import json

import aiohttp

from ..engine.smallbodies import OrbitalElements, parse_sbdb
from .base import fetch_json

URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
JD_UNIX_EPOCH = 2440587.5


def _jd(moment: datetime) -> float:
    return moment.timestamp() / 86400.0 + JD_UNIX_EPOCH


async def fetch_comets(
    session: aiohttp.ClientSession, now: datetime, headers: dict[str, str]
) -> list[OrbitalElements]:
    """Comets with a perihelion within ~13 months of now and q < 4 AU."""
    jd = _jd(now)
    constraint = {"AND": [f"tp|RG|{jd - 400:.1f}|{jd + 400:.1f}", "q|LT|4"]}
    payload = await fetch_json(
        session,
        URL,
        {
            "fields": "full_name,pdes,epoch,e,q,i,om,w,tp,M1,K1",
            "sb-kind": "c",
            "full-prec": "true",
            "sb-cdata": json.dumps(constraint, separators=(",", ":")),
        },
        timeout=60.0,
        headers=headers,
    )
    return parse_sbdb(payload, "comet")


async def fetch_asteroids(
    session: aiohttp.ClientSession, headers: dict[str, str]
) -> list[OrbitalElements]:
    """Inner Solar System asteroids that can become brighter than about mag 10."""
    constraint = {"AND": ["H|LT|7.5", "a|LT|4.2"]}
    payload = await fetch_json(
        session,
        URL,
        {
            "fields": "full_name,pdes,epoch,e,a,q,i,om,w,tp,H,G",
            "sb-kind": "a",
            "full-prec": "true",
            "sb-cdata": json.dumps(constraint, separators=(",", ":")),
        },
        timeout=60.0,
        headers=headers,
    )
    return parse_sbdb(payload, "asteroid")
