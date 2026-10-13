"""Astronomy engine: ephemerides, small bodies, events and sky brightness."""

from __future__ import annotations

from datetime import UTC, date, datetime
import math

import astronomy
import numpy as np
import pytest

from custom_components.astrocast.engine import skyglow
from custom_components.astrocast.engine.catalog import load_catalog
from custom_components.astrocast.engine.ephemeris import (
    BODIES,
    Location,
    compute_night,
    horizontal,
    moon_phase_name,
)
from custom_components.astrocast.engine.events import (
    compute_events,
    lunar_eclipses,
    meteor_showers,
    moon_phases,
    oppositions,
    seasons,
    solar_eclipses,
)
from custom_components.astrocast.engine.meteors import SHOWERS, limiting_magnitude, peak_time
from custom_components.astrocast.engine.positions import altaz, precess
from custom_components.astrocast.engine.smallbodies import parse_sbdb, position
from custom_components.astrocast.engine.timeutil import from_astro, night_date_for, to_astro

from .conftest import load_fixture

AVIGNON = Location(43.92, 5.05, 100)
SITES = [
    AVIGNON,
    Location(-33.87, 151.21, 20),  # Sydney
    Location(64.15, -21.94, 0),  # Reykjavik
    Location(0.0, -78.5, 2800),  # Quito
]


def _ref_altitude(loc: Location, start: datetime, direction: astronomy.Direction, alt: float):
    found = astronomy.SearchAltitude(
        astronomy.Body.Sun, loc.observer, direction, to_astro(start), 1.0, alt
    )
    return from_astro(found) if found else None


@pytest.mark.parametrize("loc", SITES)
@pytest.mark.parametrize("night", [date(2026, 3, 20), date(2026, 6, 21), date(2026, 12, 21)])
def test_twilight_times_match_exact_searches(loc: Location, night: date) -> None:
    """Interpolated twilight instants agree with astronomy-engine searches."""
    ephem = compute_night(loc, night, with_planets=False)
    pairs = [
        (ephem.astro_dusk, astronomy.Direction.Set, -18.0),
        (ephem.nautical_dusk, astronomy.Direction.Set, -12.0),
        (ephem.civil_dusk, astronomy.Direction.Set, -6.0),
    ]
    for value, direction, alt in pairs:
        ref = _ref_altitude(loc, ephem.start, direction, alt)
        if ref is None or ref >= ephem.end:
            assert value is None
        else:
            assert value is not None
            assert abs((value - ref).total_seconds()) < 30
    ref_set = astronomy.SearchRiseSet(
        astronomy.Body.Sun, loc.observer, astronomy.Direction.Set, to_astro(ephem.start), 1.0
    )
    if ref_set is not None and from_astro(ref_set) < ephem.end:
        # astronomy-engine also models the thinner air of high-altitude sites.
        assert abs((ephem.sunset - from_astro(ref_set)).total_seconds()) < 60


def test_polar_cases() -> None:
    """Midnight sun has no darkness; polar night is dark all day."""
    tromso = Location(69.65, 18.96, 0)
    summer = compute_night(tromso, date(2026, 6, 21), with_planets=False)
    assert summer.sunset is None and summer.sunrise is None
    assert summer.dark_hours == 0
    winter = compute_night(tromso, date(2026, 12, 21), with_planets=False)
    assert winter.sunset is None
    assert winter.astro_dusk is not None
    assert winter.dark_hours > 12


def test_body_positions_match_direct_computation() -> None:
    """Interpolated planet and Moon altitudes stay within 0.02°."""
    ephem = compute_night(AVIGNON, date(2026, 10, 13))
    for key in ("mars", "jupiter", "saturn", "venus"):
        track = ephem.planets[key]
        for i in range(0, len(ephem.times), 5):
            alt, _az = horizontal(BODIES[key], to_astro(ephem.times[i]), AVIGNON.observer)
            if alt > 0:
                assert abs(alt - track.alt[i]) < 0.02, key
    for i in range(0, len(ephem.times), 5):
        alt, _az = horizontal(astronomy.Body.Moon, to_astro(ephem.times[i]), AVIGNON.observer)
        if alt > 0:
            assert abs(alt - ephem.moon_alt[i]) < 0.02


def test_planet_data_october_2026() -> None:
    """Saturn and Neptune are near opposition in October 2026."""
    ephem = compute_night(AVIGNON, date(2026, 10, 13))
    saturn = ephem.planets["saturn"]
    assert abs(saturn.elongation) > 165
    assert saturn.constellation in ("Cet", "Psc")
    assert 0 < saturn.mag < 1
    assert ephem.planets["jupiter"].mag < -1.5
    assert ephem.moon_illumination < 0.2
    assert moon_phase_name(ephem.moon_phase) == "waxing_crescent"


def test_moon_phase_names() -> None:
    assert moon_phase_name(0.5) == "new_moon"
    assert moon_phase_name(45) == "waxing_crescent"
    assert moon_phase_name(90) == "first_quarter"
    assert moon_phase_name(180) == "full_moon"
    assert moon_phase_name(270) == "last_quarter"
    assert moon_phase_name(300) == "waning_crescent"


def test_night_date_for() -> None:
    assert night_date_for(datetime(2026, 10, 14, 1, 0, tzinfo=UTC), 5.0) == date(2026, 10, 13)
    assert night_date_for(datetime(2026, 10, 13, 15, 0, tzinfo=UTC), 5.0) == date(2026, 10, 13)


def test_vectorised_catalog_positions() -> None:
    """Vectorised alt/az of catalog objects agree with astronomy-engine."""
    catalog = load_catalog()
    ephem = compute_night(AVIGNON, date(2026, 10, 13), with_planets=False)
    ra, dec = precess(catalog.vectors, ephem.precession)
    alt, az = altaz(ra, dec, ephem.lst_deg, AVIGNON.latitude)
    for oid in ("M31", "M45", "M13", "NGC7000"):
        i = catalog.objects.index(catalog.by_id[oid])
        obj = catalog.by_id[oid]
        for k in (40, 60, 80):
            time = to_astro(ephem.times[k])
            vec = astronomy.Vector(
                math.cos(math.radians(obj.dec)) * math.cos(math.radians(obj.ra)),
                math.cos(math.radians(obj.dec)) * math.sin(math.radians(obj.ra)),
                math.sin(math.radians(obj.dec)),
                time,
            )
            sph = astronomy.EquatorFromVector(
                astronomy.RotateVector(astronomy.Rotation_EQJ_EQD(time), vec)
            )
            hor = astronomy.Horizon(
                time, AVIGNON.observer, sph.ra, sph.dec, astronomy.Refraction.Normal
            )
            if hor.altitude > 5:
                assert abs(hor.altitude - alt[i, k]) < 0.05
                assert abs(((hor.azimuth - az[i, k] + 180) % 360) - 180) < 0.1


@pytest.mark.parametrize(
    ("object_id", "ra", "dec", "mag", "delta"),
    [
        # JPL Horizons, astrometric J2000, geocentric, 2026-10-14 00:00 UT.
        ("asteroid:4", 22.35008, -3.42239, 6.394, 1.48358589570973),
        ("comet:2026 A2", 283.34260, 64.14547, 14.345, 1.78442464351136),
        ("comet:2025 V2", 185.49741, 15.78065, 16.080, 3.57718860937986),
    ],
)
def test_small_bodies_against_horizons(
    object_id: str, ra: float, dec: float, mag: float, delta: float
) -> None:
    elements = {
        e.id: e
        for e in parse_sbdb(load_fixture("jpl_comets.json"), "comet")
        + parse_sbdb(load_fixture("jpl_asteroids.json"), "asteroid")
    }[object_id]
    pos = position(elements, datetime(2026, 10, 14, tzinfo=UTC), None)
    dra = (pos.ra_j2000_hours * 15.0 - ra) * math.cos(math.radians(dec))
    error_arcmin = math.hypot(dra, pos.dec_j2000 - dec) * 60.0
    assert error_arcmin < 2.0
    assert abs(pos.mag - mag) < 0.15
    assert abs(pos.distance_au - delta) / delta < 1e-3


def test_parse_sbdb_skips_incomplete_rows() -> None:
    payload = {
        "fields": ["full_name", "pdes", "epoch", "e", "q", "i", "om", "w", "tp", "M1", "K1"],
        "data": [
            [
                "  1P/Halley",
                "1P",
                "2439875.5",
                ".967",
                ".575",
                "162.2",
                "59.1",
                "112.2",
                "2446470",
                "5.5",
                "8",
            ],
            ["  Broken", "X", None, None, None, None, None, None, None, None, None],
        ],
    }
    result = parse_sbdb(payload, "comet")
    assert [e.id for e in result] == ["comet:1P"]
    assert result[0].semi_major_axis == pytest.approx(0.575 / 0.033, rel=1e-6)


def test_solar_eclipse_2026_august() -> None:
    """12 Aug 2026: total in northern Spain, deep partial at sunset in Provence."""
    start, end = datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
    burgos = solar_eclipses(start, end, Location(42.34, -3.70, 850).observer)
    assert len(burgos) == 1
    assert burgos[0].data["kind"] == "total"
    total = burgos[0].data["total_end"] - burgos[0].data["total_begin"]
    assert 90 < total.total_seconds() < 120
    avignon = solar_eclipses(start, end, AVIGNON.observer)
    assert avignon[0].data["kind"] == "partial"
    assert avignon[0].data["obscuration"] > 0.9


def test_lunar_eclipses_2026() -> None:
    events = lunar_eclipses(
        datetime(2026, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC), AVIGNON.observer
    )
    by_date = {e.best_time.date(): e for e in events}
    march = by_date[date(2026, 3, 3)]
    assert march.data["kind"] == "total"
    assert march.visible is False  # Moon below the horizon in Europe
    august = by_date[date(2026, 8, 28)]
    assert august.data["kind"] == "partial"
    assert august.visible is True


def test_oppositions() -> None:
    events = oppositions(
        datetime(2026, 10, 1, tzinfo=UTC), datetime(2027, 12, 31, tzinfo=UTC), AVIGNON.observer
    )
    dates = {e.data["body"]: e.start.date() for e in events}
    assert dates["saturn"] == date(2026, 10, 4)
    assert dates["mars"] == date(2027, 2, 19)
    assert dates["jupiter"] == date(2027, 2, 11)


def test_moon_phases_and_supermoon() -> None:
    events = moon_phases(datetime(2026, 12, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC))
    full = [e for e in events if e.data["phase"] == "full_moon"]
    assert len(full) == 1
    assert full[0].start.date() == date(2026, 12, 24)
    assert full[0].data["supermoon"] is True


def test_seasons() -> None:
    events = seasons(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC))
    assert [e.data["season"] for e in events] == [
        "march_equinox",
        "june_solstice",
        "september_equinox",
        "december_solstice",
    ]
    assert events[3].start.date() == date(2026, 12, 21)


def test_meteor_shower_peaks() -> None:
    """Peak dates follow the IMO calendar (computed from the solar longitude)."""
    expected = {"PER": date(2026, 8, 13), "GEM": date(2026, 12, 14), "QUA": date(2026, 1, 3)}
    for shower in SHOWERS:
        if shower.code in expected:
            assert peak_time(shower, 2026).date() == expected[shower.code]
    events = meteor_showers(
        datetime(2026, 12, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC), AVIGNON, 21.0
    )
    geminids = next(e for e in events if e.data["code"] == "GEM")
    assert geminids.importance == 3
    assert 50 < geminids.data["rate"] < 150
    assert geminids.visible


def test_limiting_magnitude() -> None:
    assert limiting_magnitude(21.5) == pytest.approx(6.4, abs=0.2)
    assert limiting_magnitude(18.0) < limiting_magnitude(20.0) < limiting_magnitude(21.5)


def test_compute_events_is_sorted_and_complete() -> None:
    comets = parse_sbdb(load_fixture("jpl_comets.json"), "comet")
    events = compute_events(AVIGNON, datetime(2026, 10, 13, 18, tzinfo=UTC), 21.0, comets)
    assert events == sorted(events, key=lambda e: e.start)
    types = {e.type for e in events}
    assert {"moon_phase", "meteor_shower", "opposition", "season", "conjunction"} <= types
    assert len({e.id for e in events}) == len(events)


def test_moonlight_model() -> None:
    """Full Moon high in the sky brightens a dark site by ~3 mag/arcsec²."""
    full = float(skyglow.moon_brightening_mag(21.4, 0.0, 50.0, 60.0, 90.0, 0.2))
    assert 2.5 < full < 3.6
    quarter = float(skyglow.moon_brightening_mag(21.4, 90.0, 50.0, 40.0, 90.0, 0.2))
    assert 0.5 < quarter < 1.5
    below = float(skyglow.moon_brightening_mag(21.4, 0.0, 120.0, -10.0, 90.0, 0.2))
    assert below == pytest.approx(0.0, abs=1e-9)
    city = float(skyglow.moon_brightening_mag(17.8, 0.0, 50.0, 60.0, 90.0, 0.2))
    assert city < full  # light pollution dilutes moonlight


def test_skyglow_helpers() -> None:
    assert skyglow.bortle_to_sqm(1) > skyglow.bortle_to_sqm(5) > skyglow.bortle_to_sqm(9)
    assert skyglow.bortle_to_sqm(42) == skyglow.bortle_to_sqm(9)
    sqm = np.array([18.0, 21.5])
    np.testing.assert_allclose(
        skyglow.nanolambert_to_sqm(skyglow.sqm_to_nanolambert(sqm)), sqm, rtol=1e-9
    )
    assert skyglow.extinction_from_aod(0.1, 0) == pytest.approx(1.086 * (0.0973 + 0.016 + 0.1))
    assert skyglow.extinction_from_aod(0.1, 3000) < skyglow.extinction_from_aod(0.1, 0)
    assert skyglow.airmass(90.0) == pytest.approx(1.0, abs=1e-3)
    assert 1.99 < skyglow.airmass(30.0) < 2.01
