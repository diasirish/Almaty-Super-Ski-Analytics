# METHODS

**Almaty SuperSki ski terrain analytics — an independent open-data case study**
Dias Irishev · Geo & Weather Data Scientist, Almaty
Release date: 24 November 2026

Everything below is reproducible from the code in `src/` and the six notebooks.
Every number quoted in `README.md` and in the two PDFs comes from a CSV written
by that code into `outputs/superski/tables/` or `outputs/cluster/tables/`.

This file is **what is done with the data**: formulas, thresholds, masks,
validation and limits, in 22 sections. **[`DATA.md`](DATA.md) is where the data came from** —
every dataset with its endpoint, resolution, epoch, projection, datum, licence
and the cost of relying on it. Each source is named below where it is used and
documented in full there.

---

## 1. Scope and standing

This is an independent study built from open data and the author's own code. It
is not commissioned by, affiliated with, or endorsed by any resort operator,
design office or public body, and it contains no commercial or NDA material.

**No official boundary for this project has been published.** Kazakh Tourism
Development states a territory of 1,022 ha and gives no coordinates; the
government statements describe infrastructure in detail and give no geometry.
The boundary analysed here is therefore the author's own reading of the
operating area from imagery, and nothing in this release should be read as
describing a planned resort. Resort limits, lift alignments and designed pistes
require official GIS layers.

---

## 2. The study area

### 2.1 The boundary

The study area is a polygon of **24 vertices**, digitised by hand over satellite
imagery in Google Earth, exported as KML and held at
`qgis/operating_area.geojson` in EPSG:4326. **Every figure reported for the
operating area is masked to it.**

| | |
|---|---|
| area | **1,776 ha** (1,775.5 ha rasterised at 30 m) |
| perimeter | 23.19 km |
| bounds (W, S, E, N) | 76.96202, 43.09839, 77.04080, 43.14586 |
| elevation | 1,775 – 3,291 m, median 2,568 m |
| vertical | 1,516 m |
| median slope | 28.8° |
| median sky view factor | 0.901 |
| connected components | 1 |
| share of the stated 1,022 ha | **174 %** |

`src/operating_area.py` is the whole contract. It loads the polygon, repairs a
self-intersection with a zero-width buffer if one is present and refuses
anything that is not a single valid `Polygon`; derives a buffered,
outward-snapped compute bbox from it; rasterises it onto any analysis grid with
`rasterio.features`; and returns a provenance sentence that every figure caption
and table carries, so a reader never has to ask which boundary a number came
from. `is_draft()` distinguishes a machine-generated starting shape from one a
human has drawn.

`src/pipeline_operating_area.py` runs everything the boundary decides — shape
and contiguity, gradient classes, piste feasibility under both published mixes,
monthly sun, monthly snow with its coverage audit, and two figures — and
rewrites six tables. **Redrawing the polygon and re-running that one script is
the entire update path**; terrain, horizon, insolation and sunshine hours are not
recomputed, because the boundary cannot change them. The boundary must therefore
lie inside the compute window, and the script fails loudly if it does not.

The 174 % gap against the stated territory is not an error in either number.
1,022 ha is a stated territory with no published coordinates; this polygon is a
reading of the *operating area*, which may legitimately extend beyond a land
allocation. It is recorded as a difference, not reconciled away. **It is not an
official boundary.**

### 2.2 The working window and the grids

Rasters need a margin: hillshade needs surroundings, the horizon needs terrain
to hit, and a map needs context around its subject. The compute rectangle is
therefore the boundary's own envelope plus the **1 km working margin** that
`operating_area.bbox()` returns — nothing more, and never a reporting unit.

| Item | Value |
|---|---|
| WGS84 bounding box (W, S, E, N) | 76.950, 43.085, 77.055, 43.155 |
| Working projection | EPSG:32643 (UTM zone 43N) |
| Terrain / insolation grid | 292 × 267 cells at 30 m |
| Sentinel-2 / snow grid | 437 × 400 cells at 20 m |
| Grid extent | 658 530 – 667 290 E, 4 772 070 – 4 780 080 N |
| Grid area | **70.17 km²** (8.8 × 8.0 km) |
| Geodesic area of the WGS84 rectangle | 66.45 km² |
| Elevation range | 1 382 – 3 627 m |
| The boundary inside it | 17.8 km² = **25 %**, margins 1.0 – 1.7 km per side |
| Plateau reference point | 77.00433° E, 43.14239° N (a QA landmark, not a centre) |

`boundary_vs_window.csv` states what is inside the boundary and what is only
margin, so the distinction can be checked rather than trusted.

The west edge is clipped to the cluster rectangle's own west edge so that the
two 20 m grids stay pixel-aligned and the Sentinel-2 cache can be sliced rather
than re-downloaded (section 16).

**Why 70.17 km² and not 66.45 km².** The analysis grid is the **axis-aligned UTM
bounding box of the WGS84 rectangle**, snapped outward to whole cells. Meridian
convergence at 77° E (≈2° east of the zone's central meridian) is about 1.4°, so
the projected rectangle is slightly rotated and its axis-aligned bounding box is
larger than the rectangle itself. The whole difference is that rotation plus the
outward snap. Both figures are reported; statistics are computed on the grid.
Each edge of the WGS84 rectangle is sampled at 200 points before projection, so
the bounding box captures the curved projected edges exactly rather than only the
four corners.

### 2.3 How the operator's general plan was read

Sheet 3 of the Kazakh Tourism Development general plan, *«Генеральный план
горнолыжного курорта Almaty Superski»*, is a perspective panorama: no
projection, no scale bar, no graticule. It cannot be georeferenced, because an
affine or polynomial transform assumes a plan view. **Nothing in this release is
traced from it.**

What it does carry is named features, and those can be located independently.
Seven labels were resolved against OpenStreetMap peaks, saddles and places:

| sheet label | OSM feature | lon, lat | ele |
|---|---|---|---|
| MEDEU | place, suburb | 77.05757, 43.15944 | — |
| KOKGAILAU PLATEAU 1951 m | project reference point | 77.00433, 43.14239 | — |
| THREE BROTHERS ROCKS | peak «Три брата» | 77.01337, 43.12687 | 2860 |
| MOUNTAIN KUMBEL 3250 m | peak «Qumbel» | 77.03130, 43.11934 | 3221 |
| KUMBELTAU RANGE 3500 m | peak «Qumbeltau» | 77.04056, 43.08490 | 3618 |
| KIMASAR | saddle «Кімасар» | 77.08281, 43.17116 | 2080 |
| SHYMBULAK | landuse=winter_sports | 77.09312, 43.12275 | — |

These located features are what the boundary was drawn against. They are not a
boundary themselves: an envelope of them would reach to the city edge at Medeu
and Kimasar, which is why the line was drawn by hand on imagery instead.
Notebook 06 section 1 carries the table and the arithmetic.

### 2.4 The cluster area

Notebook 04 works on a second, wider area, for the questions that are about the
mountain range rather than the site: where the radiation is, how the existing
lift network sits in the terrain, and the cross-checks against Landsat and MODIS.

`src/config.py` defines `STUDY_AREAS` and reads `KZ_AREA` from the environment
before anything else is configured. Each area gets its own output subtree, so
runs cannot overwrite one another:

| `KZ_AREA` | bbox (W, S, E, N) | grid | area | outputs |
|---|---|---|---|---|
| `superski` | 76.950, 43.085, 77.055, 43.155 | 292 × 267 @ 30 m | 70.17 km² | `outputs/superski/` |
| `cluster` | 76.950, 43.070, 77.200, 43.240 | 647 × 694 @ 30 m | 404.12 km² | `outputs/cluster/` |

Notebooks 01, 02, 03, 05 and 06 pin `superski`; notebook 04 pins `cluster`. The
Sentinel-2 window cache is keyed by a grid fingerprint
(`<xmin>_<ymin>_<w>x<h>_<res>m`), so the two areas keep separate caches and
neither invalidates the other.

The cluster rectangle is the smallest round bounding box containing every place
the government statements name for the cluster, as located in OpenStreetMap:

| Place | Source | Stated role |
|---|---|---|
| Shymbulak | primeminister.kz, 24 Apr 2026 | modernisation, stage 1; first of seven cable car lines from May 2026 |
| Butakovka gorge | primeminister.kz, 24 Apr 2026 | development, stage 1 |
| Kimasar gorge | primeminister.kz, 24 Apr 2026 | development, stage 1 |
| Pioneer | primeminister.kz, 24 Apr 2026 | stage 2 from 2027, to be linked by cable car |
| Oi-Qaragai | primeminister.kz, 24 Apr 2026 | stage 2; gondola and chairlift already commissioned |
| Kok Zhailau, Kumbel | the 18 Nov 2026 board release | 60 km of runs, 16 lifts, launch December 2028 |

It is **derived, not given**, and it is not a resort boundary either.

---

## 3. Terrain

**Source.** Copernicus DEM GLO-30, tiles
`Copernicus_DSM_COG_10_N43_00_E076_00_DEM` and `...E077_00_DEM`, from the AWS
Open Data registry (`https://copernicus-dem-30m.s3.amazonaws.com`). Vertical
datum EGM2008. Licence: free use with attribution to the Copernicus Programme /
ESA.

**Processing.** Tiles merged, then reprojected to EPSG:32643 at 30 m by bilinear
resampling. A second DEM is built on a grid buffered by 6 km for the horizon
search.

**Slope and aspect.** Horn (1981) 3 × 3 operator. Aspect is the direction of
steepest descent, degrees clockwise from **true** north. Because aspect is
computed after projection, the ~1.4° grid convergence is already removed.

**Horizon.** For each of **72 azimuths (5° spacing)** a ray is marched outward to
6 km over the buffered DEM, sampling elevation by bilinear interpolation, and the
maximum angular elevation is kept. Earth curvature is applied as a drop of
d² / (2 R_eff) with R_eff = 7/6 × 6 371 km (standard atmospheric refraction). The
cluster area uses 36 azimuths, which is what its size affords.

**Sky view factor.** Dozier & Frew (1990), for a tilted surface:

> V_d = (1/2π) ∫₀²ᵖ [ cos β · sin²H_φ + sin β · cos(φ − A) · (H_φ − sin H_φ cos H_φ) ] dφ

with β the slope, A the aspect, and **H_φ the horizon angle measured from the
zenith**. In each azimuth H_φ is the smaller of the terrain horizon and the slope
plane's own horizon, so a surface never sees sky below its own plane.

### Faster horizons

The ray-march uses a geometrically growing step (30 m, ×1.02 per step, capped at
120 m) instead of a uniform 30 m. The angular size of a terrain cell falls as
1/distance, so uniform stepping heavily oversamples the far field. Validated
against uniform 30 m stepping on real terrain: **2.4× fewer samples, mean
difference −0.02°, p99 |Δ| 0.45°, max |Δ| 1.24°**. Setting
`HORIZON_STEP_GROWTH = 1.0` restores uniform stepping exactly.

### Validation (`outputs/superski/tables/qa_terrain_validation.csv`)

| Test | Expected | Computed |
|---|---|---|
| Synthetic 20° planes, 8 aspects | slope 20.00°, aspect as constructed | exact to 0.01° in all 8 cases |
| SVF, unobstructed plane, β = 0/20/40° | (1 + cos β)/2 = 1.0000 / 0.9698 / 0.8830 | 1.0000 / 0.9698 / 0.8830 |
| SVF, flat pixel inside a uniform 30° skyline | cos²30° = 0.7500 | 0.7500 |

**Resulting values** over the window: median slope 31.0°; median sky view factor
0.881 (range 0.577 – 0.999); median horizon elevation across azimuths 15.1°.
Inside the boundary: median slope 28.8°, median sky view factor 0.901.

---

## 4. Clear-sky insolation

**Model.** `pvlib` 0.16.1, Ineichen–Perez clear sky with the monthly Linke
turbidity climatology bundled with pvlib. Solar position from
`pvlib.solarposition.get_solarposition` at the window centroid; the window is
8.8 km wide, so the within-grid variation in solar position is below 0.05° and is
neglected.

**Time stepping.** 30-minute intervals, evaluated at interval mid-points, in
Asia/Almaty (UTC+5, no DST). Only steps with solar elevation above 0.5°
contribute.

**Altitude.** Clear sky is computed at **seven altitude levels** spanning the
grid's elevation range and interpolated per pixel by elevation, so the 2.2 km of
relief is not collapsed to a single atmosphere. Pressure from
`pvlib.atmosphere.alt2pres`.

**Plane-of-array components.**

| Component | Formula | Assumption |
|---|---|---|
| Direct | DNI × cos(AOI), zeroed where the sun is below the ray-marched horizon or behind the slope | terrain shading resolved at 30 m and 5° azimuth |
| Diffuse | DHI × SVF | **isotropic sky.** Real skies are brighter near the sun and near the horizon; an isotropic model under-estimates diffuse on slopes facing the sun and over-estimates it on slopes facing away |
| Reflected | GHI × α × (1 − SVF) | **α = 0.50, fixed.** The terrain configuration factor is approximated by (1 − SVF), which assumes surrounding terrain is an isotropic reflector at the mean surface albedo |

**Why α = 0.50, and why no conclusion depends on it.** The winter surface here
ranges from fresh snow (≈0.8) through old snow, bare rock and conifer (≈0.1). A
single seasonal value is a deliberate simplification. Its weight is small: in the
2200–2300 m band over March–April the median reflected term is **25.0 kWh/m²**
against **312.4 kWh/m²** direct, **7.0 %** of the total. More directly, the
exposure contrast in that band is **identical whether it is computed on total
insolation or on direct beam alone** — 0.750 against 0.100 either way (March–April
2023, lowest against highest quartile, 1,846 pixels per group). The albedo cannot
be carrying the result.

**Reference periods.** The historical reference season is
2022-11-01 → 2023-04-30, matching the first fully covered snow season. Clear-sky
totals vary year to year by well under 1 %, so one reference season is used for
the December / March / November–December / January–February / March–April
rasters. The 2027 outlook is computed on 2027 calendar dates.

**What these numbers are.** A clear-sky ceiling, in kWh/m², on the plane of each
slope. Not expected irradiance: real cloud reduces them, and cloud attenuation is
not measured here.

---

## 5. Direct sunshine duration

Energy and duration answer different questions, so both are computed. A pixel
counts as sunlit at an instant when **all three** hold:

1. the sun is above the astronomical horizon,
2. the sun is above the ray-marched terrain horizon at its azimuth,
3. the slope faces the sun (cos of the incidence angle > 0).

Stepped at **10 minutes** on the study window and 15 minutes on the cluster —
finer than the 30-minute energy integration in both cases, because a duration is
more sensitive to the step. Output per pixel per month, plus a month ×
hour-of-day table of the sunlit fraction of each zone.

The two measures rank terrain differently. Over the cluster in November–April
2027 the correlation between the sunshine-hours raster and the energy raster is
**r = 0.73**, and the top-10 skiable sites by each measure share **no points at
all**. Energy maxima sit on steep (≈34°) south faces near 4 000 m, where high sun
angles on a steep plane maximise irradiance; duration maxima sit on gentler
15–20° south slopes that clear their own horizon earlier and hold the sun longer.

---

## 6. Sentinel-2 snow

**Source.** Sentinel-2 L2A surface reflectance, searched through the Element 84
Earth Search STAC API (`https://earth-search.aws.element84.com/v1`, collection
`sentinel-2-l2a`), MGRS tile **43TFH**, metadata cloud cover < 15 %.
Copernicus Sentinel data, processed by ESA.

A fallback to the Copernicus Data Space Ecosystem STAC was coded but **not
needed**: every scene in this run came from Earth Search, so there is no
collection change to declare. Had one occurred it would appear in the
`collection` and `stac_url` columns of `scene_manifest.csv`, which carry the
provenance of every scene.

**What was read.** 115 scenes — 114 across the four complete seasons (30 / 28 /
25 / 31) plus one current-season scene — collapsing to 112 unique dates, with
**0 download failures**.

**Reading.** Only the AOI window of each Cloud-Optimised GeoTIFF is read and
reprojected onto the 20 m grid: B03 (green, 10 m, area-averaged), B08 (NIR, 10 m,
area-averaged), B11 (SWIR, 20 m, bilinear), SCL (20 m, nearest). Each scene's
window is cached as a small `.npz` outside the release folder, which makes the
download resumable after a failure.

**Radiometry.** Scale and offset are read from each item's `raster:bands`
metadata and recorded per scene in the manifest. Every scene in this run uses
scale 1e-4 and offset −0.1 (processing baselines 04.00 and 05.09 – 05.13), i.e.
the post-baseline-04.00 BOA offset is applied before any index is computed.

**Snow rule.**

> snow = NDSI > 0.40 **and** B08 > 0.11 (surface reflectance),
> with NDSI = (B03 − B11)/(B03 + B11)

**Masking.** A pixel is a *usable observation* unless its SCL class is one of
no-data (0), saturated (1), cast shadow (2), cloud shadow (3), unclassified (7),
cloud medium (8), cloud high (9) or thin cirrus (10), or all three bands are
fill. Water (6) is a usable observation but can never be classed as snow.

**Threshold justification** (`ndsi_threshold_sensitivity.csv`). The rule was
re-run across NDSI ∈ {0.30, 0.40, 0.50} × B08 ∈ {0.07, 0.11, 0.15} on six
March–April 2023 scenes. Mean snow fraction of usable pixels ranges
**64.4 % – 74.6 %** across that grid; the chosen rule gives **70.2 %**. The answer
is therefore stable to about ±5 percentage points under reasonable threshold
choices — a real uncertainty, and smaller than the exposure contrast the study
reports.

**Independent check.** Scene-level agreement between this rule and the Sen2Cor
SCL snow class (11), which is produced independently by the L2A processor:
**r = 0.970** over 115 scenes, with the NDSI rule running 0.117 lower on average.

**Duplicate dates.** Scenes sharing an acquisition date are merged: a pixel is
usable if usable in any scene of that date, and snow if flagged snow in any scene
where it was usable.

**Frequency.** For a period, each season contributes equally: the per-season
ratio (snow dates / usable dates) is averaged over the seasons that have data, so
a season with many clear dates cannot outvote a cloudy one. A value is published
only where a pixel has **≥ 4 usable observations** in the period; multi-season
maps additionally require **≥ 3 seasons** of support. Over all four seasons
**99.3 %** of the window qualifies; over the spring window, 97.4 %.

**Melt-out.** The satellite brackets rather than dates the disappearance: the
last date a pixel was seen with snow, and the first usable snow-free date after
it. The midpoint is reported together with the width of the bracket. Pixels
lacking either bound are left unestimated — **37 % – 66 %** of pixels are
estimable depending on season, with median bracket widths of 5 – 12 days.

### The coverage bias, measured rather than caveated

A pixel enters a monthly map only once it has four cloud- and shadow-free
observations. Cast shadow and cloud shadow are rejected before counting, so
**shaded, steep ground loses observations exactly where the snow signal matters
most** — and in deep shade NDSI is also weakest, so a snow-covered pixel there is
more likely than average to be scored snow-free. Both effects push the measured
low-exposure frequency **down**, which means the reported exposure contrast is,
if anything, conservative.

`snow.coverage_bias` measures the skew instead of leaving it to a sentence.
Inside the boundary (`operating_area_snow_by_month.csv`):

| month | qualifying share | median valid obs | insolation skew | slope skew |
|---|---|---|---|---|
| November | 76.8 % | 17 | +19.9 kWh/m² | −2.4° |
| **December** | **51.9 %** | **5** | **+42.5 kWh/m²** | **−4.0°** |
| January | 59.6 % | 9 | +34.9 kWh/m² | −3.6° |
| February | 92.2 % | 11 | +5.1 kWh/m² | −0.7° |
| March | 97.9 % | 24 | +1.4 kWh/m² | −0.2° |
| April | 94.0 % | 14 | +3.9 kWh/m² | −0.5° |

A December snow figure here is a statement about the sunnier, gentler ~half of
the site, and is labelled as such everywhere it appears. February through April
are sound. **This applies to the sun-and-snow index in section 12 as well**: its
December and January entries carry the same skew and should be read as indicative
only.

Within March, where coverage is not the issue, the pale ground on the map is real
rather than missing: of the 1,776 ha, **37 ha (2.1 %)** lack four clear looks,
while **224 ha (12.6 %)** have data and carried snow on half the dates or fewer.
That low-frequency ground sits at a median 2,119 m against the site's 2,568 m —
it is the lower, sunnier part of the site, not a gap in the record.

---

## 7. Joining terrain to snow

Statistics that combine the two are computed on the **20 m Sentinel-2 grid**.
Terrain and insolation are resampled from 30 m to 20 m bilinearly; **aspect is
interpolated as a unit vector** (sin/cos components) rather than as degrees, to
avoid the 0°/360° wrap, and is set undefined where the interpolated vector
magnitude falls below 0.2 (opposing aspects averaging out). GeoTIFFs of terrain
products are published at their native 30 m.

**Exposure contrast.** Within each 100 m elevation band, on 15–35° slopes only,
pixels are split at that band's own 25th and 75th insolation percentiles. Holding
elevation fixed and taking quartiles within the band means the remaining
difference is an exposure effect, not an elevation effect. Group sizes and
per-group coverage are reported alongside every comparison; in the 2200–2300 m
band over the four-season spring window, coverage is 97 % in the low-insolation
quartile against 100 % in the high.

---

## 8. Gradient classes and the piste arithmetic

`src/ski_terrain.py`. Class boundaries are the percent grades of the **British
Columbia All Season Resort Guidelines, Chapter II (Mountain Resorts)**, converted
to degrees: beginner 0–15 % (0–8.5°), novice 15–25 % (8.5–14.0°), low
intermediate 25–35 % (14.0–19.3°), intermediate 35–40 % (19.3–21.8°), advanced
intermediate 40–60 % (21.8–31.0°), expert above 60 % (31.0°+). Skier densities in
the same table are that document's per-hectare ranges.

This is a published planning convention from the jurisdiction the named planners
work in. **It is not a Kazakh standard and not this project's design criteria.**
It is used only to ask whether a published mix of runs is consistent with the
ground. "Green and blue" is read as beginner through low intermediate, i.e.
grades up to 35 %.

**The arithmetic, and its one assumption.** The operator publishes a length
(60 km) and a mix but no width, and width is what turns a length into an area.
Three mean widths are carried through rather than one: 30, 40 and 50 m. Both
published mixes (section 9) are reported side by side, and
`operating_area_piste_feasibility.csv` names the source in a column. Nothing
downstream picks silently.

---

## 9. What the operator publishes, and two sources that disagree

From the board meeting of Kazakh Tourism Development on 18 November 2026, chaired
by the Prime Minister, together with the company's general-plan sheet: **60 km of
runs, 16 lifts of which 11 cableways are POMA's, a difficulty split of 10.6 %
green / 50.3 % blue / 22.7 % red / 16.4 % black, 70 % of runs equipped with
snowmaking, up to 10 000 skiers a day, 9 000 000 tourists a year, 1 022 ha of
territory with about 20 ha built on, and a launch in December 2028**, with a
mountain-village concept by BIG, timber base- and top-station structures by
Blumer-Lehmann, and Ecosign also engaged.

Press reporting of the April 2026 statement instead gave **17 lifts** and "about
70 % of runs green and blue".

Green and blue on the operator's own sheet sum to **60.9 %**, not 70 %. The same
70 % appearing in the sheet against *snowmaking* makes a conflation the most
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

Still unpublished, and therefore still absent from this release: any boundary,
any lift alignment, any station coordinate, any elevation, any capacity in
persons per hour, and any breakdown of the 60 km by difficulty.

---

## 10. What is inside the boundary

`operating_area_terrain.csv`, `operating_area_gradient_classes.csv`,
`operating_area_piste_feasibility.csv`, `operating_area_sun_by_month.csv`,
`operating_area_snow_by_month.csv`. Notebook 06 is the narrative.

**Gradient and contiguity.**

| | |
|---|---|
| ground at green/blue gradients (≤ 19.3°) | **364 ha**, 20.5 % of the boundary |
| in how many pieces | 133 |
| largest unbroken piece | **182 ha = 50 %** of all the gentle ground |
| above 31° | 39.1 % |

Contiguity is reported with `scipy.ndimage.label` because it is the result, not a
diagnostic. Quantity is not the constraint here; connectivity is, and
connectivity is what a lift network consumes. What a 30 m DEM cannot show is
whether two separate benches can be joined by a lift — a survey question, listed
as one in section 18.

**The piste arithmetic closes with room.** 60 km of runs at the general plan's
60.9 % green and blue implies 110 ha of easy piste at a 30 m mean width, 146 ha
at 40 m and 183 ha at 50 m — **30 %, 40 % and 50 %** of the 364 ha available. On
the press figure of 70 % it is **35 %, 46 % and 58 %**.

**Sun.** Median direct sun across the whole of December is **110 h** inside the
boundary, 3.6 h a day, and the bottom tenth of pixels sees **none at all**. On the
green/blue ground it is **168 h, 5.4 h a day**. The plateau faces the city, which
is north — but the gentle shelves that would carry beginner runs are not the
north-facing part of it. By March the site median is 274 h, 8.8 h a day.

**Snow.** March median detection frequency inside the boundary is **1.00** on a
median of 24 usable observations; December is 1.00 on a median of 5, over the
51.9 % of the site that qualifies at all (section 6).

---

## 11. Comparable operating areas

`src/resorts.py`. Comparing the site against the OSM `landuse=winter_sports`
polygons for Shymbulak and Oi-Qaragai would be unfair: those are 2.2 and 1.0 km²,
far smaller than either resort operates. One rule is applied to every place
instead: **an operating area is the ground within 150 m of its lift lines unioned
with the ground within 100 m of its pistes**, with lines assigned to the nearest
named place within 3.5 km.

| place | lifts | lift km | pistes | piste km |
|---|---|---|---|---|
| Shymbulak | 7 | 10.73 | 24 | 18.6 |
| Oi-Qaragai | 8 | 6.51 | 6 | 4.7 |
| unassigned | 6 | 3.81 | 2 | 1.1 |

Seven lifts at Shymbulak is an independent match to the "7 lines" in the
April 2026 statement.

Kok Zhailau has neither lifts nor pistes, because nothing is built there, so it
enters as the **drawn boundary**, rasterised onto the cluster grid. That asymmetry
is real and cannot be removed: a working resort's corridors are *where planners
already chose to build*, which is a selected sample of good terrain, while the
drawn boundary is a line round a whole mountainside.

**Holding altitude and gradient constant.** Every area is restricted to 15–35° and
compared band by 200 m elevation band, with a band reported only where that area
holds at least 50 pixels in it. Against the drawn boundary:

* **Shymbulak's corridors**: **−62 kWh/m²** of November–April energy and **−224 h**
  of direct sun over 8 shared 200 m bands spanning 1 800 – 3 400 m, and March snow detected
  **+0.018** more often. They trade sun for snow — they sit in the shade of Talgar.
* **Oi-Qaragai**: **+95 kWh/m²**, **+89 h** and **+0.301**, over only 3 shared
  bands spanning 1 800 – 2 400 m, and it sits under forest where NDSI beneath canopy is a
  known weak point. This is the least comparable number in the table and is
  labelled as such.

The median difference understates where the action is. Shymbulak's March snow
advantage is +0.018 over eight bands because five of them have both areas at
1.00; below 2 400 m the gap is large — 0.83 against 0.46 at 1 800 – 2 000 m, 0.89
against 0.65 at 2 000 – 2 200 m. The band table
(`three_area_elevation_bands.csv`) is the thing to read, not the summary.

Sun and snow do not rank these places the same way — the same result notebook 04
finds *within* one area, reappearing *between* areas.

---

## 12. The sun-and-snow index

`sunlit fraction × snow detection frequency` for the month — the share of a zone
that is, at that hour, both in the sun and (on four seasons of satellite record)
usually snow-covered. **A screening index, not a forecast.** It multiplies a
clear-sky geometric quantity by an empirical frequency; it says nothing about
whether a given day will be clear, and nothing about snow depth.

On the existing lift corridors in the cluster the daily window with over half the
corridor in sun runs **10:00–14:00 in December** (peak 69 % sunlit at noon) and
**08:00–17:00 in March** (100 % at midday). The index peaks in **February around
12:00**, where 96 % sunlit meets a 100 % snow-detection frequency.

---

## 13. The 2027 outlook

Three separate things, deliberately kept apart.

**1. Clear-sky insolation for 2027.** Deterministic solar geometry with
climatological turbidity, computed on 2027 calendar dates. This is the only part
of the outlook that is a calculation rather than an analogue.

**2. Spring timing scenarios.** No forecast of 2027 snow cover is made, because
nothing in this data supports one. Instead the four-season spring record is
re-cut against three calendar windows — 11 March → 20 April (the historical
analogue), the same window ten days earlier, and ten days later — and the three
maps are compared **on the pixels observed in all three** (40.38 km², 87.2 % of
skiable terrain). That isolates the effect of timing from the effect of coverage.
The median detection frequency moves 0.93 → 0.89 → 0.74 across the range, an
18-percentage-point swing. **No probabilities are attached**: assigning one would
need a calibrated and verified model, which this is not.

**3. Published seasonal outlooks**, transcribed from the primary documents and
stored in `docs/seasonal_outlooks.json`:

* **Kazhydromet**, *Сезонный прогноз погоды, декабрь 2026 – февраль 2027*, issued
  16 November 2026, retrieved 19 November 2026
  ([PDF](https://www.kazhydromet.kz/uploads/files_calendar/13401/file/6afacdf27e503sp-na-zimu-2026-2027-gg-ot-16-11-2026g.pdf),
  [landing page](https://www.kazhydromet.kz/ru/weather/konsultativnyy-prognoz-pogody-na-sezon)).
  Advisory, issued for 17 oblasts, normals 1991–2020, analogue years December 2005
  and January–February 2026. For the Almaty area: December temperature above
  normal by 1–2 °C over most of the country (near normal in the east of Almaty
  oblast), precipitation near normal nationwide; January temperature above normal
  by 1–2 °C, precipitation below normal in the northern half of Almaty oblast;
  February temperature above normal by 1–3 °C, precipitation above normal over
  most of the country.
* **C3S multi-system seasonal forecast**, November 2026 issue (1 November
  initialisation, graphics published 10 November 2026 12 UTC), retrieved
  19 November 2026. Published highlights: ENSO expected to peak around the end of
  2026, with eastern Asia among the wetter-than-average regions. **The C3S anomaly
  charts render client-side and no Central Asia value could be read
  programmatically on the retrieval date**; the exact chart URLs are recorded in
  `docs/seasonal_outlooks.json` so a reader can check them directly. No anomaly
  value is invented here.

**Scale caveat.** Both outlooks are warm-leaning at a scale of hundreds of
kilometres. Almaty oblast spans roughly 500 – 5 000 m; a single oblast statement
cannot be read as a forecast for a site that itself spans 1 775 – 3 291 m, and
neither outlook forecasts snow depth.

---

## 14. Validation: does the DEM choice change the answer?

`src/dem_validation.py`. Comparing elevations is the half of a DEM check that
flatters every product. The planning reads slope, horizon, insolation and
sunshine hours, so the **whole chain** — slope, aspect, ray-marched horizon, sky
view factor, clear-sky insolation, direct-sunshine duration — was rebuilt on
NASADEM and ALOS World 3D-30m and the *products* compared, on skiable gradients
only (**49 883 pixels** of the window).

| layer | min correlation vs GLO-30 | p95 abs difference (NASADEM / ALOS) |
|---|---|---|
| elevation | 0.99992 | 13.4 / 11.1 m |
| slope | 0.827 | 7.5 / 5.9° |
| sky view factor | 0.905 | 0.047 / 0.034 |
| insolation Nov–Apr | 0.981 | 123 / 78 kWh/m² (23 / 17 %) |
| insolation December | 0.982 | 19.8 / 10.6 kWh/m² (59 / 37 %) |
| direct sun hours Nov–Apr | 0.970 | 202 / 148 h (27 / 18 %) |

Three findings, and they do not point the same way:

1. **Agreement does not survive differentiation.** Elevation correlates at
   0.99992 and slope, built from those same pixels, at 0.827.
2. **Bias is negligible, spread is not.** The December median difference is at
   worst 0.2 kWh/m², but at the 95th percentile the December figure moves by
   **37–59 %** of its own value depending on which open DEM was used.
3. **The ranking survives.** **84–94 %** of the top tenth of terrain is the same
   ground whichever DEM is used (Spearman 0.969–0.988).

Operationally: screen sites with this, on any of the three DEMs. Do not sign off
one site's December number on it without a horizon survey or a local DEM.

---

## 15. Cross-validation against independent sources

Nothing here rests on a single sensor. These checks run on the cluster area,
where the samples are largest.

### Elevation — three DEMs

| DEM | sensor and epoch | mean Δ | median Δ | σ | p95 \|Δ\| | correlation |
|---|---|---|---|---|---|---|
| NASADEM | radar, SRTM 2000, EGM96 | +0.26 m | −0.09 m | 7.40 m | 13.97 m | 0.999952 |
| ALOS AW3D30 | optical stereo 2006–2011, EGM96 | +1.92 m | +1.59 m | 7.15 m | 12.68 m | 0.999956 |

Against Copernicus GLO-30 (radar, TanDEM-X 2010–2015, EGM2008) on 449 018 cluster
pixels. The three have largely independent error sources, so agreement to a few
metres is meaningful. NASADEM reads 1.4° flatter in slope on average, consistent
with SRTM's coarser effective resolution.

### Snow — Landsat 8/9 against Sentinel-2

77 Landsat 8/9 Collection 2 Level-2 scenes (cloud < 20 %) over the four seasons,
read through the Microsoft Planetary Computer and reduced with the **same**
NDSI > 0.40 and NIR > 0.11 rule, masked with `QA_PIXEL` (fill, dilated cloud,
cirrus, cloud, cloud shadow). Landsat 7 is excluded: its scan-line corrector
failed in 2003 and the striping corrupts area statistics.

* Within Landsat, our rule against the USGS `QA_PIXEL` snow flag: **r = 0.879**.
* Against Sentinel-2, **scene-aggregate**, same date ±1 day: r = 0.820, mean
  difference +0.353.
* Against Sentinel-2, **same date and restricted to pixels both call usable**:
  **r = 0.969**, mean difference **+0.096**, per-pixel agreement **86.8 %**, over
  25 dates and 8.5 M common pixels.

The scene-aggregate comparison is unfair, and the gap between the two rows is the
lesson: each sensor was averaging over *its own* valid pixels, and Landsat's
`dilated_cloud` bit deliberately removes a wide halo. Almost all of the apparent
disagreement was the two masks covering different ground.

What remains is one-sided — Sentinel-2 calls snow on 11.4 % of common pixels where
Landsat does not, against 1.8 % the other way — which is the direction a 30 m
sensor resampled to a 20 m grid should err in, since a part-snow pixel averages
below the NDSI threshold at the coarser footprint. Landsat also crosses roughly
half an hour earlier. The two records are consistent.

### MODIS daily snow cover

MOD10A1 and MYD10A1 v061 `NDSI_Snow_Cover`, 500 m, read over the cluster area for
February–April 2023. Granules with less than half the area unclouded are dropped.
The result adds **36 days on which Sentinel-2 has no usable scene** in that
window, against 14 Sentinel-2 dates — the melt-timing signal between clear optical
dates. At 500 m over 2 km of relief this is regional context and never an answer
about an individual slope.

### A bug this found

Windowed COG reads originally computed the read window from the AOI bounds in the
**target** CRS against the **source** transform. That is correct only while the
two CRSs match — which they did for Sentinel-2 and Landsat, both EPSG:32643 — and
silently read the wrong place otherwise. MODIS is in a sinusoidal projection, and
the first MODIS run returned exactly zero snow everywhere with a valid fraction of
1.0. The read now transforms the bounds into the source CRS first (densified at
21 points per edge). Sentinel-2 and Landsat results are unaffected; this was
verified by checking the CRS of every Landsat scene used.

---

## 16. OpenStreetMap reference layers, and reusing the scene cache

**OSM.** Queried once through the Overpass API over 76.85–77.30 E, 43.00–43.25 N
and cached in `data/raw/osm/`. Licence: ODbL, © OpenStreetMap contributors.
Inside the cluster rectangle: **21 aerialway lines longer than 150 m totalling
21.1 km**, 23 lift stations, 32 mapped downhill pistes totalling 24.4 km, 63 named
peaks, 36 named saddles, and the Shymbulak and Oi-Qaragai `landuse=winter_sports`
polygons. Lift corridors are everything within 150 m of an existing line
(7.36 km²), piste corridors within 100 m (3.00 km²).

**These are the lifts that exist today.** No planned alignment is drawn anywhere
in this release, because none has been published.

**Scene cache.** `src/reuse_cache.py`, driven by `src/slice_window_cache.py`. The
20 m study window is a pixel-aligned subset of the 20 m cluster grid, so the 115
Sentinel-2 windows already read for the cluster contain every observation the
window needs. The module asserts equal resolution, equal CRS, integer pixel
offsets and containment, then slices at offset (row 487, col 11). **No pixel is
resampled.**

Verified rather than asserted: one scene (`S2B_43TFH_20231126_0_L2A`) was re-read
from the COGs onto the window grid and compared with the sliced arrays — **0
differing pixels out of 174 800** in both the snow and the validity plane.

---

## 17. Weather at this scale

One ERA5-Land cell is ~9 km across and one ERA5 cell ~31 km, against an operating
area of 17.8 km² spanning 1 516 m of relief. Reanalysis here is a regional season
descriptor, not a site record.

Daily ERA5-Land (cell elevation 2 235 m) at the plateau point via the Open-Meteo
Historical Weather API, for temperature. **ERA5-Land returns no precipitation at
this point through that API**, so snowfall and precipitation fall back to ERA5 at
~31 km and are labelled as such rather than silently summed to zero. Both grids
smooth the orography heavily and ERA5 precipitation over complex terrain carries
large errors; they say what kind of winter a season was, and are not evidence
about any individual slope.

The published Kazhydromet seasonal outlook is oblast-level with no mountain zone.

---

## 18. What this study cannot tell you

| Question | Why not | What would answer it |
|---|---|---|
| Number of ski days | A frequency is a share of **usable satellite dates**, not days of operation | continuous depth record against an operating threshold |
| Snow depth or water equivalent | Optical imagery sees the surface, not what is under it | snow pillow or ultrasonic depth sensor plus density cores, on at least one shaded and one sunny plot in the same elevation band |
| Season opening date | A 5-day revisit with cloud gaps cannot resolve a threshold crossing to the day | the same record, over several seasons |
| Mid-winter snow on shaded ground | In December only 51.9 % of the site has four clear looks, and that subset is +42.5 kWh/m² sunnier | ground observation, or Sentinel-1 SAR wet-snow retrieval to see through cloud |
| The December sun figure for one specific site | Open DEMs disagree by 37–59 % at the 95th percentile on exactly this quantity | a horizon survey from the site, or a short-baseline photogrammetric or lidar DEM |
| Real (not clear-sky) irradiance | The model is clear-sky by construction; cloud attenuation is unmeasured | two pyranometers on contrasting aspects inside the boundary |
| Snowmaking feasibility or cost | None of the governing variables is observed from orbit | wet-bulb temperature at the gun line, wind speed and direction, water yield and temperature, equipment curves |
| Avalanche hazard | Slope angle is geometry; release depends on the snowpack | snowpack profiles, wind transport and loading, mapped start and runout zones, local forecaster judgement |
| Where the beginner terrain can physically go | A 30 m DEM resolves that the gentle ground arrives in 133 pieces, not whether two of them can be joined | a design-grade survey of the gentle benches and of what can be linked by lift |
| Resort boundaries or trail alignments | Not derivable from open terrain data | official GIS layers from the project |

The full table, with why orbit cannot supply each quantity, is in
`outputs/superski/tables/local_measurements_required.csv`.

A four-season record is also far too short to support any statement about trend.

**Two further limits.** The boundary is one person's reading of imagery: not
surveyed, not official, 174 % of the stated territory, and replaceable in one file
the day the operator publishes a GIS layer. And nothing here establishes where a
lift may legally be built — the site lies against Ile-Alatau National Park, and no
protected-area geometry is carried in this release.

---

## 19. Attribution and licences

Full provenance for every source — endpoint, access terms, epoch, projection and
what it costs to rely on it — is in [`DATA.md`](DATA.md).

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
* **OpenStreetMap** — © OpenStreetMap contributors, ODbL 1.0, via the Overpass API.
* **Landsat 8/9 Collection 2 Level-2** — courtesy of the U.S. Geological Survey,
  accessed through the Microsoft Planetary Computer.
* **MODIS MOD10A1 / MYD10A1 v061** — NSIDC DAAC / NASA, via the Microsoft
  Planetary Computer.
* **NASADEM** — NASA JPL, via the Microsoft Planetary Computer.
* **ALOS World 3D-30m (AW3D30)** — © JAXA, via the Microsoft Planetary Computer.
* **Microsoft Planetary Computer** — STAC API with anonymous asset signing.
* **pvlib-python** — BSD-3-Clause.
* Analysis code and figures in this release: Dias Irishev, 2026.

The full list of sources used and of further sources worth reaching for, with
endpoints, access cost, what each adds and what it costs, is in
`outputs/cluster/tables/data_source_registry.csv`: **12 sources, 7 used here.**

## 20. Software

Python 3.12.10. Pinned versions in `requirements.txt`; the key ones are
numpy 2.5.5, rasterio 1.5.2, pvlib 0.16.1, pyproj, pystac-client, scipy, pandas,
matplotlib, reportlab.

---

## 21. Provenance of this document

This release reports one study area, the drawn polygon, and nothing else. It did
not start there. Two earlier releases reported over author-chosen rectangles —
69 km² and then 125 km² — and over two synthetic 1,022 ha footprints built by a
module that no longer exists. All of them covered ground well outside anywhere
skiing is planned, and every figure derived from them is withdrawn. Notebook 06
section 1 holds the measurement that forced the change, and the git history holds
the rest.

Nothing above is inherited from those releases without being recomputed on the
current window and masked to the current boundary.

Section 22 was added on 25 November 2026, after the rest. It answers a question
the earlier sections do not: whether the snow that is there adds up to a season
on the ground that will carry pistes. It introduced one new dataset — hourly
ERA5-Land and ERA5 — and no change to anything already published.

---

## 22. Snow sufficiency on the pistes

Added 25 November 2026. Everything above answers *where* snow is and *how often*
a pixel looked like snow. None of it answers the operator's question: will the
ground that carries pistes hold snow long enough, without breaking, and where it
will not, can the missing snow be made? This section is that question, measured
three ways.

Code: `src/snow_sufficiency.py` and `src/snow.season_span`, run by
`KZ_AREA=superski python src/pipeline_snow_sufficiency.py`. The narrative, with
every table printed and the reasoning in between, is
`notebooks/07_snow_sufficiency.ipynb`.

### 22.1 Where it is measured

Two readings of "piste ground", carried side by side rather than picking one,
both inside the drawn boundary and on the 20 m snow grid:

* **gentle**, slope ≤ 19.29° — what beginner and intermediate runs need, the
  ground section 10 counts as green/blue;
* **skiable**, 15–35° — the project's standard definition of ski terrain, which
  keeps these tables comparable with sections 11 and 12.

Both are cut into 200 m elevation bands (`SUFFICIENCY_BAND_M`). A band carrying
fewer than 100 bracketed pixels — 4 ha — is dropped rather than quoted; at this
site that drops exactly one row, the 1.6 ha sliver where the boundary's bottom
edge clips into 1,775–1,800 m. `band_elev_min_m` and `band_elev_max_m` give the
real elevation range behind every row, because the boundary cuts several bands
in half. The gentle bands sum to 361.7 ha against the 364 ha section 10 reports
on the 30 m grid: the same ground, counted on a finer mesh.

### 22.2 The observed season, and why it is a lower bound

`snow.season_span` walks one season's valid observations twice. The first pass
records, per pixel, the first and the last date with a snow detection. The
second finds the last snow-free look before the first snow, the first snow-free
look after the last snow, and counts the snow-free looks **inside** the span.

The reported `span_days` is `last_snow_day − first_snow_day`: the interval the
record actually saw snow across. It is **not** an interpolated count of
snow-covered days. With a median of 15–25 usable looks a season, interpolation
would invent days nobody observed.

That makes the span a lower bound, and the two brackets say by how much:
`median_span_upper_days` adds the onset and melt-out gaps. At the beginner band
the observed spans across four seasons are 130, 135, 130 and 93 days, and the
upper bounds 145, 167, 144 and 135. The shortest season's upper bound lands
exactly on the longest season's lower bound, so `seasons_resolved` is **false**
there: 2025/26 was the shortest of the four, the direction is certain, and four
seasons of optical satellite cannot say by how much. The envelope columns carry
what can be said — **93 to 167 days** at 1,800–2,000 m, **148 to 177** at
2,200–2,400.

**Censoring is reported, not averaged in.** Where no snow-free look exists
before the first snow detection, or after the last, the season extends past
what the record can see. At and above 2,400 m that is the normal case: averaged
over the four seasons, 0.736–0.873 of pixels are left-censored and 0.737–0.962
right-censored, and in the worst season of each band 0.872–0.990 and
0.959–1.000. So the ~171 days those bands report is the 1 November – 30 April
observation window, not a measurement. The 2,200–2,400 m band is the transition:
0.780 left-censored but only 0.390 right, so its melt-out is seen and its onset
is not. `seasons_resolved` means nothing where censoring is high, and the
column sits next to `max_left_censored_share` and `max_right_censored_share` so
it cannot be read alone.

### 22.3 Continuity: the cover was never seen to break

`breaks` counts snow-free valid observations strictly inside the span, and
`continuity` is snow looks over snow-plus-free looks inside it. Across every
band and season the median is **0 breaks** and continuity 0.97–1.00.

This is a weaker statement than it looks, and the limit is worth stating
plainly: with 15–25 looks spread over six months, the median gap between usable
observations is about twelve days, so **no thaw shorter than that is visible**.
"Never seen to break" is not "never broke". Section 22.5 measures, from an
independent dataset, what the satellite is too sparse to see.

### 22.4 The snowmaking window

Hourly ERA5-Land temperature, relative humidity and dew point, with surface
pressure and precipitation from ERA5, at the plateau reference point —
`DATA.md` §6.1 has the request and the cells. One cell, one elevation: Open-Meteo
reports 2,235 m for that point and this project's Copernicus DEM says 2,238 m,
so the two independent terrain models agree there to 3 m.

**Wet-bulb temperature** is solved from the psychrometric equation

    e_s(Tw) − e = A · p · (T − Tw),     A = 6.6 × 10⁻⁴ K⁻¹ over water

by bisection, with `e_s` from Buck (1996) and `e` from the measured relative
humidity. Pressure is carried explicitly because it moves the answer at this
altitude. Two checks are written to `wet_bulb_method_check.csv` rather than
asserted:

| compared with | median Δ | p05 … p95 | hours below −4 °C |
|---|---|---|---|
| Stull (2011) closed form, a sea-level fit | **+0.28 °C** | −0.69 … +0.49 | 8,447 here vs 8,708 |
| the same solver at sea-level pressure | **−0.30 °C** | −0.66 … −0.06 | 8,447 here vs 8,023 |

So using the familiar closed form would have over-counted the snowmaking window
by 3.1 %, and ignoring the ~800 hPa of this altitude would have under-counted it
by 5.0 %. Both are small; both are now measured.

**Thresholds.** Published wet-bulb thresholds for snow production run from about
−1 to −4 °C. López-Moreno et al. (2018) define snowmaking hours as hours with
wet bulb below −2 °C in exactly this kind of study, and equipment makers quote
about −2.5 °C to start a system. Three are carried — **−2, −4, −6 °C** — as with
piste width, rather than assuming one. The New South Wales alpine assessment
reports that *relative* changes are insensitive to which threshold is chosen,
which is the reason to show all three and quote none as the answer.

**The elevation correction is the largest assumption in this section.** The cell
sits at 2,235 m; the beginner ground is 335 m below it. Temperature is carried
down at a fixed **6.5 °C/km** (`LAPSE_RATE_C_PER_KM`, the standard atmosphere,
and also what Open-Meteo itself applies), pressure by the hypsometric formula,
and **relative humidity unchanged** — an assumption, not a measurement. This is
a model's own vertical gradient, not a measured local one, and winter inversions
in the Almaty valley break it; López-Moreno et al. studied precisely that in a
Pyrenean resort. So every downstream number is swept across ±2 °C:

| at 1,900 m | −2 °C | 0 | +2 °C |
|---|---|---|---|
| November hours below −4 °C wet bulb | 361.5 | **269.5** | 171.5 |
| December hours below −4 °C wet bulb | 633.2 | **538.8** | 441.8 |
| thaw days inside the observed season | 48.8 | **69.5** | 90.0 |
| rain-on-snow days | 5.2 | **10.8** | 17.2 |

The window survives the sweep: even 2 °C warmer than assumed, November at the
beginner ground still gives 171 hours below −4 °C. The thaw counts do not
survive it as precisely — they move by a factor of two — and are quoted with
that range. A measured local lapse rate from Kazhydromet station pairs would
replace this entirely, and that is the single cheapest improvement available to
this section.

### 22.5 Joining the two: what the weather did inside the observed season

For each band and season the window runs from that band's median first snow
detection to its median last one — not the calendar season — so the counts
answer "what happened to the snow that was actually there". Windows shorter than
14 days are dropped.

* **thaw day**: daily maximum above 0 °C at band elevation
* **freeze-thaw day**: maximum above 0 °C and minimum below it on the same day
* **rain-on-snow day**: total precipitation ≥ 1 mm with the band's daily mean
  temperature above freezing. The rain/snow split is re-made at band elevation
  rather than taken from ERA5's own, which belongs to a 31 km cell at 2,235 m
* **melting degree-days**: the sum of positive daily mean temperatures

### 22.6 What this section cannot tell you

* **No depth, no water volume, no cost.** Nothing here is a snowmaking budget.
  Production rate depends on water supply, pumping capacity and gun type, none
  of which is published for this project. ERA5-Land does carry a modelled snow
  depth and it is fetched, but it belongs to a 9 km cell at one elevation and is
  not used for any claim.
* **One reanalysis cell.** Every temperature here descends from a single point,
  spread across 1,775–3,291 m by a fixed gradient. There is no local wind, no
  cold-air pooling and no valley inversion in it.
* **The satellite cannot see short thaws**, as 22.3 says, so continuity is an
  upper bound on how continuous the cover really was.
* **Four seasons is not a climatology.** Nothing here is a forecast, and no
  probability is attached to any of it.
* Sentinel-1 SAR would see wet snow directly, through cloud and at night, and
  is the one addition that would turn "the cover was never seen to break" into
  a measurement. `DATA.md` §8 says why it is not here yet.
