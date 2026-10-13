# Data sources, libraries and licences

AstroCast only uses free services that do not require an account or an API key. All
requests identify the integration with the User-Agent
`AstroCast/<version> (+https://github.com/FigurinePanda43/AstroCast)`.

## Weather and atmosphere

| Service | Endpoint | Data | Terms / licence | Refresh |
| --- | --- | --- | --- | --- |
| **7Timer!** (Ye Quanzhi) | `www.7timer.info/bin/api.pl?product=astro` | 3-hourly cloud cover, seeing, transparency, lifted index, humidity, wind, temperature, precipitation type — 72 h, from NOAA GFS | Free public service; please keep the request rate low. Attribution: "7Timer!" | every 3 h |
| **Open-Meteo** forecast | `api.open-meteo.com/v1/forecast` | hourly clouds by layer, humidity, dew point, temperature, wind and gusts, precipitation and probability, visibility, 250 hPa wind, lifted index — 16 days | Free for non-commercial use, < 10 000 requests/day; data **CC BY 4.0** | every hour |
| **Open-Meteo** ensemble | `ensemble-api.open-meteo.com/v1/ensemble` (`ecmwf_ifs025`, fallback `gfs025`) | cloud cover of each member — 15 days | same; ECMWF open data | every 6 h |
| **Open-Meteo** air quality | `air-quality-api.open-meteo.com/v1/air-quality` | aerosol optical depth at 550 nm, dust — 5 days (Copernicus CAMS) | same; contains modified Copernicus Atmosphere Monitoring Service information | every 6 h |
| **Open-Meteo** elevation | `api.open-meteo.com/v1/elevation` | ground elevation (Copernicus GLO-90 DEM) | same | once, during setup |
| **MET Norway** Locationforecast 2.0 | `api.met.no/weatherapi/locationforecast/2.0/complete` | fallback forecast (~10 days) | Free; identifying User-Agent required; data **CC BY 4.0** (MET Norway) | hourly, only while Open-Meteo is unavailable |

About 40 requests are made per site per day in normal operation (plus two shared JPL requests).

## Astronomy

| Source | Use | Licence |
| --- | --- | --- |
| **astronomy-engine** 2.1.19 (Don Cross) | Sun, Moon and planet positions, eclipses, phases, apsides, constellations | MIT |
| **NASA/JPL Small-Body Database** query API (`ssd-api.jpl.nasa.gov/sbdb_query.api`) | Orbits of comets with a perihelion within ±13 months and of asteroids with H < 7.5 (a < 4.2 AU) | Public U.S. Government data |
| **OpenNGC** (Mattia Verga) | 635-object deep-sky catalog bundled in `data/dso_catalog.json` | CC BY-SA 4.0 — the derived file keeps that licence, see `data/LICENSE-catalog.md` |
| **IMO** meteor shower calendar | Solar longitude of maximum, ZHR, radiant, velocity, population index of 13 major showers | Factual data |
| Krisciunas & Schaefer (1991), PASP 103, 1033 | Moonlight sky-brightness model | Published model |

## Software dependencies

| Package | Why | Licence |
| --- | --- | --- |
| `astronomy-engine` | Ephemerides (pure Python, no binary wheels needed — works on every architecture) | MIT |
| `numpy` | Vectorised computations (already part of Home Assistant installations) | BSD-3-Clause |

## Why these choices

* **astronomy-engine instead of Skyfield/Astropy:** comparable accuracy for observation
  planning (±1′), no ephemeris file to download (Skyfield needs a 17 MB+ JPL kernel), pure
  Python (no compilation on ARM/musl), MIT licence. Astropy/Astroplan are far too heavy for a
  Home Assistant host.
* **Open-Meteo as the main weather source:** a single free API giving the best available
  high-resolution models for the location (e.g. AROME 1.3 km over France), up to 16 days, plus
  ensembles and aerosols. 7Timer! is kept for its astronomy-specific seeing and transparency.
* **Ensembles for the long range:** deterministic cloud forecasts beyond a week are mostly noise;
  the share of clear members is an honest probability.
