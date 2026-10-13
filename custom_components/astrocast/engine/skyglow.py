"""Night-sky brightness models.

* Light pollution is described by the Bortle scale, converted to a zenith sky
  brightness in V mag/arcsec² (approximate class mid-points; the user can enter a
  measured SQM value instead).
* Moonlight is modelled with Krisciunas & Schaefer (1991), "A model of the
  brightness of moonlight", PASP 103, 1033. The model gives the sky brightness
  added by the Moon at a given position as a function of lunar phase, the
  Moon-target separation, both zenith distances and the extinction coefficient.
"""

from __future__ import annotations

import math

import numpy as np

# Approximate zenith sky brightness (V mag/arcsec²) per Bortle class.
BORTLE_SQM: dict[int, float] = {
    1: 21.85,
    2: 21.65,
    3: 21.4,
    4: 20.85,
    5: 19.9,
    6: 19.1,
    7: 18.4,
    8: 17.8,
    9: 17.2,
}

DEFAULT_EXTINCTION = 0.2  # mag/airmass, typical clear sky in V


def bortle_to_sqm(bortle: int) -> float:
    """Return the zenith sky brightness for a Bortle class."""
    return BORTLE_SQM[min(9, max(1, int(bortle)))]


def sqm_to_nanolambert(sqm: float | np.ndarray) -> float | np.ndarray:
    """Convert V mag/arcsec² to nanoLamberts (Krisciunas & Schaefer eq. 1)."""
    return 34.08 * np.exp(20.7233 - 0.92104 * np.asarray(sqm, dtype=float))


def nanolambert_to_sqm(value: float | np.ndarray) -> float | np.ndarray:
    """Convert nanoLamberts to V mag/arcsec²."""
    value = np.maximum(np.asarray(value, dtype=float), 1e-6)
    return (20.7233 - np.log(value / 34.08)) / 0.92104


def airmass_ks(zenith_deg: float | np.ndarray) -> np.ndarray:
    """Airmass formula used by Krisciunas & Schaefer (valid down to the horizon)."""
    z = np.radians(np.clip(np.asarray(zenith_deg, dtype=float), 0.0, 90.0))
    return (1.0 - 0.96 * np.sin(z) ** 2) ** -0.5


def airmass(altitude_deg: float | np.ndarray) -> np.ndarray:
    """Kasten & Young (1989) relative airmass; altitudes below 0 are clipped."""
    h = np.clip(np.asarray(altitude_deg, dtype=float), 0.0, 90.0)
    return 1.0 / (np.sin(np.radians(h)) + 0.50572 * (h + 6.07995) ** -1.6364)


def dark_sky_brightness(
    sqm_zenith: float, zenith_deg: float | np.ndarray, extinction: float
) -> np.ndarray:
    """Moonless sky brightness (nL) at a zenith distance (K&S eq. 2)."""
    x = airmass_ks(zenith_deg)
    return sqm_to_nanolambert(sqm_zenith) * 10 ** (-0.4 * extinction * (x - 1.0)) * x


def moon_sky_brightness(
    phase_angle_deg: float | np.ndarray,
    separation_deg: float | np.ndarray,
    moon_zenith_deg: float | np.ndarray,
    target_zenith_deg: float | np.ndarray,
    extinction: float | np.ndarray,
) -> np.ndarray:
    """Sky brightness (nL) added by the Moon at a target (K&S eqs. 15-21).

    Returns 0 where the Moon is below the horizon. The scattering function is
    not valid very close to the Moon, so separations are floored at 3°.
    """
    alpha = np.abs(np.asarray(phase_angle_deg, dtype=float))
    rho = np.maximum(np.asarray(separation_deg, dtype=float), 3.0)
    zm = np.asarray(moon_zenith_deg, dtype=float)
    k = np.asarray(extinction, dtype=float)
    illuminance = 10 ** (-0.4 * (3.84 + 0.026 * alpha + 4e-9 * alpha**4))
    cos_rho = np.cos(np.radians(rho))
    scattering = 10**5.36 * (1.06 + cos_rho**2) + 10 ** (6.15 - rho / 40.0)
    brightness = (
        scattering
        * illuminance
        * 10 ** (-0.4 * k * airmass_ks(zm))
        * (1.0 - 10 ** (-0.4 * k * airmass_ks(target_zenith_deg)))
    )
    return np.where(zm < 90.5, brightness, 0.0)


def moon_brightening_mag(
    sqm_zenith: float,
    phase_angle_deg: float | np.ndarray,
    separation_deg: float | np.ndarray,
    moon_altitude_deg: float | np.ndarray,
    target_altitude_deg: float | np.ndarray,
    extinction: float | np.ndarray = DEFAULT_EXTINCTION,
) -> np.ndarray:
    """Return how much brighter (mag/arcsec²) the Moon makes the sky at a target."""
    target_z = 90.0 - np.clip(np.asarray(target_altitude_deg, dtype=float), 0.0, 90.0)
    moon_z = 90.0 - np.asarray(moon_altitude_deg, dtype=float)
    k = float(np.mean(extinction)) if np.ndim(extinction) else float(extinction)
    dark = dark_sky_brightness(sqm_zenith, target_z, k)
    moon = moon_sky_brightness(phase_angle_deg, separation_deg, moon_z, target_z, extinction)
    return 2.5 * np.log10((dark + moon) / dark)


def phase_angle_from_illumination(fraction: float) -> float:
    """Approximate lunar phase angle (deg) from the illuminated fraction."""
    fraction = min(1.0, max(0.0, fraction))
    return math.degrees(math.acos(2.0 * fraction - 1.0))


def extinction_from_aod(aod_550: float, elevation_m: float) -> float:
    """V-band extinction coefficient (mag/airmass) from aerosol optical depth.

    k = 1.086 · (τ_Rayleigh + τ_ozone + τ_aerosol), with the Rayleigh optical
    depth at 550 nm (0.0973 at sea level) scaled by the pressure ratio
    (scale height 8.4 km) and a typical ozone contribution of 0.016.
    """
    tau_rayleigh = 0.0973 * math.exp(-max(0.0, elevation_m) / 8400.0)
    return 1.086 * (tau_rayleigh + 0.016 + max(0.0, aod_550))


def refraction_deg(altitude_deg: np.ndarray) -> np.ndarray:
    """Atmospheric refraction (Sæmundsson 1986) to add to a geometric altitude."""
    h = np.asarray(altitude_deg, dtype=float)
    hc = np.maximum(h, -1.0)
    r = 1.02 / np.tan(np.radians(hc + 10.3 / (hc + 5.11))) / 60.0
    return np.where(h > -1.0, r, 0.0)
