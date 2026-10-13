#!/usr/bin/env python3
"""Build the AstroCast deep-sky catalog from OpenNGC.

OpenNGC (https://github.com/mattiaverga/OpenNGC) is (c) Mattia Verga and is
released under CC BY-SA 4.0. The generated JSON file is a derivative work and
is therefore distributed under the same licence (see data/LICENSE-catalog.md).

Usage:
    python scripts/build_catalog.py path/to/NGC.csv path/to/addendum.csv

The selection keeps every Messier and Caldwell object, every NGC/IC object of
an observable type brighter than V=10 (B=10.5 when V is missing), and named
nebulae/objects that are classic visual or imaging targets.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import re
import sys

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "astrocast"
    / "data"
    / "dso_catalog.json"
)

TYPE_MAP = {
    "G": "galaxy",
    "GPair": "galaxy",
    "GTrpl": "galaxy",
    "GGroup": "galaxy_group",
    "OCl": "open_cluster",
    "GCl": "globular_cluster",
    "Cl+N": "cluster_nebula",
    "PN": "planetary_nebula",
    "HII": "emission_nebula",
    "EmN": "emission_nebula",
    "RfN": "reflection_nebula",
    "Neb": "nebula",
    "SNR": "supernova_remnant",
    "DrkN": "dark_nebula",
    "*Ass": "asterism",
    "**": "double_star",
}

NEBULA_TYPES = {
    "emission_nebula",
    "reflection_nebula",
    "nebula",
    "supernova_remnant",
    "cluster_nebula",
    "dark_nebula",
}

# Caldwell number -> OpenNGC identifier. The Caldwell list is a list of
# designations (Patrick Moore, 1995); entries 9, 14, 41 and 99 are stored in the
# OpenNGC addendum with a "C" prefix.
CALDWELL = {
    1: "NGC0188", 2: "NGC0040", 3: "NGC4236", 4: "NGC7023", 5: "IC0342",
    6: "NGC6543", 7: "NGC2403", 8: "NGC0559", 9: "C009", 10: "NGC0663",
    11: "NGC7635", 12: "NGC6946", 13: "NGC0457", 14: "C014", 15: "NGC6826",
    16: "NGC7243", 17: "NGC0147", 18: "NGC0185", 19: "IC5146", 20: "NGC7000",
    21: "NGC4449", 22: "NGC7662", 23: "NGC0891", 24: "NGC1275", 25: "NGC2419",
    26: "NGC4244", 27: "NGC6888", 28: "NGC0752", 29: "NGC5005", 30: "NGC7331",
    31: "IC0405", 32: "NGC4631", 33: "NGC6992", 34: "NGC6960", 35: "NGC4889",
    36: "NGC4559", 37: "NGC6882", 38: "NGC4565", 39: "NGC2392", 40: "NGC3626",
    41: "C041", 42: "NGC7006", 43: "NGC7814", 44: "NGC7479", 45: "NGC5248",
    46: "NGC2261", 47: "NGC6934", 48: "NGC2775", 49: "NGC2237", 50: "NGC2239",
    51: "IC1613", 52: "NGC4697", 53: "NGC3115", 54: "NGC2506", 55: "NGC7009",
    56: "NGC0246", 57: "NGC6822", 58: "NGC2360", 59: "NGC3242", 60: "NGC4038",
    61: "NGC4039", 62: "NGC0247", 63: "NGC7293", 64: "NGC2362", 65: "NGC0253",
    66: "NGC5694", 67: "NGC1097", 68: "NGC6729", 69: "NGC6302", 70: "NGC0300",
    71: "NGC2477", 72: "NGC0055", 73: "NGC1851", 74: "NGC3132", 75: "NGC6124",
    76: "NGC6231", 77: "NGC5128", 78: "NGC6541", 79: "NGC3201", 80: "NGC5139",
    81: "NGC6352", 82: "NGC6193", 83: "NGC4945", 84: "NGC5286", 85: "IC2391",
    86: "NGC6397", 87: "NGC1261", 88: "NGC5823", 89: "NGC6087", 90: "NGC2867",
    91: "NGC3532", 92: "NGC3372", 93: "NGC6752", 94: "NGC4755", 95: "NGC6025",
    96: "NGC2516", 97: "NGC3766", 98: "NGC4609", 99: "C099", 100: "IC2944",
    101: "NGC6744", 102: "IC2602", 103: "NGC2070", 104: "NGC0362", 105: "NGC4833",
    106: "NGC0104", 107: "NGC6101", 108: "NGC4372", 109: "NGC3195",
}

# Curated English common names when OpenNGC has none or a less usual one.
EN_NAMES = {
    "M1": "Crab Nebula",
    "M8": "Lagoon Nebula",
    "M13": "Great Hercules Cluster",
    "M16": "Eagle Nebula",
    "M17": "Omega Nebula",
    "M20": "Trifid Nebula",
    "M27": "Dumbbell Nebula",
    "M31": "Andromeda Galaxy",
    "M33": "Triangulum Galaxy",
    "M42": "Orion Nebula",
    "M44": "Beehive Cluster",
    "M45": "Pleiades",
    "M51": "Whirlpool Galaxy",
    "M57": "Ring Nebula",
    "M81": "Bode's Galaxy",
    "M82": "Cigar Galaxy",
    "M97": "Owl Nebula",
    "M101": "Pinwheel Galaxy",
    "M104": "Sombrero Galaxy",
    "NGC6960": "Western Veil Nebula",
    "NGC6992": "Eastern Veil Nebula",
    "NGC2237": "Rosette Nebula",
    "NGC869": "Double Cluster (h Persei)",
    "IC1805": "Heart Nebula",
    "IC1848": "Soul Nebula",
    "IC1396": "Elephant's Trunk Nebula",
    "IC2177": "Seagull Nebula",
    "NGC2359": "Thor's Helmet",
    "NGC6334": "Cat's Paw Nebula",
    "NGC2024": "Flame Nebula",
    "IC434": "Horsehead Nebula (IC 434)",
    "NGC281": "Pacman Nebula",
    "NGC7380": "Wizard Nebula",
    "IC443": "Jellyfish Nebula",
    "NGC1977": "Running Man Nebula",
    "NGC6357": "Lobster Nebula",
    "NGC2264": "Christmas Tree Cluster & Cone Nebula",
    "NGC2239": "Rosette Cluster",
    "M73": "M73 asterism",
    "NGC884": "Double Cluster (chi Persei)",
}

# French common names for the most popular targets.
FR_NAMES = {
    "M1": "Nébuleuse du Crabe",
    "M2": "Amas globulaire du Verseau",
    "M3": "Amas globulaire des Chiens de chasse",
    "M4": "Amas globulaire du Scorpion",
    "M6": "Amas du Papillon",
    "M7": "Amas de Ptolémée",
    "M8": "Nébuleuse de la Lagune",
    "M11": "Amas du Canard sauvage",
    "M13": "Grand amas d'Hercule",
    "M15": "Amas globulaire de Pégase",
    "M16": "Nébuleuse de l'Aigle",
    "M17": "Nébuleuse Oméga",
    "M20": "Nébuleuse Trifide",
    "M22": "Amas globulaire du Sagittaire",
    "M24": "Nuage stellaire du Sagittaire",
    "M27": "Nébuleuse de l'Haltère",
    "M31": "Galaxie d'Andromède",
    "M33": "Galaxie du Triangle",
    "M35": "Amas des Gémeaux",
    "M42": "Grande nébuleuse d'Orion",
    "M43": "Nébuleuse de De Mairan",
    "M44": "Amas de la Ruche",
    "M45": "Pléiades",
    "M51": "Galaxie du Tourbillon",
    "M57": "Nébuleuse de l'Anneau",
    "M63": "Galaxie du Tournesol",
    "M64": "Galaxie de l'Œil noir",
    "M65": "Triplet du Lion (M65)",
    "M66": "Triplet du Lion (M66)",
    "M74": "Galaxie fantôme",
    "M76": "Petite Haltère",
    "M78": "Nébuleuse M78",
    "M81": "Galaxie de Bode",
    "M82": "Galaxie du Cigare",
    "M83": "Galaxie du Moulinet austral",
    "M87": "Virgo A",
    "M97": "Nébuleuse du Hibou",
    "M101": "Galaxie du Moulinet",
    "M104": "Galaxie du Sombrero",
    "M106": "Galaxie M106",
    "M108": "Galaxie de la Planche de surf",
    "M110": "Galaxie M110",
    "C9": "Nébuleuse de la Caverne",
    "C14": "Double amas de Persée",
    "C41": "Hyades",
    "C99": "Sac à charbon",
    "B33": "Nébuleuse de la Tête de cheval",
    "Cr399": "Amas de Brocchi (le Cintre)",
    "Mel111": "Amas de la Chevelure de Bérénice",
    "HCG92": "Quintette de Stephan",
    "ESO56-115": "Grand Nuage de Magellan",
    "NGC292": "Petit Nuage de Magellan",
    "NGC7000": "Nébuleuse de l'Amérique du Nord",
    "IC5070": "Nébuleuse du Pélican",
    "NGC6960": "Dentelles du Cygne (ouest)",
    "NGC6992": "Dentelles du Cygne (est)",
    "NGC6995": "Dentelles du Cygne (est)",
    "NGC2237": "Nébuleuse de la Rosette",
    "NGC2239": "Amas de la Rosette",
    "NGC7635": "Nébuleuse de la Bulle",
    "NGC6888": "Nébuleuse du Croissant",
    "IC1396": "Nébuleuse de la Trompe d'éléphant",
    "IC1805": "Nébuleuse du Cœur",
    "IC1848": "Nébuleuse de l'Âme",
    "NGC869": "Double amas de Persée (h)",
    "NGC884": "Double amas de Persée (χ)",
    "NGC7293": "Nébuleuse de l'Hélice",
    "NGC6543": "Nébuleuse de l'Œil de chat",
    "NGC253": "Galaxie du Sculpteur",
    "NGC4565": "Galaxie de l'Aiguille",
    "NGC2392": "Nébuleuse de l'Esquimau",
    "IC434": "Nébuleuse de la Tête de cheval (IC 434)",
    "NGC2024": "Nébuleuse de la Flamme",
    "IC405": "Nébuleuse de l'Étoile flamboyante",
    "NGC7023": "Nébuleuse de l'Iris",
    "IC5146": "Nébuleuse du Cocon",
    "NGC281": "Nébuleuse Pac-Man",
    "NGC1499": "Nébuleuse Californie",
    "NGC2264": "Amas de l'Arbre de Noël",
    "NGC5139": "Oméga du Centaure",
    "NGC104": "47 Toucan",
    "NGC3372": "Nébuleuse de la Carène",
    "NGC2070": "Nébuleuse de la Tarentule",
    "NGC4038": "Galaxies des Antennes",
    "NGC4039": "Galaxies des Antennes",
    "NGC7009": "Nébuleuse Saturne",
    "NGC3242": "Fantôme de Jupiter",
    "NGC7662": "Boule de neige bleue",
    "NGC457": "Amas de la Chouette",
    "NGC6826": "Nébuleuse clignotante",
    "NGC246": "Nébuleuse du Crâne",
    "NGC4631": "Galaxie de la Baleine",
    "NGC2261": "Nébuleuse variable de Hubble",
    "NGC6302": "Nébuleuse de la Punaise",
    "NGC891": "Galaxie NGC 891",
    "NGC6946": "Galaxie du Feu d'artifice",
    "NGC5128": "Centaurus A",
    "NGC188": "Amas de Polarissima",
    "NGC40": "Nébuleuse du Nœud papillon",
    "NGC2359": "Casque de Thor",
    "IC2177": "Nébuleuse de la Mouette",
    "NGC1333": "Nébuleuse NGC 1333",
    "IC443": "Nébuleuse de la Méduse",
    "NGC6820": "Nébuleuse NGC 6820",
    "NGC6334": "Nébuleuse de la Patte de chat",
    "NGC6357": "Nébuleuse du Homard",
    "IC4592": "Nébuleuse de la Tête de cheval bleue",
    "IC4604": "Nébuleuse Rho Ophiuchi",
    "NGC2403": "Galaxie NGC 2403",
    "IC342": "Galaxie cachée",
    "NGC3628": "Galaxie du Hamburger",
    "NGC4449": "Galaxie NGC 4449",
    "NGC6822": "Galaxie de Barnard",
    "NGC6939": "Amas NGC 6939",
    "NGC1977": "Nébuleuse de l'Homme qui court",
    "NGC1973": "Nébuleuse de l'Homme qui court",
    "NGC2174": "Nébuleuse de la Tête de singe",
    "NGC7380": "Nébuleuse du Sorcier",
    "IC1795": "Nébuleuse de la Tête de poisson",
    "NGC1491": "Nébuleuse NGC 1491",
    "NGC6914": "Nébuleuse NGC 6914",
}

# Magnitudes that are clearly wrong for visual use in the source (e.g. the
# magnitude of a single member star instead of the integrated cluster value).
MAG_OVERRIDES = {"NGC6882": 8.1}

_DESIGNATION_RE = re.compile(r"^([A-Za-z]+?)(\d+)(.*)$")


def parse_ra(value: str) -> float | None:
    """Convert 'HH:MM:SS.s' to degrees."""
    if not value:
        return None
    h, m, s = value.split(":")
    return (int(h) + int(m) / 60 + float(s) / 3600) * 15.0


def parse_dec(value: str) -> float | None:
    """Convert '+DD:MM:SS.s' to degrees."""
    if not value:
        return None
    sign = -1.0 if value.startswith("-") else 1.0
    d, m, s = value.lstrip("+-").split(":")
    return sign * (int(d) + int(m) / 60 + float(s) / 3600)


def fnum(value: str) -> float | None:
    """Parse an optional float."""
    try:
        return float(value) if value not in ("", None) else None
    except ValueError:
        return None


def short_id(name: str) -> str:
    """'NGC0224' -> 'NGC224', 'ESO056-115' -> 'ESO56-115'."""
    match = _DESIGNATION_RE.match(name)
    if not match:
        return name
    prefix, number, rest = match.groups()
    if prefix == "Cl":
        prefix = "Cr"
    return f"{prefix}{int(number)}{rest}"


def display_id(sid: str) -> str:
    """'NGC224' -> 'NGC 224'."""
    match = _DESIGNATION_RE.match(sid)
    if not match:
        return sid
    prefix, number, rest = match.groups()
    if prefix == "Sh":
        return sid
    return f"{prefix} {number}{rest}"


def main(ngc_path: str, addendum_path: str) -> None:
    """Build the catalog."""
    rows: dict[str, dict[str, str]] = {}
    for path in (ngc_path, addendum_path):
        with open(path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter=";"):
                rows[row["Name"]] = row

    caldwell_by_name = {v: k for k, v in CALDWELL.items()}
    objects: list[dict] = []
    seen: set[str] = set()

    for name, row in rows.items():
        messier = int(row["M"]) if row["M"] else None
        otype = TYPE_MAP.get(row["Type"])
        if otype is None and messier is not None and row["Type"] == "Other":
            otype = "asterism"
        if otype is None:
            continue
        if name == "C014":
            otype = "open_cluster"
        if name == "M102":  # OpenNGC treats M102 as a duplicate of M101.
            continue
        caldwell = caldwell_by_name.get(name)
        vmag = fnum(row["V-Mag"])
        bmag = fnum(row["B-Mag"])
        mag = vmag if vmag is not None else (bmag - 0.6 if bmag is not None else None)
        common = [
            re.sub(r"^the ", "", c.strip())
            for c in row["Common names"].split(",")
            if c.strip()
        ]

        keep = messier is not None or caldwell is not None
        if not keep and mag is not None and mag <= 10.0 and otype != "double_star":
            keep = True
        if not keep and common and otype != "double_star":
            if otype in NEBULA_TYPES or (mag is not None and mag <= 12.0):
                keep = True
            if name.startswith(("ESO", "PGC", "UGC", "HCG", "Cl", "Mel", "B0", "C0")):
                keep = keep or (mag is None or mag <= 12.0)
        if not keep:
            continue

        ra = parse_ra(row["RA"])
        dec = parse_dec(row["Dec"])
        if ra is None or dec is None:
            continue

        sid = short_id(name)
        if messier is not None:
            oid = f"M{messier}"
        elif name.startswith("C0") and caldwell is not None:
            oid = f"C{caldwell}"
        else:
            oid = sid
        if oid in seen:
            continue
        seen.add(oid)

        aliases: list[str] = []
        if messier is not None:
            aliases.append(f"M {messier}")
        if caldwell is not None:
            aliases.append(f"C {caldwell}")
        if not name.startswith("C0") and display_id(sid) not in aliases:
            aliases.append(display_id(sid))
        for col in ("NGC", "IC"):
            for ref in filter(None, (r.strip() for r in row[col].split(","))):
                alias = f"{col} {int(re.sub(r'[^0-9]', '', ref) or 0)}"
                if alias not in aliases and not alias.endswith(" 0"):
                    aliases.append(alias)
        for ident in filter(None, (r.strip() for r in row["Identifiers"].split(","))):
            if ident.startswith(("LBN", "SH 2", "Sh2", "Cr ", "Mel", "B ", "Barnard")):
                alias = ident.replace("SH 2-", "Sh2-")
                alias = re.sub(r"(?<=\s)0+(?=\d)", "", alias)
                if alias not in aliases:
                    aliases.append(alias)

        name_en = EN_NAMES.get(oid) or (common[0] if common else None)
        name_fr = FR_NAMES.get(oid) or FR_NAMES.get(sid)

        maj = fnum(row["MajAx"])
        minr = fnum(row["MinAx"])
        entry = {
            "id": oid,
            "aliases": aliases,
            "type": otype,
            "ra": round(ra, 5),
            "dec": round(dec, 5),
            "const": row["Const"],
        }
        if name_en:
            entry["name_en"] = name_en
        if name_fr:
            entry["name_fr"] = name_fr
        mag = MAG_OVERRIDES.get(oid, mag)
        if mag is not None:
            entry["mag"] = round(mag, 2)
        if maj is not None:
            entry["size"] = round(maj, 2)
            if minr is not None:
                entry["size_minor"] = round(minr, 2)
        surf = fnum(row["SurfBr"])
        if surf is not None:
            entry["sb"] = round(surf, 2)
        if messier is not None:
            entry["messier"] = messier
        if caldwell is not None:
            entry["caldwell"] = caldwell
        objects.append(entry)

    def sort_key(obj: dict) -> tuple:
        if "messier" in obj:
            return (0, obj["messier"], "")
        if "caldwell" in obj:
            return (1, obj["caldwell"], "")
        return (2, 0, obj["id"])

    objects.sort(key=sort_key)
    missing_messier = sorted(
        set(range(1, 111)) - {o["messier"] for o in objects if "messier" in o}
    )
    missing_caldwell = sorted(
        set(range(1, 110)) - {o["caldwell"] for o in objects if "caldwell" in o}
    )
    payload = {
        "source": "OpenNGC (https://github.com/mattiaverga/OpenNGC), CC BY-SA 4.0",
        "epoch": "J2000",
        "count": len(objects),
        "objects": objects,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"{len(objects)} objects written to {OUTPUT}")
    print("Missing Messier:", missing_messier)
    print("Missing Caldwell:", missing_caldwell)
    counts: dict[str, int] = {}
    for obj in objects:
        counts[obj["type"]] = counts.get(obj["type"], 0) + 1
    print(counts)
    if not math.isfinite(len(objects)):
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
