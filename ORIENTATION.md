# Orientation — read this first after a break

A map of the project for someone who has not opened it in a while: what it
concluded, what it assumed, which files are current, and the shortest path back
into the logic. `README.md` is the result; this file is the route to it.

---

## 1. The project in six lines

An independent open-data study of the mountains above Almaty, built to show four
organisations working on Almaty SuperSki that the author can do their GIS,
validate their models locally and handle their weather data. It is **not**
commissioned by anyone. It measures three things on real terrain — **gradient**,
**hours of direct winter sun** and **how often snow is actually there** — and
then spends about half its length trying to break its own results.

The single most sellable finding is not a number about the mountain. It is this:
**open DEMs agree to four decimal places on elevation and fall apart once you
compute anything useful from them** — but the *ranking* of good terrain survives.
So: screen sites on open data, never sign off one site's number on it.

---

## 2. The 30-minute path back in

Do these in order. Nothing here needs the pipeline to be re-run.

| # | Open | Why | Time |
|---|---|---|---|
| 1 | `almaty-superski-gis-demo.pdf` | 4 slides, the whole argument | 5 min |
| 2 | `README.md`, "Five measured results" + findings 6–12 | every conclusion, with its number | 10 min |
| 3 | **`notebooks/06_operating_boundary.ipynb`** | the study area and the two rectangles it replaced; renders on GitHub | 10 min |
| 4 | `METHODS.md` §9 and §18 | the two published figures that disagree, and what the study cannot tell you | 5 min |
| 5 | `DATA.md` §1 and §8 | every source in one table, and the five that were costed and not used | 5 min |

If you read only one thing after the demo, read `METHODS.md` §18. It is the list
of questions this work does **not** answer, with the measurement each one needs —
the fastest way to avoid quoting a number for something it was never measuring.

---

## 3. Where each conclusion lives

| Conclusion | Notebook | Tables |
|---|---|---|
| Exposure beats elevation for snow | `03` §1 | `outputs/superski/tables/` |
| ±10 days of timing ≈ 18 pp of spring snow | `03` §4 | `spring_2027_scenarios.csv` |
| December is terrain shading, not day length | `01` §3 | `insolation_period_summary.csv` |
| Energy and hours of sun rank terrain differently | `04` §3 | `outputs/cluster/tables/` |
| The skiing window: 4 h in December, 9 h in March | `04` §4–5 | `outputs/cluster/tables/` |
| **Gentle ground: 364 ha, half of it one 182 ha field** | **`06` §3** | `operating_area_terrain.csv` |
| **60 km of runs fits, using 30–50 % of gentle ground** | **`06` §4** | `operating_area_piste_feasibility.csv` |
| **The gentle ground is the sunny ground** | **`06` §5** | `operating_area_sun_by_month.csv` |
| **December snow map covers only 52 % of the site** | **`06` §6** | `operating_area_snow_by_month.csv` |
| DEM agreement does not survive differentiation | `05` §4 | `dem_propagation.csv` |
| Kok Zhailau vs Shymbulak vs Oi-Qaragai | `05` §3 | `three_area_matched_differences.csv` |

---

## 4. What is current, and what is not

**There is one study area: the hand-drawn polygon.** Everything else is either
the working window around it or the wider cluster.

| `KZ_AREA` | What | Used by | Status |
|---|---|---|---|
| `superski` | the drawn boundary (17.8 km²) and the 70 km² working window round it | **nb 01, 02, 03, 05, 06** and `pipeline_operating_area.py` | **current** |
| `cluster` | 404 km², the whole mountain cluster | nb 04 | current |

Two rectangles were retired on 24 November 2026 and are gone from `config.py`:
the first release's 69 km² box around the plateau, and the second's 125 km²
envelope of the general-plan control points. Both reached about 3 km north of the
drawn boundary, over the dacha belt below 1,775 m, and only 14 % of the second
one was the site. Their outputs are deleted; notebook 06 §1 and `METHODS.md` §21
keep the record of why.

Deleted with them: `src/footprint.py` and the two synthetic 1,022 ha footprints
it built — a disc on the plateau and the gentlest ground within 3.5 km. Neither
was the operating area. Every number they produced is withdrawn.

**The boundary is one file.** `qgis/operating_area.geojson` — 24 vertices, drawn
by hand over imagery, **not official**. Redraw it and re-run one command; every
table, figure and PDF number follows. That is the whole update path.

---

## 5. The assumptions, in one place

These are choices, not measurements. Each one would move a conclusion if changed,
and each lives in `src/config.py`.

| Knob | Value | What it decides |
|---|---|---|
| snow rule | NDSI > 0.40 **and** B08 > 0.11 | what counts as snow at all |
| min observations | 4 per pixel per period | below this no monthly value is drawn — **this is what creates the December bias** |
| ground albedo | 0.50 | mixed snow/rock/forest; moves the reflected term |
| skiable band | 15–35° | what counts as ski terrain in every comparison |
| green/blue ceiling | 19.29° (= 35 % grade) | **BC All Season Resort Guidelines — a Canadian convention, not a Kazakh standard** |
| black threshold | > 31° | the steep class |
| cloud filter | scene cloud < 15 % | which scenes enter at all |
| horizon buffer | 6 km | terrain included beyond the window when ray-marching |
| working margin | 1 km around the boundary | how much context the compute rectangle carries |
| reference season | 2022/23 | the single season insolation is quoted for |
| piste width | 30 / 40 / 50 m | never one assumed value; all three always carried |

**Two published figures are disputed and the project refuses to pick silently:**
the operator's general plan says **16 lifts** and **60.9 %** green and blue (its
own 70 % is *snowmaking*); press reporting of the April 2026 statement said
**17 lifts** and "about 70 %". Both are in `config.py`, both are reported, and
every table names which one it used. `METHODS.md` §9.

---

## 6. File map

```
README.md          the results, written for a reader who will not run anything
DATA.md            provenance: every dataset, endpoint, resolution, epoch,
                   projection, datum and licence, plus the five sources that
                   were costed and not used. The study area is its §10
METHODS.md         every threshold, formula and limit, for the current study
                   area only. 21 sections: §2 the boundary and the window,
                   §3–7 how each layer is built, §8–12 what is measured and
                   against what, §13–17 the outlook and the validation,
                   §18 what it cannot tell you
ORIENTATION.md     this file
qgis/              the boundary, plus a layer pack and a one-paste QGIS loader
                     operating_area.geojson   <- the boundary. One file.
notebooks/         narrative; each pins its own KZ_AREA. .py twins are the
                   jupytext source — diff those, not the .ipynb
src/               the library. Nothing is computed twice:
                     config.py                every tunable number, 2 study areas
                     grids.py                 the UTM grid each raster lives on
                     dem.py                   DEM, slope, aspect, horizon, sky view
                     insolation.py            clear-sky ENERGY (pvlib)
                     sunhours.py              hours of DIRECT sun — a different question
                     s2.py / snow.py          Sentinel-2 windows, NDSI, frequency, bias
                     operating_area.py        the boundary: load, mask, provenance
                     ski_terrain.py           BC gradient classes, piste arithmetic
                     resorts.py               one comparison rule for all three places
                     dem_validation.py        rerun the whole chain on NASADEM + ALOS
                     reuse_cache.py           slice the cluster's scene cache
                     viz.py                   all map styling, one place
                   entry points:
                     pipeline_terrain.py      terrain + insolation for one area
                     pipeline_sun.py          sunshine hours for one area
                     slice_window_cache.py    give the window its S2 cache
                     pipeline_operating_area.py   everything the boundary decides
                     build_qgis_pack.py       rebuild qgis/ on the current grid
                     build_extent_review.py   the three study areas in one figure
                     build_brief.py / build_demo.py   the two PDFs
outputs/<area>/    geotiff/ png/ tables/ — one subtree per area
data/              NOT in git. Regenerated by run_all.sh (~45 min cold)
```

---

## 7. Re-running things

```bash
source .venv/bin/activate
```

Change the boundary only — seconds, no downloads:

```bash
KZ_AREA=superski python src/pipeline_operating_area.py
```

Rebuild the two PDFs from whatever the tables currently say:

```bash
python src/build_brief.py && python src/build_demo.py
```

Everything, from nothing:

```bash
./run_all.sh
```

`cluster` must be built before `superski`: the window slices the cluster's
Sentinel-2 cache rather than downloading the scenes again.

**If you move the boundary far enough that it leaves the window**, change the
`superski` bbox in `config.py` to `operating_area.bbox(poly)` and re-run from
step 1 — the pipeline fails loudly rather than reporting a clipped site.

---

## 8. What this project cannot tell you

Worth re-reading before quoting any of it to someone else.

* A snow frequency here is *the share of usable satellite dates on which a pixel
  looked like snow*. **Not** ski days, **not** snow depth, **not** a snowmaking cost.
* Insolation is **clear-sky**. There is no cloud model in it.
* The December snow figure describes the sunnier ~half of the site, because
  shaded ground fails the four-observation test more often. Measured, not hidden.
* No boundary here is official, and no planned lift alignment is drawn anywhere,
  because none has been published.
* Nothing addresses protected-area status. The site lies against Ile-Alatau
  National Park and no protected-area geometry is carried.

`METHODS.md` §18 lists what would have to be measured on the ground, and why
orbit cannot supply it.

---

## 9. Not done

Three pieces of work were scoped and deliberately set aside:

1. **Demand forecast and audience structure** — beginners against advanced.
   The gradient half exists (nb 06 §4); the demand half does not.
2. **Lift capacity and queueing** — persons/hour against piste area, comfortable
   skier density per hectare, peak-weekend bottlenecks. Blocked on per-lift
   capacity, which is not published.
3. **Econometric attendance forecast to the 2028/29 opening.** Only a handful of
   annual data points are open, so a regression would produce standard errors
   that cannot be trusted. A structural model with sourced parameter ranges is
   the honest version, and that was the open question when work stopped.
