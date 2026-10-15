# How AstroCast computes its forecasts

This page documents every computation so that each number shown by AstroCast can be
understood and challenged. Source code references are given in `code` style.

## 1. Nights and astronomy

* A **night** runs from local mean solar noon to the next noon (`engine/timeutil.py`). This
  definition works everywhere, including polar regions, and does not depend on political time
  zones. Each night is sampled every 15 minutes, aligned on whole quarter hours.
* **Tonight** is the night containing the current moment until sunrise, then the coming night
  (`Planner.current_night`): in the morning, sensors and the card already describe the next
  evening. Without a sunrise (polar day or night) the change happens at local mean solar noon.
* Positions of the Sun, Moon and planets come from **astronomy-engine** (VSOP87 / ELP-based,
  ±1′ against JPL DE ephemerides), topocentric, with aberration and nutation. To stay fast
  on small ARM boards, exact positions are computed every 4 h (Sun), 1 h (Moon) or 12 h
  (planets) and interpolated; the tests check that interpolated altitudes stay within 0.02°
  and twilight/rise/set instants within a few seconds of exact searches.
* Twilights use the geometric altitude of the Sun's centre: civil −6°, nautical −12°,
  astronomical −18°; sunrise/sunset use −0.833° (refraction + semi-diameter).
* Deep-sky positions (J2000, OpenNGC) are precessed to the date and converted to
  altitude/azimuth with numpy for all 635 objects at once; refraction uses Sæmundsson's
  formula.
* Comets and asteroids: osculating elements from the JPL Small-Body Database, propagated with a
  universal-variable Kepler solver (any eccentricity), light-time corrected, topocentric.
  Validated against JPL Horizons to better than 2′ (planetary perturbations are ignored, so
  orbits are refreshed daily and old orbit solutions are flagged).
  Magnitudes: `H + 5 log10(rΔ) − 2.5 log10((1−G)Φ1 + GΦ2)` for asteroids,
  `M1 + 5 log10 Δ + K1 log10 r` for comets (always labelled as an estimate).

## 2. Weather fusion

Each provider returns a time series; they are merged hour by hour (`engine/weather.py`):

| Quantity | Priority |
| --- | --- |
| Cloud cover (total, low/mid/high), humidity, dew point, wind, gusts, precipitation | Open-Meteo → MET Norway → 7Timer! |
| Seeing | 7Timer! ASTRO (72 h) → jet-stream proxy (250 hPa wind) |
| Transparency (V extinction *k*, mag/airmass) | CAMS aerosol optical depth → 7Timer! transparency class |
| Clear-sky probability | ECMWF ensemble: share of members with < 25 % cloud |

* **Transparency from aerosols:** `k = 1.086 · (τ_Rayleigh + τ_ozone + τ_aerosol)` with
  τ_Rayleigh = 0.0973·exp(−h/8.4 km) at 550 nm and τ_ozone ≈ 0.016.
* **Seeing proxy:** strong jet-stream winds generate high-altitude turbulence. Beyond the
  7Timer! range the 250 hPa wind is mapped to a rough seeing value (1.0″ when calm, 2.1″ at
  130 km/h, 3.2″ at 250 km/h). It is flagged `source: jetstream` and only used to rank nights.
* **Forecast tiers:** `detailed` (≤ 72 h), `forecast` (≤ 7 days), `trend` (> 7 days).
  In the trend tier the cloud factor is the **expectation over the ensemble members**
  (a night with 50 % of clear members scores about half of its clear-sky potential): this is
  a probability, not a deterministic forecast, and the UI shows the clear-sky chance instead
  of a cloud amount.
* **Confidence** (0–1) decreases with lead time and with the ensemble spread; it is shown as
  high (≥ 0.7), medium (≥ 0.45) or low.
* Each provider has its own refresh interval, exponential back-off on errors, a persistent cache
  (no new requests after a restart if data is fresh) and a maximum age after which its data is
  discarded rather than shown.

## 3. Scores

For every 15-minute sample, the score is

```
score = 100 × clouds × precipitation × darkness × moon × transparency × seeing × wind × humidity × dew
```

Each factor is in [0, 1]. A product means that one fatal limitation (overcast, daylight, rain)
is enough to make the score zero, which matches the experience of observers. The factor with
the lowest average over the best window is reported as the **limiting factor**.

Three profiles are computed: **deep sky** (visual or broadband imaging of faint objects),
**planetary** (Moon, planets, double stars) and **narrowband** (emission nebulae imaged
through 3–7 nm Hα, OIII or SII filters).

| Factor | Deep sky | Planetary | Narrowband |
| --- | --- | --- | --- |
| Clouds *c* | (1 − c)^1.6 | (1 − c)^1.1 (planets show through gaps) | as deep sky |
| Precipitation | 0 if rain ≥ 0.2 mm/h, reduced with rain probability > 20 % | same | same |
| Darkness (Sun altitude) | 1 below −18°, 0.55 at −15°, 0 above −12° | 1 below −8°, 0 above −1° | 1 below −15°, 0.6 at −12°, 0 above −10° |
| Moon | 10^(−0.2 Δm) (see below) | 1 | 10^(−0.2 × 0.25 Δm) |
| Transparency *k* | 10^(−0.4·max(0, k − 0.15)·1.3) | same ^0.4 | same ^0.8 |
| Seeing | table (1.0 at 0.8″, 0.78 at 1.5″, 0.6 at 2″, 0.3 at 3″) ^0.35 | same table | as deep sky |
| Wind (max of wind, 0.6 × gusts) | 1 up to 12 km/h, 0.7 at 30, 0.22 at 55 | same ^0.8 | as deep sky |
| Humidity / fog | 1 up to 85 %, 0.82 at 95 %, 0.68 at 100 %; fog reduces it further | same | same |
| Dew (see below) | 1 with a margin ≥ 3 °C, 0.3 once dew has formed (without heaters) | same | same |

**Narrowband.** A narrowband filter passes the emission lines of the nebula but only a few
nanometres of the moonlit (continuum) sky, so the moonlight brightening counts for a quarter
of its deep-sky weight, and imaging can start at the end of nautical twilight. Broadband
targets (galaxies, clusters, reflection nebulae) still need the deep-sky score.

**Dew.** Optics exposed to a clear, calm sky cool by radiation about 2 °C below the air.
The *optics margin* is `(T − Td) − 2 °C × clear fraction × calm factor` (calm factor 1 without
wind, 0 from 15 km/h). Dew forms on unprotected optics when the margin drops below 0.5 °C;
from that moment the rest of the night gets a 0.3 factor (wet optics, the session is over).
Before that, a shrinking margin costs a little (0.97 at 2 °C, 0.9 at 1 °C). With the *dew
heaters* option, there is no onset: the factor only drops to 0.95 at a zero margin and 0.85
at −2 °C (saturated, hazy air). The night summary gives the expected onset time and the
lowest margin; the dew risk sensor gives the current level (high ≤ 0.5 °C, moderate ≤ 2 °C).

**Moonlight.** The sky brightening Δm (mag/arcsec²) caused by the Moon is computed with the
Krisciunas & Schaefer (1991) model from the lunar phase angle, the Moon–target separation, both
zenith distances and the extinction coefficient, relative to the natural sky brightness of the
site (Bortle class or measured SQM). For a sky-limited observation the signal-to-noise ratio at
a fixed exposure scales with √(B_dark / B_total), hence the factor 10^(−0.2 Δm). Consequences:
a full Moon high in the sky costs ~3 magnitudes at a dark site but much less under a
light-polluted sky, which is physically correct. The night score uses the zenith; object scores
use the object's own position.

**Ratings:** excellent ≥ 75, good ≥ 55, fair ≥ 35, poor ≥ 15, bad below.

### Night score and windows

* The **night score** is the value of the best continuous **session**: over every window of
  the usable darkness, `mean score × duration factor(length)`, and the best window wins.
  Long exposures need long windows, so a two-hour clearing is not a good night:

  | Session length | 1 h | 2 h | 3 h | 4 h | 5 h | 6 h |
  | --- | --- | --- | --- | --- | --- | --- |
  | Deep sky / narrowband | 0.35 | 0.6 | 0.78 | 0.9 | 0.97 | 1 |
  | Planetary | 0.7 | 0.92 | 1 | 1 | 1 | 1 |

  A session only spans samples worth at least half of the night's best level (90th
  percentile), with dips of up to 30 minutes bridged (a passing cloud), so it cannot gain
  length with clouded or dewed-up hours. When part of the night is beyond the forecast range,
  the duration factor is normalised by the known hours, so missing data is not mistaken for
  a short window. When the duration factor is the weakest factor, the limiting factor is
  reported as `duration` ("short window").
* The **best window** is that session (reported when its mean score is at least 35), with its
  length (`window_hours`), its mean quality (`window_quality`) and its duration factor.
* **Good hours** counts the samples above your threshold.
* **Potential** is the same computation assuming a clear sky with average transparency and
  seeing: it is used beyond the weather horizon (dark-sky planning) and drawn as a faint curve.

## 4. Objects

For each object and sample:

```
object score = 100 × sky factors × altitude factor × moon factor at the object
```

* **Altitude factor:** 0 below your minimum altitude or below the local horizon profile at the
  object's azimuth (linear interpolation between your `azimuth:altitude` points); above it, the extinction loss
  10^(−0.2 (k + 0.1)(X − 1)) with the Kasten & Young airmass X. For planets and the Moon the
  seeing is degraded with altitude (FWHM ∝ X^0.6).
* **Moon sensitivity** depends on the object type (1 for galaxies and nebulae, 0.45 for open
  clusters, 0.2 for double stars).
* **Appeal** (0–1) combines brightness against what your equipment can show (limiting magnitude
  from 6.0 naked eye to 15 for imaging, reduced under light pollution; extended objects are
  penalised by their surface brightness), the affinity between object type and equipment, and
  how classic the target is (Messier/Caldwell/named).
* **Interest** = best object score × appeal × duration factor. An object is **recommended**
  only if interest ≥ 30 and its best score ≥ 35; this is what separates an object that is
  merely above the horizon from one that is worth observing tonight.
* Reasons are attached (high in the sky, Moon below the horizon, moonlight interference, near
  opposition, evening/morning sky, steady air, faint for your equipment, short window, estimated
  brightness…).

Favourites are evaluated on every forecast night; the next favourable window is the first
covered by the weather forecast whose best score reaches your threshold.

## 5. Events

| Event | Method |
| --- | --- |
| Lunar phases, supermoons | Exact quarter search; supermoon when a full Moon is closer than 360 000 km |
| Lunar eclipses | Kind, obscuration and contacts; visible when the Moon is above the horizon during the eclipse |
| Solar eclipses | Local circumstances (partial/annular/total, obscuration, totality times) |
| Oppositions | Superior planets, exact search |
| Greatest elongations | Mercury and Venus, with the best viewing time and altitude at your site |
| Conjunctions | Moon–planet, Moon–bright star/cluster (Aldebaran, Regulus, Spica, Antares, Pleiades, Beehive) and planet–planet minima of geocentric separation, refined to the minute; best visible time in a dark sky |
| Occultations | Topocentric minimum separation smaller than the lunar radius (+ planet radius) |
| Meteor showers | IMO list (13 major showers); peak from the solar longitude every year; expected hourly rate `HR = ZHR · sin(h_radiant) / r^(6.5 − LM)` where the limiting magnitude LM comes from your sky brightness and the Moon |
| Equinoxes, solstices | Exact |
| Comets | Perihelion passages of comets predicted brighter than magnitude 10 |

## 6. Known limitations

* Weather forecasts — especially cloud cover more than a few days ahead — are uncertain; the
  tiers and confidence are there to remind it.
* 7Timer! seeing is itself a model output (from GFS); the jet-stream proxy is coarse.
* No light-pollution map and no satellite pass predictions yet; the horizon profile is a
  simple polyline.
