"""Vectorised horizontal coordinates for fixed (or slowly moving) targets."""

from __future__ import annotations

import numpy as np

from .skyglow import refraction_deg


def precess(vectors: np.ndarray, matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Apply a J2000→date rotation to unit vectors (3, N); return RA/Dec (rad)."""
    rotated = matrix @ vectors
    ra = np.arctan2(rotated[1], rotated[0]) % (2 * np.pi)
    dec = np.arcsin(np.clip(rotated[2], -1.0, 1.0))
    return ra, dec


def altaz(
    ra_rad: np.ndarray,
    dec_rad: np.ndarray,
    lst_deg: np.ndarray,
    latitude_deg: float,
    refraction: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Altitude/azimuth (deg) for N targets at T sidereal times → arrays (N, T).

    Azimuth is measured from north through east. Refraction (Sæmundsson) is
    applied to the geometric altitude when requested.
    """
    phi = np.radians(latitude_deg)
    ha = np.radians(lst_deg)[None, :] - np.asarray(ra_rad)[:, None]
    dec = np.asarray(dec_rad)[:, None]
    sin_alt = np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(ha)
    alt = np.degrees(np.arcsin(np.clip(sin_alt, -1.0, 1.0)))
    az = (
        np.degrees(
            np.arctan2(
                -np.sin(ha) * np.cos(dec),
                np.cos(phi) * np.sin(dec) - np.sin(phi) * np.cos(dec) * np.cos(ha),
            )
        )
        % 360.0
    )
    if refraction:
        alt = alt + refraction_deg(alt)
    return alt, az


def angular_separation(
    alt1: np.ndarray, az1: np.ndarray, alt2: np.ndarray, az2: np.ndarray
) -> np.ndarray:
    """Great-circle separation (deg) between two sets of horizontal positions."""
    a1 = np.radians(alt1)
    a2 = np.radians(alt2)
    daz = np.radians(np.asarray(az1) - np.asarray(az2))
    cos_sep = np.sin(a1) * np.sin(a2) + np.cos(a1) * np.cos(a2) * np.cos(daz)
    return np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0)))


def transit_info(
    ra_rad: np.ndarray, dec_rad: np.ndarray, latitude_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return (culmination altitude in deg, RA in deg) for targets."""
    culmination = 90.0 - np.abs(latitude_deg - np.degrees(dec_rad))
    return culmination, np.degrees(ra_rad)


def max_altitude(dec_deg: float, latitude_deg: float) -> float:
    """Highest geometric altitude reached by a target at a given declination."""
    return 90.0 - abs(latitude_deg - dec_deg)
