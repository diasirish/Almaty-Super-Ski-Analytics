"""Enough snow on the pistes? Season length, continuity, and the snowmaking window.

The snow record elsewhere in this project answers "did this pixel look like snow
on that date". That is not an operator's question. An operator asks whether the
ground that will carry pistes holds snow for long enough, without breaking, and
- where it does not - whether the weather allows the missing snow to be made.

Three measurements, all over ground inside the drawn boundary:

1. **The natural season.** Per pixel, per season, the observed span between the
   first and the last snow detection, both ends bracketed by the gaps in the
   satellite record, with censoring reported where the record cannot see the
   end. From `snow.season_span`.
2. **Continuity.** Snow-free observations *inside* that span. A 150-day span
   with four breaks is not a 150-day season, and a frequency map cannot tell
   the two apart.
3. **The snowmaking window.** Hours below each of three published wet-bulb
   thresholds, per month and per elevation band, from hourly ERA5-Land
   temperature and humidity carried to band elevation with a stated lapse rate
   and swept across a +/-2 C error.

What this cannot do: give a snow depth, a water volume or a cost. Depth is not
observable from these sensors, and the modelled depth ERA5-Land carries belongs
to a 9 km cell at a single elevation. METHODS section 22 says so in full.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import (LAPSE_RATE_C_PER_KM, LAPSE_SENSITIVITY_C, RAIN_ON_SNOW_MM,
                    SEASONS, SKIABLE_SLOPE_MAX, SKIABLE_SLOPE_MIN,
                    SNOWMAKING_WETBULB_C, SUFFICIENCY_BAND_M)
from ski_terrain import GREEN_BLUE_MAX_DEG


def _nanmed(a) -> float:
    """Median of the finite values, or NaN, without the all-NaN warning."""
    v = np.asarray(a, dtype="float64")
    v = v[np.isfinite(v)]
    return float(np.median(v)) if v.size else float("nan")

MONTH_NAMES = {11: "November", 12: "December", 1: "January", 2: "February",
               3: "March", 4: "April"}
SEASON_MONTHS = (11, 12, 1, 2, 3, 4)


# --------------------------------------------------------------------------
# Where to measure: elevation bands crossed with the two kinds of piste ground
# --------------------------------------------------------------------------

def band_edges(dem: np.ndarray, mask: np.ndarray,
               step: float = SUFFICIENCY_BAND_M) -> list[tuple[float, float]]:
    """Elevation bands covering the masked ground, snapped outward to `step`."""
    v = dem[mask & np.isfinite(dem)]
    lo = np.floor(float(v.min()) / step) * step
    hi = np.ceil(float(v.max()) / step) * step
    return [(e, e + step) for e in np.arange(lo, hi, step)]


def ground_masks(slope: np.ndarray, mask: np.ndarray) -> dict[str, np.ndarray]:
    """The two readings of "piste ground", carried side by side.

    Gentle ground is what beginner and intermediate runs need and is where the
    snow problem turns out to live. The 15-35 deg band is the project's standard
    definition of ski terrain and keeps this table comparable with the rest.
    """
    fin = np.isfinite(slope)
    return {
        f"gentle (<={GREEN_BLUE_MAX_DEG:.1f} deg)":
            mask & fin & (slope <= GREEN_BLUE_MAX_DEG),
        f"skiable ({SKIABLE_SLOPE_MIN:.0f}-{SKIABLE_SLOPE_MAX:.0f} deg)":
            mask & fin & (slope >= SKIABLE_SLOPE_MIN) & (slope <= SKIABLE_SLOPE_MAX),
    }


# --------------------------------------------------------------------------
# 1 + 2. The natural season, from the satellite record
# --------------------------------------------------------------------------

def season_table(days: list[dict], dem20: np.ndarray, slope20: np.ndarray,
                 m20: np.ndarray, px_ha: float,
                 min_px: int = 100) -> pd.DataFrame:
    """Observed snow season per ground type, elevation band and season.

    Medians are taken over pixels whose season is bracketed at all. A band
    carrying fewer than `min_px` such pixels - 4 ha at 20 m - is dropped rather
    than quoted, because a median over a handful of pixels is a rumour. At this
    site that drops exactly one row: the 1.6 ha sliver where the boundary's
    bottom edge clips into 1,775-1,800 m, where single-date "seasons" of 0 to 15
    days were being reported.

    `band_elev_min_m` and `band_elev_max_m` are the real elevation range of the
    pixels behind each row, which is not the band's nominal range wherever the
    boundary cuts a band in half.
    """
    from snow import season_span, day_to_date

    grounds = ground_masks(slope20, m20)
    bands = band_edges(dem20, m20)
    rows = []
    for season in SEASONS:
        sp = season_span(days, season)
        for gname, gmask in grounds.items():
            for lo, hi in bands:
                sel = gmask & (dem20 >= lo) & (dem20 < hi)
                area_ha = float(sel.sum()) * px_ha
                est = sel & sp["has_snow"] & np.isfinite(sp["span_days"])
                n = int(est.sum())
                if n < min_px:
                    continue
                span = sp["span_days"][est]
                first = sp["first_snow_day"][est]
                last = sp["last_snow_day"][est]
                # The observed span is a lower bound: snow may have arrived any
                # time back to the last bare-ground look, and may have gone any
                # time up to the first bare-ground look after. Where an end is
                # censored the bracket is unknown and adds nothing, so the upper
                # bound is itself a lower bound there.
                pad = (np.nan_to_num(sp["onset_bracket_days"][est])
                       + np.nan_to_num(sp["meltout_bracket_days"][est]))
                upper = span + pad
                rows.append({
                    "ground": gname,
                    "band_low_m": lo, "band_high_m": hi,
                    "band_elev_min_m": round(float(dem20[sel].min()), 0),
                    "band_elev_max_m": round(float(dem20[sel].max()), 0),
                    "area_ha": round(area_ha, 1),
                    "season": season.replace("_", "/"),
                    "n_px_bracketed": n,
                    "bracketed_share": round(n / max(int(sel.sum()), 1), 3),
                    "median_first_snow": day_to_date(float(np.median(first)), sp["origin"]),
                    "median_last_snow": day_to_date(float(np.median(last)), sp["origin"]),
                    "median_span_days": round(float(np.median(span)), 1),
                    "median_span_upper_days": round(float(np.median(upper)), 1),
                    "p25_span_days": round(float(np.percentile(span, 25)), 1),
                    "p75_span_days": round(float(np.percentile(span, 75)), 1),
                    "median_breaks": float(np.median(sp["breaks"][est])),
                    "median_continuity": round(_nanmed(sp["continuity"][est]), 3),
                    "median_onset_bracket_days": round(
                        _nanmed(sp["onset_bracket_days"][est]), 1),
                    "median_meltout_bracket_days": round(
                        _nanmed(sp["meltout_bracket_days"][est]), 1),
                    "right_censored_share": round(
                        float(sp["right_censored"][est].mean()), 3),
                    "left_censored_share": round(
                        float(sp["left_censored"][est].mean()), 3),
                    "median_valid_obs": int(np.median(sp["n_valid"][est])),
                })
    return pd.DataFrame(rows)


def season_summary(season_df: pd.DataFrame) -> pd.DataFrame:
    """One row per ground type and band: the four seasons reduced to a range.

    The spread between the shortest and the longest of four observed seasons is
    the number worth carrying. A single mean would hide that the same band lost
    a month between 2022/23 and 2024/25.
    """
    g = season_df.groupby(["ground", "band_low_m", "band_high_m"], as_index=False)
    out = g.agg(area_ha=("area_ha", "max"),
                seasons=("season", "nunique"),
                median_span_days=("median_span_days", "median"),
                shortest_season_days=("median_span_days", "min"),
                longest_season_days=("median_span_days", "max"),
                longest_lower_bound_days=("median_span_days", "max"),
                shortest_upper_bound_days=("median_span_upper_days", "min"),
                span_envelope_low_days=("median_span_days", "min"),
                span_envelope_high_days=("median_span_upper_days", "max"),
                median_onset_bracket_days=("median_onset_bracket_days", "median"),
                median_breaks=("median_breaks", "median"),
                median_continuity=("median_continuity", "median"),
                band_elev_min_m=("band_elev_min_m", "min"),
                band_elev_max_m=("band_elev_max_m", "max"),
                right_censored_share=("right_censored_share", "mean"),
                left_censored_share=("left_censored_share", "mean"),
                max_left_censored_share=("left_censored_share", "max"),
                max_right_censored_share=("right_censored_share", "max"),
                min_valid_obs=("median_valid_obs", "min"),
                median_bracket_days=("median_meltout_bracket_days", "median"))
    out["season_spread_days"] = (out.longest_season_days
                                 - out.shortest_season_days).round(1)
    # Is the spread bigger than the gaps in the record? Each season's true span
    # lies between what was observed and that plus the bracket either side. The
    # seasons are only told apart when the longest season's lower bound clears
    # the shortest season's upper bound.
    #
    # Read `*_censored_share` before this column. Where an end is censored the
    # bracket is unknown and adds nothing, so the interval is artificially
    # tight and "resolved" means nothing. Above about 2,200 m here, both ends
    # are censored for most pixels and the span is simply the Nov 1 - Apr 30
    # observation window.
    out["seasons_resolved"] = (out.longest_lower_bound_days
                               > out.shortest_upper_bound_days)
    out["resolution_gap_days"] = (out.longest_lower_bound_days
                                  - out.shortest_upper_bound_days).round(1)
    for c in ("median_span_days", "shortest_season_days", "longest_season_days",
              "median_breaks", "median_onset_bracket_days",
              "shortest_upper_bound_days", "longest_lower_bound_days",
              "span_envelope_low_days", "span_envelope_high_days"):
        out[c] = out[c].round(1)
    out["median_continuity"] = out.median_continuity.round(3)
    for c in ("right_censored_share", "left_censored_share",
              "max_left_censored_share", "max_right_censored_share"):
        out[c] = out[c].round(3)
    return out.sort_values(["ground", "band_low_m"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# 3. The snowmaking window, from hourly reanalysis
# --------------------------------------------------------------------------

def _band_hourly(hourly: pd.DataFrame, band_mid_m: float, cell_m: float,
                 offset_c: float = 0.0) -> pd.DataFrame:
    import weather
    df = weather.at_elevation(hourly, band_mid_m, cell_m,
                              LAPSE_RATE_C_PER_KM, offset_c=offset_c)
    df["season"] = [_season_of_ts(t) for t in df["time"]]
    return df[df["season"].notna()]


def _season_of_ts(ts) -> str | None:
    d = ts.date().isoformat()
    for name, (s, e) in SEASONS.items():
        if s <= d <= e:
            return name.replace("_", "/")
    return None


def snowmaking_table(hourly: pd.DataFrame, cell_m: float,
                     bands: list[tuple[float, float]],
                     thresholds=SNOWMAKING_WETBULB_C) -> pd.DataFrame:
    """Hours below each wet-bulb threshold, per elevation band and month.

    Reported as the mean over the four observed seasons with the weakest and
    strongest season alongside, because a mean alone would let a reader plan on
    a season that never happened.
    """
    rows = []
    for lo, hi in bands:
        mid = (lo + hi) / 2
        df = _band_hourly(hourly, mid, cell_m)
        df = df.assign(month=df["time"].dt.month)
        for mo in SEASON_MONTHS:
            sub = df[df.month == mo]
            if sub.empty:
                continue
            rec = {"band_low_m": lo, "band_high_m": hi, "band_mid_m": mid,
                   "month": MONTH_NAMES[mo], "month_num": mo,
                   "n_seasons": int(sub.season.nunique()),
                   "hours_total_mean": round(len(sub) / sub.season.nunique(), 1),
                   "mean_air_T_C": round(float(sub.temperature_2m.mean()), 2),
                   "mean_wet_bulb_C": round(float(sub.wet_bulb_c.mean()), 2)}
            for th in thresholds:
                per_season = (sub.wet_bulb_c < th).groupby(sub.season).sum()
                key = f"hours_below_{abs(th):.0f}C"
                rec[f"{key}_mean"] = round(float(per_season.mean()), 1)
                rec[f"{key}_min"] = int(per_season.min())
                rec[f"{key}_max"] = int(per_season.max())
            rows.append(rec)
    return pd.DataFrame(rows)


def lapse_sensitivity(hourly: pd.DataFrame, cell_m: float, band_mid_m: float,
                      months=(11, 12), threshold: float = -4.0,
                      offsets=LAPSE_SENSITIVITY_C) -> pd.DataFrame:
    """How far does a wrong lapse rate move the snowmaking window?

    The temperature at band elevation is the cell's temperature shifted by a
    standard gradient. Shifting the whole series by +/-2 C brackets a lapse-rate
    error of about +/-6 C/km over the 335 m from the cell down to the beginner
    ground - far wider than any plausible error - and shows whether the
    conclusion survives it.
    """
    rows = []
    for off in offsets:
        df = _band_hourly(hourly, band_mid_m, cell_m, offset_c=off)
        df = df.assign(month=df["time"].dt.month)
        for mo in months:
            sub = df[df.month == mo]
            if sub.empty:
                continue
            per_season = (sub.wet_bulb_c < threshold).groupby(sub.season).sum()
            rows.append({
                "band_mid_m": band_mid_m, "month": MONTH_NAMES[mo],
                "temperature_offset_C": off,
                # Only meaningful when the band is far enough below the cell
                # for the offset to correspond to a plausible gradient at all.
                "implied_lapse_C_per_km": (
                    round(LAPSE_RATE_C_PER_KM - off / ((band_mid_m - cell_m) / 1000.0), 2)
                    if abs(band_mid_m - cell_m) >= 300 else np.nan),
                "threshold_C": threshold,
                "hours_mean": round(float(per_season.mean()), 1),
                "hours_min": int(per_season.min()), "hours_max": int(per_season.max()),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Joining the two: what the weather did inside the observed snow season
# --------------------------------------------------------------------------

def thaw_table(hourly: pd.DataFrame, cell_m: float, season_df: pd.DataFrame,
               ground: str, offset_c: float = 0.0,
               min_window_days: int = 14) -> pd.DataFrame:
    """Thaw, freeze-thaw and rain-on-snow inside each band's observed season.

    The window is not the calendar season: it runs from that band's median first
    snow detection to its median last one, in that season, on `ground`. So the
    count answers "what happened to the snow that was actually there".

    Rain is re-partitioned at band elevation rather than taken from ERA5's own
    rain/snow split, which belongs to a 31 km cell at 2,235 m: a day counts as
    rain-on-snow when total precipitation reaches RAIN_ON_SNOW_MM and the band's
    daily mean temperature is above freezing.
    """
    sub = season_df[season_df.ground == ground]
    rows = []
    for (lo, hi), grp in sub.groupby(["band_low_m", "band_high_m"]):
        mid = (lo + hi) / 2
        h = _band_hourly(hourly, mid, cell_m, offset_c=offset_c)
        daily = h.set_index("time").resample("1D").agg(
            T_mean=("temperature_2m", "mean"), T_max=("temperature_2m", "max"),
            T_min=("temperature_2m", "min"), precip_mm=("precipitation", "sum"),
            tw_mean=("wet_bulb_c", "mean"))
        for _, r in grp.iterrows():
            w = daily.loc[r.median_first_snow:r.median_last_snow]
            if len(w) < min_window_days:
                continue
            thaw = w.T_max > 0
            rows.append({
                "band_low_m": lo, "band_high_m": hi, "season": r.season,
                "temperature_offset_C": offset_c,
                "window_start": r.median_first_snow, "window_end": r.median_last_snow,
                "window_days": len(w),
                "thaw_days": int(thaw.sum()),
                "thaw_share": round(float(thaw.mean()), 3),
                "freeze_thaw_days": int(((w.T_max > 0) & (w.T_min < 0)).sum()),
                "rain_on_snow_days": int(((w.precip_mm >= RAIN_ON_SNOW_MM)
                                          & (w.T_mean > 0)).sum()),
                "melting_degree_days_C": round(float(w.T_mean.clip(lower=0).sum()), 1),
                "mean_T_C": round(float(w.T_mean.mean()), 2),
            })
    return pd.DataFrame(rows)


def sufficiency_table(summary_df: pd.DataFrame, snow_by_band: pd.DataFrame,
                      making_df: pd.DataFrame, thaw_df: pd.DataFrame,
                      ground: str, threshold: float = -4.0) -> pd.DataFrame:
    """One row per band: natural season, what breaks it, what can be made.

    No verdict column. The numbers are put side by side and the reader draws
    the line, because "enough" depends on an opening date and a snowmaking
    budget that are not published.
    """
    s = summary_df[summary_df.ground == ground].copy()
    key = f"hours_below_{abs(threshold):.0f}C_mean"
    mk = making_df[making_df.month_num.isin((11, 12))].groupby(
        ["band_low_m"], as_index=False)[key].sum().rename(
        columns={key: "snowmaking_hours_nov_dec"})
    th = thaw_df.groupby("band_low_m", as_index=False).agg(
        thaw_days_mean=("thaw_days", "mean"),
        thaw_share_mean=("thaw_share", "mean"),
        rain_on_snow_days_mean=("rain_on_snow_days", "mean"))
    out = (s.merge(snow_by_band, on="band_low_m", how="left")
            .merge(mk, on="band_low_m", how="left")
            .merge(th, on="band_low_m", how="left"))
    out["thaw_days_mean"] = out.thaw_days_mean.round(1)
    out["thaw_share_mean"] = out.thaw_share_mean.round(3)
    out["rain_on_snow_days_mean"] = out.rain_on_snow_days_mean.round(1)
    out["snowmaking_threshold_C"] = threshold
    cols = ["band_low_m", "band_high_m", "band_elev_min_m", "band_elev_max_m",
            "area_ha", "median_span_days", "shortest_season_days",
            "longest_season_days", "span_envelope_low_days",
            "span_envelope_high_days", "seasons_resolved", "resolution_gap_days",
            "median_breaks", "median_continuity",
            "snow_freq_december", "covered_share_december", "snow_freq_march",
            "thaw_days_mean", "thaw_share_mean", "rain_on_snow_days_mean",
            "snowmaking_threshold_C", "snowmaking_hours_nov_dec",
            "left_censored_share", "right_censored_share", "min_valid_obs"]
    return out[[c for c in cols if c in out.columns]]


def snow_frequency_by_band(planes: dict, dem20: np.ndarray, slope20: np.ndarray,
                           m20: np.ndarray, ground: str,
                           bands: list[tuple[float, float]]) -> pd.DataFrame:
    """December and March snow frequency over the same bands, for cross-reading."""
    gmask = ground_masks(slope20, m20)[ground]
    rows = []
    for lo, hi in bands:
        sel = gmask & (dem20 >= lo) & (dem20 < hi)
        rec = {"band_low_m": lo}
        for mo, lab in ((12, "december"), (3, "march")):
            freq, ok = planes[mo]
            v = freq[sel & ok]
            v = v[np.isfinite(v)]
            rec[f"snow_freq_{lab}"] = round(float(np.median(v)), 3) if v.size else np.nan
            rec[f"covered_share_{lab}"] = round(
                float((sel & ok).sum() / max(int(sel.sum()), 1)), 3)
        rows.append(rec)
    return pd.DataFrame(rows)
