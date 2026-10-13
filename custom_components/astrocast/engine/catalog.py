"""Deep-sky object catalog (derived from OpenNGC, CC BY-SA 4.0)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata

import numpy as np

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "dso_catalog.json"

# Default integrated magnitudes used when the catalog has none (mostly large
# nebulae). They are only used to rank objects, never displayed.
TYPE_DEFAULT_MAG = {
    "emission_nebula": 7.5,
    "reflection_nebula": 8.5,
    "nebula": 8.0,
    "supernova_remnant": 8.0,
    "cluster_nebula": 6.5,
    "dark_nebula": 12.0,
    "galaxy_group": 12.5,
    "galaxy": 11.0,
    "open_cluster": 7.0,
    "globular_cluster": 8.0,
    "planetary_nebula": 10.0,
    "asterism": 6.0,
    "double_star": 7.0,
}

NEBULA_TYPES = frozenset(
    {
        "emission_nebula",
        "reflection_nebula",
        "nebula",
        "supernova_remnant",
        "cluster_nebula",
        "dark_nebula",
        "planetary_nebula",
    }
)


@dataclass(slots=True, frozen=True)
class DeepSkyObject:
    """A deep-sky object."""

    id: str
    type: str
    ra: float  # degrees, J2000
    dec: float  # degrees, J2000
    constellation: str
    aliases: tuple[str, ...]
    name_en: str | None = None
    name_fr: str | None = None
    mag: float | None = None
    size: float | None = None  # major axis, arcmin
    size_minor: float | None = None
    surface_brightness: float | None = None
    messier: int | None = None
    caldwell: int | None = None

    def name(self, language: str = "en") -> str | None:
        """Common name in the requested language (falls back to English)."""
        if language.startswith("fr") and self.name_fr:
            return self.name_fr
        return self.name_en or self.name_fr

    def label(self, language: str = "en") -> str:
        """Short designation followed by the common name, e.g. 'M 31 – Andromeda'."""
        designation = self.aliases[0] if self.aliases else self.id
        common = self.name(language)
        return f"{designation} – {common}" if common else designation

    @property
    def effective_mag(self) -> float:
        """Integrated magnitude, or a type-based default when unknown."""
        if self.mag is not None:
            return self.mag
        return TYPE_DEFAULT_MAG.get(self.type, 10.0)

    @property
    def is_showpiece(self) -> bool:
        """Messier, Caldwell or named objects are classic targets."""
        return bool(self.messier or self.caldwell or self.name_en)


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


class Catalog:
    """In-memory catalog with numpy arrays for vectorised computations."""

    def __init__(self, objects: list[DeepSkyObject]) -> None:
        """Initialise from a list of objects."""
        self.objects = objects
        self.by_id = {obj.id: obj for obj in objects}
        self.ra_rad = np.radians(np.array([o.ra for o in objects], dtype=float))
        self.dec_rad = np.radians(np.array([o.dec for o in objects], dtype=float))
        cos_dec = np.cos(self.dec_rad)
        # Unit vectors (J2000 equatorial), shape (3, N).
        self.vectors = np.vstack(
            (cos_dec * np.cos(self.ra_rad), cos_dec * np.sin(self.ra_rad), np.sin(self.dec_rad))
        )
        self._index: dict[str, str] = {}
        for obj in objects:
            keys = {obj.id, *obj.aliases}
            if obj.name_en:
                keys.add(obj.name_en)
            if obj.name_fr:
                keys.add(obj.name_fr)
            for key in keys:
                self._index.setdefault(_normalise(key), obj.id)

    def __len__(self) -> int:
        """Number of objects."""
        return len(self.objects)

    def get(self, object_id: str) -> DeepSkyObject | None:
        """Find an object by id, alias or common name."""
        if object_id in self.by_id:
            return self.by_id[object_id]
        found = self._index.get(_normalise(object_id))
        return self.by_id.get(found) if found else None

    def search(self, query: str, limit: int = 20) -> list[DeepSkyObject]:
        """Search objects whose id, alias or name contains ``query``."""
        needle = _normalise(query)
        if not needle:
            return []
        exact = self.get(query)
        results: list[DeepSkyObject] = [exact] if exact else []
        for obj in self.objects:
            if obj is exact:
                continue
            haystack = [obj.id, *obj.aliases, obj.name_en or "", obj.name_fr or ""]
            if any(needle in _normalise(h) for h in haystack):
                results.append(obj)
                if len(results) >= limit:
                    break
        return results


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    """Load the bundled catalog (blocking I/O: run in an executor)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    objects = [
        DeepSkyObject(
            id=item["id"],
            type=item["type"],
            ra=item["ra"],
            dec=item["dec"],
            constellation=item.get("const", ""),
            aliases=tuple(item.get("aliases", ())),
            name_en=item.get("name_en"),
            name_fr=item.get("name_fr"),
            mag=item.get("mag"),
            size=item.get("size"),
            size_minor=item.get("size_minor"),
            surface_brightness=item.get("sb"),
            messier=item.get("messier"),
            caldwell=item.get("caldwell"),
        )
        for item in payload["objects"]
    ]
    return Catalog(objects)
