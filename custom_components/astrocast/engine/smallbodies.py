"""Comets and asteroids: two-body propagation from osculating elements.

Orbital elements come from the JPL Small-Body Database (SBDB) query API.
Positions are propagated with a universal-variable Kepler solver (valid for
elliptic, parabolic and hyperbolic orbits) and converted to topocentric
coordinates with astronomy-engine for the Earth and observer vectors.

Two-body propagation ignores planetary perturbations; with elements refreshed
regularly from JPL the error is typically well below a few arcminutes, which is
adequate for observation planning. Comet magnitudes use the standard total
magnitude law m = M1 + 5 log Δ + K1 log r and are notoriously uncertain
(comets can outburst or fade): they are always reported as estimates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any

import astronomy

from .timeutil import to_astro

GAUSS_K = 0.01720209895  # Gaussian gravitational constant (AU^1.5 / day)
MU = GAUSS_K**2  # AU³/day²
SPEED_OF_LIGHT_AU_PER_DAY = 173.1446326846693
OBLIQUITY_J2000 = math.radians(23.4392911)
JD_J2000 = 2451545.0


@dataclass(slots=True, frozen=True)
class OrbitalElements:
    """Heliocentric osculating elements (ecliptic and equinox J2000)."""

    id: str
    name: str
    kind: str  # "comet" or "asteroid"
    q: float  # perihelion distance (AU)
    e: float
    i: float  # inclination (deg)
    node: float  # longitude of ascending node (deg)
    peri: float  # argument of perihelion (deg)
    tp: float  # time of perihelion (JD, TDB)
    epoch: float  # JD of osculation
    h: float | None = None  # asteroid absolute magnitude / comet M1
    g: float | None = None  # asteroid slope / comet K1

    @property
    def semi_major_axis(self) -> float | None:
        """Semi-major axis (AU) for bound orbits."""
        if self.e >= 1.0:
            return None
        return self.q / (1.0 - self.e)

    @property
    def period_days(self) -> float | None:
        """Orbital period in days for bound orbits."""
        a = self.semi_major_axis
        if a is None:
            return None
        return 2.0 * math.pi * a**1.5 / GAUSS_K


def _stumpff(z: float) -> tuple[float, float]:
    """Stumpff functions C(z), S(z)."""
    if z > 1e-6:
        sz = math.sqrt(z)
        return (1.0 - math.cos(sz)) / z, (sz - math.sin(sz)) / (sz**3)
    if z < -1e-6:
        sz = math.sqrt(-z)
        return (math.cosh(sz) - 1.0) / (-z), (math.sinh(sz) - sz) / (sz**3)
    return 0.5 - z / 24.0 + z * z / 720.0, 1.0 / 6.0 - z / 120.0 + z * z / 5040.0


def _perifocal_position(q: float, e: float, dt_days: float) -> tuple[float, float]:
    """Position in the orbital plane (x towards perihelion) after ``dt`` days."""
    alpha = (1.0 - e) / q  # reciprocal semi-major axis
    v0 = math.sqrt(MU * (1.0 + e) / q)
    sqrt_mu = math.sqrt(MU)
    # Initial guess for the universal anomaly.
    if alpha > 0:
        chi = sqrt_mu * dt_days * alpha
    else:
        chi = math.copysign(1.0, dt_days) * (abs(6.0 * q * sqrt_mu * dt_days)) ** (1.0 / 3.0)
        if abs(dt_days) < 1e-9:
            chi = 0.0
    for _ in range(80):
        z = alpha * chi * chi
        c, s = _stumpff(z)
        f_val = (1.0 - alpha * q) * chi**3 * s + q * chi - sqrt_mu * dt_days
        # dF/dchi equals the heliocentric distance for this formulation.
        derivative = (1.0 - alpha * q) * chi * chi * c + q
        step = f_val / derivative
        chi -= step
        if abs(step) < 1e-12 * max(1.0, abs(chi)):
            break
    z = alpha * chi * chi
    c, s = _stumpff(z)
    f = 1.0 - chi * chi / q * c
    g = dt_days - chi**3 * s / sqrt_mu
    return f * q, g * v0


def heliocentric_ecliptic(elements: OrbitalElements, jd: float) -> tuple[float, float, float]:
    """Heliocentric ecliptic J2000 position (AU) at Julian date ``jd`` (TDB)."""
    dt = jd - elements.tp
    period = elements.period_days
    if period is not None:
        dt = (dt + period / 2.0) % period - period / 2.0
    x_p, y_p = _perifocal_position(elements.q, elements.e, dt)
    w = math.radians(elements.peri)
    node = math.radians(elements.node)
    inc = math.radians(elements.i)
    cw, sw = math.cos(w), math.sin(w)
    cn, sn = math.cos(node), math.sin(node)
    ci, si = math.cos(inc), math.sin(inc)
    x = (cn * cw - sn * sw * ci) * x_p + (-cn * sw - sn * cw * ci) * y_p
    y = (sn * cw + cn * sw * ci) * x_p + (-sn * sw + cn * cw * ci) * y_p
    zc = (sw * si) * x_p + (cw * si) * y_p
    return x, y, zc


def ecliptic_to_equatorial(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Rotate an ecliptic J2000 vector to the J2000 equator (EQJ)."""
    ce, se = math.cos(OBLIQUITY_J2000), math.sin(OBLIQUITY_J2000)
    return x, ce * y - se * z, se * y + ce * z


@dataclass(slots=True)
class SmallBodyPosition:
    """Apparent position and brightness of a small body."""

    ra_hours: float  # equator of date
    dec: float
    ra_j2000_hours: float
    dec_j2000: float
    distance_au: float  # from the observer
    sun_distance_au: float
    phase_angle: float
    elongation: float
    mag: float | None
    constellation: str


def position(
    elements: OrbitalElements,
    moment: datetime,
    observer: astronomy.Observer | None,
) -> SmallBodyPosition:
    """Apparent position of a small body (topocentric, or geocentric if None)."""
    time = to_astro(moment)
    jd = time.tt + JD_J2000
    earth = astronomy.HelioVector(astronomy.Body.Earth, time)
    ox, oy, oz = earth.x, earth.y, earth.z
    if observer is not None:
        obs = astronomy.ObserverVector(time, observer, False)
        ox, oy, oz = ox + obs.x, oy + obs.y, oz + obs.z

    # Light-time iteration.
    tau = 0.0
    for _ in range(3):
        bx, by, bz = ecliptic_to_equatorial(*heliocentric_ecliptic(elements, jd - tau))
        dx, dy, dz = bx - ox, by - oy, bz - oz
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        tau = distance / SPEED_OF_LIGHT_AU_PER_DAY

    r = math.sqrt(bx * bx + by * by + bz * bz)
    r_earth = math.sqrt(ox * ox + oy * oy + oz * oz)
    cos_phase = (r * r + distance * distance - r_earth * r_earth) / (2 * r * distance)
    phase = math.degrees(math.acos(max(-1.0, min(1.0, cos_phase))))
    cos_elong = (r_earth * r_earth + distance * distance - r * r) / (2 * r_earth * distance)
    elong = math.degrees(math.acos(max(-1.0, min(1.0, cos_elong))))

    vec_j2000 = astronomy.Vector(dx, dy, dz, time)
    sph_j2000 = astronomy.EquatorFromVector(vec_j2000)
    vec_date = astronomy.RotateVector(astronomy.Rotation_EQJ_EQD(time), vec_j2000)
    sph_date = astronomy.EquatorFromVector(vec_date)
    constellation = astronomy.Constellation(sph_j2000.ra, sph_j2000.dec).symbol

    return SmallBodyPosition(
        ra_hours=sph_date.ra,
        dec=sph_date.dec,
        ra_j2000_hours=sph_j2000.ra,
        dec_j2000=sph_j2000.dec,
        distance_au=distance,
        sun_distance_au=r,
        phase_angle=phase,
        elongation=elong,
        mag=magnitude(elements, r, distance, phase),
        constellation=constellation,
    )


def magnitude(
    elements: OrbitalElements, r: float, delta: float, phase_deg: float
) -> float | None:
    """Apparent magnitude estimate."""
    if elements.h is None:
        return None
    if elements.kind == "comet":
        k1 = elements.g if elements.g is not None else 10.0
        return elements.h + 5.0 * math.log10(delta) + k1 * math.log10(r)
    g = elements.g if elements.g is not None else 0.15
    tan_half = math.tan(math.radians(phase_deg) / 2.0)
    phi1 = math.exp(-3.33 * tan_half**0.63)
    phi2 = math.exp(-1.87 * tan_half**1.22)
    reduced = (1.0 - g) * phi1 + g * phi2
    return elements.h + 5.0 * math.log10(r * delta) - 2.5 * math.log10(max(reduced, 1e-9))


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_sbdb(payload: dict[str, Any], kind: str) -> list[OrbitalElements]:
    """Parse a JPL SBDB query API response into orbital elements.

    Expected fields: full_name, pdes, epoch, e, q, i, om, w, tp and either
    (H, G) for asteroids or (M1, K1) for comets.
    """
    fields = payload.get("fields") or []
    result: list[OrbitalElements] = []
    for row in payload.get("data") or []:
        item = dict(zip(fields, row, strict=False))
        e = _float(item.get("e"))
        q = _float(item.get("q"))
        if q is None and (a := _float(item.get("a"))) is not None and e is not None:
            q = a * (1.0 - e)
        values = [e, q, _float(item.get("i")), _float(item.get("om")), _float(item.get("w")), _float(item.get("tp"))]
        if any(v is None for v in values) or q is None or q <= 0:
            continue
        e, q, inc, node, peri, tp = values  # type: ignore[misc]
        name = " ".join(str(item.get("full_name", "")).split())
        designation = str(item.get("pdes") or name).strip()
        if kind == "comet":
            h, g = _float(item.get("M1")), _float(item.get("K1"))
        else:
            h, g = _float(item.get("H")), _float(item.get("G"))
        result.append(
            OrbitalElements(
                id=f"{kind}:{designation}",
                name=name,
                kind=kind,
                q=q,
                e=e,
                i=inc,
                node=node,
                peri=peri,
                tp=tp,
                epoch=_float(item.get("epoch")) or tp,
                h=h,
                g=g,
            )
        )
    return result
