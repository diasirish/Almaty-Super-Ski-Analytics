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
| 3 | **`notebooks/06_operating_boundary.ipynb`** | the current study area and why it moved; renders on GitHub | 10 min |
| 4 | `METHODS.md` §31 | **what the project withdrew about itself** | 5 min |

If you read only one file, read §31. It is the list of claims an earlier version
of this project made and later retracted, and it is the fastest way to know which
of your own memories of this work are out of date.

---

## 3. Where each conclusion lives

| Conclusion | Notebook | Tables |
|---|---|---|
| Exposure beats elevation for snow | `03` §1 | `outputs/tables/` |
| ±10 days of timing ≈ 33 pp of spring snow | `03` §4 | `outputs/tables/spring_2027_scenarios.csv` |
| December is terrain shading, not day length | `01` §3 | `outputs/tables/` |
| Energy and hours of sun rank terrain differently | `04` §3 | `outputs/cluster/tables/` |
| The skiing window: 4 h in December, 9 h in March | `04` §4–5 | `outputs/cluster/tables/` |
| **Gentle ground: 364 ha, half of it one 182 ha field** | **`06` §3** | `outputs/superski/tables/operating_area_vs_reconstructions.csv` |
| **60 km of runs fits, using 30–50 % of gentle ground** | **`06` §4** | `operating_area_piste_feasibility.csv` |
| **The gentle ground is the sunny ground** | **`06` §5** | `operating_area_sun_by_month.csv` |
| **December snow map covers only 52 % of the site** | **`06` §6** | `operating_area_snow_by_month.csv` |
| DEM agreement does not survive differentiation | `05` §6 | `outputs/kz_project/tables/dem_propagation.csv` |
| Kok Zhailau vs Shymbulak vs Oi-Qaragai | `05` §5 | `three_area_matched_differences.csv` |

---

## 4. What is current, and what is not

**Four study areas exist and they are not interchangeable.** Every script and
notebook pins one with `KZ_AREA`; outputs go to a separate subtree per area, so
they never collide.

| `KZ_AREA` | What | Used by | Status |
|---|---|---|---|
| `superski` | 125 km², derived from the operator's general plan | **nb 01, 02, 03, 06** and `pipeline_operating_area.py` | **current** |
| `cluster` | 404 km², the whole mountain cluster | nb 04 | current |
| `kz_project` | 42 km² window around the plateau | nb 05 | current, for the validation work only |
| `kok_zhailau` | 69 km², the author's first guess | nothing | **retired** — see nb 06 §1 |

Every notebook now runs on a current area. Notebooks 01–03 were moved onto the
125 km² extent and re-executed, so the numbers in README findings 1–3 are the
ones this area produces, not the ones the first rectangle produced. The old run
is still in `outputs/geotiff|png|tables/` so the move can be audited, but nothing
regenerates it and notebook 06 §7 lists what it superseded.

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
| horizon buffer | 6 km | terrain included beyond the area when ray-marching |
| reference season | 2022/23 | the single season insolation is quoted for |
| piste width | 30 / 40 / 50 m | never one assumed value; all three always carried |

**Two published figures are disputed and the project refuses to pick silently:**
the operator's general plan says **16 lifts** and **60.9 %** green and blue (its
own 70 % is *snowmaking*); press reporting of the April 2026 statement said
**17 lifts** and "about 70 %". Both are in `config.py`, both are reported, and
every table names which one it used. `METHODS.md` §28.

---

## 6. File map

```
README.md          the results, written for a reader who will not run anything
METHODS.md         every threshold, source, formula and limit.
                     Parts I–III = the original study
                     Part IV §28–32 = the extent correction and what it withdrew
ORIENTATION.md     this file
qgis/              the boundary, plus a layer pack and a one-paste QGIS loader
                     operating_area.geojson   <- the boundary. One file.
notebooks/         narrative; each pins its own KZ_AREA. .py twins are the
                   jupytext source — diff those, not the .ipynb
src/               the library. Nothing is computed twice:
                     config.py                every tunable number, 4 study areas
                     grids.py                 the UTM grid each raster lives on
                     dem.py                   DEM, slope, aspect, horizon, sky view
                     insolation.py            clear-sky ENERGY (pvlib)
                     sunhours.py              hours of DIRECT sun — a different question
                     s2.py / snow.py          Sentinel-2 windows, NDSI, frequency, bias
                     operating_area.py        the boundary: load, mask, provenance
                     footprint.py             the two machine reconstructions
                     ski_terrain.py           BC gradient classes, piste arithmetic
                     resorts.py               one comparison rule for all three places
                     dem_validation.py        rerun the whole chain on NASADEM + ALOS
                     reuse_cache.py           slice one area's scene cache onto another
                     viz.py                   all map styling, one place
                   entry points:
                     pipeline_terrain.py      terrain + insolation for one area
                     pipeline_sun.py          sunshine hours for one area
                     pipeline_operating_area.py   everything the boundary decides
                     build_brief.py / build_demo.py   the two PDFs
outputs/<area>/    geotiff/ png/ tables/ — one subtree per study area
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

`cluster` must be built before `superski` and `kz_project`: those two slice its
Sentinel-2 cache rather than downloading the scenes again.

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

`METHODS.md` §8 and §32 list what would have to be measured on the ground, and
why orbit cannot supply it.

---

## 9. Not done

Three pieces of work were scoped and deliberately set aside:

1. **Demand forecast and audience structure** — beginners against advanced.
   The gradient half exists (nb 05 §2, nb 06 §4); the demand half does not.
2. **Lift capacity and queueing** — persons/hour against piste area, comfortable
   skier density per hectare, peak-weekend bottlenecks. Blocked on per-lift
   capacity, which is not published.
3. **Econometric attendance forecast to the 2028/29 opening.** Only a handful of
   annual data points are open, so a regression would produce standard errors
   that cannot be trusted. A structural model with sourced parameter ranges is
   the honest version, and that was the open question when work stopped.
