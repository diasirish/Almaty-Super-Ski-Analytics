# %% [markdown]
# # 07 — Enough snow on the pistes? Season length, continuity, and what can be made
#
# **Almaty SuperSki terrain analytics — an independent open-data case study**
# Dias Irishev · Geo & Weather Data Scientist, Almaty
#
# Notebooks 02 and 06 answer *where* snow is and *how often* a pixel looked like
# snow. Useful, and not the operator's question. The operator asks whether the
# ground that will carry pistes holds snow **long enough**, **without breaking**,
# and where it does not, whether the weather allows the missing snow to be
# **made**.
#
# A frequency map cannot answer any of the three. "Snow on 95 % of usable dates"
# is consistent with a season that starts in mid-December, and with a cover that
# melts and refreezes every other week. So this notebook measures three different
# things:
#
# 1. **The observed season** — the interval between the first and the last snow
#    detection of a season, per pixel, with the gaps in the record carried as
#    brackets and censoring reported rather than averaged in.
# 2. **Continuity** — snow-free looks *inside* that interval, and the honest
#    limit on what 15–25 looks a season can see.
# 3. **The snowmaking window** — hours below three published wet-bulb thresholds,
#    from hourly reanalysis, with the elevation correction swept across ±2 °C
#    because it is the largest assumption here.
#
# Everything is computed by `src/snow_sufficiency.py` and run end to end by
# `src/pipeline_snow_sufficiency.py`. This notebook calls that module rather than
# reimplementing it, so the tables, the figure, `METHODS.md` §22 and this page
# cannot drift apart.
#
# > **Nothing here is a forecast, a snow depth or a snowmaking budget.** Four
# > seasons is not a climatology, no probability is attached to anything, and
# > water supply, pumping capacity and gun type are not published for this
# > project. The boundary is hand-drawn and not official.

# %%
import os

os.environ["KZ_AREA"] = "superski"        # must be set before importing config

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd().parent / "src"))

import operating_area as OA
import pipeline_snow_sufficiency as PS
import snow_sufficiency as SS
import weather
from config import (LAPSE_RATE_C_PER_KM, LAPSE_SENSITIVITY_C, MIN_VALID_OBS,
                    OUT_PNG, OUT_TAB, RAIN_ON_SNOW_MM, S2_RES_M, SEASONS,
                    SNOWMAKING_WETBULB_C, SUFFICIENCY_BAND_M)
from grids import DEM_GRID as G
from grids import make_grid
from pipeline_snow import historical_days, load_days
from ski_terrain import GREEN_BLUE_MAX_DEG
from snow import season_span, snow_frequency

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)

poly, props = OA.load()
dem, slope = PS._terrain()
S2 = make_grid(S2_RES_M)
M20 = OA.mask(S2, poly)
DEM20, SLOPE20 = PS._lift_to_20m(dem, S2), PS._lift_to_20m(slope, S2)
PX_HA = S2.res ** 2 / 1e4

DAYS, _manifest, _failed = load_days(verbose=False)
HIST = historical_days(DAYS)

print(f"boundary    : {M20.sum() * PX_HA:,.0f} ha on the {S2.res:.0f} m snow grid")
print(f"seasons     : {', '.join(s.replace('_', '/') for s in SEASONS)}")
print(f"observations: {len(HIST)} usable dates inside them")
print(f"bands       : {SUFFICIENCY_BAND_M:.0f} m, gradient split at "
      f"{GREEN_BLUE_MAX_DEG:.2f} deg")
print(f"thresholds  : wet bulb {SNOWMAKING_WETBULB_C} C, "
      f"lapse {LAPSE_RATE_C_PER_KM} C/km swept {LAPSE_SENSITIVITY_C}")

# %% [markdown]
# ## 1. Where it is measured
#
# Two readings of "piste ground", carried side by side rather than picking one.
# **Gentle** (≤ 19.29°) is what beginner and intermediate runs need — the ground
# notebook 06 counts as green/blue. **Skiable** (15–35°) is the project's
# standard definition of ski terrain, which keeps this page comparable with
# notebook 05's three-area work.
#
# The two overlap between 15° and 19.29°, deliberately: they answer different
# questions and neither is a subset worth hiding.

# %%
GROUNDS = SS.ground_masks(SLOPE20, M20)
BANDS = SS.band_edges(DEM20, M20)

rows = []
for name, m in GROUNDS.items():
    rows.append({"ground": name, "area_ha": round(m.sum() * PX_HA, 1),
                 "share_of_boundary": round(m.sum() / M20.sum(), 3),
                 "median_slope_deg": round(float(np.median(SLOPE20[m])), 1),
                 "elev_min_m": round(float(DEM20[m].min())),
                 "elev_max_m": round(float(DEM20[m].max()))})
rows.append({"ground": "everything inside the boundary",
             "area_ha": round(M20.sum() * PX_HA, 1), "share_of_boundary": 1.0,
             "median_slope_deg": round(float(np.median(SLOPE20[M20])), 1),
             "elev_min_m": round(float(DEM20[M20].min())),
             "elev_max_m": round(float(DEM20[M20].max()))})
print(pd.DataFrame(rows).to_string(index=False))
print(f"\n{len(BANDS)} bands: {BANDS[0][0]:.0f} to {BANDS[-1][1]:.0f} m")

# %% [markdown]
# ## 2. The observed season, and why it is a lower bound
#
# `snow.season_span` walks one season's valid observations twice. The first pass
# records the first and the last snow detection per pixel. The second finds the
# last snow-free look *before* the first snow, the first snow-free look *after*
# the last, and counts the snow-free looks *inside*.
#
# What is reported is `last_snow_day − first_snow_day`: the interval the record
# actually saw snow across. It is **not** an interpolated count of snow-covered
# days. With a median of 15–25 usable looks a season, interpolation would invent
# days nobody observed.
#
# That makes every span a **lower bound**, and the two brackets say by how much.
# Take the beginner band one season at a time:

# %%
SPANS = {s: season_span(HIST, s) for s in SEASONS}

gentle = [g for g in GROUNDS if g.startswith("gentle")][0]
skiable = [g for g in GROUNDS if g != gentle][0]
beginner = GROUNDS[gentle] & (DEM20 >= 1800) & (DEM20 < 2000)

rows = []
for s, sp in SPANS.items():
    est = beginner & sp["has_snow"] & np.isfinite(sp["span_days"])
    from snow import day_to_date
    rows.append({
        "season": s.replace("_", "/"),
        "first snow (median)": day_to_date(float(np.median(sp["first_snow_day"][est])), sp["origin"]),
        "last snow (median)": day_to_date(float(np.median(sp["last_snow_day"][est])), sp["origin"]),
        "observed span (d)": float(np.median(sp["span_days"][est])),
        "onset bracket (d)": SS._nanmed(sp["onset_bracket_days"][est]),
        "meltout bracket (d)": SS._nanmed(sp["meltout_bracket_days"][est]),
        "upper bound (d)": float(np.median(
            sp["span_days"][est] + np.nan_to_num(sp["onset_bracket_days"][est])
            + np.nan_to_num(sp["meltout_bracket_days"][est]))),
        "left censored": round(float(sp["left_censored"][est].mean()), 3),
        "right censored": round(float(sp["right_censored"][est].mean()), 3),
        "looks (median)": int(np.median(sp["n_valid"][est])),
    })
beg = pd.DataFrame(rows)
print(f"gentle ground, 1,800-2,000 m — {beginner.sum() * PX_HA:.1f} ha\n")
print(beg.to_string(index=False))

lo, hi = beg["observed span (d)"].min(), beg["upper bound (d)"].max()
print(f"\nshortest observed span      {beg['observed span (d)'].min():.0f} d "
      f"({beg.loc[beg['observed span (d)'].idxmin(), 'season']})")
print(f"longest observed span       {beg['observed span (d)'].max():.0f} d")
print(f"shortest season's ceiling   {beg['upper bound (d)'].min():.0f} d")
print(f"longest season's floor      {beg['observed span (d)'].max():.0f} d")
print(f"-> seasons separable?       "
      f"{beg['observed span (d)'].max() > beg['upper bound (d)'].min()}")
print(f"-> all that can be said     the season fell somewhere in {lo:.0f}-{hi:.0f} days")

# %% [markdown]
# The shortest season's ceiling lands **exactly** on the longest season's floor.
# 2025/26 was the shortest of the four — the direction is certain, because its
# upper bound does not clear the others' lower bounds — and four seasons of
# optical satellite cannot say by how much. That is the honest result, and it is
# more useful than a single number: it says what a second sensor would buy.
#
# **Censoring is reported, not averaged in.** Where no snow-free look exists
# before the first snow detection, or after the last, the season runs past what
# the record can see. Higher up, that is the normal case:

# %%
SEASON_DF = SS.season_table(HIST, DEM20, SLOPE20, M20, PX_HA)
SUMMARY = SS.season_summary(SEASON_DF)

cols = ["band_low_m", "band_high_m", "area_ha", "median_span_days",
        "span_envelope_low_days", "span_envelope_high_days",
        "left_censored_share", "right_censored_share",
        "seasons_resolved", "min_valid_obs"]
print(f"{gentle}\n")
print(SUMMARY[SUMMARY.ground == gentle][cols].to_string(index=False))

# %% [markdown]
# Read `seasons_resolved` only next to the censoring columns. Where an end is
# censored the bracket is unknown and adds nothing, so the interval is
# artificially tight and "resolved" means nothing. At and above 2,400 m roughly
# three quarters to nine tenths of pixels are censored at both ends, and the
# ~171 days those bands report is simply the 1 November – 30 April observation
# window.
#
# The one band where the record genuinely sees snow arrive *and* leave is the
# beginner band — which is also the band a December opening depends on.

# %% [markdown]
# ## 3. Continuity, and what the record cannot see
#
# `breaks` counts snow-free valid observations strictly inside the span;
# `continuity` is snow looks over snow-plus-free looks inside it.

# %%
print(SUMMARY[["ground", "band_low_m", "median_breaks", "median_continuity",
               "min_valid_obs"]].to_string(index=False))

gaps = []
for s, sp in SPANS.items():
    dates = sorted(d["date"] for d in HIST
                   if SEASONS[s][0] <= d["date"] <= SEASONS[s][1])
    dd = pd.to_datetime(pd.Series(dates)).diff().dt.days.dropna()
    gaps.append({"season": s.replace("_", "/"), "dates": len(dates),
                 "median gap (d)": float(dd.median()),
                 "p90 gap (d)": float(dd.quantile(0.9)),
                 "longest gap (d)": float(dd.max())})
print("\ngaps between usable observations:")
print(pd.DataFrame(gaps).to_string(index=False))

# %% [markdown]
# Median breaks: **0**, everywhere. The cover was never *seen* to break.
#
# That is a weaker statement than it reads. The median gap between usable looks
# is about a week and a half, and the longest gaps run to several weeks, so **no
# thaw shorter than that is visible**. "Never seen to break" is not "never
# broke", and section 7 measures, from an independent dataset, what the satellite
# is too sparse to see.

# %% [markdown]
# ## 4. The same elevation, two gradients
#
# The site-wide result in notebook 06 is that the gentle ground is the *sunny*
# ground: 168 h of December sun against 110 h for the boundary as a whole. Inside
# a single low band that reverses, and the reversal is what decides where
# snowmaking is actually needed.

# %%
ins_dec = np.load(PS.INTERIM / "insolation" / "2027_12.npz")["total"]
DEC20 = PS._lift_to_20m(ins_dec, S2)
r3 = snow_frequency([d for d in HIST if d["date"][5:7] == "03"])
F3, OK3 = r3["frequency"], r3["n_valid"] >= MIN_VALID_OBS

rows = []
for lo_m, hi_m in BANDS[:4]:
    for name, m in GROUNDS.items():
        sel = m & (DEM20 >= lo_m) & (DEM20 < hi_m)
        if sel.sum() * PX_HA < 4:
            continue
        ok = sel & OK3
        rows.append({
            "band": f"{lo_m:.0f}-{hi_m:.0f}", "ground": name,
            "area_ha": round(sel.sum() * PX_HA, 1),
            "median_slope_deg": round(float(np.median(SLOPE20[sel])), 1),
            "dec_insolation_kwh": round(float(np.median(DEC20[sel])), 1),
            "march_snow_freq": round(float(np.nanmedian(F3[ok])), 3),
            "observed_span_d": float(SUMMARY[(SUMMARY.ground == name)
                                             & (SUMMARY.band_low_m == lo_m)]
                                     .median_span_days.iloc[0]),
        })
contrast = pd.DataFrame(rows)
print(contrast.to_string(index=False))

# %% [markdown]
# At 1,800–2,000 m the gentle ground takes **47.7 kWh/m²** of December sun
# against **78.7** on the 15–35° ground beside it, holds snow on **95 %** of
# usable March dates against **42 %**, and keeps it **130 days** against **99**.
# At this elevation the gentle shelves are the *shaded* ground — they sit in the
# north-west arm, under its own skyline — and that is why they keep their snow.
#
# The operational reading: **the snowmaking case at the bottom of this mountain
# is about the descent routes, not the beginner benches.** Both are at the same
# elevation, so both get the same air temperature; they do not get the same sun,
# and the satellite can see the difference.

# %% [markdown]
# ## 5. The snowmaking window
#
# Hourly ERA5-Land temperature, relative humidity and dew point, with surface
# pressure and precipitation from ERA5, at the plateau reference point. One cell,
# one elevation: Open-Meteo reports 2,235 m for that point and this project's
# Copernicus DEM says 2,238 m, so two independent terrain models agree there to
# 3 m.
#
# **Wet-bulb temperature** is solved from the psychrometric equation
#
# $$e_s(T_w) - e = A \cdot p \cdot (T - T_w), \qquad A = 6.6 \times 10^{-4}\ \mathrm{K^{-1}}$$
#
# by bisection, with $e_s$ from Buck (1996). Pressure is carried explicitly
# because it moves the answer at this altitude. The familiar closed form —
# Stull (2011) — is a sea-level least-squares fit, so it is checked against
# rather than used:

# %%
HOURLY = weather.era5_hourly(PS.SEASON_START, PS.SEASON_END)
CELL_M = float(HOURLY.attrs["era5_land_cell_elevation_m"])
print(f"{len(HOURLY):,} hours, cell {CELL_M:.0f} m, "
      f"ERA5-Land {HOURLY.attrs['era5_land_cell']}, ERA5 {HOURLY.attrs['era5_cell']}")
print(f"retrieved {HOURLY.attrs['retrieved']}\n")
print(PS.wet_bulb_method_check(HOURLY, CELL_M, 1900.0).to_string(index=False))

# %% [markdown]
# Using the closed form would have over-counted the snowmaking window by about
# 3 %; ignoring the ~800 hPa of this altitude would have under-counted it by
# about 5 %. Both are small. Both are now measured rather than waved away.
#
# **Thresholds.** Published wet-bulb thresholds for snow production run from
# about −1 to −4 °C; López-Moreno et al. (2018) define snowmaking hours as hours
# below −2 °C, and equipment makers quote about −2.5 °C to start a system. Three
# are carried — −2, −4, −6 °C — as with piste width, rather than assuming one.

# %%
USED = [(lo, hi) for lo, hi in BANDS if (SUMMARY.band_low_m == lo).any()]
MAKING = SS.snowmaking_table(HOURLY, CELL_M, USED)
show = ["month", "mean_air_T_C", "mean_wet_bulb_C", "hours_below_2C_mean",
        "hours_below_4C_mean", "hours_below_4C_min", "hours_below_4C_max",
        "hours_below_6C_mean"]
for mid in (1900.0, 2100.0):
    print(f"--- {mid:,.0f} m ---")
    print(MAKING[MAKING.band_mid_m == mid][show].to_string(index=False))
    print()

# %% [markdown]
# ## 6. Does a wrong lapse rate change the answer?
#
# The cell sits at 2,235 m; the beginner ground is 335 m below it. Temperature is
# carried down at a fixed 6.5 °C/km — the standard atmosphere, and also what
# Open-Meteo itself applies — pressure by the hypsometric formula, and relative
# humidity unchanged, which is an assumption and not a measurement.
#
# This is a model's own vertical gradient, not a measured local one, and winter
# inversions in the Almaty valley break it. López-Moreno et al. studied precisely
# that problem in a Pyrenean resort. So the whole series is shifted by ±2 °C,
# which brackets any plausible error, and the result is reported across the
# sweep:

# %%
SENS = pd.concat([SS.lapse_sensitivity(HOURLY, CELL_M, 1900.0),
                  SS.lapse_sensitivity(HOURLY, CELL_M, 2100.0)], ignore_index=True)
print(SENS[SENS.band_mid_m == 1900.0][
    ["month", "temperature_offset_C", "implied_lapse_C_per_km", "hours_mean",
     "hours_min", "hours_max"]].to_string(index=False))

# %% [markdown]
# The window survives the sweep. Even 2 °C warmer than assumed, November at the
# beginner ground still gives **171.5 hours** below −4 °C wet bulb, and December
# 441.8. The conclusion "there is a usable snowmaking window at the bottom of
# this mountain in every one of the four observed seasons" does not depend on the
# lapse rate being right.
#
# A measured local lapse rate from Kazhydromet station pairs would replace this
# assumption outright, and it is the cheapest improvement available to this
# chapter.

# %% [markdown]
# ## 7. What the weather did inside the observed season
#
# The window is not the calendar season: for each band it runs from that band's
# median first snow detection to its median last one, so the counts answer *what
# happened to the snow that was actually there*.
#
# * **thaw day** — daily maximum above 0 °C at band elevation
# * **freeze-thaw day** — maximum above 0 °C and minimum below it, same day
# * **rain-on-snow day** — precipitation ≥ 1 mm with the band's daily mean above
#   freezing. The rain/snow split is re-made at band elevation rather than taken
#   from ERA5's own, which belongs to a 31 km cell at 2,235 m
# * **melting degree-days** — the sum of positive daily means

# %%
THAW = SS.thaw_table(HOURLY, CELL_M, SEASON_DF, gentle)
print(f"{gentle}, inside each band's own observed season\n")
print(THAW[THAW.band_low_m <= 2400].to_string(index=False))

THAW_SENS = pd.concat(
    [SS.thaw_table(HOURLY, CELL_M, SEASON_DF, gentle, offset_c=off)
     for off in LAPSE_SENSITIVITY_C], ignore_index=True)
agg = (THAW_SENS[THAW_SENS.band_low_m == 1800]
       .groupby("temperature_offset_C", as_index=False)
       .agg(thaw_days=("thaw_days", "mean"),
            freeze_thaw_days=("freeze_thaw_days", "mean"),
            rain_on_snow_days=("rain_on_snow_days", "mean"),
            melting_degree_days=("melting_degree_days_C", "mean")).round(1))
print("\n1,800-2,000 m across the same ±2 °C sweep:")
print(agg.to_string(index=False))

# %% [markdown]
# Inside the observed season at 1,800–2,000 m, **57 % of days reached above
# freezing**, 58–71 days froze and thawed within the same day, and **10.8 days a
# season brought rain on snow** — the single most damaging event type for piste
# surface.
#
# Put beside section 3, the two datasets say something neither says alone: the
# satellite never saw the cover break, and the thermometer says the pack spent
# more than half the season passing through the melting point. Both can be true.
# The low ground keeps its snow as a melting, refreezing pack, not as a dry one —
# and that is a statement about **quality**, which no frequency map makes.
#
# Unlike the snowmaking window, these counts do **not** survive the lapse sweep
# cleanly: thaw days run 49 to 90 and rain-on-snow 5 to 17 across ±2 °C. They are
# quoted with that range, never as a point value.

# %% [markdown]
# ## 8. The figure

# %%
median_span = np.nanmedian(np.stack([SPANS[s]["span_days"] for s in SEASONS]), axis=0)
PS.figure(poly, DEM20, SLOPE20, M20, median_span, S2, SUMMARY, MAKING,
          gentle, 1900.0)

# %% [markdown]
# ## 9. What this notebook cannot tell you
#
# * **No depth, no water volume, no cost.** Production rate depends on water
#   supply, pumping capacity and gun type, none of which is published. ERA5-Land
#   does carry a modelled snow depth, and it is fetched and inspected, but no
#   claim here rests on it: it is a 9 km cell's own snowpack at one elevation.
# * **One reanalysis cell.** Every temperature descends from a single point,
#   spread across 1,775–3,291 m by a fixed gradient. No local wind, no cold-air
#   pooling, no valley inversion.
# * **The satellite cannot see short thaws**, so continuity is an upper bound on
#   how continuous the cover really was.
# * **Four seasons is not a climatology**, nothing here is a forecast, and no
#   probability is attached to any of it.
# * **Sentinel-1 SAR** would see wet snow directly, through cloud and at night,
#   and is the one addition that would turn "never seen to break" into a
#   measurement. `DATA.md` §8 says why it is not here yet.
#
# `METHODS.md` §22 is the full method; `DATA.md` §6.1 is where the hourly series
# comes from and §11 lists the published work this chapter leans on.

# %% [markdown]
# ## 10. Outputs
#
# Everything on this page is written by one command:
#
# ```bash
# KZ_AREA=superski python src/pipeline_snow_sufficiency.py
# ```

# %%
for pat in ("piste_snow_*.csv", "snowmaking_*.csv", "thaw_*.csv",
            "wet_bulb_*.csv"):
    for p in sorted(OUT_TAB.glob(pat)):
        print(f"   {p.name:42s} {p.stat().st_size / 1024:6.1f} KB")
print(f"\nfigure  -> {OUT_PNG / '08_snow_sufficiency.png'}")
