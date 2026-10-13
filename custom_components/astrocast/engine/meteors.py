"""Major annual meteor showers.

Parameters follow the International Meteor Organization (IMO) Meteor Shower
Calendar / working list: activity period, solar longitude of the maximum
(J2000.0), zenithal hourly rate (ZHR), radiant at maximum, geocentric velocity
and population index r. The peak instant is computed every year from the
solar longitude, so the table never needs a yearly update (the ZHR of some
showers — Quadrantids, Draconids, Leonids — is variable from year to year).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math

import astronomy

from .timeutil import from_astro, to_astro


@dataclass(slots=True, frozen=True)
class MeteorShower:
    """Static description of a meteor shower."""

    code: str
    name_en: str
    name_fr: str
    start: tuple[int, int]  # (month, day) of activity start
    end: tuple[int, int]  # (month, day) of activity end
    peak_longitude: float  # solar longitude J2000.0 (deg)
    zhr: float
    radiant_ra: float  # deg
    radiant_dec: float  # deg
    velocity: float  # km/s
    population_index: float
    variable: bool = False

    def name(self, language: str = "en") -> str:
        """Localised name."""
        return self.name_fr if language.startswith("fr") else self.name_en


SHOWERS: tuple[MeteorShower, ...] = (
    MeteorShower("QUA", "Quadrantids", "Quadrantides", (12, 28), (1, 12), 283.15, 80, 230, 49, 41, 2.1, True),
    MeteorShower("LYR", "Lyrids", "Lyrides", (4, 14), (4, 30), 32.32, 18, 271, 34, 49, 2.1),
    MeteorShower("ETA", "Eta Aquariids", "Êta Aquarides", (4, 19), (5, 28), 45.5, 50, 338, -1, 66, 2.4),
    MeteorShower("SDA", "Southern Delta Aquariids", "Delta Aquarides du Sud", (7, 12), (8, 23), 127.0, 25, 340, -16, 41, 2.5),
    MeteorShower("CAP", "Alpha Capricornids", "Alpha Capricornides", (7, 3), (8, 15), 127.0, 5, 307, -10, 23, 2.5),
    MeteorShower("PER", "Perseids", "Perséides", (7, 17), (8, 24), 140.0, 100, 48, 58, 59, 2.2),
    MeteorShower("DRA", "Draconids", "Draconides", (10, 6), (10, 10), 195.4, 10, 262, 54, 20, 2.6, True),
    MeteorShower("STA", "Southern Taurids", "Taurides du Sud", (9, 10), (11, 20), 197.0, 5, 32, 9, 27, 2.3),
    MeteorShower("ORI", "Orionids", "Orionides", (10, 2), (11, 7), 208.0, 20, 95, 16, 66, 2.5),
    MeteorShower("NTA", "Northern Taurids", "Taurides du Nord", (10, 20), (12, 10), 230.0, 5, 58, 22, 29, 2.3),
    MeteorShower("LEO", "Leonids", "Léonides", (11, 6), (11, 30), 235.27, 15, 152, 22, 71, 2.5, True),
    MeteorShower("GEM", "Geminids", "Géminides", (12, 4), (12, 20), 262.2, 150, 112, 33, 35, 2.6),
    MeteorShower("URS", "Ursids", "Ursides", (12, 17), (12, 26), 270.7, 10, 217, 76, 33, 3.0, True),
)


def peak_time(shower: MeteorShower, year: int) -> datetime | None:
    """Instant of maximum activity for ``year`` (from the J2000 solar longitude).

    astronomy-engine searches the apparent longitude of date; the J2000 value is
    converted with the general precession in longitude (1.3969713°/century).
    """
    start = to_astro(datetime(year, 1, 1, tzinfo=UTC))
    centuries = (year + 0.5 - 2000.0) / 100.0
    target = (shower.peak_longitude + 1.3969713 * centuries) % 360.0
    found = astronomy.SearchSunLongitude(target, start, 366.0)
    if found is None:
        return None
    moment = from_astro(found)
    return moment if moment.year == year else None


def limiting_magnitude(sqm: float) -> float:
    """Naked-eye limiting magnitude from sky brightness (Schaefer 1990 approx.)."""
    return 7.93 - 5.0 * math.log10(10 ** (4.316 - sqm / 5.0) + 1.0)


def hourly_rate(
    shower: MeteorShower, radiant_altitude: float, limiting_mag: float
) -> float:
    """Expected visual hourly rate: HR = ZHR · sin(h) / r^(6.5 − LM)."""
    if radiant_altitude <= 0:
        return 0.0
    return (
        shower.zhr
        * math.sin(math.radians(radiant_altitude))
        / shower.population_index ** (6.5 - limiting_mag)
    )
