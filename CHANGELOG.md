# Changelog

All notable changes to AstroCast are documented here. The project follows
[semantic versioning](https://semver.org/); 0.x releases are beta releases.

## [0.3.0] – 2026-10-28

### Added
- **Local weather station.** Optional temperature and humidity sensors (options): the current
  conditions and the dew risk use your measurements, and the forecast temperature and dew
  point of the next hours are corrected by the current error, fading out over about 6 hours.
  The dew onset and the dew penalty of tonight's scores follow your garden rather than the
  model grid. Fahrenheit and kelvin sensors are converted; a sensor more than 8 °C away from
  the forecast or silent for 90 minutes is ignored. The dew risk sensor, the card and the
  diagnostics show the measurement and the forecast error.

## [0.2.0] – 2026-10-15

### Changed
- **Night scores reward long sessions.** A night is now judged on its best continuous session
  (mean score × a duration factor: full value at 6 h for deep sky and narrowband, at 3 h for
  planetary), instead of its best 3-hour block. A short clearing (e.g. 21:00–23:00) no longer
  rates as a good night, and "short window" is reported as the limiting factor. Scores of
  nights with short or broken windows are lower than in 0.1.x.
- **Dew is part of the scores.** From the predicted dew onset on unprotected optics, the rest
  of the night is heavily penalised. If your optics have dew heaters, enable the new
  *dew heaters* option (Configure): dew then only costs a little.

### Added
- **Narrowband profile** for emission nebulae through Hα/OIII/SII filters, much less sensitive
  to the Moon: *Narrowband tonight* and *Narrowband now* sensors, narrowband score in the card
  and the nights list, and calendar windows on nights that only suit narrowband imaging.
- **Dew sensors**: *Dew risk* (now, with the optics margin to the dew point) and *Dew expected
  tonight* (time of onset). The onset is also shown in the card, the night attributes and the
  calendar windows.
- **Red night-vision mode** for the card and the panel: a button in the header (remembered per
  device), or the `night_mode: on | auto` card option. Everything is drawn in pure red on black.
- **Automation blueprints**: observing window ahead, tonight's briefing (English/French),
  favourite object well placed, astronomical event (keyword filter), dew heaters.
- Window length and quality in the sensor attributes, the card, the calendar descriptions and
  the `get_forecast` response; the favourite sensors expose the object `name`.

## [0.1.1] – 2026-10-14

### Fixed
- "Tonight" now switches to the coming night at sunrise instead of local solar noon: in the
  morning, the tonight sensors, favourites, calendars and the card no longer describe the night
  that has just ended (automations run in the morning now see the right night).

## [0.1.0] – 2026-10-14

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
- Local horizon profile (obstacles by azimuth) used for object visibility and drawn on the sky map.
