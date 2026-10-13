# Changelog

All notable changes to AstroCast are documented here. The project follows
[semantic versioning](https://semver.org/); 0.x releases are beta releases.

## [0.1.0] – 2026-10-13

First public beta.

### Added
- Config flow with an interactive map, automatic elevation lookup, observing preferences
  (Bortle class or SQM, equipment, minimum altitude, threshold), reconfigure and options flows,
  multiple sites.
- Weather fusion of 7Timer! ASTRO, Open-Meteo (forecast, ECMWF ensemble, CAMS aerosols) and
  MET Norway (fallback), with forecast tiers, confidence, back-off and persistent cache.
- Local astronomy: Sun/Moon/planet ephemerides, twilights, moonlight sky brightness, 635-object
  deep-sky catalog (OpenNGC), comets and bright asteroids from JPL orbits.
- Explainable deep-sky and planetary scores, best windows, night outlook up to 15 days and
  dark-sky potential up to 30 days.
- Object recommendations with reasons, favourites with their next favourable window.
- Events: lunar phases and supermoons, eclipses, oppositions, elongations, conjunctions, lunar
  occultations, meteor showers with expected rates, equinoxes/solstices, bright comets.
- Sensors, binary sensors, calendars, actions with responses, websocket API, diagnostics,
  English and French translations.
- Lovelace card and sidebar panel registered automatically.
