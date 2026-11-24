# %% [markdown]
# # 06 — The operating boundary: where the study area came from, and what is inside it
#
# **Almaty SuperSki terrain analytics — an independent open-data case study**
# Dias Irishev · Geo & Weather Data Scientist, Almaty
#
# Notebooks 01–03 report a 69 km² rectangle the author chose around the plateau.
# Notebook 04 widens to the 404 km² cluster; notebook 05 narrows to a 42 km²
# project window and reconstructs the stated 1,022 ha two ways.
#
# **All four of those pick their study area by assertion.** This notebook replaces
# that twice over — first with a rectangle derived from the operator's own
# published general plan, then with a boundary drawn by hand over satellite
# imagery — and reports what is actually inside it.
#
# Everything here is computed by `src/pipeline_operating_area.py`. This notebook
# calls that module rather than reimplementing it, so there is exactly one
# implementation of every number and the PDF, the tables and this page can never
# drift apart. Redraw `qgis/operating_area.geojson`, re-run, and every figure
# below follows.
#
# > **This boundary is not official.** Kazakh Tourism Development states a
# > territory of 1,022 ha and has published no coordinates. Nothing here is
# > commissioned by, affiliated with or endorsed by any operator or public body.

# %%
import os

os.environ["KZ_AREA"] = "superski"        # must be set before importing config

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd().parent / "src"))

import footprint
import operating_area as OA
import pipeline_operating_area as PL
import ski_terrain as ST
import viz
from config import (AREA_LABEL, AREA_NOTE, HORIZON_N_AZIMUTH, INTERIM,
                    MIN_VALID_OBS, OUT_PNG, OUT_TAB, PROJECT_AREA_HA,
                    PROJECT_GREEN_BLUE_SHARE, PROJECT_GREEN_BLUE_SHARE_PRESS,
                    PROJECT_LIFTS, PROJECT_LIFTS_PRESS, PROJECT_PISTE_KM,
                    PROJECT_SNOWMAKING_SHARE, STUDY_AREAS, SUN_HOUR_STEP_MIN)
from grids import DEM_GRID

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

print(f"area        : {AREA_LABEL}")
print(f"grid        : {DEM_GRID.width} x {DEM_GRID.height} @ {DEM_GRID.res:.0f} m "
      f"= {DEM_GRID.area_km2:.0f} km2, {DEM_GRID.crs}")
print(f"horizon     : {HORIZON_N_AZIMUTH} azimuths ({360//HORIZON_N_AZIMUTH} deg)")
print(f"sun step    : {SUN_HOUR_STEP_MIN} min")

# %% [markdown]
# ## 1. Why the study area moved
#
# The rectangle notebooks 01–03 use was chosen before the operator's general plan
# was on hand. Measured against the features that plan names, it is in the wrong
# place. The plan itself is a perspective panorama — no projection, no scale bar,
# no graticule — so **nothing is traced from it**. What it carries is *named
# features*, and those can be located independently in OpenStreetMap.

# %%
CONTROL_POINTS = {
    "MEDEU":                    (77.05757, 43.15944, "OSM place, suburb"),
    "KOKGAILAU PLATEAU 1951 m":  (77.00433, 43.14239, "project reference point"),
    "THREE BROTHERS ROCKS":     (77.01337, 43.12687, "OSM peak «Три брата», 2860 m"),
    "MOUNTAIN KUMBEL 3250 m":   (77.03130, 43.11934, "OSM peak «Qumbel», 3221 m"),
    "KUMBELTAU RANGE 3500 m":   (77.04056, 43.08490, "OSM peak «Qumbeltau», 3618 m"),
    "KIMASAR":                  (77.08281, 43.17116, "OSM saddle «Кімасар», 2080 m"),
    "SHYMBULAK":                (77.09312, 43.12275, "OSM landuse=winter_sports"),
}
cp = pd.DataFrame([{"sheet_label": k, "lon": v[0], "lat": v[1], "located_as": v[2]}
                   for k, v in CONTROL_POINTS.items()])
old = STUDY_AREAS["kok_zhailau"]["bbox"]
cp["inside_old_rectangle"] = [(old[0] <= r.lon <= old[2]) and (old[1] <= r.lat <= old[3])
                              for r in cp.itertuples()]
print(cp.to_string(index=False))
print(f"\ncontrol points the superseded 69 km2 rectangle misses: "
      f"{(~cp.inside_old_rectangle).sum()} of {len(cp)}")

# %% [markdown]
# The old rectangle fails on three counts at once, and the failures point the same
# way: it sampled the ground **below** the resort and stopped short of the ground
# **above** it.

# %%
dem_old = np.load(INTERIM.parent / "terrain.npz")["dem"]      # kok_zhailau cache
dem_new = np.load(INTERIM / "terrain.npz")["dem"]
BANDS = {"below the base village (<1,900 m)": (0, 1900),
         "the plan's operating band (1,900–3,400 m)": (1900, 3400),
         "above the plan's top station (>3,400 m)": (3400, 1e9)}
rows = []
for label, d, res in (("superseded 69 km²", dem_old, 30.0), ("superski 125 km²", dem_new, 30.0)):
    ha = res ** 2 / 1e4
    row = {"rectangle": label, "total_ha": round(float(np.isfinite(d).sum() * ha))}
    for name, (lo, hi) in BANDS.items():
        row[name] = round(float(((d >= lo) & (d < hi)).sum() * ha))
    rows.append(row)
extent = pd.DataFrame(rows)
print(extent.to_string(index=False))
print("\nThe replacement more than doubles the terrain the plan actually uses,")
print("while the ground below the village grows by only ~160 ha.")

# %% [markdown]
# The `superski` rectangle is the envelope of those seven control points plus a
# 1.5 km working buffer. It is **derived, not given** — and it is still only a
# compute grid, because a rectangle is not a site.

# %% [markdown]
# ## 2. The boundary itself
#
# The reporting boundary is a polygon digitised by hand over satellite imagery and
# exported as KML. `operating_area.py` loads it, refuses anything that is not a
# single valid polygon, rasterises it onto any grid, and carries one provenance
# sentence into every caption so a reader never has to ask which boundary a number
# came from.

# %%
poly, props = OA.load()
summary = OA.summary(poly, DEM_GRID, dem_new, np.load(INTERIM / "terrain.npz")["slope"])
print(f"provenance : {OA.provenance(props)}\n")
for k, v in summary.items():
    print(f"  {k:24s} {v}")
print(f"\nstated territory         {PROJECT_AREA_HA:,.0f} ha")
print(f"drawn boundary           {summary['raster_area_ha']:,.0f} ha "
      f"= {100 * summary['raster_area_ha'] / PROJECT_AREA_HA:.0f} % of it")

# %% [markdown]
# **The 74 % gap is recorded, not reconciled away.** 1,022 ha is a stated
# territory with no published coordinates; this polygon is a reading of the
# *operating area*, which may legitimately extend beyond a land allocation. If the
# operator publishes a boundary, it replaces this one file and every number below
# re-derives.

# %% [markdown]
# ## 3. Is the drawn boundary better than a rule?
#
# A hand-drawn boundary is only worth having if it beats what an algorithm would
# pick. Two reconstructions of **exactly the same area** are the reference:
#
# * **A — a disc on the plateau.** What you get with no terrain information.
# * **B — the gentlest ground within 3.5 km.** The most favourable placement
#   available, and therefore the right adversarial reference rather than a
#   flattering one.

# %%
terrain = np.load(INTERIM / "terrain.npz")
dem, slope, svf = terrain["dem"], terrain["slope"], terrain["svf"]
mask = OA.mask(DEM_GRID, poly)
cmp_df, alts = PL.shape_and_terrain(poly, dem, slope, mask)
print(cmp_df.to_string(index=False))

# %% [markdown]
# Read the last three columns together. **B finds twice the gentle ground and
# scatters it**: its largest unbroken field holds only ~28 % of its own gentle
# hectares. The drawn boundary takes more gentle ground than the disc, more
# vertical, and keeps half of its gentle ground in **one** field.
#
# Connectivity, not quantity, is what separates the three — and connectivity is
# what a lift network actually consumes.

# %%
PL.figure_reconstructions(dem, slope, alts)

# %% [markdown]
# ## 4. The published mix of runs, against the gradients that exist
#
# Two published sources disagree, so both are carried and every table names which
# one it used. The operator's own general plan gives a four-way difficulty split;
# press reporting of the April 2026 statement gave a round number. The plan
# attaches its own 70 % to **snowmaking**, which is the most economical
# explanation of where the press figure came from.

# %%
print(f"general plan : {PROJECT_LIFTS} lifts, "
      f"{100 * PROJECT_GREEN_BLUE_SHARE:.1f} % green+blue, "
      f"{100 * PROJECT_SNOWMAKING_SHARE:.0f} % snowmaking")
print(f"press        : {PROJECT_LIFTS_PRESS} lifts, "
      f"about {100 * PROJECT_GREEN_BLUE_SHARE_PRESS:.0f} % green+blue")
print()
print(PL.published_parameters().to_string(index=False))

# %%
grad = PL.gradients(slope, alts)
print(grad.pivot(index="gradient_class", columns="area", values="area_ha")
          .reindex([c[0] for c in ST.GRADIENT_CLASSES]).to_string())

# %%
gb_ha = float(cmp_df.loc[cmp_df.footprint == "Drawn boundary", "green_blue_ha"].iloc[0])
feas = PL.feasibility(gb_ha)
print(feas[["green_blue_source", "assumed_mean_piste_width_m", "green_blue_piste_ha",
            "available_green_blue_ha", "share_of_available_consumed"]].to_string(index=False))

# %% [markdown]
# **The easy-terrain budget closes with room** — 30–50 % of available gentle
# ground on the plan's own mix, 35–58 % on the press figure.
#
# An earlier draft of this project put the same arithmetic at up to **101 %** and
# concluded that easy terrain was the binding constraint. That figure combined the
# superseded footprint with the conflated 70 %, and it is **withdrawn**
# (`METHODS.md` §31). What a 30 m DEM still cannot show is whether two gentle
# benches can be joined by a lift. That is a survey question.

# %% [markdown]
# ## 5. Sun inside the boundary
#
# Energy and duration answer different questions, and for a December launch the
# one that matters is *hours of direct sun on the ground people ski on*.

# %%
sun = PL.sun(mask, slope)
print(sun.to_string(index=False))

# %% [markdown]
# The important column is the last pair. **The median pixel sees 3.6 h of direct
# sun a day in December and the bottom tenth sees none — but the green and blue
# ground sees 5.4 h.** The plateau faces the city, which is north; the gentle
# shelves that would carry beginner runs are not the north-facing part of it.
#
# That inverts an earlier reading of this site, which took the whole footprint's
# December median as the number a beginner area would live with.

# %% [markdown]
# ## 6. Snow, and the snow record's own blind spot
#
# A pixel needs four cloud- and shadow-free observations before it enters a monthly
# map. Shaded ground fails that test more often, so in mid-winter the pixels that
# survive are the sunniest and flattest — and the median then describes *that
# ground*, not the site. The bias columns measure it instead of leaving it to a
# caveat.

# %%
snow, ctx = PL.snow(poly, dem, slope)
print(snow.to_string(index=False))

# %% [markdown]
# March is sound: 97.9 % of the area qualifies on a median of 24 observations with
# a bias near zero. **December is not**: barely half the area qualifies, on a
# median of 5 observations, and those pixels are ~43 kWh/m² sunnier and 4° flatter
# than the site. The December snow figure is real, but it is a figure about the
# sunnier half of the boundary and is labelled as such everywhere it appears.

# %%
PL.figure(poly, props, dem, slope, mask, ctx)

# %% [markdown]
# ## 7. What this notebook supersedes
#
# | earlier claim | where | status |
# |---|---|---|
# | 69 km² rectangle is the study area | nb 01–03 | superseded by the control-point extent |
# | 1,022 ha reconstructed as footprints A and B | nb 05 §1 | kept as the adversarial reference only |
# | green/blue runs need up to 101 % of available ground | nb 05 §2 | **withdrawn** — 30–50 % here |
# | gentle ground exists but is not in one place | nb 05 §1 | **withdrawn** — half of it is one 182 ha field |
# | placement moves December sun by 3.9× | nb 05 §3 | narrowed — gentle ground is the sunny ground |
# | 17 lifts, about 70 % green and blue | nb 05 §0 | superseded by the general plan; both carried |
#
# Notebook 04 (the 404 km² cluster) and notebook 05 §5–§6 (the three-area
# comparison and the DEM propagation check) are **unaffected**: neither depends on
# where this boundary is drawn.

# %% [markdown]
# ## 8. Outputs
#
# Everything on this page is written by one command:
#
# ```bash
# KZ_AREA=superski python src/pipeline_operating_area.py
# ```

# %%
print(f"tables  -> {OUT_TAB}")
for p in sorted(OUT_TAB.glob("operating_area_*.csv")) + sorted(OUT_TAB.glob("published_*.csv")):
    print(f"   {p.name:46s} {p.stat().st_size/1024:6.1f} KB")
print(f"\nfigures -> {OUT_PNG}")
for p in sorted(OUT_PNG.glob("*.png")):
    print(f"   {p.name:46s} {p.stat().st_size/1e6:6.2f} MB")
print(f"\nboundary -> qgis/operating_area.geojson  ({int(summary['n_vertices'])} vertices)")
