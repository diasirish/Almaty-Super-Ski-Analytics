# METHODS

**Kok Zhailau ski terrain analytics — an independent open-data case study**
Dias Irishev · Geo & Weather Data Scientist, Almaty
Release date: 19 November 2026

Everything below is reproducible from the code in `src/` and the three notebooks.
Every number quoted in `README.md` and in the PDF brief comes from a CSV in
`outputs/tables/` written by those notebooks.

---

## 1. Scope and standing

This is an independent study built from open data and the author's own code. It is
not commissioned by, affiliated with, or endorsed by any resort operator, design
office or public body, and it contains no commercial or NDA material.

The official statement of 18 November 2026 on the Almaty SuperSki cluster
([primeminister.kz](https://primeminister.kz/en/news/construction-of-almaty-superski-cluster-is-in-active-phase-32133))
names no individual resort site. The rectangle analysed here is therefore the
author's own choice of study area, not a project boundary, and nothing in this
release should be read as describing a planned resort.

**The study rectangle is not a resort boundary and not a trail plan.** Resort
limits, lift alignments and designed pistes require official GIS layers.

---

## 2. Study area and grids

| Item | Value |
|---|---|
| WGS84 bounding box (W, S, E, N) | 76.960, 43.105, 77.065, 43.174 |
| Working projection | EPSG:32643 (UTM zone 43N) |
| Terrain / insolation grid | 263 × 292 cells at 30 m |
| Sentinel-2 / snow grid | 395 × 437 cells at 20 m |
| Grid extent | 659 280 – 668 040 E, 4 774 320 – 4 782 210 N |
| Grid area | **69.12 km²** |
| Geodesic area of the WGS84 rectangle | 65.48 km² |
| Plateau reference point | 77.00433° E, 43.14239° N (inside the rectangle) |
| Elevation range | 1271 – 3318 m |

### Why 69.12 km² and not 65.48 km²

The analysis grid is the **axis-aligned UTM bounding box of the WGS84 rectangle**,
snapped outward to whole cells. Meridian convergence at 77° E (≈2° east of the
zone's central meridian) is about 1.4°, so the projected rectangle is slightly
rotated and its axis-aligned bounding box is larger than the rectangle itself. The
whole 3.6 km² difference is that rotation plus the outward snap. Both figures are
reported; statistics are computed on the grid.

Edge densification: each edge of the WGS84 rectangle is sampled at 200 points
before projection, so the bounding box captures the curved projected edges exactly
rather than only the four corners.

---

## 3. Terrain

**Source.** Copernicus DEM GLO-30, tiles `Copernicus_DSM_COG_10_N43_00_E076_00_DEM`
and `...E077_00_DEM`, from the AWS Open Data registry
(`https://copernicus-dem-30m.s3.amazonaws.com`). Vertical datum EGM2008. Licence:
free use with attribution to the Copernicus Programme / ESA.

**Processing.** Tiles merged, then reprojected to EPSG:32643 at 30 m by bilinear
resampling. A second DEM is built on a grid buffered by 6 km for the horizon search.

**Slope and aspect.** Horn (1981) 3 × 3 operator. Aspect is the direction of
steepest descent, degrees clockwise from **true** north. Because aspect is computed
after projection, the ~1.4° grid convergence is already removed.

**Horizon.** For each of 36 azimuths (10° spacing) a ray is marched outward in 30 m
steps to 6 km over the buffered DEM, sampling elevation by bilinear interpolation,
and the maximum angular elevation is kept. Earth curvature is applied as a drop of
d² / (2 R_eff) with R_eff = 7/6 × 6 371 km (standard atmospheric refraction).

**Sky view factor.** Dozier & Frew (1990), for a tilted surface:

> V_d = (1/2π) ∫₀²ᵖ [ cos β · sin²H_φ + sin β · cos(φ − A) · (H_φ − sin H_φ cos H_φ) ] dφ

with β the slope, A the aspect, and **H_φ the horizon angle measured from the
zenith**. In each azimuth H_φ is the smaller of the terrain horizon and the slope
plane's own horizon, so a surface never sees sky below its own plane.

### Validation (`outputs/tables/qa_terrain_validation.csv`)

| Test | Expected | Computed |
|---|---|---|
| Synthetic 20° planes, 8 aspects | slope 20.00°, aspect as constructed | exact to 0.01° in all 8 cases |
| SVF, unobstructed plane, β = 0/20/40° | (1 + cos β)/2 = 1.0000 / 0.9698 / 0.8830 | 1.0000 / 0.9698 / 0.8830 |
| SVF, flat pixel inside a uniform 30° skyline | cos²30° = 0.7500 | 0.7500 |
| Horizon, 1000 m wall at 1980 m (grid-snapped) | atan(1000/1980) with curvature = 26.79° | 26.79° |

**Resulting values.** Median slope 28.8°; median sky view factor 0.889 (range
0.652 – 0.998); median horizon elevation across azimuths 14.5°.

---

## 4. Clear-sky insolation

**Model.** `pvlib` 0.16.1, Ineichen–Perez clear sky with the monthly Linke
turbidity climatology bundled with pvlib. Solar position from
`pvlib.solarposition.get_solarposition` at the rectangle centroid; the rectangle is
8.8 km wide, so the within-grid variation in solar position is below 0.05° and is
neglected.

**Time stepping.** 30-minute intervals, evaluated at interval mid-points, in
Asia/Almaty (UTC+5, no DST). Only steps with solar elevation above 0.5° contribute.

**Altitude.** Clear sky is computed at **seven altitude levels** spanning the grid's
elevation range and interpolated per pixel by elevation, so the ~2 km of relief is
not collapsed to a single atmosphere. Pressure from `pvlib.atmosphere.alt2pres`.

**Plane-of-array components.**

| Component | Formula | Assumption |
|---|---|---|
| Direct | DNI × cos(AOI), zeroed where the sun is below the ray-marched horizon or behind the slope | terrain shading resolved at 30 m and 10° azimuth |
| Diffuse | DHI × SVF | **isotropic sky.** Real skies are brighter near the sun and near the horizon; an isotropic model under-estimates diffuse on slopes facing the sun and over-estimates it on slopes facing away |
| Reflected | GHI × α × (1 − SVF) | **α = 0.50, fixed.** The terrain configuration factor is approximated by (1 − SVF), which assumes surrounding terrain is an isotropic reflector at the mean surface albedo |

**Why α = 0.50.** The winter surface here ranges from fresh snow (≈0.8) through
old snow, bare rock and conifer (≈0.1). A single seasonal value is a deliberate
simplification. Its weight is small: in the 2200–2300 m band over March–April the
median reflected term is 23.7 kWh/m² against 305.2 kWh/m² direct, under 7% of the
total. **The exposure contrast reported in notebook 03 reproduces on direct beam
alone** (low vs high quartile: 0.800 vs 0.300 on direct, 0.778 vs 0.300 on total,
March–April 2023), so no conclusion in this release depends on the albedo choice.

**Reference periods.** The historical reference season is 2022-11-01 → 2023-04-30,
matching the first fully covered snow season. Clear-sky totals vary year to year by
well under 1%, so one reference season is used for the December / March /
November–December / January–February / March–April rasters. The 2027 outlook is
computed on 2027 calendar dates.

**What these numbers are.** A clear-sky ceiling, in kWh/m², on the plane of each
slope. Not expected irradiance: real cloud reduces them, and cloud attenuation is
not measured here.

---

## 5. Sentinel-2 snow

**Source.** Sentinel-2 L2A surface reflectance, searched through the Element 84
Earth Search STAC API (`https://earth-search.aws.element84.com/v1`, collection
`sentinel-2-l2a`), MGRS tile **43TFH**, metadata cloud cover < 15%.
Copernicus Sentinel data, processed by ESA.

A fallback to the Copernicus Data Space Ecosystem STAC was coded but **not needed**:
every scene in this run came from Earth Search, so there is no collection change to
declare. Had one occurred it would appear in the `collection` and `stac_url` columns
of `outputs/tables/scene_manifest.csv`, which carry the provenance of every scene.

**Reading.** Only the AOI window of each Cloud-Optimised GeoTIFF is read and
reprojected onto the 20 m grid: B03 (green, 10 m, area-averaged), B08 (NIR, 10 m,
area-averaged), B11 (SWIR, 20 m, bilinear), SCL (20 m, nearest). Each scene's window
is cached as a small `.npz` outside the release folder, which makes the download
resumable after a failure.

**Radiometry.** Scale and offset are read from each item's `raster:bands` metadata
and recorded per scene in the manifest. Every scene in this run uses scale 1e-4 and
offset −0.1 (processing baselines 04.00 and 05.09 – 05.13), i.e. the post-baseline-04.00
BOA offset is applied before any index is computed.

**Snow rule.**

> snow = NDSI > 0.40 **and** B08 > 0.11 (surface reflectance), with NDSI = (B03 − B11)/(B03 + B11)

**Masking.** A pixel is a *usable observation* unless its SCL class is one of
no-data (0), saturated (1), cast shadow (2), cloud shadow (3), unclassified (7),
cloud medium (8), cloud high (9) or thin cirrus (10), or all three bands are fill.
Water (6) is a usable observation but can never be classed as snow.

**Threshold justification** (`outputs/tables/ndsi_threshold_sensitivity.csv`). The
rule was re-run across NDSI ∈ {0.30, 0.40, 0.50} × B08 ∈ {0.07, 0.11, 0.15} on six
March–April 2023 scenes. Mean snow fraction of usable pixels ranges 59.1% – 72.1%
across that whole grid; the chosen rule gives 66.6%. The answer is therefore stable
to about ±6 percentage points under reasonable threshold choices — a real
uncertainty, and smaller than the exposure contrast the study reports.

**Independent check.** Scene-level agreement between this rule and the Sen2Cor SCL
snow class (11), which is produced independently by the L2A processor: r = 0.973
over 115 scenes, with the NDSI rule running 0.109 lower on average.

**Duplicate dates.** Scenes sharing an acquisition date are merged: a pixel is
usable if usable in any scene of that date, and snow if flagged snow in any scene
where it was usable. 115 scenes collapse to 112 unique dates.

**Frequency.** For a period, each season contributes equally: the per-season ratio
(snow dates / usable dates) is averaged over the seasons that have data, so a
season with many clear dates cannot outvote a cloudy one. A value is published only
where a pixel has **≥ 4 usable observations** in the period; multi-season maps
additionally require **≥ 3 seasons** of support.

**Melt-out.** The satellite brackets rather than dates the disappearance: the last
date a pixel was seen with snow, and the first usable snow-free date after it. The
midpoint is reported together with the width of the bracket. Pixels lacking either
bound are left unestimated — 51% – 75% of pixels are estimable depending on season.

### Known bias

Cast shadow and cloud shadow are rejected before counting, so **shaded north slopes
lose observations exactly where the snow signal matters most**. In the 2200–2300 m
band over March–April 2023, coverage is 86% in the lowest insolation quartile
against 100% in the highest. In deep shade NDSI is also weakest, so a snow-covered
pixel there is more likely than average to be scored snow-free. Both effects push
the measured low-exposure frequency **down**, which means the reported exposure
contrast is, if anything, conservative.

---

## 6. Joining terrain to snow

Statistics that combine the two are computed on the **20 m Sentinel-2 grid**.
Terrain and insolation are resampled from 30 m to 20 m bilinearly; **aspect is
interpolated as a unit vector** (sin/cos components) rather than as degrees, to
avoid the 0°/360° wrap, and is set undefined where the interpolated vector magnitude
falls below 0.2 (opposing aspects averaging out). GeoTIFFs of terrain products are
published at their native 30 m.

**Exposure contrast.** Within each 100 m elevation band, on 15–35° slopes only,
pixels are split at that band's own 25th and 75th insolation percentiles. Holding
elevation fixed and taking quartiles within the band means the remaining difference
is an exposure effect, not an elevation effect. Group sizes and per-group coverage
are reported alongside every comparison.

---

## 7. The 2027 outlook

Three separate things, deliberately kept apart.

**1. Clear-sky insolation for 2027.** Deterministic solar geometry with
climatological turbidity, computed on 2027 calendar dates. This is the only part of
the outlook that is a calculation rather than an analogue.

**2. Spring timing scenarios.** No forecast of 2027 snow cover is made, because
nothing in this data supports one. Instead the four-season spring record is re-cut
against three calendar windows — 11 March → 20 April (the historical analogue),
the same window ten days earlier, and ten days later — and the three maps are
compared **on the pixels observed in all three** (43.44 km², 89.2% of skiable
terrain). That isolates the effect of timing from the effect of coverage.
**No probabilities are attached**: assigning one would need a calibrated and
verified model, which this is not.

**3. Published seasonal outlooks**, transcribed from the primary documents and
stored in `docs/seasonal_outlooks.json`:

* **Kazhydromet**, *Сезонный прогноз погоды, декабрь 2026 – февраль 2027*, issued
  16 November 2026, retrieved 19 November 2026
  ([PDF](https://www.kazhydromet.kz/uploads/files_calendar/13401/file/6afacdf27e503sp-na-zimu-2026-2027-gg-ot-16-11-2026g.pdf),
  [landing page](https://www.kazhydromet.kz/ru/weather/konsultativnyy-prognoz-pogody-na-sezon)).
  Advisory, issued for 17 oblasts, normals 1991–2020, analogue years December 2005
  and January–February 2026. For the Almaty area: December temperature above normal
  by 1–2 °C over most of the country (near normal in the east of Almaty oblast),
  precipitation near normal nationwide; January temperature above normal by 1–2 °C,
  precipitation below normal in the northern half of Almaty oblast; February
  temperature above normal by 1–3 °C, precipitation above normal over most of the
  country.
* **C3S multi-system seasonal forecast**, November 2026 issue (1 November
  initialisation, graphics published 10 November 2026 12 UTC), retrieved
  19 November 2026. Published highlights: ENSO expected to peak around the end of
  2026, with eastern Asia among the wetter-than-average regions. **The C3S anomaly
  charts render client-side and no Central Asia value could be read
  programmatically on the retrieval date**; the exact chart URLs are recorded in
  `docs/seasonal_outlooks.json` so a reader can check them directly. No anomaly
  value is invented here.

**Scale caveat.** Both outlooks are warm-leaning at a scale of hundreds of
kilometres. Almaty oblast spans roughly 500 – 5000 m; a single oblast statement
cannot be read as a forecast for a rectangle that itself spans 1271 – 3318 m, and
neither outlook forecasts snow depth.

**Reanalysis context.** Daily ERA5-Land (≈9 km grid, cell elevation 2235 m) at the
plateau point via the Open-Meteo Historical Weather API, for temperature.
ERA5-Land returns no precipitation at this point through that API, so snowfall and
precipitation fall back to **ERA5 at ≈31 km** and are labelled as such. Both grids
smooth the orography heavily and ERA5 precipitation over complex terrain carries
large errors; they say what kind of winter a season was, and are not evidence about
any individual slope.

---

## 8. What this study cannot tell you

| Question | Why not | What would answer it |
|---|---|---|
| Number of ski days | A frequency is a share of **usable satellite dates**, not days of operation | continuous depth record against an operating threshold |
| Snow depth or water equivalent | Optical imagery sees the surface, not what is under it | snow pillow or ultrasonic depth sensor plus density cores |
| Season opening date | A 5-day revisit with cloud gaps cannot resolve a threshold crossing to the day | same as above, over several seasons |
| Snowmaking feasibility or cost | None of the governing variables is observed from orbit | wet-bulb temperature at the gun line, wind, water yield and temperature, equipment curves, target depth |
| Avalanche hazard | Slope angle is geometry; release depends on the snowpack | snowpack profiles, wind transport and loading, mapped start and runout zones, local forecaster judgement |
| Real (not clear-sky) irradiance | The model is clear-sky by construction | pyranometer pair on contrasting aspects |
| Resort boundaries or trail alignments | Not derivable from open terrain data | official GIS layers from the project |

A four-season record is also far too short to support any statement about trend.

---

## 9. Comparison with the earlier pilot run

The earlier pilot had 41 of 112 planned scenes cached and one complete season. This
run processed **114 historical scenes across all four seasons** plus one
current-season scene. Full table: `outputs/tables/pilot_comparison.csv`.

| Quantity | Pilot | This run | Reading |
|---|---|---|---|
| Area of the study rectangle | 69.1 km² | 69.12 km² | reproduces exactly |
| Candidate dates, Mar–Apr 2023 | 12 | 13 | within one date |
| Coverage at ≥4 usable obs, Mar–Apr 2023 | ~74% | 85% | higher here |
| 2200–2300 m, low-insolation quartile | ~94% | 78% | lower here |
| 2200–2300 m, high-insolation quartile | ~23% | 30% | close |

The geometry reproduces exactly, so the grid is not the source of the difference.
The most likely explanation for the remaining gap is the **valid-observation
definition**: this run keeps a pixel whenever its SCL class permits a snow /
no-snow decision, and the pixels thereby recovered sit disproportionately in deep
shade, where NDSI is weakest. That raises coverage (74% → 85%) and lowers the
measured low-exposure frequency at the same time, which is exactly the pattern
observed. The high-exposure group — where no such recovery happens — agrees
closely. Note also that over the **four-season** spring window the low-exposure
figure in the same band is 93.3%, close to the pilot's single-season ~94%.

Resolving this properly needs ground truth, not more processing. That is the
purpose of the field pilot proposed in notebook 03.

---

## 10. Attribution and licences

* **Copernicus DEM GLO-30** — © DLR e.V. 2010–2014 and © Airbus Defence and Space
  GmbH 2014–2018, provided under the Copernicus DEM open licence; distributed via
  the AWS Open Data registry.
* **Sentinel-2 L2A** — Copernicus Sentinel data 2022–2026, processed by ESA.
  Contains modified Copernicus Sentinel data.
* **ERA5 / ERA5-Land** — Copernicus Climate Change Service (C3S) information
  2022–2026, accessed through the Open-Meteo Historical Weather API. Neither the
  European Commission nor ECMWF is responsible for any use of this information.
* **C3S seasonal forecasts** — Copernicus Climate Change Service information 2026.
* **Kazhydromet seasonal forecast** — RSE Kazhydromet, Ministry of Ecology and
  Natural Resources of the Republic of Kazakhstan.
* **pvlib-python** — BSD-3-Clause.
* Analysis code and figures in this release: Dias Irishev, 2026.

## 11. Software

Python 3.12.10. Pinned versions in `requirements.txt`; the key ones are
numpy 2.5.5, rasterio 1.5.2, pvlib 0.16.1, pyproj, pystac-client, scipy, pandas,
matplotlib, reportlab.

---

# PART II — The cluster area (added 19 November 2026)

Notebook 04 widens the analysis from the 69 km² Kok Zhailau rectangle to the
whole area the Almaty SuperSki cluster is reported to touch, adds direct
sunshine duration alongside energy, and cross-checks the snow record against a
second satellite. Everything in Part I is unchanged.

## 12. Study areas are now a parameter

`src/config.py` defines `STUDY_AREAS` and reads `KZ_AREA` from the environment
before anything else is configured. Each area gets its own output subtree, so
runs cannot overwrite one another:

| `KZ_AREA` | bbox (W, S, E, N) | grid | area | outputs |
|---|---|---|---|---|
| `kok_zhailau` | 76.960, 43.105, 77.065, 43.174 | 263 × 292 @ 30 m | 69.12 km² | `outputs/` |
| `cluster` (default) | 76.950, 43.070, 77.200, 43.240 | 647 × 694 @ 30 m | 404.12 km² | `outputs/cluster/` |

Notebooks 01–03 pin `kok_zhailau` on their first line; notebook 04 pins
`cluster`. The Sentinel-2 window cache is keyed by a grid fingerprint
(`<xmin>_<ymin>_<w>x<h>_<res>m`), so the two areas keep separate caches and
neither invalidates the other.

### How the cluster rectangle was derived

**No official project boundary has been published.** The government statements
read for this release describe infrastructure in detail — 11 POMA cableways,
3S gondolas, 10-seat gondolas and chairlifts, base and upper stations, a
mountain village concept by BIG, an architectural concept by Foster + Partners,
a 6 km access road, a resort launch in December 2028 — but give no coordinate,
no station location and no boundary.

The places they do name are:

| Place | Source | Stated role |
|---|---|---|
| Shymbulak | primeminister.kz, 24 Apr 2026 | modernisation, stage 1; first of seven cable car lines from May 2026 |
| Butakovka gorge | primeminister.kz, 24 Apr 2026 | development, stage 1 |
| Kimasar gorge | primeminister.kz, 24 Apr 2026 | development, stage 1 |
| Pioneer | primeminister.kz, 24 Apr 2026 | stage 2 from 2027, to be linked by cable car |
| Oi-Qaragai | primeminister.kz, 24 Apr 2026 | stage 2; gondola and chairlift already commissioned |
| Kok Zhailau, Kumbel | Wikipedia (citing AnewZ, 2025) | reported as combined into the cluster; **not** in the statements read here |

The rectangle is the smallest round bounding box containing all of them, as
located in OpenStreetMap. It is **derived, not given**, and it is not a resort
boundary.

## 13. OpenStreetMap reference layers

Queried once through the Overpass API over 76.85–77.30 E, 43.00–43.25 N and
cached in `data/raw/osm/`. Licence: ODbL, © OpenStreetMap contributors.

Inside the cluster rectangle: **21 aerialway lines longer than 150 m totalling
21.1 km**, 23 lift stations, 32 mapped downhill pistes totalling 24.4 km, 63
named peaks, 36 named saddles, and the Shymbulak and Oi-Qaragai
`landuse=winter_sports` polygons. Exported to
`outputs/cluster/osm_reference_layers.geojson`.

**These are the lifts that exist today.** No planned alignment is drawn anywhere
in this release, because none has been published. Zones used for reporting are
built from these features: lift corridors are everything within 150 m of an
existing line (7.36 km²), piste corridors within 100 m (3.00 km²).

## 14. Direct sunshine duration

Energy and duration answer different questions, so both are computed. A pixel
counts as sunlit at an instant when **all three** hold:

1. the sun is above the astronomical horizon,
2. the sun is above the ray-marched terrain horizon at its azimuth,
3. the slope faces the sun (cos of the incidence angle > 0).

Stepped at **15 minutes** (finer than the 30-minute energy integration, because
a duration is more sensitive to the step), in Asia/Almaty. Output per pixel per
month, plus a month × hour-of-day table of the sunlit fraction of each zone.

The two measures rank terrain differently: over November–April 2027 the
correlation between the sunshine-hours raster and the energy raster is
**r = 0.73**, and the top-10 skiable sites by each measure share **no points at
all**. Energy maxima sit on steep (≈34°) south faces near 4000 m, where high
sun angles on a steep plane maximise irradiance; duration maxima sit on gentler
15–20° south slopes that clear their own horizon earlier and hold the sun
longer.

### Faster horizons

The ray-march now uses a geometrically growing step (30 m, ×1.02 per step,
capped at 120 m) instead of a uniform 30 m. The angular size of a terrain cell
falls as 1/distance, so uniform stepping heavily oversamples the far field.
Validated against uniform 30 m stepping on real terrain: **2.4× fewer samples,
mean difference −0.02°, p99 |Δ| 0.45°, max |Δ| 1.24°**. Setting
`HORIZON_STEP_GROWTH = 1.0` restores uniform stepping exactly.

## 15. The sun-and-snow index

`sunlit fraction × snow detection frequency` for the month — the share of a zone
that is, at that hour, both in the sun and (on four seasons of satellite record)
usually snow-covered. **A screening index, not a forecast.** It multiplies a
clear-sky geometric quantity by an empirical frequency; it says nothing about
whether a given day will be clear, and nothing about snow depth.

On the existing lift corridors the daily window with over half the corridor in
sun runs **10:00–14:00 in December** (peak 69% sunlit at noon) and
**08:00–17:00 in March** (100% at midday). The index peaks in **February around
12:00**, where 96% sunlit meets a 100% snow-detection frequency.

## 16. Cross-validation against independent sources

### Elevation — three DEMs

| DEM | sensor and epoch | mean Δ | median Δ | σ | p95 \|Δ\| | correlation |
|---|---|---|---|---|---|---|
| NASADEM | radar, SRTM 2000, EGM96 | +0.26 m | −0.09 m | 7.40 m | 13.97 m | 0.999952 |
| ALOS AW3D30 | optical stereo 2006–2011, EGM96 | +1.92 m | +1.59 m | 7.15 m | 12.68 m | 0.999956 |

Against Copernicus GLO-30 (radar, TanDEM-X 2010–2015, EGM2008) on the 449 018
cluster pixels. The three have largely independent error sources, so agreement
to a few metres is meaningful. NASADEM reads 1.4° flatter in slope on average,
consistent with SRTM's coarser effective resolution.

### Snow — Landsat 8/9 against Sentinel-2

77 Landsat 8/9 Collection 2 Level-2 scenes (cloud < 20%) over the four seasons,
read through the Microsoft Planetary Computer and reduced with the **same**
NDSI > 0.40 and NIR > 0.11 rule, masked with `QA_PIXEL` (fill, dilated cloud,
cirrus, cloud, cloud shadow). Landsat 7 is excluded: its scan-line corrector
failed in 2003 and the striping corrupts area statistics.

* Within Landsat, our rule against the USGS `QA_PIXEL` snow flag: **r = 0.879**.
* Against Sentinel-2, **scene-aggregate**, same date ±1 day: r = 0.820, mean
  difference +0.353.
* Against Sentinel-2, **same date and restricted to pixels both call usable**:
  **r = 0.969**, mean difference **+0.096**, per-pixel agreement **86.8%**, over
  25 dates and 8.5 M common pixels.

The scene-aggregate comparison is unfair, and the gap between the two rows is
the lesson: each sensor was averaging over *its own* valid pixels, and Landsat's
`dilated_cloud` bit deliberately removes a wide halo. Almost all of the apparent
disagreement was the two masks covering different ground.

What remains is one-sided — Sentinel-2 calls snow on 11.4% of common pixels
where Landsat does not, against 1.8% the other way — which is the direction a
30 m sensor resampled to a 20 m grid should err in, since a part-snow pixel
averages below the NDSI threshold at the coarser footprint. Landsat also crosses
roughly half an hour earlier. The two records are consistent.

### MODIS daily snow cover

MOD10A1 and MYD10A1 v061 `NDSI_Snow_Cover`, 500 m, read over the cluster area
for February–April 2023. Granules with less than half the area unclouded are
dropped. The result adds **36 days on which Sentinel-2 has no usable scene** in
that window, against 14 Sentinel-2 dates — the melt-timing signal between clear
optical dates. At 500 m over 2 km of relief this is regional context and never
an answer about an individual slope.

### A bug this found

Windowed COG reads originally computed the read window from the AOI bounds in
the **target** CRS against the **source** transform. That is correct only while
the two CRSs match — which they did for Sentinel-2 and Landsat, both EPSG:32643
— and silently read the wrong place otherwise. MODIS is in a sinusoidal
projection, and the first MODIS run returned exactly zero snow everywhere with a
valid fraction of 1.0. The read now transforms the bounds into the source CRS
first (densified at 21 points per edge). Sentinel-2 and Landsat results are
unaffected; this was verified by checking the CRS of every Landsat scene used.

## 17. Additional attribution

* **OpenStreetMap** — © OpenStreetMap contributors, ODbL 1.0, via the Overpass API.
* **Landsat 8/9 Collection 2 Level-2** — courtesy of the U.S. Geological Survey,
  accessed through the Microsoft Planetary Computer.
* **MODIS MOD10A1 / MYD10A1 v061** — NSIDC DAAC / NASA, via the Microsoft
  Planetary Computer.
* **NASADEM** — NASA JPL, via the Microsoft Planetary Computer.
* **ALOS World 3D-30m (AW3D30)** — © JAXA, via the Microsoft Planetary Computer.
* **Microsoft Planetary Computer** — STAC API with anonymous asset signing.

The full list of sources used and of further sources worth reaching for, with
endpoints, access cost, what each adds and what it costs, is in
`outputs/cluster/tables/data_source_registry.csv`: **12 sources, 7 used here.**

---

# PART III — Project scale and engineering validation (added 19 November 2026)

Part III is the demo layer: the same machinery pointed at the scale the project
is being built at, then deliberately stress-tested. Notebook
`05_project_scale_and_validation.ipynb`.

## 18. A correction to Part II

Part II said that Kok Zhailau "appears in the cluster plan as reported on
Wikipedia, not in the statements read here". That was true of the single
primeminister.kz statement of 24 April 2026 that had been fetched, and wrong as
a claim about the record. Almaty SuperSki **is** the Kok Zhailau project: Kazakh
Tourism Development's own release from the board meeting of 18 November 2026,
chaired by the Prime Minister, describes 60 km of runs and 17 lifts *on Kok
Zhailau*, with POMA building 11 cableways, about 70 % of runs green and blue, up
to 10 000 skiers a day, a territory of 1 022 ha of which about 20 ha is built
on, and a launch in December 2028. Part II's cluster rectangle is unaffected —
it still contains every named place — but its framing of Kok Zhailau was too
narrow and is withdrawn.

Still unpublished, and therefore still absent from this release: any boundary,
any lift alignment, any station coordinate, any elevation, any capacity in
persons per hour, and any breakdown of the 60 km by difficulty.

## 19. Reconstructing the 1,022 ha

`src/footprint.py`. The stated area is used; the stated shape does not exist, so
two footprints of exactly 1 022 ha are derived inside a 42 km² window centred on
the plateau reference point, and every project-scale number is reported against
both:

* **A — disc.** The 1 022 ha closest to the point, i.e. the pixels with the
  smallest centre-to-centre distance. It uses no terrain information, so it
  cannot flatter the ground. One connected piece.
* **B — gentlest.** The 1 022 ha of lowest slope within 3 km of the same point,
  slope first mean-filtered over 150 m so that a single flat pixel inside a cliff
  band cannot outrank a real bench. This is the most favourable territory a
  planner could choose, which makes it the right adversarial reference: a
  gradient conclusion that survives on B is not an artefact of the boundary.

Contiguity is reported with `scipy.ndimage.label` because it turned out to be
the result, not a diagnostic: footprint B is **67 separate pieces**, the largest
455 ha (44 % of the footprint).

## 20. Gradient classes

`src/ski_terrain.py`. Class boundaries are the percent grades of the **British
Columbia All Season Resort Guidelines, Chapter II (Mountain Resorts)**,
converted to degrees: beginner 0–15 % (0–8.5°), novice 15–25 % (8.5–14.0°), low
intermediate 25–35 % (14.0–19.3°), intermediate 35–40 % (19.3–21.8°), advanced
intermediate 40–60 % (21.8–31.0°), expert above 60 % (31.0°+). Skier densities
in the same table are that document's per-hectare ranges.

This is a published planning convention from the jurisdiction the named planners
work in. **It is not a Kazakh standard and not this project's design criteria.**
It is used only to ask whether a published mix of runs is consistent with the
ground. "Green and blue" is read as beginner through low intermediate, i.e.
grades up to 35 %.

| Footprint | green/blue share | green/blue area | median slope | above 31° |
|---|---|---|---|---|
| A — 1 022 ha disc | 20.4 % | 208 ha | 28.8° | 39.1 % |
| B — gentlest 1 022 ha | 46.6 % | 476 ha | 20.0° | 2.1 % |
| 42 km² window | 21.4 % | 902 ha | 28.3° | 38.7 % |

### The arithmetic, and its one assumption

The operator publishes a length (60 km) and a mix (about 70 % green and blue)
but no width, and width is what turns a length into an area. Three mean widths
are carried through rather than one: 30 m gives 126 ha of green/blue runs, 40 m
gives 168 ha, 50 m gives 210 ha. Against 208 ha available on footprint A that is
61 %, 81 % and 101 % — at 50 m the arithmetic does not close. On footprint B,
476 ha available, it is 26 %, 35 % and 44 %.

So the binding constraint is not the quantity of gentle ground but its
connectivity, and a 30 m DEM can show that it fragments without showing whether
two benches can be joined by a lift. That is a survey question and it is listed
as one.

## 21. Finer sampling at project scale

At 42 km² the horizon is sampled over **72 azimuths (5°)** instead of 36, and
direct-sunshine duration is stepped every **5 minutes** instead of 15. Both are
per-area overrides in `STUDY_AREAS` rather than global changes, so the cluster
products are unchanged and comparable with Part II.

Median direct sun over the whole of December: **34.8 h on footprint A (1.1 h a
day) against 135.0 h (4.4 h a day) on footprint B**, a factor of 3.9 from the
choice of footprint alone. The plateau faces the city, which is north — good for
holding snow, poor for mid-winter sun.

## 22. Reusing the scene cache instead of re-downloading

`src/reuse_cache.py`. The 20 m project grid is a pixel-aligned subset of the
20 m cluster grid, so the 115 Sentinel-2 windows already read for Part II
contain every observation this window needs. The module asserts equal
resolution, equal CRS, integer pixel offsets and containment, then slices. **No
pixel is resampled.**

Verified rather than asserted: one scene (`S2B_43TFH_20231126_0_L2A`) was
re-read from the COGs onto the project grid and compared with the sliced arrays
— **0 differing pixels out of 104 895** in both the snow and the validity plane.

## 23. A bias this release used to leave implicit

A pixel enters a monthly snow map only once it has four cloud- and shadow-free
observations (`MIN_VALID_OBS`). Steep shaded ground fails that test more often
than open sunlit ground, so the qualifying pixels are not a fair sample of the
terrain — and in mid-winter, when valid observations are scarcest, the skew
falls on exactly the quantity being measured. `snow.coverage_bias` now measures
it on the project window:

| month | qualifying share | median valid obs | insolation skew | slope skew |
|---|---|---|---|---|
| November | 70.9 % | 11 | +128 kWh/m² | −3.0° |
| **December** | **43.2 %** | **1** | **+285 kWh/m²** | **−4.5°** |
| January | 52.8 % | 5 | +231 kWh/m² | −4.2° |
| February | 82.7 % | 8 | +58 kWh/m² | −1.2° |
| March | 97.9 % | 21 | +8 kWh/m² | −0.2° |
| April | 87.4 % | 11 | +45 kWh/m² | −0.8° |

A December snow figure here is a statement about the sunnier, gentler 43 % of
the terrain. February through April are sound. **This applies to the Part II
sun-and-snow index as well**: its December and January entries carry the same
skew, and should be read as indicative only. The index was not recomputed, but
the caveat is now explicit rather than absent.

## 24. Comparable operating areas

`src/resorts.py`. Part II compared Kok Zhailau against the OSM
`landuse=winter_sports` polygons for Shymbulak and Oi-Qaragai, which are 2.2 and
1.0 km² — far smaller than either resort operates. That comparison is
**superseded**. One rule is now applied to every place: an operating area is the
ground within 150 m of its lift lines unioned with the ground within 100 m of
its pistes, with lines assigned to the nearest named place within 3.5 km.

| place | lifts | lift km | pistes | piste km |
|---|---|---|---|---|
| Shymbulak | 7 | 10.73 | 24 | 18.6 |
| Oi-Qaragai | 8 | 6.51 | 6 | 4.7 |
| unassigned | 6 | 3.81 | 2 | 1.1 |

Seven lifts at Shymbulak is an independent match to the "7 lines" in the
April 2026 statement.

Kok Zhailau has neither lifts nor pistes, so it enters as its reconstructed
footprints. That asymmetry is real and cannot be removed: a working resort's
corridors are *where planners already chose to build*, which is a selected
sample of good terrain. Footprint B — Kok Zhailau's own best ground — is
therefore the reference, so the comparison is best-selected against
best-selected.

### Holding altitude and gradient constant

Every area is restricted to 15–35° and compared band by 200 m elevation band,
with a band reported only where that area holds at least 50 pixels in it. Against
footprint B:

* Shymbulak's corridors: **−134 kWh/m²** of November–April energy over 8 shared
  bands, and snow detected **+0.074** more often in March. They trade sun for
  snow.
* Oi-Qaragai: **+90 kWh/m²** and **+0.182**. But Oi-Qaragai sits at 1 520–2 280 m
  under forest, and NDSI beneath canopy is a known weak point, so this is the
  least comparable number in the table and is labelled as such.

Sun and snow do not rank these places the same way — the same result Part II
found *within* one area, reappearing *between* areas.

## 25. Does the DEM choice change the answer?

`src/dem_validation.py`. Comparing elevations is the half of a DEM check that
flatters every product. The planning reads slope, horizon, insolation and
sunshine hours, so the **whole chain** — slope, aspect, ray-marched horizon, sky
view factor, clear-sky insolation, direct-sunshine duration — was rebuilt on
NASADEM and ALOS World 3D-30m and the *products* compared, on skiable gradients
only (32 167 pixels).

| layer | min correlation vs GLO-30 | p95 abs difference |
|---|---|---|
| elevation | 0.9999 | 13.5 / 15.0 m |
| slope | 0.836 | 7.6 / 6.7° |
| sky view factor | — | 0.050 / 0.038 |
| insolation Nov–Apr | 0.981 | 116 / 93 kWh/m² (23 / 21 %) |
| insolation December | 0.983 | 17.9 / 12.2 kWh/m² (66 / 50 %) |
| direct sun hours Nov–Apr | 0.965 | 223 / 180 h (29 / 22 %) |

Two findings, and they point in opposite directions:

1. **Agreement does not survive differentiation.** Elevation correlates at
   0.9999 and slope, built from those same pixels, at 0.836.
2. **Bias is negligible, spread is not.** The December median difference is at
   worst 0.3 kWh/m², but at the 95th percentile the December figure moves by
   50–66 % of its own value depending on which open DEM was used.
3. **The ranking survives.** 85–95 % of the top tenth of terrain is the same
   ground whichever DEM is used (Spearman 0.955–0.977).

Operationally: screen sites with this, on any of the three DEMs. Do not sign off
one site's December number on it without a horizon survey or a local DEM.

## 26. Weather at this scale

ERA5-Land is ~9 km and ERA5 ~31 km against a 6 km window spanning 1 867 m of
relief, so reanalysis here is a regional season descriptor, not a site record.
ERA5-Land returns no precipitation at this point through the archive API, so
snowfall and precipitation come from ERA5 and are labelled separately rather
than silently summed to zero. The published Kazhydromet seasonal outlook
(issued 16 November 2026) is oblast-level with no mountain zone.

## 27. What Part III still cannot settle

`outputs/kz_project/tables/local_measurements_required.csv` lists eight
quantities with the measurement each needs and why orbit cannot supply it,
including the three that Part III itself created the case for: a site-specific
December sun figure (section 25), mid-winter snow statistics on shaded ground
(section 23), and whether two gentle benches can be joined by a lift
(section 19).

---

# Part IV — the study area, re-derived and then hand-drawn

Parts I–III ran on a rectangle the author chose. Part IV replaces it twice: once
with a rectangle derived from the operator's own general plan, and once more with
a boundary drawn over imagery. Several Part III numbers do not survive that, and
section 31 lists each one that is withdrawn.

## 28. Two published sources, and the 70 % that belongs to snowmaking

Sheet 3 of the Kazakh Tourism Development general plan, *«Генеральный план
горнолыжного курорта Almaty Superski»*, states **16 lifts**, a difficulty split
of **10.6 % green / 50.3 % blue / 22.7 % red / 16.4 % black**, 60 km of runs,
10,000 skiers a day, 9,000,000 tourists a year, and that **70 % of runs will be
equipped with snowmaking**. Press reporting of the April 2026 statement gave
**17 lifts** and "about 70 % of runs green and blue", which Parts II and III used.

Green and blue on the operator's own sheet sum to **60.9 %**, not 70 %. The same
70 % appearing in the sheet against snowmaking makes a conflation the most
economical explanation, but the April text was not re-read for this release — a
search of the primeminister.kz archive reached only as far back as October 2026 —
so the press figure is **not disproved, only contradicted by a later and more
detailed source**. `config.py` therefore carries both:

```python
PROJECT_DIFFICULTY_PLAN  = {"green": .106, "blue": .503, "red": .227, "black": .164}
PROJECT_GREEN_BLUE_SHARE = 0.609          # default: the operator's own sheet
PROJECT_GREEN_BLUE_SHARE_PRESS = 0.70     # carried for comparison
PROJECT_LIFTS = 16 ; PROJECT_LIFTS_PRESS = 17
PROJECT_SNOWMAKING_SHARE = 0.70
```

`operating_area_piste_feasibility.csv` reports every demand figure twice, once
per source, and names the source in a column. Nothing downstream picks silently.

## 29. Re-deriving the rectangle from control points

The general-plan sheet is a perspective panorama: no projection, no scale bar, no
graticule. It cannot be georeferenced, because an affine or polynomial transform
assumes a plan view. **Nothing in this release is traced from it.**

What it does carry is named features, and those can be located independently.
Seven labels on the sheet were resolved against OpenStreetMap peaks, saddles and
places, plus this project's own plateau reference point:

| sheet label | OSM feature | lon, lat | ele |
|---|---|---|---|
| MEDEU | place, suburb | 77.05757, 43.15944 | — |
| KOKGAILAU PLATEAU 1951 m | project reference point | 77.00433, 43.14239 | — |
| THREE BROTHERS ROCKS | peak «Три брата» | 77.01337, 43.12687 | 2860 |
| MOUNTAIN KUMBEL 3250 m | peak «Qumbel» | 77.03130, 43.11934 | 3221 |
| KUMBELTAU RANGE 3500 m | peak «Qumbeltau» | 77.04056, 43.08490 | 3618 |
| KIMASAR | saddle «Кімасар» | 77.08281, 43.17116 | 2080 |
| SHYMBULAK | landuse=winter_sports | 77.09312, 43.12275 | — |

The `superski` rectangle is the envelope of those points plus a 1.5 km working
buffer: 76.955–77.095° E, 43.078–43.172° N, 125 km², 389 × 358 at 30 m.

The rectangle it replaces failed three tests against the same control points.
Kumbeltau (3,618 m), Shymbulak and the Kimasar saddle all fell outside it; **37.1 %**
of it lay below 1,900 m, the elevation of the base village on the plan; and
**0 ha** of it reached above 3,400 m, where the plan puts a top station. In the
plan's 1,900–3,400 m operating band the old rectangle held 4,117 ha against
**8,847 ha** in the new one, while the ground below the village grew only from
2,431 to 2,592 ha. The replacement adds relevant terrain, not margin.

Horizon sampling was raised to **72 azimuths** and sunshine duration to a
**10-minute** step for this area, affordable because it is a third of the
cluster's size.

## 30. The hand-drawn operating boundary

A rectangle is a compute grid, not a site. The reporting boundary is a polygon of
**24 vertices** digitised over satellite imagery in Google Earth and exported as
KML, held at `qgis/operating_area.geojson` in EPSG:4326.

`src/operating_area.py` is the whole contract. It loads the polygon, repairs a
self-intersection with a zero-width buffer if one is present and refuses anything
that is not a single valid `Polygon`; derives a buffered, outward-snapped compute
bbox from it; rasterises it onto any analysis grid with `rasterio.features`; and
returns a provenance sentence that every figure caption and table carries, so a
reader never has to ask which boundary a number came from. `is_draft()`
distinguishes a machine-generated starting shape from one a human has drawn.

`src/pipeline_operating_area.py` runs everything the boundary decides —
shape, the comparison against two same-area reconstructions, gradient classes,
piste feasibility under both published mixes, monthly sun, monthly snow with its
coverage audit, and the three-panel figure — and rewrites eight tables. Redrawing
the polygon and re-running that one script is the entire update path; terrain,
horizon, insolation and sunshine hours are not recomputed, because the boundary
cannot change them. The boundary must therefore lie inside the compute rectangle,
and the script fails loudly if it does not.

The boundary encloses **1,776 ha**, which is **174 %** of the 1,022 ha the
operator states. That gap is not an error in either number: 1,022 ha is a stated
territory with no published coordinates, and this polygon is a reading of the
*operating area*, which may legitimately extend beyond a land allocation. It is
recorded as a difference, not reconciled away. **It is not an official boundary.**

### What the boundary is worth

A drawn boundary is only interesting if it beats what a rule would pick, so every
number is reported against two reconstructions of exactly the same area: **A**, a
disc on the plateau, which uses no terrain information, and **B**, the gentlest
ground within 3.5 km, which is the most favourable placement available and
therefore the right adversarial reference.

| | drawn | A, disc | B, gentlest |
|---|---|---|---|
| pieces | 1 | 1 | 49 |
| elevation | 1775–3291 m | 1569–3002 m | 1334–3208 m |
| vertical | **1516 m** | 1432 m | 1874 m |
| median slope | 28.8° | 29.5° | 21.0° |
| green/blue | 364 ha (20.5 %) | 318 ha (17.9 %) | 738 ha (41.6 %) |
| green/blue pieces | 141 | 206 | 352 |
| largest gentle field | **182 ha (50 %)** | 149 ha (47 %) | 209 ha (28 %) |

B wins on raw gentle hectares and loses on all of them being somewhere else: its
largest field holds 28 % of its own gentle ground. The drawn boundary takes more
gentle ground than the disc, more vertical, and keeps half of its gentle ground in
one field. Connectivity is the quantity that separates the three, and it is the
one a lift network actually consumes.

## 31. What Part III claimed that Part IV withdraws

* **"The implied green/blue area is up to 101 % of the gentle ground that exists."**
  Withdrawn. It combined the superseded footprint A with the conflated 70 %. On
  the drawn boundary and the operator's own 60.9 %, the same arithmetic gives
  **30–50 %** depending on assumed piste width, and **35–58 %** on the press
  figure. The easy-terrain budget is not the binding constraint.
* **"The gentle ground exists; it is not in one place."**
  Withdrawn as stated. Inside the drawn boundary half of the gentle ground is a
  single 182 ha field. Fragmentation is a property of the slope-optimised
  placement, not of the site.
* **"Where the 1,022 ha is placed moves mid-winter sun by 3.9×."**
  Narrowed. The spread between placements is real, but the drawn boundary's
  December median is 110 h with **168 h on its green/blue ground**: the gentle
  shelves are sunnier than the site average, not darker.
* **"In December only 43.2 % of the window qualifies, median one valid
  observation."** Superseded by the boundary's own audit: **51.9 %** on a median
  of **5**, biased **+42.5 kWh/m²** sunnier and **4.0°** gentler. March is sound at
  97.9 % on a median of 24, bias +1.3 kWh/m² and −0.2°.
* **17 lifts and about 70 % green and blue.** Superseded by the general plan; see
  section 28. Both figures remain in `config.py` under their source.

Sections 25 (DEM propagation) and 24 (comparable operating areas) are unaffected:
both were computed on the project window and are reported as such.

## 32. What Part IV still cannot settle

The boundary is one person's reading of imagery. It is not surveyed, not official,
and 174 % of the stated territory; a published GIS layer would replace it in one
file. Neither it nor any rectangle here establishes where a lift may legally be
built: the site lies against Ile-Alatau National Park, and no protected-area
geometry is carried in this release. Whether the 182 ha gentle field can actually
be served by the same lift that serves the upper mountain is a question about
alignment and vertical, not about the terrain statistics computed here, and
section 27's list of measurements that orbit cannot supply still stands in full.
