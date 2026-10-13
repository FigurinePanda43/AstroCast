"""Backend strings that Home Assistant translations cannot cover.

Calendar event summaries/descriptions and service responses are plain strings
generated server-side, so they are localised here (English and French). The
dashboard card ships its own strings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .engine.events import AstroEvent
from .engine.meteors import SHOWERS

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "sun": "Sun",
        "moon": "Moon",
        "mercury": "Mercury",
        "venus": "Venus",
        "mars": "Mars",
        "jupiter": "Jupiter",
        "saturn": "Saturn",
        "uranus": "Uranus",
        "neptune": "Neptune",
        "aldebaran": "Aldebaran",
        "regulus": "Regulus",
        "spica": "Spica",
        "antares": "Antares",
        "pleiades": "the Pleiades",
        "beehive": "the Beehive Cluster",
        "new_moon": "New Moon",
        "first_quarter": "First Quarter",
        "full_moon": "Full Moon",
        "last_quarter": "Last Quarter",
        "supermoon": "Full Moon (supermoon)",
        "march_equinox": "March equinox",
        "june_solstice": "June solstice",
        "september_equinox": "September equinox",
        "december_solstice": "December solstice",
        "lunar_eclipse": "{kind} lunar eclipse",
        "solar_eclipse": "{kind} solar eclipse ({pct}% obscured)",
        "kind_total": "Total",
        "kind_partial": "Partial",
        "kind_penumbral": "Penumbral",
        "kind_annular": "Annular",
        "opposition": "{body} at opposition",
        "greatest_elongation": "{body} at greatest {side} elongation ({elong}°)",
        "side_evening": "eastern (evening)",
        "side_morning": "western (morning)",
        "conjunction": "{a} – {b} conjunction ({sep}°)",
        "occultation": "Occultation of {b} by the Moon",
        "meteor_shower": "{name} meteor shower peak",
        "comet": "Comet {name} at perihelion",
        "deep_sky_window": "Deep-sky window – {rating} ({score}/100)",
        "planetary_window": "Planetary window – {rating} ({score}/100)",
        "rating_excellent": "excellent",
        "rating_good": "good",
        "rating_fair": "fair",
        "rating_poor": "poor",
        "rating_bad": "bad",
        "desc_visible": "Visible from {site}.",
        "desc_not_visible": "Not visible from {site}.",
        "desc_best_time": "Best viewing: {time} (altitude {alt}°).",
        "desc_best_time_noalt": "Best viewing: {time}.",
        "desc_rate": "Expected rate: about {rate} meteors/hour (ZHR {zhr}), Moon {moon}% illuminated.",
        "desc_mag": "Magnitude {mag}.",
        "desc_comet": "Estimated peak magnitude {mag} (comet brightness is uncertain).",
        "desc_daylight": "Occurs in daylight or twilight: telescope needed.",
        "desc_window": "Clouds {cloud}% · seeing {seeing}″ · Moon {moon}% · confidence {conf}.",
        "desc_limiting": "Main limitation: {factor}.",
        "factor_clouds": "clouds",
        "factor_precipitation": "precipitation",
        "factor_darkness": "twilight",
        "factor_moon": "moonlight",
        "factor_transparency": "transparency",
        "factor_seeing": "seeing",
        "factor_wind": "wind",
        "factor_humidity": "humidity",
        "confidence_high": "high",
        "confidence_medium": "medium",
        "confidence_low": "low",
        "unknown": "n/a",
    },
    "fr": {
        "sun": "Soleil",
        "moon": "Lune",
        "mercury": "Mercure",
        "venus": "Vénus",
        "mars": "Mars",
        "jupiter": "Jupiter",
        "saturn": "Saturne",
        "uranus": "Uranus",
        "neptune": "Neptune",
        "aldebaran": "Aldébaran",
        "regulus": "Régulus",
        "spica": "l'Épi",
        "antares": "Antarès",
        "pleiades": "les Pléiades",
        "beehive": "l'amas de la Ruche",
        "new_moon": "Nouvelle Lune",
        "first_quarter": "Premier quartier",
        "full_moon": "Pleine Lune",
        "last_quarter": "Dernier quartier",
        "supermoon": "Pleine Lune (super Lune)",
        "march_equinox": "Équinoxe de mars",
        "june_solstice": "Solstice de juin",
        "september_equinox": "Équinoxe de septembre",
        "december_solstice": "Solstice de décembre",
        "lunar_eclipse": "Éclipse {kind} de Lune",
        "solar_eclipse": "Éclipse {kind} de Soleil ({pct} % occulté)",
        "kind_total": "totale",
        "kind_partial": "partielle",
        "kind_penumbral": "pénombrale",
        "kind_annular": "annulaire",
        "opposition": "{body} à l'opposition",
        "greatest_elongation": "{body} à sa plus grande élongation {side} ({elong}°)",
        "side_evening": "est (soir)",
        "side_morning": "ouest (matin)",
        "conjunction": "Conjonction {a} – {b} ({sep}°)",
        "occultation": "Occultation de {b} par la Lune",
        "meteor_shower": "Maximum des {name}",
        "comet": "Comète {name} au périhélie",
        "deep_sky_window": "Fenêtre ciel profond – {rating} ({score}/100)",
        "planetary_window": "Fenêtre planétaire – {rating} ({score}/100)",
        "rating_excellent": "excellente",
        "rating_good": "bonne",
        "rating_fair": "moyenne",
        "rating_poor": "médiocre",
        "rating_bad": "mauvaise",
        "desc_visible": "Visible depuis {site}.",
        "desc_not_visible": "Non visible depuis {site}.",
        "desc_best_time": "Meilleur moment : {time} (hauteur {alt}°).",
        "desc_best_time_noalt": "Meilleur moment : {time}.",
        "desc_rate": "Taux attendu : environ {rate} météores/heure (THZ {zhr}), Lune éclairée à {moon} %.",
        "desc_mag": "Magnitude {mag}.",
        "desc_comet": "Magnitude maximale estimée {mag} (l'éclat des comètes est incertain).",
        "desc_daylight": "Se produit de jour ou au crépuscule : télescope nécessaire.",
        "desc_window": "Nuages {cloud} % · seeing {seeing}″ · Lune {moon} % · confiance {conf}.",
        "desc_limiting": "Principale limitation : {factor}.",
        "factor_clouds": "nuages",
        "factor_precipitation": "précipitations",
        "factor_darkness": "crépuscule",
        "factor_moon": "clair de Lune",
        "factor_transparency": "transparence",
        "factor_seeing": "turbulence (seeing)",
        "factor_wind": "vent",
        "factor_humidity": "humidité",
        "confidence_high": "élevée",
        "confidence_medium": "moyenne",
        "confidence_low": "faible",
        "unknown": "n/d",
    },
}


def lang_of(language: str | None) -> str:
    """Supported language code."""
    return "fr" if language and language.lower().startswith("fr") else "en"


def text(language: str, key: str, **params: Any) -> str:
    """Translate and format."""
    table = STRINGS[lang_of(language)]
    template = table.get(key) or STRINGS["en"].get(key) or key
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return template


def body_name(language: str, key: str) -> str:
    """Localised name of a solar-system body or ecliptic star."""
    return text(language, key)


def confidence_label(language: str, confidence: float | None) -> str:
    """Qualitative confidence."""
    if confidence is None:
        return text(language, "unknown")
    if confidence >= 0.7:
        return text(language, "confidence_high")
    if confidence >= 0.45:
        return text(language, "confidence_medium")
    return text(language, "confidence_low")


def _time(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    return dt_util.as_local(moment).strftime("%Y-%m-%d %H:%M")


def event_title(event: AstroEvent, language: str) -> str:
    """Localised one-line title of an event."""
    data = event.data
    t = event.type
    if t == "moon_phase":
        key = "supermoon" if data.get("supermoon") else data["phase"]
        return text(language, key)
    if t == "season":
        return text(language, data["season"])
    if t == "lunar_eclipse":
        return text(language, "lunar_eclipse", kind=text(language, f"kind_{data['kind']}"))
    if t == "solar_eclipse":
        return text(
            language,
            "solar_eclipse",
            kind=text(language, f"kind_{data['kind']}"),
            pct=round(data["obscuration"] * 100),
        )
    if t == "opposition":
        return text(language, "opposition", body=body_name(language, data["body"]))
    if t == "greatest_elongation":
        return text(
            language,
            "greatest_elongation",
            body=body_name(language, data["body"]),
            side=text(language, f"side_{data['side']}"),
            elong=data["elongation"],
        )
    if t == "conjunction":
        a, b = data["bodies"]
        return text(
            language,
            "conjunction",
            a=body_name(language, a),
            b=body_name(language, b),
            sep=data["separation"],
        )
    if t == "occultation":
        return text(language, "occultation", b=body_name(language, data["bodies"][1]))
    if t == "meteor_shower":
        shower = next((s for s in SHOWERS if s.code == data["code"]), None)
        name = shower.name(lang_of(language)) if shower else data["code"]
        return text(language, "meteor_shower", name=name)
    if t == "comet":
        return text(language, "comet", name=data["name"])
    return t


def event_description(event: AstroEvent, language: str, site: str) -> str:
    """Localised multi-line description of an event."""
    lines: list[str] = []
    data = event.data
    if event.visible is True:
        lines.append(text(language, "desc_visible", site=site))
    elif event.visible is False:
        lines.append(text(language, "desc_not_visible", site=site))
    if event.best_time is not None:
        alt = data.get("altitude") or data.get("radiant_altitude") or data.get("peak_altitude")
        if alt is not None:
            lines.append(text(language, "desc_best_time", time=_time(event.best_time), alt=alt))
        else:
            lines.append(text(language, "desc_best_time_noalt", time=_time(event.best_time)))
    if event.type == "meteor_shower":
        lines.append(
            text(
                language,
                "desc_rate",
                rate=data.get("rate", 0),
                zhr=data.get("zhr"),
                moon=data.get("moon_illumination"),
            )
        )
    if event.type in ("opposition", "greatest_elongation") and data.get("mag") is not None:
        lines.append(text(language, "desc_mag", mag=data["mag"]))
    if event.type == "comet":
        lines.append(text(language, "desc_comet", mag=data.get("peak_mag")))
    if event.type == "occultation" and data.get("daylight"):
        lines.append(text(language, "desc_daylight"))
    return "\n".join(lines)
