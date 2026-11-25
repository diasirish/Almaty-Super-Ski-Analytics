"""Enough snow on the pistes? One command, five tables and one figure.

    KZ_AREA=superski python src/pipeline_snow_sufficiency.py

Everything is read inside the drawn boundary. The satellite record gives how
long snow lay and how often the cover broke; hourly reanalysis gives how many
hours the weather allowed snow to be made at each elevation. Neither gives a
depth, and nothing here is a forecast.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import operating_area as oa
import snow_sufficiency as ss
from config import (AREA, INTERIM, LAPSE_RATE_C_PER_KM, LAPSE_SENSITIVITY_C,
                    OUT_TAB, S2_RES_M, SEASONS, SNOWMAKING_WETBULB_C)
from grids import DEM_GRID as G
from grids import make_grid

SEASON_START, SEASON_END = "2022-11-01", "2026-04-30"


def _terrain():
    z = np.load(INTERIM / "terrain.npz")
    return z["dem"], z["slope"]


def _lift_to_20m(arr, S2):
    """Nearest-neighbour index lift of a 30 m layer onto the 20 m snow grid."""
    xs, ys = S2.xy_centers()
    cc = np.clip(((xs - G.xmin) / G.res).astype(int), 0, G.width - 1)
    rr = np.clip(((G.ymax - ys) / G.res).astype(int), 0, G.height - 1)
    return arr[np.ix_(rr, cc)]


def wet_bulb_method_check(hourly, cell_m, band_mid_m) -> pd.DataFrame:
    """Does the wet-bulb implementation matter? Report it, do not assert it.

    Two comparisons at the band that carries the beginner ground: the
    psychrometric solution against Stull's (2011) sea-level closed form, and
    the same solution at sea-level pressure against the real ~800 hPa.
    """
    import weather
    b = ss._band_hourly(hourly, band_mid_m, cell_m)
    stull = weather.stull_wet_bulb_c(b.temperature_2m, b.relative_humidity_2m)
    sea = weather.wet_bulb_c(b.temperature_2m, b.relative_humidity_2m, 1013.25)
    rows = []
    for label, other in (("Stull (2011) closed form, sea-level fit", stull),
                         ("same solver at sea-level pressure", sea)):
        d = np.asarray(b.wet_bulb_c) - np.asarray(other)
        rows.append({
            "band_mid_m": band_mid_m, "n_hours": int(d.size),
            "compared_with": label,
            "median_difference_C": round(float(np.median(d)), 3),
            "p05_difference_C": round(float(np.percentile(d, 5)), 3),
            "p95_difference_C": round(float(np.percentile(d, 95)), 3),
            "hours_below_minus4_this": int((b.wet_bulb_c < -4).sum()),
            "hours_below_minus4_other": int((np.asarray(other) < -4).sum()),
        })
    return pd.DataFrame(rows)


def run(verbose: bool = True) -> dict:
    if AREA != "superski":
        raise SystemExit("run with KZ_AREA=superski: the boundary lives in that window")

    import weather
    from pipeline_snow import historical_days, load_days
    from snow import season_span, snow_frequency

    poly, _props = oa.load()
    dem, slope = _terrain()
    S2 = make_grid(S2_RES_M)
    m20 = oa.mask(S2, poly)
    dem20, slope20 = _lift_to_20m(dem, S2), _lift_to_20m(slope, S2)
    px_ha = S2.res ** 2 / 1e4

    days, _, _ = load_days(verbose=False)
    hist = historical_days(days)

    # ---- 1-2. the natural season, and how often it broke -------------------
    season_df = ss.season_table(hist, dem20, slope20, m20, px_ha)
    season_df.to_csv(OUT_TAB / "piste_snow_season_by_band.csv", index=False)
    summary_df = ss.season_summary(season_df)
    summary_df.to_csv(OUT_TAB / "piste_snow_season_summary.csv", index=False)

    grounds = list(summary_df.ground.unique())
    gentle = [g for g in grounds if g.startswith("gentle")][0]
    steep = [g for g in grounds if g != gentle][0]
    bands = ss.band_edges(dem20, m20)

    planes = {}
    for mo in (12, 3):
        sel = [d for d in hist if int(d["date"][5:7]) == mo]
        r = snow_frequency(sel)
        planes[mo] = (r["frequency"], m20 & (r["n_valid"] >= 4))
    freq = {g: ss.snow_frequency_by_band(planes, dem20, slope20, m20, g, bands)
            for g in grounds}

    # ---- 3. the snowmaking window ------------------------------------------
    hourly = weather.era5_hourly(SEASON_START, SEASON_END)
    cell_m = float(hourly.attrs["era5_land_cell_elevation_m"])
    # Snowmaking depends on elevation alone, so one table serves both grounds.
    used_bands = [(lo, hi) for lo, hi in bands
                  if (summary_df.band_low_m == lo).any()]
    making_df = ss.snowmaking_table(hourly, cell_m, used_bands)
    making_df.to_csv(OUT_TAB / "snowmaking_hours_by_band_month.csv", index=False)

    low_band = min(b[0] for b in used_bands)
    low_mid = low_band + (used_bands[0][1] - used_bands[0][0]) / 2
    sens = pd.concat([ss.lapse_sensitivity(hourly, cell_m, low_mid),
                      ss.lapse_sensitivity(hourly, cell_m, low_mid + 200)],
                     ignore_index=True)
    sens.to_csv(OUT_TAB / "snowmaking_lapse_sensitivity.csv", index=False)

    check = wet_bulb_method_check(hourly, cell_m, low_mid)
    check.to_csv(OUT_TAB / "wet_bulb_method_check.csv", index=False)

    # ---- the join: what the weather did inside the observed season ---------
    thaw = {g: ss.thaw_table(hourly, cell_m, season_df, g) for g in grounds}
    thaw_df = pd.concat([d.assign(ground=g) for g, d in thaw.items()],
                        ignore_index=True)
    thaw_df.to_csv(OUT_TAB / "thaw_and_rain_on_snow_by_band.csv", index=False)

    # The thaw counts rest on the same extrapolated temperature as the
    # snowmaking window, so they are swept across the same error.
    thaw_sens = pd.concat(
        [ss.thaw_table(hourly, cell_m, season_df, gentle, offset_c=off)
         for off in LAPSE_SENSITIVITY_C], ignore_index=True)
    thaw_sens = (thaw_sens.groupby(["band_low_m", "temperature_offset_C"],
                                   as_index=False)
                 .agg(seasons=("season", "nunique"),
                      window_days_mean=("window_days", "mean"),
                      thaw_days_mean=("thaw_days", "mean"),
                      rain_on_snow_days_mean=("rain_on_snow_days", "mean"),
                      melting_degree_days_mean=("melting_degree_days_C", "mean"))
                 .round(1))
    thaw_sens.to_csv(OUT_TAB / "thaw_lapse_sensitivity.csv", index=False)

    suff = pd.concat(
        [ss.sufficiency_table(summary_df, freq[g], making_df, thaw[g], g).assign(ground=g)
         for g in grounds], ignore_index=True)
    suff = suff[["ground"] + [c for c in suff.columns if c != "ground"]]
    suff.to_csv(OUT_TAB / "piste_snow_sufficiency.csv", index=False)

    # ---- per-pixel median span, for the map --------------------------------
    spans = np.stack([season_span(hist, s)["span_days"] for s in SEASONS])
    median_span = np.nanmedian(spans, axis=0)

    png = figure(poly, dem20, slope20, m20, median_span, S2, summary_df,
                 making_df, gentle, low_mid)

    if verbose:
        print(f"ERA5-Land cell {cell_m:.0f} m, lapse {LAPSE_RATE_C_PER_KM} C/km, "
              f"wet-bulb thresholds {SNOWMAKING_WETBULB_C}")
        print("\n--- observed snow season ---")
        print(summary_df.to_string(index=False))
        print("\n--- snowmaking window, hours per month ---")
        print(making_df.to_string(index=False))
        print("\n--- sufficiency, side by side ---")
        print(suff.to_string(index=False))
        print("\n--- the same band, two gradients ---")
        print(suff[suff.band_low_m <= 2200][
            ["ground", "band_low_m", "area_ha", "median_span_days",
             "span_envelope_low_days", "span_envelope_high_days",
             "snow_freq_march", "thaw_days_mean"]].to_string(index=False))
        print("\n--- lapse-rate sensitivity: snowmaking ---")
        print(sens.to_string(index=False))
        print("\n--- lapse-rate sensitivity: thaw ---")
        print(thaw_sens.to_string(index=False))
        print("\n--- wet-bulb method check ---")
        print(check.to_string(index=False))
        print(f"\nfigure -> {png}\ntables -> {OUT_TAB}")
    return {"season": season_df, "summary": summary_df, "making": making_df,
            "sufficiency": suff, "sensitivity": sens, "png": png}


def figure(poly, dem20, slope20, m20, median_span, S2, summary_df, making_df,
           gentle, low_mid) -> Path:
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from pyproj import Transformer

    import viz
    from config import SNOWMAKING_WETBULB_C

    fig, axes = plt.subplots(1, 3, figsize=(17.4, 5.0))

    # --- 1. how long the snow lay, by elevation -----------------------------
    ax = axes[0]
    gent = summary_df[summary_df.ground == gentle].sort_values("band_low_m")
    mid = gent.band_low_m + (gent.band_high_m - gent.band_low_m) / 2
    ax.fill_betweenx(mid, gent.shortest_season_days, gent.longest_season_days,
                     color="#1f9d55", alpha=0.18,
                     label="gentle ground — shortest to longest of 4 seasons")
    ax.plot(gent.median_span_days, mid, marker="o", color="#1f9d55", lw=2.0, ms=5,
            label=f"{gentle} — median")
    other = [g for g in summary_df.ground.unique() if g != gentle][0]
    st = summary_df[summary_df.ground == other].sort_values("band_low_m")
    mid2 = st.band_low_m + (st.band_high_m - st.band_low_m) / 2
    ax.plot(st.median_span_days, mid2, marker="s", color="#c2563a", lw=2.0, ms=5,
            ls="--", label=f"{other} — median")

    # Above the first band where most pixels are censored at both ends, the span
    # is the observation window, not a measurement. Say so on the figure.
    cens = gent[(gent.max_left_censored_share > 0.7)
                & (gent.max_right_censored_share > 0.7)]
    if len(cens):
        y = float(cens.band_low_m.min())
        ax.axhline(y, color="#555", lw=1.0, ls=":")
        ax.annotate("above this line both ends of the season are censored for\n"
                    "most pixels: the span is the 1 Nov – 30 Apr record, not a\n"
                    "measurement",
                    (0.98, y - 30), xycoords=("axes fraction", "data"),
                    fontsize=7.0, color="#555", va="top", ha="right")
    ax.set_xlabel("observed days between first and last snow detection")
    ax.set_ylabel("elevation (m)")
    ax.set_title("How long the snow lay, and how much the seasons differed")
    ax.grid(alpha=0.25, lw=0.5)
    ax.legend(fontsize=7.0, loc="upper left", framealpha=0.92)

    # --- 2. the snowmaking window at the beginner ground --------------------
    ax = axes[1]
    sub = making_df[making_df.band_mid_m == low_mid].sort_values("month_num")
    order = [11, 12, 1, 2, 3, 4]
    sub = sub.set_index("month_num").reindex(order).dropna(how="all")
    x = np.arange(len(sub))
    w = 0.26
    for i, (th, colour) in enumerate(zip(SNOWMAKING_WETBULB_C,
                                         ("#9ecae1", "#2e7ebb", "#0b3d6b"))):
        key = f"hours_below_{abs(th):.0f}C"
        ax.bar(x + (i - 1) * w, sub[f"{key}_mean"], width=w, color=colour,
               label=f"wet bulb < {th:.0f} °C")
        ax.errorbar(x + (i - 1) * w, sub[f"{key}_mean"],
                    yerr=[sub[f"{key}_mean"] - sub[f"{key}_min"],
                          sub[f"{key}_max"] - sub[f"{key}_mean"]],
                    fmt="none", ecolor="#333", elinewidth=0.9, capsize=2.5)
    ax.set_xticks(x)
    ax.set_xticklabels([m[:3] for m in sub.month], fontsize=8)
    ax.set_ylabel("hours per month")
    ax.set_title(f"Snowmaking window at {low_mid:,.0f} m — the beginner ground\n"
                 f"bars: mean of 4 seasons, whiskers: weakest to strongest")
    ax.grid(alpha=0.25, lw=0.5, axis="y")
    ax.legend(fontsize=7.5, framealpha=0.92)

    # --- 3. where the snow lies longest -------------------------------------
    ax = axes[2]
    shown = np.where(m20, median_span, np.nan)
    viz.map_panel(ax, shown, S2, cmap="YlGnBu", vmin=0,
                  vmax=float(np.nanpercentile(shown, 98)),
                  dem=dem20, shade=0.42, mark_plateau=False,
                  title="Median snow span inside the boundary, 4 seasons",
                  cbar_label="days between first and last snow detection")
    ext = (S2.xmin / 1000, S2.xmax / 1000, S2.ymin / 1000, S2.ymax / 1000)
    gmask = ss.ground_masks(slope20, m20)[gentle]
    ax.contour(gmask.astype(float), levels=[0.5], colors=["#0b3d20"],
               linewidths=1.1, extent=ext, origin="upper", zorder=11)
    ax.plot([], [], color="#0b3d20", lw=1.1, label="gentle ground")
    tr = Transformer.from_crs("EPSG:4326", S2.crs, always_xy=True)
    bx, by = tr.transform(*zip(*poly.exterior.coords))
    ax.plot(np.array(bx) / 1000, np.array(by) / 1000, color="#ff6a00", lw=2.0,
            zorder=12, label="drawn boundary",
            path_effects=[pe.withStroke(linewidth=3.4, foreground="white")])
    ax.legend(fontsize=7.0, loc="lower left", framealpha=0.92)

    fig.tight_layout()
    return viz.save(fig, "08_snow_sufficiency.png", subtitle=(
        "Snow span is the observed interval between the first and the last Sentinel-2 snow "
        "detection of a season — a lower bound, not an interpolated count of snow-covered "
        "days, and censored wherever the record never saw bare ground. Snowmaking hours are "
        "hours with wet-bulb temperature below each threshold, from hourly ERA5-Land "
        f"temperature and humidity carried from a 2,235 m cell to band elevation at "
        f"{LAPSE_RATE_C_PER_KM} °C/km — a standard gradient, not a measured one, swept "
        "across ±2 °C in snowmaking_lapse_sensitivity.csv. METHODS §22."))


if __name__ == "__main__":
    run()
