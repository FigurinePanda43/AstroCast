# Deep-sky catalog licence

`dso_catalog.json` is derived from **OpenNGC** — "A license friendly NGC/IC
objects database" — by Mattia Verga: <https://github.com/mattiaverga/OpenNGC>.

OpenNGC is released under the
[Creative Commons Attribution-ShareAlike 4.0 International licence](https://creativecommons.org/licenses/by-sa/4.0/)
(CC BY-SA 4.0). In accordance with that licence:

* **Attribution** — data © Mattia Verga and OpenNGC contributors.
* **Changes made** — subset selection (Messier, Caldwell, NGC/IC objects brighter
  than V≈10 and named nebulae), coordinate conversion to decimal degrees,
  type normalisation, Caldwell cross-identifications, curated English and French
  common names, and a single magnitude correction (NGC 6882 / C 37).
* **ShareAlike** — `dso_catalog.json` is distributed under CC BY-SA 4.0.

The file is regenerated with `scripts/build_catalog.py`. The rest of AstroCast
(source code) is distributed under the MIT licence.
