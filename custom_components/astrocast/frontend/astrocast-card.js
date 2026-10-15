/*
 * AstroCast dashboard card and sidebar panel for Home Assistant.
 *
 * Plain ES module, no build step and no external dependency. The data comes
 * from the integration's websocket API (`astrocast/subscribe`) and is pushed
 * again every time the forecast is recomputed.
 */

const VERSION = "0.2.0";

/* ------------------------------------------------------------------ i18n -- */

const STRINGS = {
  en: {
    deep_sky: "Deep sky",
    planetary: "Planetary",
    narrowband: "Narrowband",
    narrowband_hint: "Moonlit night: narrowband filters (Hα, OIII, SII) still work",
    dew_at: "Dew around",
    dew_heaters: "heaters",
    night_mode: "Night vision (red)",
    editor_night: "Night vision (red)",
    editor_night_toggle: "Button in the card",
    editor_night_on: "Always",
    editor_night_auto: "Automatic after sunset",
    now: "Now",
    tonight: "Tonight",
    nights: "Nights",
    objects: "Objects",
    events: "Events",
    sky: "Sky",
    best_window: "Best window",
    no_window: "No good window tonight",
    no_weather: "No weather forecast available right now: the curves show what the sky would offer if clear.",
    if_clear: "If clear",
    limited_by: "limited by",
    astro_night: "Astronomical night",
    no_astro_night: "No astronomical night",
    moon: "Moon",
    moonrise: "rise",
    moonset: "set",
    updated: "Updated",
    loading: "Loading AstroCast…",
    no_site: "No AstroCast site is configured. Add the integration first.",
    error: "AstroCast is unavailable",
    clouds: "Clouds",
    seeing: "Seeing",
    transparency: "Transparency",
    humidity: "Humidity",
    wind: "Wind",
    temperature: "Temperature",
    dew_point: "Dew point",
    dew_risk: "Dew risk",
    clear_chance: "Clear-sky chance",
    score: "Score",
    potential: "If clear",
    dark_hours: "dark",
    moonless_hours: "moonless",
    tier_detailed: "Detailed",
    tier_forecast: "Forecast",
    tier_trend: "Trend",
    tier_astro: "Astronomy only",
    confidence: "Confidence",
    conf_high: "high",
    conf_medium: "medium",
    conf_low: "low",
    best: "Best night",
    weather_horizon:
      "Beyond the weather horizon only astronomical conditions are known: moonless dark hours and potential score if the sky is clear.",
    trend_note:
      "Long-range nights are probabilistic (ensemble forecast): use the clear-sky chance, not the exact values.",
    all: "All",
    favorites: "Favourites",
    planets: "Planets",
    galaxies: "Galaxies",
    nebulae: "Nebulae",
    clusters: "Clusters",
    small_bodies: "Comets & asteroids",
    best_time: "Best",
    max_alt: "Max alt.",
    mag: "Mag.",
    visible_for: "visible",
    search_placeholder: "Search an object (M31, Jupiter, NGC 7000…)",
    add_favorite: "Add to favourites",
    remove_favorite: "Remove from favourites",
    next_nights: "Coming nights",
    no_objects: "No object is worth observing with the expected conditions.",
    visible: "Visible",
    not_visible: "Not visible from here",
    upcoming_events: "Upcoming events",
    data_sources: "Data sources",
    stale: "stale",
    failing: "failing",
    fallback: "fallback",
    active: "active",
    inactive: "inactive",
    sky_time: "Sky at",
    horizon_limit: "Your horizon limit",
    north: "N",
    east: "E",
    south: "S",
    west: "W",
    hours_short: "h",
    estimate: "estimate",
    rating_excellent: "Excellent",
    rating_good: "Good",
    rating_fair: "Fair",
    rating_poor: "Poor",
    rating_bad: "Bad",
    factor_clouds: "clouds",
    factor_precipitation: "precipitation",
    factor_darkness: "twilight",
    factor_moon: "moonlight",
    factor_transparency: "transparency",
    factor_seeing: "seeing",
    factor_wind: "wind",
    factor_humidity: "humidity",
    factor_dew: "dew",
    factor_duration: "a short window",
    reason_showpiece: "Showpiece",
    reason_high_altitude: "High in the sky ({alt}°)",
    reason_low_altitude: "Low ({alt}°)",
    reason_moon_down: "Moon below horizon",
    reason_moon_far: "Moon far away ({sep}°)",
    reason_moon_interference: "Moonlight interference ({sep}°)",
    reason_faint_for_equipment: "Faint for your equipment",
    reason_short_window: "Short window ({hours} h)",
    reason_near_opposition: "Near opposition",
    reason_evening_sky: "Evening sky ({elong}° from Sun)",
    reason_morning_sky: "Morning sky ({elong}° from Sun)",
    reason_good_seeing: "Steady air ({seeing}″)",
    reason_comet_estimate: "Brightness is an estimate",
    dew_low: "low",
    dew_moderate: "moderate",
    dew_high: "high",
    dark_window: "Dark sky",
    illumination: "lit",
    window: "Window",
    open_details: "Details",
    phase_new_moon: "New moon",
    phase_waxing_crescent: "Waxing crescent",
    phase_first_quarter: "First quarter",
    phase_waxing_gibbous: "Waxing gibbous",
    phase_full_moon: "Full moon",
    phase_waning_gibbous: "Waning gibbous",
    phase_last_quarter: "Last quarter",
    phase_waning_crescent: "Waning crescent",
    type_galaxy: "Galaxy",
    type_galaxy_group: "Galaxy group",
    type_open_cluster: "Open cluster",
    type_globular_cluster: "Globular cluster",
    type_cluster_nebula: "Cluster + nebula",
    type_planetary_nebula: "Planetary nebula",
    type_emission_nebula: "Emission nebula",
    type_reflection_nebula: "Reflection nebula",
    type_nebula: "Nebula",
    type_supernova_remnant: "Supernova remnant",
    type_dark_nebula: "Dark nebula",
    type_asterism: "Asterism",
    type_double_star: "Double star",
    type_planet: "Planet",
    type_moon: "Moon",
    type_comet: "Comet",
    type_asteroid: "Asteroid",
    editor_site: "Observing site",
    editor_view: "Default tab",
    editor_compact: "Compact (header only)",
    editor_auto: "First configured site",
  },
  fr: {
    deep_sky: "Ciel profond",
    planetary: "Planétaire",
    narrowband: "Bande étroite",
    narrowband_hint: "Nuit éclairée par la Lune : les filtres à bande étroite (Hα, OIII, SII) restent utilisables",
    dew_at: "Rosée vers",
    dew_heaters: "résistances",
    night_mode: "Vision nocturne (rouge)",
    editor_night: "Vision nocturne (rouge)",
    editor_night_toggle: "Bouton dans la carte",
    editor_night_on: "Toujours",
    editor_night_auto: "Automatique après le coucher du soleil",
    now: "Maintenant",
    tonight: "Cette nuit",
    nights: "Nuits",
    objects: "Objets",
    events: "Événements",
    sky: "Ciel",
    best_window: "Meilleure fenêtre",
    no_window: "Pas de bonne fenêtre cette nuit",
    no_weather: "Aucune prévision météo disponible pour le moment : les courbes montrent ce que le ciel offrirait s'il était dégagé.",
    if_clear: "Si dégagé",
    limited_by: "limité par",
    astro_night: "Nuit astronomique",
    no_astro_night: "Pas de nuit astronomique",
    moon: "Lune",
    moonrise: "lever",
    moonset: "coucher",
    updated: "Mis à jour",
    loading: "Chargement d'AstroCast…",
    no_site: "Aucun site AstroCast n'est configuré. Ajoutez d'abord l'intégration.",
    error: "AstroCast est indisponible",
    clouds: "Nuages",
    seeing: "Seeing",
    transparency: "Transparence",
    humidity: "Humidité",
    wind: "Vent",
    temperature: "Température",
    dew_point: "Point de rosée",
    dew_risk: "Risque de rosée",
    clear_chance: "Probabilité de ciel dégagé",
    score: "Score",
    potential: "Si dégagé",
    dark_hours: "de nuit noire",
    moonless_hours: "sans Lune",
    tier_detailed: "Détaillée",
    tier_forecast: "Prévision",
    tier_trend: "Tendance",
    tier_astro: "Astronomie seule",
    confidence: "Confiance",
    conf_high: "élevée",
    conf_medium: "moyenne",
    conf_low: "faible",
    best: "Meilleure nuit",
    weather_horizon:
      "Au-delà de l'horizon météo, seules les conditions astronomiques sont connues : heures de nuit noire sans Lune et score potentiel si le ciel est dégagé.",
    trend_note:
      "Les nuits lointaines sont probabilistes (prévision d'ensemble) : fiez-vous à la probabilité de ciel dégagé plutôt qu'aux valeurs exactes.",
    all: "Tous",
    favorites: "Favoris",
    planets: "Planètes",
    galaxies: "Galaxies",
    nebulae: "Nébuleuses",
    clusters: "Amas",
    small_bodies: "Comètes et astéroïdes",
    best_time: "Optimal",
    max_alt: "Haut. max",
    mag: "Mag.",
    visible_for: "visible",
    search_placeholder: "Rechercher un objet (M31, Jupiter, NGC 7000…)",
    add_favorite: "Ajouter aux favoris",
    remove_favorite: "Retirer des favoris",
    next_nights: "Prochaines nuits",
    no_objects: "Aucun objet ne vaut le détour avec les conditions prévues.",
    visible: "Visible",
    not_visible: "Non visible d'ici",
    upcoming_events: "Événements à venir",
    data_sources: "Sources de données",
    stale: "périmée",
    failing: "en échec",
    fallback: "secours",
    active: "active",
    inactive: "inactive",
    sky_time: "Ciel à",
    horizon_limit: "Votre limite d'horizon",
    north: "N",
    east: "E",
    south: "S",
    west: "O",
    hours_short: "h",
    estimate: "estimation",
    rating_excellent: "Excellent",
    rating_good: "Bon",
    rating_fair: "Moyen",
    rating_poor: "Médiocre",
    rating_bad: "Mauvais",
    factor_clouds: "les nuages",
    factor_precipitation: "les précipitations",
    factor_darkness: "le crépuscule",
    factor_moon: "la Lune",
    factor_transparency: "la transparence",
    factor_seeing: "la turbulence",
    factor_wind: "le vent",
    factor_humidity: "l'humidité",
    factor_dew: "la rosée",
    factor_duration: "une fenêtre trop courte",
    reason_showpiece: "Incontournable",
    reason_high_altitude: "Haut dans le ciel ({alt}°)",
    reason_low_altitude: "Bas ({alt}°)",
    reason_moon_down: "Lune sous l'horizon",
    reason_moon_far: "Lune éloignée ({sep}°)",
    reason_moon_interference: "Gêné par la Lune ({sep}°)",
    reason_faint_for_equipment: "Faible pour votre instrument",
    reason_short_window: "Fenêtre courte ({hours} h)",
    reason_near_opposition: "Proche de l'opposition",
    reason_evening_sky: "Ciel du soir ({elong}° du Soleil)",
    reason_morning_sky: "Ciel du matin ({elong}° du Soleil)",
    reason_good_seeing: "Air stable ({seeing}″)",
    reason_comet_estimate: "Éclat estimé",
    dew_low: "faible",
    dew_moderate: "modéré",
    dew_high: "élevé",
    dark_window: "Nuit noire",
    illumination: "éclairée",
    window: "Fenêtre",
    open_details: "Détails",
    phase_new_moon: "Nouvelle Lune",
    phase_waxing_crescent: "Premier croissant",
    phase_first_quarter: "Premier quartier",
    phase_waxing_gibbous: "Gibbeuse croissante",
    phase_full_moon: "Pleine Lune",
    phase_waning_gibbous: "Gibbeuse décroissante",
    phase_last_quarter: "Dernier quartier",
    phase_waning_crescent: "Dernier croissant",
    type_galaxy: "Galaxie",
    type_galaxy_group: "Groupe de galaxies",
    type_open_cluster: "Amas ouvert",
    type_globular_cluster: "Amas globulaire",
    type_cluster_nebula: "Amas + nébuleuse",
    type_planetary_nebula: "Nébuleuse planétaire",
    type_emission_nebula: "Nébuleuse en émission",
    type_reflection_nebula: "Nébuleuse par réflexion",
    type_nebula: "Nébuleuse",
    type_supernova_remnant: "Rémanent de supernova",
    type_dark_nebula: "Nébuleuse obscure",
    type_asterism: "Astérisme",
    type_double_star: "Étoile double",
    type_planet: "Planète",
    type_moon: "Lune",
    type_comet: "Comète",
    type_asteroid: "Astéroïde",
    editor_site: "Site d'observation",
    editor_view: "Onglet par défaut",
    editor_compact: "Compacte (en-tête seulement)",
    editor_auto: "Premier site configuré",
  },
};

const TABS = ["tonight", "nights", "objects", "events", "sky"];
const RATING_COLORS = {
  excellent: "#2e9d55",
  good: "#7cb342",
  fair: "#f2b630",
  poor: "#f07b3f",
  bad: "#d64545",
};
const DEEP_COLOR = "#6c7cff";
const PLANET_COLOR = "#ffa23a";
const NARROW_COLOR = "#e0569b";
const NIGHT_KEY = "astrocast-night-mode";
const NIGHT_EVENT = "astrocast-night-mode";
const MOON_COLOR = "#c9cfd8";

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

function ratingOf(score) {
  if (score === null || score === undefined) return null;
  if (score >= 75) return "excellent";
  if (score >= 55) return "good";
  if (score >= 35) return "fair";
  if (score >= 15) return "poor";
  return "bad";
}

function fmtHours(hours) {
  const minutes = Math.round((hours || 0) * 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} h`;
}

let nightFallback = false; // used when the browser storage is unavailable

function storedNightMode() {
  try {
    return window.localStorage.getItem(NIGHT_KEY) === "on";
  } catch (_e) {
    return nightFallback;
  }
}

function confidenceKey(value) {
  if (value === null || value === undefined) return null;
  if (value >= 0.7) return "conf_high";
  if (value >= 0.45) return "conf_medium";
  return "conf_low";
}

/* -------------------------------------------------------------- glyphs -- */

function glyph(type, size = 22) {
  const s = size;
  const common = `width="${s}" height="${s}" viewBox="0 0 24 24" aria-hidden="true"`;
  switch (type) {
    case "galaxy":
    case "galaxy_group":
      return `<svg ${common}><ellipse cx="12" cy="12" rx="10" ry="4.2" transform="rotate(-25 12 12)" fill="none" stroke="currentColor" stroke-width="1.4" opacity=".75"/><ellipse cx="12" cy="12" rx="5.5" ry="2.2" transform="rotate(-25 12 12)" fill="currentColor" opacity=".35"/><circle cx="12" cy="12" r="1.9" fill="currentColor"/></svg>`;
    case "open_cluster":
    case "asterism":
      return `<svg ${common}>${[[6, 8], [11, 5], [16, 9], [9, 13], [14, 14], [18, 16], [7, 18], [12, 19]]
        .map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.5" fill="currentColor"/>`)
        .join("")}</svg>`;
    case "globular_cluster":
      return `<svg ${common}><circle cx="12" cy="12" r="8" fill="currentColor" opacity=".18"/><circle cx="12" cy="12" r="5" fill="currentColor" opacity=".35"/><circle cx="12" cy="12" r="2.4" fill="currentColor"/></svg>`;
    case "planetary_nebula":
      return `<svg ${common}><circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="2.4" opacity=".7"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/></svg>`;
    case "dark_nebula":
      return `<svg ${common}><path d="M4 14c2-6 7-9 11-7s5 7 2 10-11 3-13-3z" fill="currentColor" opacity=".55"/></svg>`;
    case "double_star":
      return `<svg ${common}><circle cx="9" cy="12" r="3" fill="currentColor"/><circle cx="16" cy="11" r="2" fill="currentColor" opacity=".7"/></svg>`;
    case "planet":
      return `<svg ${common}><circle cx="12" cy="12" r="5.5" fill="currentColor"/><ellipse cx="12" cy="12" rx="10" ry="3" fill="none" stroke="currentColor" stroke-width="1.3" transform="rotate(-20 12 12)"/></svg>`;
    case "moon":
      return `<svg ${common}><path d="M15 3a9 9 0 1 0 6 15A8 8 0 0 1 15 3z" fill="currentColor"/></svg>`;
    case "comet":
      return `<svg ${common}><circle cx="17" cy="7" r="3" fill="currentColor"/><path d="M15 9 3 21M16 10 6 21M14 8 3 17" stroke="currentColor" stroke-width="1.4" opacity=".5"/></svg>`;
    case "asteroid":
      return `<svg ${common}><path d="M7 6l6-2 6 5-1 7-6 4-6-3-2-6z" fill="currentColor" opacity=".8"/></svg>`;
    default:
      // emission/reflection nebulae, supernova remnants, cluster + nebula
      return `<svg ${common}><path d="M5 15c-2-4 1-9 6-9 2-3 8-2 9 3 3 1 3 6-1 8-2 3-8 3-10 1-2 0-4-1-4-3z" fill="currentColor" opacity=".45"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/></svg>`;
  }
}

function moonIcon(illumination, waxing, size = 22) {
  // Draws the lit part of the Moon for an illuminated fraction (0-1).
  const r = size / 2 - 1;
  const c = size / 2;
  const f = Math.max(0, Math.min(1, illumination));
  const k = 1 - 2 * f; // terminator ellipse x-radius factor
  const rx = Math.abs(k) * r;
  const sweepOuter = waxing ? 1 : 0;
  const sweepInner = k > 0 ? (waxing ? 0 : 1) : waxing ? 1 : 0;
  const lit = `M ${c} ${c - r} A ${r} ${r} 0 0 ${sweepOuter} ${c} ${c + r} A ${rx} ${r} 0 0 ${sweepInner} ${c} ${c - r} Z`;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true"><circle cx="${c}" cy="${c}" r="${r}" fill="var(--ac-moon-dark)"/><path d="${lit}" fill="var(--ac-moon-lit)"/></svg>`;
}

/* --------------------------------------------------------------- styles -- */

const STYLES = `
:host {
  --ac-deep: ${DEEP_COLOR};
  --ac-planet: ${PLANET_COLOR};
  --ac-narrow: ${NARROW_COLOR};
  --ac-moon: ${MOON_COLOR};
  --ac-moon-lit: #f3f1e8;
  --ac-moon-dark: rgba(127,127,140,.35);
  --ac-muted: var(--secondary-text-color, #6b7280);
  --ac-line: var(--divider-color, rgba(127,127,127,.25));
  --ac-chip: rgba(127,127,140,.14);
  --ac-radius: 12px;
  display: block;
}
* { box-sizing: border-box; }
.wrap { padding: 16px; color: var(--primary-text-color); }
.header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.title { font-size: 1.15rem; font-weight: 600; flex: 1 1 auto; display: flex; align-items: center; gap: 8px; min-width: 0; }
.title span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.health { display: inline-flex; align-items: center; gap: 6px; font-size: .78rem; color: var(--ac-muted); cursor: pointer; background: none; border: none; padding: 4px 6px; border-radius: 8px; font-family: inherit; }
.health:hover { background: var(--ac-chip); }
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.scores { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 8px; margin-top: 12px; }
.score { border-radius: var(--ac-radius); padding: 9px 10px; background: var(--ac-chip); position: relative; overflow: hidden; min-width: 0; }
.score .label { font-size: .76rem; color: var(--ac-muted); display: flex; justify-content: space-between; gap: 6px; line-height: 1.25; }
.score .value { font-size: 2rem; font-weight: 700; line-height: 1.1; margin-top: 2px; }
.score .value small { font-size: .9rem; font-weight: 500; color: var(--ac-muted); }
.score .rating { font-size: .85rem; font-weight: 600; }
.score .bar { position: absolute; left: 0; bottom: 0; height: 4px; }
.score .now { font-size: .72rem; color: var(--ac-muted); margin-top: 2px; line-height: 1.3; }
.summary { margin-top: 10px; font-size: .88rem; line-height: 1.45; }
.summary b { font-weight: 600; }
.facts { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; font-size: .82rem; color: var(--ac-muted); align-items: center; }
.facts .fact { display: inline-flex; align-items: center; gap: 5px; }
.tabs { display: flex; gap: 4px; margin: 14px -4px 10px; overflow-x: auto; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tab { flex: 0 0 auto; border: none; background: none; color: var(--ac-muted); font: inherit; font-size: .88rem; padding: 7px 12px; border-radius: 999px; cursor: pointer; }
.tab[aria-selected="true"] { background: var(--primary-color); color: var(--text-primary-color, #fff); }
.tab:focus-visible, button:focus-visible, input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.section-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .06em; color: var(--ac-muted); margin: 14px 0 6px; }
svg text { font-family: inherit; }
.timeline { width: 100%; display: block; touch-action: pan-y; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: .75rem; color: var(--ac-muted); margin-top: 4px; }
.legend i { display: inline-block; width: 14px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 4px; }
.inspect { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin-top: 8px; font-size: .8rem; }
.inspect div { background: var(--ac-chip); border-radius: 8px; padding: 6px 8px; }
.inspect b { display: block; font-size: .95rem; }
.nightsel { display: flex; gap: 6px; overflow-x: auto; margin-bottom: 8px; scrollbar-width: none; }
.nightsel button { flex: 0 0 auto; }
.chip { border: 1px solid var(--ac-line); background: none; color: var(--primary-text-color); border-radius: 999px; padding: 4px 10px; font: inherit; font-size: .8rem; cursor: pointer; }
.chip[aria-pressed="true"] { border-color: var(--primary-color); background: var(--primary-color); color: var(--text-primary-color, #fff); }
.night { display: grid; grid-template-columns: 74px 26px 1fr; gap: 8px; align-items: center; padding: 8px 4px; border-bottom: 1px solid var(--ac-line); cursor: pointer; border-radius: 8px; }
.night:hover { background: var(--ac-chip); }
.night .date { font-size: .85rem; line-height: 1.2; }
.night .date small { color: var(--ac-muted); display: block; }
.bars { display: grid; gap: 4px; }
.barline { display: grid; grid-template-columns: 1fr 34px; gap: 6px; align-items: center; font-size: .78rem; }
.track { height: 8px; border-radius: 4px; background: var(--ac-chip); overflow: hidden; }
.fill { height: 100%; border-radius: 4px; }
.meta { font-size: .74rem; color: var(--ac-muted); display: flex; flex-wrap: wrap; gap: 2px 10px; }
.badge { display: inline-block; font-size: .68rem; padding: 1px 6px; border-radius: 999px; background: var(--ac-chip); color: var(--ac-muted); }
.badge.star { background: #f2b630; color: #222; }
.note { font-size: .78rem; color: var(--ac-muted); margin: 10px 0 4px; line-height: 1.4; }
.filters { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.search { width: 100%; padding: 8px 12px; border-radius: 999px; border: 1px solid var(--ac-line); background: transparent; color: var(--primary-text-color); font: inherit; font-size: .88rem; margin-bottom: 8px; }
.obj { border-bottom: 1px solid var(--ac-line); }
.obj-row { display: grid; grid-template-columns: 26px 1fr auto; gap: 10px; align-items: center; padding: 8px 2px; cursor: pointer; }
.obj-row .icon { color: var(--ac-deep); display: flex; }
.obj-row .icon.planet, .obj-row .icon.moon { color: var(--ac-planet); }
.obj-row .name { font-size: .9rem; font-weight: 500; line-height: 1.25; }
.obj-row .sub { font-size: .75rem; color: var(--ac-muted); }
.pill { min-width: 38px; text-align: center; font-weight: 700; font-size: .85rem; border-radius: 8px; padding: 3px 6px; color: #fff; }
.reasons { display: flex; flex-wrap: wrap; gap: 4px; margin: 2px 0 0; }
.reasons span { font-size: .7rem; background: var(--ac-chip); border-radius: 999px; padding: 1px 7px; color: var(--ac-muted); }
.detail { padding: 4px 4px 12px 38px; font-size: .8rem; }
.detail .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 4px 12px; color: var(--ac-muted); }
.detail .grid b { color: var(--primary-text-color); font-weight: 500; }
.iconbtn { border: none; background: none; color: var(--ac-muted); cursor: pointer; padding: 4px; border-radius: 50%; display: inline-flex; font: inherit; }
.iconbtn:hover { background: var(--ac-chip); }
.iconbtn.on { color: #f2b630; }
.event { display: grid; grid-template-columns: 26px 1fr; gap: 10px; padding: 8px 2px; border-bottom: 1px solid var(--ac-line); cursor: pointer; }
.event .t { font-size: .88rem; }
.event.major .t { font-weight: 600; }
.event .when { font-size: .75rem; color: var(--ac-muted); }
.event .desc { font-size: .78rem; color: var(--ac-muted); white-space: pre-line; margin-top: 4px; }
.event .icon { color: var(--ac-deep); display: flex; padding-top: 2px; }
.month { font-size: .78rem; font-weight: 600; color: var(--ac-muted); margin: 12px 0 2px; text-transform: capitalize; }
.providers { font-size: .78rem; margin-top: 8px; display: grid; gap: 4px; }
.providers div { display: flex; justify-content: space-between; gap: 8px; border-bottom: 1px dashed var(--ac-line); padding: 2px 0; }
.empty { color: var(--ac-muted); font-size: .88rem; padding: 18px 4px; text-align: center; }
.skymap { width: 100%; max-width: 420px; margin: 0 auto; display: block; }
input[type=range] { width: 100%; accent-color: var(--primary-color); }
.attribution { font-size: .66rem; color: var(--ac-muted); margin-top: 12px; line-height: 1.35; }
.two-col { display: grid; gap: 0 24px; }
@media (min-width: 1100px) { .panel .two-col { grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); } }
.nightbtn { color: #d33; }
.nightbtn[aria-pressed="true"] { background: var(--ac-chip); }
/* Night vision: everything is rendered in shades of pure red on black. The
   content is turned to grey, then multiplied by red, so no green or blue light
   is emitted whatever the colours used by the card. */
.nightshell { position: relative; isolation: isolate; background: #000; border-radius: var(--ha-card-border-radius, 12px); overflow: hidden; }
.nightshell.panel-shell { border-radius: 0; min-height: 100vh; }
.nightshell::after { content: ""; position: absolute; inset: 0; background: #f00; mix-blend-mode: multiply; pointer-events: none; z-index: 10; }
.nightinner {
  filter: grayscale(1) brightness(.85);
  --ha-card-background: #000; --card-background-color: #000; --primary-background-color: #000;
  --primary-text-color: #fff; --secondary-text-color: #c4c4c4; --divider-color: rgba(255,255,255,.22);
  --primary-color: #ddd; --text-primary-color: #000; --ac-chip: rgba(255,255,255,.12);
  --ha-card-box-shadow: none; --ha-card-border-color: rgba(255,255,255,.2);
  color: #fff; background: #000;
}
`;

/* ----------------------------------------------------------- base class -- */

class AstroCastView extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._tab = "tonight";
    this._nightIndex = 0;
    this._filter = "all";
    this._expanded = new Set();
    this._expandedEvents = new Set();
    this._objectDetails = {};
    this._search = "";
    this._searchResults = null;
    this._inspect = null;
    this._skyIndex = null;
    this._showProviders = false;
    this._subscribedFor = null;
    this._unsub = null;
  }

  disconnectedCallback() {
    if (this._onNightMode) {
      window.removeEventListener(NIGHT_EVENT, this._onNightMode);
      this._onNightMode = null;
    }
    this._unsubscribe();
    this._resizeObserver?.disconnect();
    this._resizeObserver = null;
  }

  _observeSize() {
    if (this._resizeObserver || typeof ResizeObserver === "undefined") return;
    this._resizeObserver = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width;
      if (!width) return;
      const inner = Math.round(width - 32);
      if (Math.abs(inner - (this._width || 0)) > 8) {
        this._width = inner;
        clearTimeout(this._resizeTimer);
        this._resizeTimer = setTimeout(() => this._render(true), 120);
      }
    });
    this._resizeObserver.observe(this);
  }

  get lang() {
    const raw = this._hass?.locale?.language || this._hass?.language || "en";
    return raw.toLowerCase().startsWith("fr") ? "fr" : "en";
  }

  t(key, params) {
    let text = (STRINGS[this.lang] && STRINGS[this.lang][key]) || STRINGS.en[key] || key;
    if (params) for (const [k, v] of Object.entries(params)) text = text.replace(`{${k}}`, v);
    return text;
  }

  get timeZone() {
    const tz = this._hass?.locale?.time_zone;
    if (tz === "local") return undefined;
    return this._hass?.config?.time_zone || undefined;
  }

  fmtTime(iso) {
    if (!iso) return "—";
    return new Intl.DateTimeFormat(this.lang, {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: this.timeZone,
    }).format(new Date(iso));
  }

  fmtDate(iso, opts = { weekday: "short", day: "numeric", month: "short" }) {
    if (!iso) return "—";
    // Night dates ("2026-10-13") are calendar dates: format them at noon UTC.
    const date = iso.length === 10 ? new Date(`${iso}T12:00:00Z`) : new Date(iso);
    return new Intl.DateTimeFormat(this.lang, {
      ...opts,
      timeZone: iso.length === 10 ? "UTC" : this.timeZone,
    }).format(date);
  }

  fmtDateTime(iso) {
    if (!iso) return "—";
    return new Intl.DateTimeFormat(this.lang, {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: this.timeZone,
    }).format(new Date(iso));
  }

  _subscribe(entryId) {
    const key = `${entryId || "auto"}|${this.lang}`;
    if (!this._hass || this._subscribedFor === key) return;
    if (this._retryAfter && Date.now() < this._retryAfter) return;
    this._unsubscribe();
    this._subscribedFor = key;
    const msg = { type: "astrocast/subscribe", language: this.lang };
    if (entryId) msg.entry_id = entryId;
    this._unsub = this._hass.connection
      .subscribeMessage((data) => {
        this._data = data;
        this._error = null;
        // Details fetched on demand belong to the previous forecast.
        this._objectDetails = {};
        if (!data.nights[this._nightIndex]?.samples) this._nightIndex = 0;
        this._render();
      }, msg)
      .catch((err) => {
        // Retry later rather than on every Home Assistant state change.
        this._retryAfter = Date.now() + 60000;
        this._subscribedFor = null;
        this._error = err?.message || String(err);
        this._render();
      });
  }

  _unsubscribe() {
    if (this._unsub) {
      const pending = this._unsub;
      this._unsub = null;
      pending.then((unsub) => typeof unsub === "function" && unsub()).catch(() => {});
    }
    this._subscribedFor = null;
  }

  get isAdmin() {
    return Boolean(this._hass?.user?.is_admin);
  }

  async _toggleFavorite(objectId, favorite) {
    if (!this._data) return;
    try {
      await this._hass.callWS({
        type: "astrocast/favorite",
        entry_id: this._data.entry_id,
        object_id: objectId,
        favorite,
      });
    } catch (err) {
      this._error = err?.message || String(err);
      this._render();
    }
  }

  async _loadObject(objectId) {
    if (this._objectDetails[objectId] || !this._data) return;
    this._objectDetails[objectId] = "loading";
    try {
      this._objectDetails[objectId] = await this._hass.callWS({
        type: "astrocast/object",
        entry_id: this._data.entry_id,
        object_id: objectId,
      });
    } catch (err) {
      this._objectDetails[objectId] = { error: err?.message || String(err) };
    }
    this._render();
  }

  async _runSearch(query) {
    this._search = query;
    if (!query || query.trim().length < 2 || !this._data) {
      this._searchResults = null;
      this._render(true);
      return;
    }
    const current = query;
    try {
      const results = await this._hass.callWS({
        type: "astrocast/search",
        entry_id: this._data.entry_id,
        query,
        language: this.lang,
      });
      if (current === this._search) {
        this._searchResults = results;
        this._render(true);
      }
    } catch (_err) {
      this._searchResults = [];
      this._render(true);
    }
  }

  /* ---------------------------------------------------------- render -- */

  _render(keepFocus = false) {
    if (!this.shadowRoot) return;
    this._observeSize();
    if (!this._width && this.isConnected) {
      const width = this.getBoundingClientRect().width;
      if (width) this._width = Math.round(width - 32);
    }
    const active = keepFocus ? this.shadowRoot.activeElement : null;
    const selection = active && active.tagName === "INPUT" ? [active.selectionStart, active.selectionEnd] : null;
    const body = this._wrap(this._content());
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>${
      this.nightMode ? `<div class="nightshell ${this._isPanel ? "panel-shell" : ""}"><div class="nightinner">${body}</div></div>` : body
    }`;
    this._bind();
    if (active && active.id) {
      const el = this.shadowRoot.getElementById(active.id);
      if (el) {
        el.focus();
        if (selection) el.setSelectionRange(selection[0], selection[1]);
      }
    }
  }

  _wrap(inner) {
    return inner;
  }

  /** Night-vision setting of the card: "toggle" (button), "on" or "auto". */
  get nightSetting() {
    const value = this._config?.night_mode;
    if (value === true || value === "on") return "on";
    if (value === "auto") return "auto";
    return "toggle";
  }

  get nightMode() {
    const setting = this.nightSetting;
    if (setting === "on") return true;
    if (setting === "auto") {
      const sunAlt = this._data?.now?.sun_alt;
      return sunAlt !== undefined && sunAlt !== null && sunAlt < -6;
    }
    return storedNightMode();
  }

  _toggleNightMode() {
    const next = !storedNightMode();
    try {
      window.localStorage.setItem(NIGHT_KEY, next ? "on" : "off");
    } catch (_e) {
      nightFallback = next; // storage unavailable: lasts until the next reload
    }
    // Every AstroCast card and panel of the page follows.
    window.dispatchEvent(new CustomEvent(NIGHT_EVENT));
  }

  connectedCallback() {
    if (!this._onNightMode) {
      this._onNightMode = () => this._render();
      window.addEventListener(NIGHT_EVENT, this._onNightMode);
    }
  }

  _content() {
    if (this._error && !this._data) {
      return `<div class="wrap"><div class="empty">${esc(this.t("error"))}<br><small>${esc(this._error)}</small></div></div>`;
    }
    if (!this._data) return `<div class="wrap"><div class="empty">${esc(this.t("loading"))}</div></div>`;
    const compact = this._config?.view === "compact";
    return `<div class="wrap">
      ${this._header()}
      ${compact ? "" : this._tabs()}
      ${compact ? "" : this._tabBody()}
      ${compact ? "" : `<div class="attribution">7Timer! · Open-Meteo (CC BY 4.0) · MET Norway (CC BY 4.0) · CAMS · NASA/JPL SBDB · OpenNGC (CC BY-SA 4.0) · astronomy-engine</div>`}
    </div>`;
  }

  _header() {
    const d = this._data;
    const night = d.nights[0];
    const healthColor = { ok: RATING_COLORS.excellent, degraded: RATING_COLORS.fair, unavailable: RATING_COLORS.bad }[d.health] || "#999";
    const scoreBox = (profile, color) => {
      const p = night[profile];
      const score = p.score;
      const rating = p.rating || ratingOf(score);
      const nowScore = d.now.scores?.[profile];
      return `<div class="score" style="border-left:4px solid ${color}">
        <div class="label"><span>${esc(this.t(profile))} · ${esc(this.t("tonight").toLowerCase())}</span></div>
        <div class="value">${score ?? "—"}<small>/100</small></div>
        <div class="rating" style="color:${RATING_COLORS[rating] || "inherit"}">${rating ? esc(this.t(`rating_${rating}`)) : p.potential !== null && p.potential !== undefined ? `<span style="color:var(--ac-muted);font-weight:500">${esc(this.t("if_clear"))} : ${p.potential}</span>` : ""}</div>
        <div class="now">${esc(this.t("now"))} : ${nowScore ?? "—"}${d.now.limiting?.[profile] && nowScore !== null ? ` · ${esc(this.t("limited_by"))} ${esc(this.t(`factor_${d.now.limiting[profile]}`))}` : ""}</div>
        <div class="bar" style="width:${score || 0}%;background:${RATING_COLORS[rating] || color}"></div>
      </div>`;
    };
    const ds = night.deep_sky;
    const nb = night.narrowband || {};
    let summary;
    if (!night.has_weather) {
      summary = esc(this.t("no_weather"));
    } else if (ds.window_start) {
      summary = `<b>${esc(this.t("best_window"))}</b> ${this.fmtTime(ds.window_start)} → ${this.fmtTime(ds.window_end)} · ${fmtHours(ds.window_hours)} (${ds.window_score}/100)`;
      if (ds.limiting) summary += ` · ${esc(this.t("limited_by"))} ${esc(this.t(`factor_${ds.limiting}`))}`;
    } else {
      summary = esc(this.t("no_window"));
      if (ds.limiting) summary += ` · ${esc(this.t("limited_by"))} ${esc(this.t(`factor_${ds.limiting}`))}`;
    }
    const conf = confidenceKey(ds.confidence);
    if (ds.tier) summary += ` <span class="badge">${esc(this.t(`tier_${ds.tier}`))}${conf ? ` · ${esc(this.t("confidence"))} ${esc(this.t(conf))}` : ""}</span>`;
    const pl = night.planetary;
    if (pl.window_start) {
      summary += `<br><b>${esc(this.t("planetary"))}</b> ${this.fmtTime(pl.window_start)} → ${this.fmtTime(pl.window_end)} · ${fmtHours(pl.window_hours)} (${pl.window_score}/100)`;
    }
    if (nb.window_start && (nb.score ?? 0) >= (ds.score ?? 0) + 15) {
      summary += `<br><b>${esc(this.t("narrowband"))}</b> ${this.fmtTime(nb.window_start)} → ${this.fmtTime(nb.window_end)} · ${fmtHours(nb.window_hours)} (${nb.window_score}/100) <span class="badge">${esc(this.t("narrowband_hint"))}</span>`;
    }
    const moonWaxing = night.moon_phase_angle < 180;
    const astro = night.astro_dusk
      ? `${this.fmtTime(night.astro_dusk)} → ${this.fmtTime(night.astro_dawn)}`
      : esc(this.t("no_astro_night"));
    const moonTimes = [
      night.moonrise ? [night.moonrise, `${esc(this.t("moonrise"))} ${this.fmtTime(night.moonrise)}`] : null,
      night.moonset ? [night.moonset, `${esc(this.t("moonset"))} ${this.fmtTime(night.moonset)}`] : null,
    ]
      .filter(Boolean)
      .sort((a, b) => new Date(a[0]) - new Date(b[0]))
      .map((m) => m[1])
      .join(", ");
    return `
      <div class="header">
        <div class="title">${glyph("galaxy", 22)}<span>${esc(this._config?.title || `AstroCast · ${d.site.name}`)}</span></div>
        <button class="health" id="health" title="${esc(this.t("data_sources"))}"><span class="dot" style="background:${healthColor}"></span>${esc(this.t("updated"))} ${this.fmtTime(d.generated)}</button>
        ${this.nightSetting === "toggle" ? `<button class="iconbtn nightbtn" id="nightmode" aria-pressed="${this.nightMode}" title="${esc(this.t("night_mode"))}" aria-label="${esc(this.t("night_mode"))}"><svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5C6.5 5 2.7 9.3 1.5 12c1.2 2.7 5 7 10.5 7s9.3-4.3 10.5-7C21.3 9.3 17.5 5 12 5zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8z" fill="currentColor"/></svg></button>` : ""}
      </div>
      ${this._showProviders ? this._providers() : ""}
      <div class="scores">${scoreBox("deep_sky", DEEP_COLOR)}${scoreBox("planetary", PLANET_COLOR)}${night.narrowband ? scoreBox("narrowband", NARROW_COLOR) : ""}</div>
      <div class="summary">${summary}</div>
      <div class="facts">
        <span class="fact">${moonIcon(night.moon_illumination / 100, moonWaxing, 18)} ${esc(this.t(`phase_${night.moon_phase}`))} · ${night.moon_illumination} %${moonTimes ? ` (${moonTimes})` : ""}</span>
        <span class="fact">🌌 ${esc(this.t("astro_night"))} ${astro}</span>
        ${night.summary.cloud_cover !== null && night.summary.cloud_cover !== undefined ? `<span class="fact">☁ ${Math.round(night.summary.cloud_cover)} %</span>` : ""}
        ${
          night.summary.dew_onset
            ? `<span class="fact">💧 ${esc(this.t("dew_at"))} ${this.fmtTime(night.summary.dew_onset)}${d.site.dew_heaters ? ` (${esc(this.t("dew_heaters"))})` : ""}</span>`
            : night.summary.dew_risk && night.summary.dew_risk !== "low"
              ? `<span class="fact">💧 ${esc(this.t("dew_risk"))} ${esc(this.t(`dew_${night.summary.dew_risk}`))}</span>`
              : ""
        }
      </div>`;
  }

  _providers() {
    const p = this._data.providers || {};
    const rows = Object.entries(p).map(([name, s]) => {
      let state = s.active ? this.t("active") : this.t("inactive");
      if (s.role === "fallback") state = `${this.t("fallback")} · ${state}`;
      if (s.failures) state += ` · ${this.t("failing")}`;
      else if (s.stale && s.active) state += ` · ${this.t("stale")}`;
      const when = s.last_success ? this.fmtDateTime(s.last_success) : "—";
      return `<div><span>${esc(name)}</span><span>${esc(state)} · ${when}</span></div>`;
    });
    return `<div class="providers">${rows.join("")}</div>`;
  }

  _tabs() {
    return `<div class="tabs" role="tablist">${TABS.map(
      (tab) => `<button class="tab" role="tab" data-tab="${tab}" aria-selected="${this._tab === tab}">${esc(this.t(tab === "tonight" ? "tonight" : tab))}</button>`,
    ).join("")}</div>`;
  }

  _tabBody() {
    switch (this._tab) {
      case "nights":
        return this._nightsTab();
      case "objects":
        return this._objectsTab();
      case "events":
        return this._eventsTab();
      case "sky":
        return this._skyTab();
      default:
        return this._tonightTab();
    }
  }

  /* ------------------------------------------------------ tonight tab -- */

  _nightSelector() {
    const nights = this._data.nights.filter((n) => n.samples).slice(0, 7);
    return `<div class="nightsel">${nights
      .map((n, i) => {
        const idx = this._data.nights.indexOf(n);
        return `<button class="chip" data-night="${idx}" aria-pressed="${idx === this._nightIndex}">${i === 0 ? esc(this.t("tonight")) : esc(this.fmtDate(n.date))}</button>`;
      })
      .join("")}</div>`;
  }

  _tonightTab() {
    const night = this._data.nights[this._nightIndex] || this._data.nights[0];
    if (!night.samples) return `${this._nightSelector()}<div class="empty">—</div>`;
    return `${this._nightSelector()}${this._timeline(night)}${this._inspectPanel(night)}`;
  }

  _timeline(night) {
    const s = night.samples;
    const n = s.deep_sky.length;
    const W = Math.max(300, Math.min(1600, Math.round(this._width || 600)));
    const H = W < 480 ? 210 : 230;
    const top = 30; // cloud strip
    const plotTop = 44;
    const plotBottom = 196;
    const x = (i) => (i / Math.max(1, n - 1)) * W;
    const yScore = (v) => plotBottom - (v / 100) * (plotBottom - plotTop);
    const yAlt = (v) => plotBottom - (Math.max(0, v) / 90) * (plotBottom - plotTop);
    const step = s.step_minutes * 60000;
    const t0 = new Date(s.start).getTime();
    const parts = [];

    // Twilight background.
    const bandColor = (alt) => {
      if (alt > 0) return "rgba(120,170,230,.28)";
      if (alt > -6) return "rgba(90,110,190,.30)";
      if (alt > -12) return "rgba(60,70,150,.34)";
      if (alt > -18) return "rgba(40,40,110,.40)";
      return "rgba(15,15,55,.50)";
    };
    let segStart = 0;
    for (let i = 1; i <= n; i++) {
      if (i === n || bandColor(s.sun_alt[i]) !== bandColor(s.sun_alt[segStart])) {
        const x0 = Math.max(0, x(segStart) - W / (2 * (n - 1)));
        const x1 = Math.min(W, x(i - 1) + W / (2 * (n - 1)));
        parts.push(`<rect x="${x0}" y="${plotTop - 4}" width="${x1 - x0}" height="${plotBottom - plotTop + 4}" fill="${bandColor(s.sun_alt[segStart])}"/>`);
        segStart = i;
      }
    }

    // Grid lines.
    for (const v of [25, 50, 75]) {
      parts.push(`<line x1="0" x2="${W}" y1="${yScore(v)}" y2="${yScore(v)}" stroke="currentColor" stroke-opacity=".12" stroke-dasharray="3 4"/>`);
    }

    // Cloud cover strip (top).
    const bw = W / n;
    s.cloud.forEach((c, i) => {
      if (c === null) return;
      const h = (c / 100) * (top - 6);
      parts.push(`<rect x="${x(i) - bw / 2}" y="${top - h}" width="${bw + 0.5}" height="${h}" fill="currentColor" fill-opacity=".38"/>`);
    });
    parts.push(`<text x="4" y="12" font-size="11" fill="currentColor" fill-opacity=".65">☁ ${esc(this.t("clouds"))}</text>`);

    // Best windows.
    const windowRect = (p, color) => {
      if (!p.window_start) return;
      const i0 = (new Date(p.window_start).getTime() - t0) / step;
      const i1 = (new Date(p.window_end).getTime() - t0) / step;
      const a = Math.max(0, x(i0));
      const b = Math.min(W, x(i1));
      if (b <= a) return;
      parts.push(`<rect x="${a}" y="${plotTop - 4}" width="${b - a}" height="${plotBottom - plotTop + 4}" fill="${color}" fill-opacity=".14" stroke="${color}" stroke-opacity=".7" stroke-dasharray="4 3"/>`);
    };
    windowRect(night.deep_sky, DEEP_COLOR);

    const poly = (values, scale) =>
      values
        .map((v, i) => (v === null || v === undefined ? null : `${x(i).toFixed(1)},${scale(v).toFixed(1)}`))
        .filter(Boolean)
        .join(" ");

    // Moon altitude.
    if (s.moon_alt.some((v) => v > 0)) {
      parts.push(`<polyline points="${poly(s.moon_alt.map((v) => (v > 0 ? v : null)), yAlt)}" fill="none" stroke="${MOON_COLOR}" stroke-width="1.6" stroke-dasharray="5 4"/>`);
    }
    // Potential (if clear) for deep sky.
    if (s.deep_sky_potential) {
      parts.push(`<polyline points="${poly(s.deep_sky_potential, yScore)}" fill="none" stroke="${DEEP_COLOR}" stroke-opacity=".35" stroke-width="1.2"/>`);
    }
    // Scores.
    const area = `0,${plotBottom} ${poly(s.deep_sky, yScore)} ${W},${plotBottom}`;
    parts.push(`<polygon points="${area}" fill="${DEEP_COLOR}" fill-opacity=".18"/>`);
    parts.push(`<polyline points="${poly(s.deep_sky, yScore)}" fill="none" stroke="${DEEP_COLOR}" stroke-width="2.4" stroke-linejoin="round"/>`);
    parts.push(`<polyline points="${poly(s.planetary, yScore)}" fill="none" stroke="${PLANET_COLOR}" stroke-width="2" stroke-linejoin="round"/>`);
    // Narrowband only when it tells something the deep-sky curve does not
    // (typically under the Moon).
    const showNarrow =
      s.narrowband && s.narrowband.some((v, i) => v !== null && s.deep_sky[i] !== null && v - s.deep_sky[i] >= 10);
    if (showNarrow) {
      parts.push(`<polyline points="${poly(s.narrowband, yScore)}" fill="none" stroke="${NARROW_COLOR}" stroke-width="2" stroke-dasharray="6 3" stroke-linejoin="round"/>`);
    }
    // Dew onset on unprotected optics.
    const dewOnset = night.summary?.dew_onset;
    if (dewOnset) {
      const iDew = (new Date(dewOnset).getTime() - t0) / step;
      if (iDew >= 0 && iDew <= n - 1) {
        parts.push(`<line x1="${x(iDew)}" x2="${x(iDew)}" y1="${plotTop - 4}" y2="${plotBottom}" stroke="#4fb3e8" stroke-width="1.5" stroke-dasharray="2 3"/>`);
        parts.push(`<text x="${Math.min(W - 14, x(iDew) + 3)}" y="${plotBottom - 6}" font-size="12">💧</text>`);
      }
    }

    // Time axis on whole local hours (every 1, 2 or 3 hours depending on width).
    const fmt = new Intl.DateTimeFormat(this.lang, { hour: "2-digit", minute: "2-digit", timeZone: this.timeZone });
    const clock = new Intl.DateTimeFormat("en-GB", { hour: "numeric", minute: "numeric", hourCycle: "h23", timeZone: this.timeZone });
    const spanHours = ((n - 1) * step) / 3600000;
    const every = W / spanHours > 55 ? 1 : W / spanHours > 30 ? 2 : 3;
    // Walk in 15-minute steps and keep whole *local* hours (time zones may be
    // offset by 30 or 45 minutes from UTC).
    const firstQuarter = Math.ceil(t0 / 900000) * 900000;
    for (let t = firstQuarter; t <= t0 + (n - 1) * step; t += 900000) {
      const date = new Date(t);
      const local = Object.fromEntries(clock.formatToParts(date).map((p) => [p.type, p.value]));
      if (Number(local.minute) !== 0 || Number(local.hour) % every !== 0) continue;
      const xi = x((t - t0) / step);
      if (xi < 16 || xi > W - 16) continue;
      parts.push(`<line x1="${xi}" x2="${xi}" y1="${plotBottom}" y2="${plotBottom + 4}" stroke="currentColor" stroke-opacity=".5"/>`);
      parts.push(`<text x="${xi}" y="${plotBottom + 17}" font-size="11" text-anchor="middle" fill="currentColor" fill-opacity=".7">${fmt.format(date)}</text>`);
    }

    // Now marker.
    const now = Date.now();
    const iNow = (now - t0) / step;
    if (iNow >= 0 && iNow <= n - 1) {
      parts.push(`<line x1="${x(iNow)}" x2="${x(iNow)}" y1="${top - 26}" y2="${plotBottom}" stroke="var(--primary-color)" stroke-width="1.5"/>`);
      parts.push(`<text x="${Math.min(W - 30, x(iNow) + 4)}" y="${plotTop + 8}" font-size="10" fill="var(--primary-color)">${esc(this.t("now"))}</text>`);
    }
    // Inspect marker.
    if (this._inspect !== null && this._inspect < n) {
      parts.push(`<line x1="${x(this._inspect)}" x2="${x(this._inspect)}" y1="${plotTop - 4}" y2="${plotBottom}" stroke="currentColor" stroke-opacity=".6"/>`);
    }

    const legend = `<div class="legend">
      <span><i style="background:${DEEP_COLOR}"></i>${esc(this.t("deep_sky"))}</span>
      <span><i style="background:${PLANET_COLOR}"></i>${esc(this.t("planetary"))}</span>
      ${showNarrow ? `<span><i style="background:${NARROW_COLOR}"></i>${esc(this.t("narrowband"))}</span>` : ""}
      ${dewOnset ? `<span>💧 ${esc(this.t("dew_at"))} ${this.fmtTime(dewOnset)}</span>` : ""}
      <span><i style="background:${DEEP_COLOR};opacity:.35"></i>${esc(this.t("potential"))}</span>
      <span><i style="background:${MOON_COLOR}"></i>${esc(this.t("moon"))}</span>
      <span><i style="background:rgba(15,15,55,.6)"></i>${esc(this.t("dark_window"))}</span>
    </div>`;
    return `<svg class="timeline" id="timeline" viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="${esc(this.t("tonight"))}" style="color:var(--primary-text-color)">${parts.join("")}<rect id="hit" x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg>${legend}`;
  }

  _inspectPanel(night) {
    const s = night.samples;
    const n = s.deep_sky.length;
    let i = this._inspect;
    if (i === null || i >= n) {
      // Default: the deep-sky peak (or now when inside the night).
      const t0 = new Date(s.start).getTime();
      const iNow = Math.round((Date.now() - t0) / (s.step_minutes * 60000));
      if (this._nightIndex === 0 && iNow >= 0 && iNow < n) i = iNow;
      else if (night.deep_sky.peak_time) i = Math.round((new Date(night.deep_sky.peak_time).getTime() - t0) / (s.step_minutes * 60000));
      else i = Math.floor(n / 2);
      i = Math.max(0, Math.min(n - 1, i));
    }
    const time = new Date(new Date(s.start).getTime() + i * s.step_minutes * 60000).toISOString();
    const val = (arr, digits = 0, unit = "") => {
      if (!arr || arr[i] === null || arr[i] === undefined) return "—";
      return `${Number(arr[i]).toFixed(digits)}${unit}`;
    };
    const cells = [
      [this.t("deep_sky"), val(s.deep_sky)],
      [this.t("planetary"), val(s.planetary)],
      ...(s.narrowband ? [[this.t("narrowband"), val(s.narrowband)]] : []),
      [this.t("clouds"), val(s.cloud, 0, " %")],
    ];
    if (s.clear_probability && s.clear_probability[i] !== null) cells.push([this.t("clear_chance"), val(s.clear_probability, 0, " %")]);
    if (s.seeing) cells.push([this.t("seeing"), val(s.seeing, 1, "″")]);
    if (s.transparency) cells.push([this.t("transparency"), val(s.transparency, 2)]);
    if (s.humidity) cells.push([this.t("humidity"), val(s.humidity, 0, " %")]);
    if (s.wind) cells.push([this.t("wind"), val(s.wind, 0, " km/h")]);
    if (s.temperature) cells.push([this.t("temperature"), val(s.temperature, 1, " °C")]);
    if (s.dew_point) cells.push([this.t("dew_point"), val(s.dew_point, 1, " °C")]);
    cells.push([this.t("moon"), s.moon_alt[i] > 0 ? `${s.moon_alt[i]}°` : "↓"]);
    const tier = night.deep_sky.tier;
    const conf = confidenceKey(night.deep_sky.confidence);
    return `<div class="section-title">${esc(this.fmtDateTime(time))}${tier ? ` · ${esc(this.t(`tier_${tier}`))}` : ""}${conf ? ` · ${esc(this.t("confidence"))} ${esc(this.t(conf))}` : ""}</div>
      <div class="inspect">${cells.map(([k, v]) => `<div>${esc(k)}<b>${esc(v)}</b></div>`).join("")}</div>
      ${tier === "trend" ? `<div class="note">${esc(this.t("trend_note"))}</div>` : ""}`;
  }

  /* ------------------------------------------------------- nights tab -- */

  _nightsTab() {
    const d = this._data;
    const rows = [];
    let horizonShown = false;
    d.nights.forEach((n, idx) => {
      const ds = n.deep_sky;
      const pl = n.planetary;
      const nbp = n.narrowband;
      const isBest = n.date === d.best_night;
      const waxing = n.moon_phase_angle < 180;
      if (!n.has_weather && !horizonShown) {
        horizonShown = true;
        rows.push(`<div class="note">${esc(this.t("weather_horizon"))}</div>`);
      }
      const bar = (p, color) => {
        const score = p.score ?? p.potential ?? 0;
        const rating = ratingOf(score);
        const faded = p.score === null || p.score === undefined;
        return `<div class="barline"><div class="track"><div class="fill" style="width:${score}%;background:${faded ? color : RATING_COLORS[rating]};opacity:${faded ? 0.35 : 1}"></div></div><span>${p.score ?? `(${p.potential ?? "—"})`}</span></div>`;
      };
      const meta = [];
      if (ds.window_start) meta.push(`${esc(this.t("window"))} ${this.fmtTime(ds.window_start)}–${this.fmtTime(ds.window_end)} (${fmtHours(ds.window_hours)})`);
      if (n.summary.dew_onset && n.has_weather) meta.push(`💧 ${this.fmtTime(n.summary.dew_onset)}`);
      // Deterministic cloud amounts are not meaningful at trend range: show the
      // ensemble clear-sky probability instead.
      if (n.summary.cloud_cover !== null && n.summary.cloud_cover !== undefined && n.has_weather && ds.tier !== "trend") meta.push(`☁ ${Math.round(n.summary.cloud_cover)} %`);
      if (n.summary.clear_probability !== null && n.summary.clear_probability !== undefined && n.has_weather && ds.tier === "trend") meta.push(`${esc(this.t("clear_chance"))} ${Math.round(n.summary.clear_probability)} %`);
      meta.push(`${n.moonless_dark_hours.toFixed(1)} ${esc(this.t("hours_short"))} ${esc(this.t("moonless_hours"))}`);
      const tier = n.has_weather ? ds.tier : "astro";
      rows.push(`<div class="night" data-open-night="${idx}" role="button" tabindex="0">
        <div class="date">${esc(this.fmtDate(n.date, { weekday: "short" }))}<small>${esc(this.fmtDate(n.date, { day: "numeric", month: "short" }))}</small>${isBest ? `<span class="badge star">★</span>` : ""}</div>
        <div title="${n.moon_illumination} %">${moonIcon(n.moon_illumination / 100, waxing, 22)}</div>
        <div><div class="bars">${bar(ds, DEEP_COLOR)}${n.has_weather ? bar(pl, PLANET_COLOR) : ""}${n.has_weather && nbp ? bar(nbp, NARROW_COLOR) : ""}</div>
          <div class="meta">${tier ? `<span class="badge">${esc(this.t(`tier_${tier}`))}</span>` : ""}${meta.map((m) => `<span>${m}</span>`).join("")}</div></div>
      </div>`);
    });
    return `<div class="legend"><span><i style="background:${DEEP_COLOR}"></i>${esc(this.t("deep_sky"))}</span><span><i style="background:${PLANET_COLOR}"></i>${esc(this.t("planetary"))}</span><span><i style="background:${NARROW_COLOR}"></i>${esc(this.t("narrowband"))}</span><span>(…) = ${esc(this.t("potential"))}</span><span><span class="badge star">★</span> ${esc(this.t("best"))}</span></div>${rows.join("")}`;
  }

  /* ------------------------------------------------------ objects tab -- */

  _objectsTab() {
    const d = this._data;
    const idx = Math.min(this._nightIndex, d.nights.length - 1);
    const night = d.nights[idx];
    const objects = night.objects || [];
    const planets = (night.planets || []).filter((p) => p.best_score > 0 || p.favorite);
    const favIds = new Set((d.favorites || []).map((f) => f.id));
    const filters = [
      ["all", this.t("all")],
      ["favorites", this.t("favorites")],
      ["planets", this.t("planets")],
      ["galaxies", this.t("galaxies")],
      ["nebulae", this.t("nebulae")],
      ["clusters", this.t("clusters")],
      ["small_bodies", this.t("small_bodies")],
    ];
    const match = (o) => {
      switch (this._filter) {
        case "favorites":
          return favIds.has(o.id);
        case "planets":
          return o.kind === "planet" || o.kind === "moon";
        case "galaxies":
          return o.type === "galaxy" || o.type === "galaxy_group";
        case "nebulae":
          return /nebula|remnant/.test(o.type);
        case "clusters":
          return /cluster|asterism/.test(o.type) && o.type !== "cluster_nebula";
        case "small_bodies":
          return o.kind === "comet" || o.kind === "asteroid";
        default:
          return true;
      }
    };
    let list;
    if (this._filter === "favorites") {
      list = (d.favorites || []).map((f) => ({ ...(f.tonight || { id: f.id, name: f.name, kind: "dso", type: "galaxy", best_score: 0 }), favorite: true, _fav: f }));
    } else {
      list = [...planets, ...objects].filter(match).sort((a, b) => (b.interest || 0) - (a.interest || 0));
    }
    const search = `<input class="search" id="search" type="search" placeholder="${esc(this.t("search_placeholder"))}" value="${esc(this._search)}" autocomplete="off">`;
    const results = this._searchResults
      ? `<div>${this._searchResults
          .map(
            (r) => `<div class="obj-row" data-detail="${esc(r.id)}"><div class="icon ${esc(r.kind)}">${glyph(r.kind === "dso" ? r.type : r.kind)}</div><div><div class="name">${esc(r.name)}</div><div class="sub">${esc(this.t(`type_${r.type}`) || "")}${r.mag !== undefined && r.mag !== null ? ` · ${esc(this.t("mag"))} ${r.mag}` : ""}${r.constellation ? ` · ${esc(r.constellation)}` : ""}</div></div>${this.isAdmin ? `<button class="iconbtn ${r.favorite || favIds.has(r.id) ? "on" : ""}" data-fav="${esc(r.id)}" data-state="${r.favorite || favIds.has(r.id) ? 1 : 0}" title="${esc(this.t(r.favorite ? "remove_favorite" : "add_favorite"))}">${r.favorite || favIds.has(r.id) ? "★" : "☆"}</button>` : ""}</div>${this._expanded.has(r.id) ? this._objectDetail({ id: r.id }) : ""}`,
          )
          .join("")}</div>`
      : "";
    const items = list.length
      ? list.map((o) => this._objectRow(o, idx, favIds)).join("")
      : `<div class="empty">${esc(this.t("no_objects"))}</div>`;
    return `${this._nightSelector()}${search}${results}
      <div class="filters">${filters.map(([k, label]) => `<button class="chip" data-filter="${k}" aria-pressed="${this._filter === k}">${esc(label)}</button>`).join("")}</div>
      ${items}`;
  }

  _objectRow(o, nightIdx, favIds) {
    const score = o.best_score ?? 0;
    const rating = ratingOf(score);
    const fav = favIds.has(o.id);
    const sub = [
      this.t(`type_${o.type}`),
      o.mag !== null && o.mag !== undefined ? `${this.t("mag")} ${o.mag}` : null,
      o.constellation || null,
      o.best_time ? `${this.t("best_time")} ${this.fmtTime(o.best_time)}` : null,
      o.max_alt !== undefined && o.max_alt > -90 ? `${this.t("max_alt")} ${Math.round(o.max_alt)}°` : null,
    ].filter(Boolean);
    const reasons = (o.reasons || []).map((r) => {
      const { key, ...params } = r;
      return `<span>${esc(this.t(`reason_${key}`, params))}</span>`;
    });
    const spark = o.alt ? this._sparkline(o.alt) : "";
    const expanded = this._expanded.has(o.id);
    return `<div class="obj">
      <div class="obj-row" data-detail="${esc(o.id)}" role="button" tabindex="0" aria-expanded="${expanded}">
        <div class="icon ${esc(o.kind)}">${glyph(o.kind === "dso" ? o.type : o.kind)}</div>
        <div><div class="name">${esc(o.name)}</div><div class="sub">${sub.map(esc).join(" · ")}</div>${reasons.length ? `<div class="reasons">${reasons.join("")}</div>` : ""}</div>
        <div style="display:flex;align-items:center;gap:6px">${spark}<span class="pill" style="background:${RATING_COLORS[rating]}">${score}</span>${this.isAdmin ? `<button class="iconbtn ${fav ? "on" : ""}" data-fav="${esc(o.id)}" data-state="${fav ? 1 : 0}" title="${esc(this.t(fav ? "remove_favorite" : "add_favorite"))}" aria-label="${esc(this.t(fav ? "remove_favorite" : "add_favorite"))}">${fav ? "★" : "☆"}</button>` : ""}</div>
      </div>
      ${expanded ? this._objectDetail(o) : ""}
    </div>`;
  }

  _sparkline(alt) {
    const W = 64;
    const H = 22;
    const minAlt = this._data.site.min_altitude || 0;
    const pts = alt.map((v, i) => `${((i / (alt.length - 1)) * W).toFixed(1)},${(H - (Math.max(0, v) / 90) * H).toFixed(1)}`).join(" ");
    const yMin = H - (minAlt / 90) * H;
    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true"><line x1="0" x2="${W}" y1="${yMin}" y2="${yMin}" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="2 2"/><polyline points="${pts}" fill="none" stroke="${DEEP_COLOR}" stroke-width="1.5"/></svg>`;
  }

  _objectDetail(o) {
    const info = this._objectDetails[o.id];
    if (!info) {
      this._loadObject(o.id);
      return `<div class="detail">…</div>`;
    }
    if (info === "loading") return `<div class="detail">…</div>`;
    if (info.error) return `<div class="detail">${esc(info.error)}</div>`;
    const t = info.tonight || {};
    const grid = [
      [this.t("best_time"), t.best_time ? this.fmtTime(t.best_time) : "—"],
      [this.t("window"), t.window_start ? `${this.fmtTime(t.window_start)}–${this.fmtTime(t.window_end)}` : "—"],
      [this.t("max_alt"), t.max_alt !== undefined ? `${Math.round(t.max_alt)}°` : "—"],
      [this.t("visible_for"), t.hours_visible !== undefined ? `${t.hours_visible} ${this.t("hours_short")}` : "—"],
    ];
    if (t.extra?.estimated_magnitude) grid.push([this.t("mag"), `${t.mag} (${this.t("estimate")})`]);
    const nights = (info.nights || []).slice(0, 10).map((n) => {
      const rating = ratingOf(n.score);
      return `<div class="barline" title="${esc(n.best_time ? this.fmtDateTime(n.best_time) : "")}"><div style="display:grid;grid-template-columns:70px 1fr;gap:6px;align-items:center"><span>${esc(this.fmtDate(n.date))}</span><div class="track"><div class="fill" style="width:${n.score}%;background:${n.weather ? RATING_COLORS[rating] : DEEP_COLOR};opacity:${n.weather ? 1 : 0.35}"></div></div></div><span>${n.weather ? n.score : `(${n.score})`}</span></div>`;
    });
    return `<div class="detail"><div class="grid">${grid.map(([k, v]) => `<div>${esc(k)} <b>${esc(v)}</b></div>`).join("")}</div>
      <div class="section-title">${esc(this.t("next_nights"))}</div><div class="bars">${nights.join("")}</div></div>`;
  }

  /* ------------------------------------------------------- events tab -- */

  _eventsTab() {
    const events = this._data.events || [];
    if (!events.length) return `<div class="empty">—</div>`;
    let month = null;
    const out = [];
    for (const e of events) {
      const m = this.fmtDate(e.start, { month: "long", year: "numeric" });
      if (m !== month) {
        month = m;
        out.push(`<div class="month">${esc(m)}</div>`);
      }
      const glyphType = {
        moon_phase: "moon",
        lunar_eclipse: "moon",
        solar_eclipse: "planet",
        opposition: "planet",
        greatest_elongation: "planet",
        conjunction: "double_star",
        occultation: "moon",
        meteor_shower: "comet",
        comet: "comet",
        season: "open_cluster",
      }[e.type] || "galaxy";
      const open = this._expandedEvents.has(e.id);
      const vis = e.visible === true ? ` · ${this.t("visible")}` : e.visible === false ? ` · ${this.t("not_visible")}` : "";
      out.push(`<div class="event ${e.importance >= 3 ? "major" : ""}" data-event="${esc(e.id)}" role="button" tabindex="0" aria-expanded="${open}">
        <div class="icon">${glyph(glyphType, 20)}</div>
        <div><div class="t">${esc(e.title)}</div><div class="when">${esc(this.fmtDateTime(e.best_time || e.start))}${esc(vis)}</div>${open && e.description ? `<div class="desc">${esc(e.description)}</div>` : ""}</div>
      </div>`);
    }
    return out.join("");
  }

  /* ---------------------------------------------------------- sky tab -- */

  _skyTab() {
    const night = this._data.nights[0];
    const s = night.samples;
    if (!s) return `<div class="empty">—</div>`;
    const n = s.sun_alt.length;
    const t0 = new Date(s.start).getTime();
    const step = s.step_minutes * 60000;
    let idx = this._skyIndex;
    if (idx === null) {
      const iNow = Math.round((Date.now() - t0) / step);
      if (iNow >= 0 && iNow < n && s.sun_alt[iNow] < -6) idx = iNow;
      else if (night.deep_sky.peak_time) idx = Math.round((new Date(night.deep_sky.peak_time).getTime() - t0) / step);
      else idx = Math.floor(n / 2);
      idx = Math.max(0, Math.min(n - 1, idx));
    }
    const R = 150;
    const C = 170;
    const proj = (alt, az) => {
      const r = ((90 - alt) / 90) * R;
      const a = (az * Math.PI) / 180;
      // Looking up at the sky with north at the top, east is on the left.
      return [C - r * Math.sin(a), C - r * Math.cos(a)];
    };
    const parts = [];
    parts.push(`<circle cx="${C}" cy="${C}" r="${R}" fill="rgba(15,15,55,.55)" stroke="currentColor" stroke-opacity=".3"/>`);
    for (const alt of [30, 60]) parts.push(`<circle cx="${C}" cy="${C}" r="${((90 - alt) / 90) * R}" fill="none" stroke="#fff" stroke-opacity=".15"/>`);
    const minAlt = this._data.site.min_altitude || 0;
    const horizon = this._data.site.horizon || [];
    if (horizon.length) {
      // Obstructed sky (horizon profile), interpolated every 5° of azimuth.
      const pts = [];
      const altAt = (az) => {
        const sorted = [...horizon].sort((a, b) => a[0] - b[0]);
        if (sorted.length === 1) return sorted[0][1];
        for (let i = 0; i < sorted.length; i++) {
          const [a0, h0] = sorted[i];
          const [a1raw, h1] = sorted[(i + 1) % sorted.length];
          const a1 = i + 1 < sorted.length ? a1raw : a1raw + 360;
          const a = az < sorted[0][0] ? az + 360 : az;
          if (a >= a0 && a <= a1) return h0 + ((h1 - h0) * (a - a0)) / (a1 - a0 || 1);
        }
        return sorted[0][1];
      };
      for (let az = 0; az <= 360; az += 5) pts.push(proj(Math.max(0, altAt(az % 360)), az));
      const outer = [];
      for (let az = 360; az >= 0; az -= 5) outer.push(proj(0, az));
      parts.push(`<path d="M${pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" L")} L${outer.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" L")} Z" fill="#000" fill-opacity=".45" stroke="#f2b630" stroke-opacity=".6"><title>${esc(this.t("horizon_limit"))}</title></path>`);
    }
    if (minAlt > 0) parts.push(`<circle cx="${C}" cy="${C}" r="${((90 - minAlt) / 90) * R}" fill="none" stroke="#f2b630" stroke-opacity=".5" stroke-dasharray="4 4"><title>${esc(this.t("horizon_limit"))}</title></circle>`);
    for (const [label, az] of [[this.t("north"), 0], [this.t("east"), 90], [this.t("south"), 180], [this.t("west"), 270]]) {
      const [x, y] = proj(-8, az);
      parts.push(`<text x="${x}" y="${y + 4}" font-size="13" text-anchor="middle" fill="currentColor" fill-opacity=".8">${esc(label)}</text>`);
    }
    const placed = [];
    const plot = (alt, az, color, label, size) => {
      if (alt === null || alt === undefined || alt < 0) return;
      const [x, y] = proj(alt, az);
      parts.push(`<circle cx="${x}" cy="${y}" r="${size}" fill="${color}"><title>${esc(label)} · ${Math.round(alt)}°</title></circle>`);
      // Skip labels that would overlap an existing one.
      if (placed.some(([px, py]) => Math.abs(px - x) < 46 && Math.abs(py - y) < 12)) return;
      placed.push([x, y]);
      parts.push(`<text x="${x + size + 3}" y="${y + 4}" font-size="10.5" fill="#fff" fill-opacity=".9">${esc(label)}</text>`);
    };
    if (s.moon_az) plot(s.moon_alt[idx], s.moon_az[idx], MOON_COLOR, this.t("moon"), 7);
    for (const p of night.planets || []) {
      if (p.kind === "planet" && p.alt && p.az) plot(p.alt[idx], p.az[idx], PLANET_COLOR, p.name, 4.5);
    }
    for (const o of (night.objects || []).slice(0, 12)) {
      if (o.alt && o.az) plot(o.alt[idx], o.az[idx], DEEP_COLOR, (o.name || "").split(" – ")[0], 3.5);
    }
    const time = new Date(t0 + idx * step).toISOString();
    return `<div class="section-title">${esc(this.t("sky_time"))} ${esc(this.fmtDateTime(time))}</div>
      <svg class="skymap" viewBox="0 0 ${2 * C} ${2 * C}" role="img" aria-label="${esc(this.t("sky"))}" style="color:var(--primary-text-color)">${parts.join("")}</svg>
      <input type="range" id="skyrange" min="0" max="${n - 1}" value="${idx}" aria-label="${esc(this.t("sky_time"))}">`;
  }

  /* ---------------------------------------------------------- events -- */

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach((el) =>
      el.addEventListener("click", () => {
        this._tab = el.dataset.tab;
        this._render();
      }),
    );
    root.getElementById("health")?.addEventListener("click", () => {
      this._showProviders = !this._showProviders;
      this._render();
    });
    root.getElementById("nightmode")?.addEventListener("click", () => this._toggleNightMode());
    root.querySelectorAll("[data-night]").forEach((el) =>
      el.addEventListener("click", () => {
        this._nightIndex = Number(el.dataset.night);
        this._inspect = null;
        this._render();
      }),
    );
    root.querySelectorAll("[data-open-night]").forEach((el) => {
      const open = () => {
        const idx = Number(el.dataset.openNight);
        if (!this._data.nights[idx].samples) return;
        this._nightIndex = idx;
        this._inspect = null;
        this._tab = "tonight";
        this._render();
      };
      el.addEventListener("click", open);
      el.addEventListener("keydown", (ev) => (ev.key === "Enter" || ev.key === " ") && open());
    });
    root.querySelectorAll("[data-filter]").forEach((el) =>
      el.addEventListener("click", () => {
        this._filter = el.dataset.filter;
        this._render();
      }),
    );
    root.querySelectorAll("[data-detail]").forEach((el) => {
      const toggle = (ev) => {
        if (ev.target.closest("[data-fav]")) return;
        const id = el.dataset.detail;
        if (this._expanded.has(id)) this._expanded.delete(id);
        else this._expanded.add(id);
        this._render();
      };
      el.addEventListener("click", toggle);
      el.addEventListener("keydown", (ev) => (ev.key === "Enter" || ev.key === " ") && toggle(ev));
    });
    root.querySelectorAll("[data-fav]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const add = el.dataset.state !== "1";
        el.dataset.state = add ? "1" : "0";
        el.textContent = add ? "★" : "☆";
        el.classList.toggle("on", add);
        this._toggleFavorite(el.dataset.fav, add);
      }),
    );
    root.querySelectorAll("[data-event]").forEach((el) => {
      const toggle = () => {
        const id = el.dataset.event;
        if (this._expandedEvents.has(id)) this._expandedEvents.delete(id);
        else this._expandedEvents.add(id);
        this._render();
      };
      el.addEventListener("click", toggle);
      el.addEventListener("keydown", (ev) => (ev.key === "Enter" || ev.key === " ") && toggle());
    });
    const search = root.getElementById("search");
    if (search) {
      let timer = null;
      search.addEventListener("input", (ev) => {
        clearTimeout(timer);
        const value = ev.target.value;
        this._search = value;
        timer = setTimeout(() => this._runSearch(value), 250);
      });
    }
    const range = root.getElementById("skyrange");
    if (range) {
      range.addEventListener("input", (ev) => {
        this._skyIndex = Number(ev.target.value);
        this._render(true);
      });
    }
    const svg = root.getElementById("timeline");
    if (svg) {
      const night = this._data.nights[this._nightIndex];
      const n = night?.samples?.deep_sky.length || 0;
      const pick = (ev) => {
        const rect = svg.getBoundingClientRect();
        const ratio = (ev.clientX - rect.left) / rect.width;
        const idx = Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1))));
        if (idx !== this._inspect) {
          this._inspect = idx;
          this._render();
        }
      };
      svg.addEventListener("click", pick);
      svg.addEventListener("pointermove", (ev) => ev.pointerType === "mouse" && pick(ev));
    }
  }
}

/* ----------------------------------------------------------------- card -- */

class AstroCastCard extends AstroCastView {
  static getConfigElement() {
    return document.createElement("astrocast-card-editor");
  }

  static getStubConfig() {
    return { type: "custom:astrocast-card" };
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    if (this._config.default_tab && TABS.includes(this._config.default_tab)) this._tab = this._config.default_tab;
    if (this._hass) this._subscribe(this._config.entry_id);
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._subscribe(this._config?.entry_id);
    if (first) this._render();
  }

  connectedCallback() {
    super.connectedCallback();
    if (this._hass) this._subscribe(this._config?.entry_id);
  }

  getCardSize() {
    return this._config?.view === "compact" ? 3 : 9;
  }

  getGridOptions() {
    return this._config?.view === "compact"
      ? { columns: 6, min_columns: 6, rows: 3 }
      : { columns: 12, min_columns: 6, rows: "auto" };
  }

  _wrap(inner) {
    return `<ha-card>${inner}</ha-card>`;
  }
}

/* ---------------------------------------------------------------- panel -- */

class AstroCastPanel extends AstroCastView {
  constructor() {
    super();
    this._sites = null;
    this._entryId = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._loadSites();
  }

  set narrow(value) {
    this._narrow = value;
  }

  set panel(value) {
    this._panel = value;
  }

  async _loadSites() {
    try {
      this._sites = await this._hass.callWS({ type: "astrocast/sites" });
    } catch (err) {
      this._error = err?.message || String(err);
      this._sites = [];
    }
    if (!this._sites.length) {
      this._error = this.t("no_site");
      this._render();
      return;
    }
    let stored = null;
    try {
      stored = window.localStorage.getItem("astrocast-panel-site");
    } catch (_e) {
      stored = null;
    }
    this._entryId = this._sites.some((s) => s.entry_id === stored) ? stored : this._sites[0].entry_id;
    this._subscribe(this._entryId);
    this._render();
  }

  connectedCallback() {
    super.connectedCallback();
    if (this._hass && this._entryId) this._subscribe(this._entryId);
  }

  get _isPanel() {
    return true;
  }

  _wrap(inner) {
    const sites =
      this._sites && this._sites.length > 1
        ? `<div class="nightsel" style="padding:12px 16px 0">${this._sites
            .map((s) => `<button class="chip" data-site="${esc(s.entry_id)}" aria-pressed="${s.entry_id === this._entryId}">${esc(s.title)}</button>`)
            .join("")}</div>`
        : "";
    const menu = `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px 0">
      <button class="iconbtn" id="menu" aria-label="Menu" style="display:${this._narrow ? "inline-flex" : "none"}"><svg width="24" height="24" viewBox="0 0 24 24"><path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z" fill="currentColor"/></svg></button></div>`;
    return `<div class="panel" style="max-width:1100px;margin:0 auto;background:var(--primary-background-color);min-height:100vh">${menu}${sites}<div style="background:var(--card-background-color);margin:12px;border-radius:var(--ha-card-border-radius,12px)">${inner}</div></div>`;
  }

  _bind() {
    super._bind();
    this.shadowRoot.querySelectorAll("[data-site]").forEach((el) =>
      el.addEventListener("click", () => {
        this._entryId = el.dataset.site;
        try {
          window.localStorage.setItem("astrocast-panel-site", this._entryId);
        } catch (_e) {
          /* storage unavailable */
        }
        this._data = null;
        this._nightIndex = 0;
        this._subscribe(this._entryId);
        this._render();
      }),
    );
    this.shadowRoot.getElementById("menu")?.addEventListener("click", () =>
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true })),
    );
  }
}

/* --------------------------------------------------------------- editor -- */

class AstroCastCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      hass
        .callWS({ type: "astrocast/sites" })
        .then((sites) => {
          this._sites = sites;
          this._render();
        })
        .catch(() => {
          this._sites = [];
          this._render();
        });
    }
  }

  get lang() {
    const raw = this._hass?.locale?.language || "en";
    return raw.toLowerCase().startsWith("fr") ? "fr" : "en";
  }

  t(key) {
    return STRINGS[this.lang][key] || STRINGS.en[key] || key;
  }

  _render() {
    if (!this._config) return;
    const sites = this._sites || [];
    const view = this._config.view === "compact" ? "compact" : this._config.default_tab || "tonight";
    const nightValue = this._config.night_mode;
    const night = nightValue === true || nightValue === "on" ? "on" : nightValue === "auto" ? "auto" : "toggle";
    this.innerHTML = `<div style="display:grid;gap:12px;padding:4px 0">
      <label style="display:grid;gap:4px">${esc(this.t("editor_site"))}
        <select id="site" style="padding:8px;border-radius:6px">
          <option value="">${esc(this.t("editor_auto"))}</option>
          ${sites.map((s) => `<option value="${esc(s.entry_id)}" ${s.entry_id === this._config.entry_id ? "selected" : ""}>${esc(s.title)}</option>`).join("")}
        </select></label>
      <label style="display:grid;gap:4px">${esc(this.t("editor_view"))}
        <select id="view" style="padding:8px;border-radius:6px">
          ${TABS.map((tab) => `<option value="${tab}" ${view === tab ? "selected" : ""}>${esc(this.t(tab))}</option>`).join("")}
          <option value="compact" ${view === "compact" ? "selected" : ""}>${esc(this.t("editor_compact"))}</option>
        </select></label>
      <label style="display:grid;gap:4px">${esc(this.t("editor_night"))}
        <select id="night" style="padding:8px;border-radius:6px">
          ${[
            ["toggle", "editor_night_toggle"],
            ["on", "editor_night_on"],
            ["auto", "editor_night_auto"],
          ]
            .map(([value, key]) => `<option value="${value}" ${night === value ? "selected" : ""}>${esc(this.t(key))}</option>`)
            .join("")}
        </select></label>
    </div>`;
    this.querySelector("#site").addEventListener("change", (ev) => {
      const config = { ...this._config };
      if (ev.target.value) config.entry_id = ev.target.value;
      else delete config.entry_id;
      this._emit(config);
    });
    this.querySelector("#night").addEventListener("change", (ev) => {
      const config = { ...this._config };
      delete config.night_mode;
      if (ev.target.value !== "toggle") config.night_mode = ev.target.value;
      this._emit(config);
    });
    this.querySelector("#view").addEventListener("change", (ev) => {
      const config = { ...this._config };
      delete config.view;
      delete config.default_tab;
      if (ev.target.value === "compact") config.view = "compact";
      else if (ev.target.value !== "tonight") config.default_tab = ev.target.value;
      this._emit(config);
    });
  }

  _emit(config) {
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }
}

if (!customElements.get("astrocast-card")) customElements.define("astrocast-card", AstroCastCard);
if (!customElements.get("astrocast-panel")) customElements.define("astrocast-panel", AstroCastPanel);
if (!customElements.get("astrocast-card-editor")) customElements.define("astrocast-card-editor", AstroCastCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "astrocast-card")) {
  window.customCards.push({
    type: "astrocast-card",
    name: "AstroCast",
    description: "Observing conditions, best windows, objects and events for your sky.",
    preview: true,
    documentationURL: "https://github.com/FigurinePanda43/AstroCast",
  });
}

console.info(`%c ASTROCAST %c ${VERSION} `, "background:#6c7cff;color:#fff;border-radius:3px 0 0 3px", "background:#222;color:#fff;border-radius:0 3px 3px 0");
