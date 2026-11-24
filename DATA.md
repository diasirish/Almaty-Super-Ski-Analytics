# DATA

**Almaty SuperSki ski terrain analytics — where every number comes from**
Dias Irishev · Geo & Weather Data Scientist, Almaty
Release date: 24 November 2026

This file is the provenance record: every dataset that enters the analysis, the
endpoint it was fetched from, its resolution and epoch, the projection and datum
it arrives in, its licence, and what it costs you to rely on it. `METHODS.md` is
the other half — what is *done* with these data, with every threshold and
formula. The study area they are read over is section 10, deliberately last: the
data stand on their own, and the boundary can be redrawn without touching any of
them.

Everything here is open. **No account, no licence fee and no commercial data are
used anywhere in this release.** Two of the eleven sources need a free
registration and were catalogued rather than used (section 8); the rest are
anonymous.

---

## 1. At a glance

| Source | Role | Resolution | What was read |
|---|---|---|---|
| **Copernicus DEM GLO-30** | terrain, primary | 30 m | 2 tiles |
| **Sentinel-2 L2A** | snow, primary | 10–20 m | **115 scenes**, 112 dates, 4 complete seasons |
| **Landsat 8/9 C2 L2** | snow, independent cross-check | 30 m → 20 m | **77 scenes** |
| **MODIS MOD10A1 / MYD10A1 v061** | daily snow context | 500 m | 80 granules, 46 usable days |
| **NASADEM** | elevation cross-check | 30 m | whole chain rebuilt on it |
| **ALOS World 3D-30m** | elevation cross-check | 30 m | whole chain rebuilt on it |
| **OpenStreetMap** | existing lifts, pistes, place names | vector | 642 elements, one Overpass query |
| **ERA5-Land / ERA5** | meteorological context | ~9 km / ~31 km | daily, 2022-11-01 → 2026-04-30 |
| Kazhydromet seasonal outlook | published forecast, transcribed | oblast | 1 bulletin |
| C3S seasonal forecast | published forecast, transcribed | global | 1 issue |
| Kazakh Tourism Development | the operator's own published figures | — | board release + general-plan sheet |

Five further sources were catalogued, costed and **not** used; section 8 says
why. The machine-readable version of the whole registry, with endpoints and the
cost of each, is `outputs/cluster/tables/data_source_registry.csv` — **12
entries, 7 used**.

---

## 2. Coordinate systems and datums

Mixing these up is the most common way a terrain study goes quietly wrong, so
they are stated once here and asserted in code.

| Where | CRS | Note |
|---|---|---|
| The drawn boundary, every bounding box, all catalogue queries | **EPSG:4326** (WGS84 lon/lat) | `CRS_WGS84` in `config.py` |
| Every analysis grid and every published GeoTIFF | **EPSG:32643** (UTM zone 43N) | `CRS_UTM`; metric, so 30 m means 30 m |
| Copernicus DEM GLO-30 vertical datum | **EGM2008** | the primary DEM |
| NASADEM and ALOS AW3D30 vertical datum | **EGM96** | a real offset against GLO-30, and part of why their median differences are +0.4 m and +2.1 m rather than zero |
| Sentinel-2 and Landsat native | EPSG:32643 | the same zone as the analysis, so windowed reads need no warp |
| MODIS native | **sinusoidal** | the one source that is not UTM, and the one that caught a bug (section 4.3) |

**Why UTM 43N and not a geographic grid.** Slope, aspect, horizon angles and
areas are all metric quantities. Computing them on degrees would make a cell
1.4× longer east–west than north–south at this latitude and silently bias every
slope. Aspect is computed *after* projection, so the ~1.4° meridian convergence
at 77° E is already removed and aspect is degrees clockwise from **true** north.

**Grid construction.** An analysis grid is the axis-aligned UTM bounding box of
its WGS84 rectangle, snapped outward to whole cells, with each edge of the
rectangle densified to 200 points before projection so the curved projected
edges are captured rather than only the four corners.

**Reprojection.** DEM tiles are warped to EPSG:32643 by bilinear resampling.
Sentinel-2 and Landsat windows are read directly in the target CRS. Terrain and
insolation are resampled 30 m → 20 m bilinearly where they must meet the snow
grid, except **aspect, which is interpolated as a unit vector** (sin/cos
components) to avoid the 0°/360° wrap.

---

## 3. Terrain

### 3.1 Copernicus DEM GLO-30 — the primary DEM

| | |
|---|---|
| Product | Copernicus DEM GLO-30, 1 arc-second (~30 m) |
| Tiles | `Copernicus_DSM_COG_10_N43_00_E076_00_DEM`, `Copernicus_DSM_COG_10_N43_00_E077_00_DEM` |
| Endpoint | `https://copernicus-dem-30m.s3.amazonaws.com` (AWS Open Data registry) |
| Access | anonymous HTTPS, no account |
| Sensor and epoch | TanDEM-X radar, 2010–2015 |
| Vertical datum | EGM2008 |
| Size on disk | 73 MB for the two tiles |
| Licence | Copernicus DEM open licence; © DLR e.V. 2010–2014, © Airbus Defence and Space GmbH 2014–2018 |

It is a **digital surface model**, not a terrain model: it includes forest
canopy and buildings. In this release that matters most in the forested lower
bands, where it slightly raises the surface and steepens local slope.

A second copy is built on a grid buffered by **6 km** so the horizon ray-march
has terrain to hit beyond the window edge. Without it, every pixel near the edge
would see an artificially open sky.

### 3.2 NASADEM and ALOS AW3D30 — the elevation cross-check

| | NASADEM | ALOS World 3D-30m |
|---|---|---|
| Collection | `nasadem` | `alos-dem` |
| Endpoint | `https://planetarycomputer.microsoft.com/api/stac/v1` | the same STAC |
| Access | anonymous, SAS signing via the `planetary-computer` package | the same |
| Sensor and epoch | SRTM radar, 2000, reprocessed | optical stereo, 2006–2011 |
| Vertical datum | EGM96 | EGM96 |
| Known weakness | radar shadow in steep terrain; 2000 epoch | cloud-related voids |

These are not averaged into the answer. They are used to **rebuild the entire
processing chain independently** — slope, aspect, ray-marched horizon, sky view
factor, clear-sky insolation, sunshine duration — so that the *products* can be
compared rather than the elevations. Their error sources are largely independent
of TanDEM-X radar, which is what makes the comparison worth anything.
`METHODS.md` §14 has the result.

Gaps are filled with the nearest finite value before slope is computed, so a
void cannot propagate as a cliff.

---

## 4. Optical snow

### 4.1 Sentinel-2 L2A — the primary snow record

| | |
|---|---|
| Collection | `sentinel-2-l2a` (surface reflectance, Level-2A) |
| Endpoint | `https://earth-search.aws.element84.com/v1` (Element 84 Earth Search STAC) |
| Access | anonymous, no account |
| MGRS tile | **43TFH** |
| Search filter | metadata cloud cover **< 15 %** |
| Scenes read | **115** — 114 across four complete seasons plus 1 current-season scene |
| Unique dates | 112 after merging same-date scenes |
| Date range | 2022-11-01 → 2026-11-07 |
| Download failures | **0** |
| Platforms | Sentinel-2B (58), 2A (38), 2C (19) |
| Processing baselines | 4.00, 05.09, 05.10, 05.11, 05.12, 05.13 |
| Radiometry | scale 1e-4, offset −0.1 on **every** scene in this run |
| Bands read | B03 green (10 m), B08 NIR (10 m), B11 SWIR (20 m), SCL scene classification (20 m) |
| Licence | Copernicus Sentinel data 2022–2026, processed by ESA |

Per season: 30 / 28 / 25 / 31 scenes for 2022/23 through 2025/26, mean scene
cloud 6.3 – 7.9 %, mean usable-pixel fraction 0.61 – 0.65. The 2026/27 season is
in progress and is excluded from every historical comparison.

**Only the window of each Cloud-Optimised GeoTIFF is read**, never the whole
scene: B03 and B08 area-averaged from 10 m, B11 bilinear, SCL nearest-neighbour.
That is what makes 115 scenes a few minutes of network rather than hundreds of
gigabytes.

**Every scene carries its own provenance.** `scene_manifest.csv` records, per
scene: id, datetime, platform, processing baseline, collection, STAC URL, the
scale and offset actually read from the item's `raster:bands` metadata, the
direct href of each band asset, and the usable and snow fractions. A fallback to
the Copernicus Data Space Ecosystem STAC is coded but was **not needed** — every
scene came from Earth Search, so there is no collection change to declare; had
one occurred it would show in the `collection` and `stac_url` columns.

The baseline-04.00 BOA offset is applied before any index is computed, which
matters because the archive spans the baseline change.

### 4.2 Landsat 8/9 Collection 2 Level-2 — the independent cross-check

| | |
|---|---|
| Collection | `landsat-c2-l2` |
| Endpoint | `https://planetarycomputer.microsoft.com/api/stac/v1` |
| Access | anonymous, SAS signing via the `planetary-computer` package |
| WRS-2 path/row | 149/30 and 150/30 |
| Search filter | cloud cover < 20 % (highest actually used: 19.2 %) |
| Scenes read | **77** — Landsat 9 (42), Landsat 8 (35) |
| Date range | 2022-11-10 → 2026-11-06 |
| Native resolution | 30 m, resampled to the 20 m analysis grid |
| Radiometry | scale 2.75e-5, offset −0.2 (Collection 2 surface reflectance) |
| Masking | `QA_PIXEL`: fill, dilated cloud, cirrus, cloud, cloud shadow |
| Licence | courtesy of the U.S. Geological Survey |

**Landsat 7 is excluded.** Its scan-line corrector failed in 2003 and the
resulting striping corrupts area statistics — a silent one if you do not look.

The same snow rule is applied as to Sentinel-2, deliberately, so that the
comparison tests the *sensors* and not two different definitions of snow.
Landsat crosses roughly half an hour earlier in the day.

### 4.3 MODIS MOD10A1 / MYD10A1 v061 — daily regional context

| | |
|---|---|
| Collection | `modis-10A1-061`, variable `NDSI_Snow_Cover` |
| Endpoint | `https://planetarycomputer.microsoft.com/api/stac/v1` |
| Access | anonymous |
| Resolution | 500 m, daily, two platforms (Terra + Aqua) |
| Window read | February–April 2023 over the cluster area |
| Granules | 80, giving **46 usable days** after dropping any granule with less than half the area unclouded |
| Native projection | **sinusoidal** |
| Licence | NSIDC DAAC / NASA |

At 500 m over 2 km of relief this is regional context and never an answer about
an individual slope. What it buys is time resolution: it adds **36 days on which
Sentinel-2 has no usable scene** in that window, against 14 Sentinel-2 dates.

**MODIS is also what caught a real bug.** Windowed COG reads originally computed
the read window from the AOI bounds in the *target* CRS against the *source*
transform. That is correct only while the two match — which they did for
Sentinel-2 and Landsat, both EPSG:32643 — and silently reads the wrong place
otherwise. The first MODIS run returned exactly zero snow everywhere with a valid
fraction of 1.0. The read now transforms the bounds into the source CRS first,
densified at 21 points per edge. Sentinel-2 and Landsat results were unaffected,
and that was verified by checking the CRS of every Landsat scene used.

---

## 5. OpenStreetMap — the only open record of what exists today

| | |
|---|---|
| Endpoint | `https://overpass-api.de/api/interpreter` |
| Query extent | 76.85 – 77.30 E, 43.00 – 43.25 N |
| Fetched | once, cached at `data/raw/osm/overpass_almaty_mountains.json` (0.9 MB) |
| OSM database snapshot | 2026-11-18 21:08:51 UTC |
| Elements | 642 |
| Licence | **ODbL 1.0**, © OpenStreetMap contributors |

Extracted: aerialway lines (`cable_car`, `gondola`, `chair_lift`, `mixed_lift`,
`t-bar`, `platter`, `drag_lift`, `rope_tow`, `magic_carpet`, `funicular`),
stations, `piste:type=downhill` ways, named peaks and saddles, and
`landuse=winter_sports` polygons.

Within the cluster rectangle: **21 aerialway lines longer than 150 m totalling
21.1 km**, 23 stations, 32 pistes totalling 24.4 km, 63 named peaks, 36 named
saddles.

Two warnings attach to this layer, and both are load-bearing:

1. **These are the lifts that exist today.** No planned alignment is drawn
   anywhere in this release, because none has been published.
2. **OSM is community-maintained** and its completeness varies. Its one
   independent corroboration here is that the rule picks out 7 lifts at
   Shymbulak, matching the "seven cable car lines" in the April 2026 government
   statement.

The ODbL applies to the derived files in `qgis/` and `outputs/*/osm_*`, not to
the analysis code.

---

## 6. Weather and published outlooks

### 6.1 ERA5-Land and ERA5 reanalysis

| | |
|---|---|
| Endpoint | Open-Meteo Historical Weather API (archive), no account required |
| Alternative | Copernicus Climate Data Store, which does need one |
| Point | 77.00433 E, 43.14239 N |
| Model cell elevation | **2 235 m** |
| Period | 2022-11-01 → 2026-04-30, daily |
| Temperature | **ERA5-Land**, ~9 km |
| Snowfall and precipitation | **ERA5**, ~31 km |
| Licence | Copernicus Climate Change Service (C3S) information 2022–2026 |

**ERA5-Land returns no precipitation at this point through that API.** Rather
than let a missing variable be summed to zero, the code falls back to ERA5 and
labels the source in both the data and the metadata file. Every reanalysis
column in this release names which model it came from.

One ERA5-Land cell is ~9 km across against an operating area of 17.8 km²
spanning 1 516 m of relief. These series say what kind of winter a season was.
They are not evidence about any individual slope, and ERA5 precipitation over
complex terrain carries large errors.

### 6.2 and 6.3 Published seasonal outlooks

Transcribed from the primary documents into `docs/seasonal_outlooks.json`, with
URL, issue date and retrieval date for each, so a reader can check the source
rather than take the transcription on trust.

* **Kazhydromet**, *Сезонный прогноз погоды, декабрь 2026 – февраль 2027*,
  issued 16 November 2026, retrieved 19 November 2026. Advisory, for 17 oblasts,
  normals 1991–2020, analogue years December 2005 and January–February 2026.
  **No separate mountain-zone forecast exists.** © RSE Kazhydromet, Ministry of
  Ecology and Natural Resources of the Republic of Kazakhstan.
* **C3S multi-system seasonal forecast**, November 2026 issue (1 November
  initialisation, graphics published 10 November 2026 12 UTC), retrieved
  19 November 2026. Its anomaly charts render client-side and **no Central Asia
  value could be read programmatically on the retrieval date**; the exact chart
  URLs are recorded so a reader can look. No anomaly value is invented.

---

## 7. The operator's own published figures

Not a dataset, but an input, and it is treated with the same provenance
discipline.

| Source | What it gives |
|---|---|
| Kazakh Tourism Development board release, 18 November 2026, chaired by the Prime Minister | 60 km of runs, 16 lifts (11 POMA cableways), 70 % of runs with snowmaking, 10 000 skiers a day, 1 022 ha with ~20 ha built, launch December 2028 |
| General-plan sheet 3, *«Генеральный план горнолыжного курорта Almaty Superski»* | difficulty split 10.6 % green / 50.3 % blue / 22.7 % red / 16.4 % black, 9 000 000 tourists a year |
| primeminister.kz, 24 April 2026 ([link](https://primeminister.kz/en/news/construction-of-almaty-superski-cluster-is-in-active-phase-32133)) | the cluster's named places: Shymbulak, Butakovka, Kimasar, Pioneer, Oi-Qaragai |
| Press reporting of the April 2026 statement | 17 lifts and "about 70 % green and blue" |

**The last two rows disagree with the first two**, and this release carries both
rather than picking silently. `METHODS.md` §9 sets out the conflict and the most
economical explanation of it; `config.py` holds both figures under their source
and every affected table names which one it used.

The general-plan sheet is a perspective panorama with no projection, scale bar
or graticule. **Nothing in this release is traced from it.** What it carries is
named features, and those were located independently in OpenStreetMap.

Still unpublished, and therefore absent from this release: any boundary, any lift
alignment, any station coordinate, any elevation, any capacity in persons per
hour, and any breakdown of the 60 km by difficulty.

---

## 8. Catalogued, costed, and not used

Naming what you did not use is part of the provenance. Full detail with
endpoints in `outputs/cluster/tables/data_source_registry.csv`.

| Source | What it would add | Why it is not here |
|---|---|---|
| **Sentinel-1 GRD (SAR)** | sees through cloud and at night; a backscatter drop identifies **wet** snow, which is what governs spring melt timing | needs radiometric terrain correction and a dry-snow reference; layover and shadow in steep terrain; poor at dry snow. The highest-value next addition |
| **Copernicus HR-S&I** | an operational, validated fractional snow cover product — removes the need to justify one's own thresholds | free registration required, and its coverage is pan-European, so Kazakhstan must be checked before relying on it |
| **VIIRS VNP10A1** | continuity after MODIS end-of-life | free Earthdata login; 375–750 m, coarser than MODIS for this purpose |
| **Kazhydromet station series** | actual measured snow depth and temperature — the only real ground truth | bulletins are public, station time series are by request; sparse in the mountains |
| **Drone photogrammetry / lidar** | 0.1–1 m terrain, the scale lift towers and pistes are actually designed at | flight permissions, field time, processing. This is the resolution gap a 30 m DEM cannot close |

---

## 9. How the data is stored

```
data/raw/           73 MB   2 Copernicus DEM tiles + the cached Overpass JSON
data/interim/       ~210 MB terrain, horizon, insolation and sunshine arrays,
                            one subtree per study area
<repo>/../kok-zhailau-scene-cache/
                    ~24 MB  Sentinel-2 and Landsat window caches, one directory
                            per grid fingerprint <xmin>_<ymin>_<w>x<h>_<res>m
outputs/<area>/     in git  geotiff/ png/ tables/ — the published products
```

**`data/` is not in git** and neither is the scene cache. Everything in them is
regenerated by `run_all.sh`; a cold run is roughly 45 minutes, dominated by the
horizon ray-marches, the downloads and the sunshine-hour integration. The scene
cache deliberately lives *outside* the project folder so it can never be swept
into a commit or a release ZIP. Override its location with
`KZ_SCENE_CACHE=/path/to/cache`.

Each scene is cached as a two-plane `uint8` `.npz` (snow, usable) rather than as
reflectance, which is why 115 scenes occupy megabytes. A failed download is
resumable: the next run reads what is cached and fetches only what is missing.

Because the grid fingerprint is part of the cache path, two study areas never
invalidate each other's cache — and a smaller area that is pixel-aligned inside a
larger one can be **sliced** from it instead of re-downloaded. That is how the
study window gets its 115 scenes from the cluster's cache: equal resolution,
equal CRS, integer pixel offsets and containment are asserted, then the arrays
are cut. No pixel is resampled, and the claim is verified rather than trusted —
one scene re-read from the COGs matched the sliced arrays on **0 differing pixels
out of 174 800**.

---

## 10. The study area these data are read over

The data above describe a mountain range. What turns them into a study is where
you draw the line — and that is a separate, revisable decision, which is why it
comes last here.

**The study area is a hand-drawn polygon**: 24 vertices, digitised over satellite
imagery in Google Earth, exported as KML and held at
`qgis/operating_area.geojson` in EPSG:4326. It encloses **1,776 ha** between
1,775 and 3,291 m. **It is not an official boundary** — Kazakh Tourism
Development states a territory of 1,022 ha and has published no coordinates, so
this polygon is one informed reading of the operating area, and it is 174 % of
the stated territory. Redraw it and one command re-derives every table, figure
and PDF number that depends on it.

Two rasters grids exist, and neither is a reporting unit on its own:

| `KZ_AREA` | bbox (W, S, E, N) | grid | area | what it is |
|---|---|---|---|---|
| `superski` | 76.950, 43.085, 77.055, 43.155 | 292 × 267 @ 30 m | 70.17 km² | the polygon's own envelope plus a 1 km working margin |
| `cluster` | 76.950, 43.070, 77.200, 43.240 | 647 × 694 @ 30 m | 404.12 km² | every place the government statements name for the cluster |

The 70 km² window exists because rasters need a margin — hillshade needs
surroundings, the horizon needs terrain to hit, and a map needs context around
its subject. The polygon is 25 % of it, and `boundary_vs_window.csv` states what
is inside and what is only margin so the distinction can be checked. The 404 km²
cluster answers the questions that are about the range rather than the site.

`METHODS.md` §2 has the full geometry, the grid construction and the contract in
`src/operating_area.py`; `METHODS.md` §21 records that the study area moved twice
before settling here.

---

## 11. Licences and attribution

* **Copernicus DEM GLO-30** — © DLR e.V. 2010–2014 and © Airbus Defence and Space
  GmbH 2014–2018, under the Copernicus DEM open licence; via the AWS Open Data
  registry.
* **Sentinel-2 L2A** — Copernicus Sentinel data 2022–2026, processed by ESA.
  Contains modified Copernicus Sentinel data.
* **ERA5 / ERA5-Land** — Copernicus Climate Change Service (C3S) information
  2022–2026, via the Open-Meteo Historical Weather API. Neither the European
  Commission nor ECMWF is responsible for any use of this information.
* **C3S seasonal forecasts** — Copernicus Climate Change Service information 2026.
* **Kazhydromet seasonal forecast** — RSE Kazhydromet, Ministry of Ecology and
  Natural Resources of the Republic of Kazakhstan.
* **OpenStreetMap** — © OpenStreetMap contributors, **ODbL 1.0**, via the
  Overpass API.
* **Landsat 8/9 Collection 2 Level-2** — courtesy of the U.S. Geological Survey,
  via the Microsoft Planetary Computer.
* **MODIS MOD10A1 / MYD10A1 v061** — NSIDC DAAC / NASA, via the Microsoft
  Planetary Computer.
* **NASADEM** — NASA JPL, via the Microsoft Planetary Computer.
* **ALOS World 3D-30m (AW3D30)** — © JAXA, via the Microsoft Planetary Computer.
* **Microsoft Planetary Computer** — STAC API with anonymous asset signing.
* **pvlib-python** — BSD-3-Clause.
* Analysis code and figures in this release: Dias Irishev, 2026, MIT (see
  `LICENSE`). The MIT licence covers the code and figures only; **each dataset
  above keeps its own terms**, and the OSM-derived files in `qgis/` are ODbL.
