"""Data providers (HTTP clients and parsers).

Every provider is free, keyless and documented in docs/data-sources.md:

* 7Timer! ASTRO (GFS based astronomical forecast, 72 h, 3-hourly).
* Open-Meteo forecast (best-match national/global models, 16 days, CC BY 4.0).
* Open-Meteo ensemble (ECMWF IFS 51 members, 15 days) for probabilities.
* Open-Meteo air quality (CAMS aerosol optical depth, 5 days).
* MET Norway Locationforecast (fallback, ~10 days, CC BY 4.0).
* JPL Small-Body Database query API (comet and asteroid orbits).
"""
