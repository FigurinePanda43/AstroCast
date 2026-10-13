"""Local horizon profile (obstacles such as trees or buildings).

The profile is entered as ``azimuth:altitude`` pairs, for example
``"0:15, 90:30, 180:10, 270:25"``. Between the points the obstruction is
linearly interpolated (wrapping around north). The effective limit for an
object is the larger of this profile and the global minimum altitude.
"""

from __future__ import annotations

import re

import numpy as np

_PAIR = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*[:=/]\s*(-?\d+(?:[.,]\d+)?)\s*$")


class HorizonError(ValueError):
    """The horizon profile cannot be parsed."""


def parse_horizon(text: str | None) -> tuple[tuple[float, float], ...]:
    """Parse ``"az:alt, az:alt"`` into sorted (azimuth, altitude) pairs."""
    if not text or not text.strip():
        return ()
    points: dict[float, float] = {}
    for raw in re.split(r"[;,\s]+(?=-?\d+(?:[.,]\d+)?\s*[:=/])", text.strip()):
        chunk = raw.strip().strip(",;")
        if not chunk:
            continue
        match = _PAIR.match(chunk)
        if not match:
            raise HorizonError(chunk)
        az = float(match.group(1).replace(",", ".")) % 360.0
        alt = float(match.group(2).replace(",", "."))
        if not -5.0 <= alt <= 90.0:
            raise HorizonError(chunk)
        points[az] = alt
    return tuple(sorted(points.items()))


def format_horizon(points: tuple[tuple[float, float], ...]) -> str:
    """Canonical text form of a profile."""
    return ", ".join(f"{az:g}:{alt:g}" for az, alt in points)


def horizon_altitude(
    points: tuple[tuple[float, float], ...] | list[list[float]], azimuth: np.ndarray
) -> np.ndarray:
    """Obstruction altitude (deg) at the given azimuths (0 where no profile)."""
    az = np.asarray(azimuth, dtype=float)
    if not points:
        return np.zeros_like(az)
    azs = np.array([p[0] for p in points], dtype=float)
    alts = np.array([p[1] for p in points], dtype=float)
    if len(azs) == 1:
        return np.full_like(az, alts[0])
    return np.interp(az % 360.0, azs, alts, period=360.0)


def altitude_limit(
    points: tuple[tuple[float, float], ...], azimuth: np.ndarray, min_altitude: float
) -> np.ndarray:
    """Lowest usable altitude: the horizon profile or the global minimum."""
    return np.maximum(horizon_altitude(points, azimuth), min_altitude)
