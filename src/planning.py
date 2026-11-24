"""Planning read-outs: elevation x insolation contrasts and field-check priorities."""
from __future__ import annotations

import numpy as np
import pandas as pd

PIXEL_AREA_M2 = 400.0   # analysis stack is on the 20 m Sentinel-2 grid

from config import (ELEV_BAND_M, NORTHY, SKIABLE_SLOPE_MAX, SKIABLE_SLOPE_MIN,
                    SOUTHY, STEEP_SLOPE_MIN)


def aspect_class(aspect: np.ndarray) -> np.ndarray:
    """0 = north sector, 1 = south sector, 2 = east/west, -1 = flat/undefined."""
    a = aspect
    out = np.full(a.shape, 2, dtype="int8")
    north = (a >= NORTHY[0]) | (a < NORTHY[1])
    south = (a >= SOUTHY[0]) & (a < SOUTHY[1])
    out[north] = 0
    out[south] = 1
    out[~np.isfinite(a)] = -1
    return out


def elevation_bands(dem: np.ndarray, band_m: float = ELEV_BAND_M) -> np.ndarray:
    """Lower edge of the 100 m band each pixel belongs to."""
    return (np.floor(dem / band_m) * band_m).astype("float32")


def skiable_mask(slope: np.ndarray,
                 lo: float = SKIABLE_SLOPE_MIN, hi: float = SKIABLE_SLOPE_MAX) -> np.ndarray:
    return np.isfinite(slope) & (slope >= lo) & (slope <= hi)


def band_insolation_contrast(dem, slope, insol, freq, band_m=ELEV_BAND_M,
                             min_pixels: int = 40) -> pd.DataFrame:
    """Lowest vs highest insolation quartile inside each 100 m elevation band.

    Quartiles are taken WITHIN each band on 15-35 deg slopes, so the contrast is
    an exposure effect rather than an elevation effect.
    """
    ski = skiable_mask(slope)
    bands = elevation_bands(dem, band_m)
    rows = []
    for b in np.unique(bands[np.isfinite(bands) & ski]):
        m = ski & (bands == b)
        n = int(m.sum())
        if n < min_pixels:
            continue
        ins = insol[m]
        fr = freq[m]
        q1, q3 = np.nanpercentile(ins, [25, 75])
        lo_m = ins <= q1
        hi_m = ins >= q3
        rec = {
            "elev_band_m": float(b),
            "band_label": f"{int(b)}-{int(b+band_m)}",
            "n_pixels_skiable": n,
            "area_skiable_km2": round(n * PIXEL_AREA_M2 / 1e6, 4),
            "insol_q1_kwh_m2": round(float(q1), 1),
            "insol_q3_kwh_m2": round(float(q3), 1),
            "n_low_insol": int(lo_m.sum()),
            "n_high_insol": int(hi_m.sum()),
            "n_low_with_freq": int(np.isfinite(fr[lo_m]).sum()),
            "n_high_with_freq": int(np.isfinite(fr[hi_m]).sum()),
            "coverage_low": round(float(np.isfinite(fr[lo_m]).mean()), 3) if lo_m.any() else np.nan,
            "coverage_high": round(float(np.isfinite(fr[hi_m]).mean()), 3) if hi_m.any() else np.nan,
        }
        for tag, mm in (("low", lo_m), ("high", hi_m)):
            v = fr[mm]
            v = v[np.isfinite(v)]
            rec[f"median_snow_freq_{tag}"] = round(float(np.median(v)), 3) if v.size else np.nan
            rec[f"p25_snow_freq_{tag}"] = round(float(np.percentile(v, 25)), 3) if v.size else np.nan
            rec[f"p75_snow_freq_{tag}"] = round(float(np.percentile(v, 75)), 3) if v.size else np.nan
        rec["snow_freq_difference"] = (
            round(rec["median_snow_freq_low"] - rec["median_snow_freq_high"], 3)
            if np.isfinite(rec["median_snow_freq_low"]) and np.isfinite(rec["median_snow_freq_high"])
            else np.nan)
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("elev_band_m").reset_index(drop=True)


def aspect_insolation_table(dem, slope, aspect, insol, freq,
                            band: tuple[float, float]) -> pd.DataFrame:
    """North vs south sector summary inside one elevation band."""
    ski = skiable_mask(slope)
    m0 = ski & (dem >= band[0]) & (dem < band[1])
    acl = aspect_class(aspect)
    rows = []
    for code, name in ((0, "north (315-45)"), (1, "south (135-225)"), (2, "east/west")):
        m = m0 & (acl == code)
        if not m.any():
            continue
        fr = freq[m]
        fr_ok = fr[np.isfinite(fr)]
        rows.append({
            "aspect_sector": name,
            "n_pixels": int(m.sum()),
            "area_km2": round(int(m.sum()) * PIXEL_AREA_M2 / 1e6, 4),
            "median_insolation_kwh_m2": round(float(np.nanmedian(insol[m])), 1),
            "coverage": round(float(np.isfinite(fr).mean()), 3),
            "median_snow_freq": round(float(np.median(fr_ok)), 3) if fr_ok.size else np.nan,
        })
    return pd.DataFrame(rows)


def field_priority(freq: np.ndarray, insol: np.ndarray, slope: np.ndarray,
                   freq_hi: float = 0.75, freq_lo: float = 0.40,
                   insol_q: tuple[float, float] = (25.0, 75.0)) -> tuple[np.ndarray, dict]:
    """Field-validation priority raster over the 15-35 deg slope window.

    0 = outside the slope window (not assessed here)
    1 = low exposure AND frequent snow    (candidate reliable-snow terrain)
    2 = high exposure AND infrequent snow (candidate early-loss terrain)
    3 = other skiable terrain
    4 = skiable but with too few usable observations to assign a frequency

    Classes 1 and 2 are the end-members a field pair should straddle: they are
    hypotheses to be checked on the ground, not conclusions.
    """
    ski = skiable_mask(slope)
    lo_cut, hi_cut = np.nanpercentile(insol[ski], insol_q)
    out = np.zeros(freq.shape, dtype="uint8")
    have = np.isfinite(freq) & ski
    out[ski & ~have] = 4
    out[have] = 3
    out[have & (insol <= lo_cut) & (freq >= freq_hi)] = 1
    out[have & (insol >= hi_cut) & (freq <= freq_lo)] = 2
    labels = {0: "outside the 15-35 deg slope window",
              1: "low exposure and frequent snow",
              2: "high exposure and infrequent snow",
              3: "other skiable terrain",
              4: "skiable, insufficient observation coverage"}
    meta = {
        "insol_low_cut_kwh_m2": round(float(lo_cut), 1),
        "insol_high_cut_kwh_m2": round(float(hi_cut), 1),
        "freq_high_threshold": freq_hi,
        "freq_low_threshold": freq_lo,
        "slope_window_deg": [SKIABLE_SLOPE_MIN, SKIABLE_SLOPE_MAX],
        "skiable_area_km2": round(float(ski.sum()) * PIXEL_AREA_M2 / 1e6, 3),
        "labels": labels,
        "class_counts": {int(c): int((out == c).sum()) for c in range(5)},
        "class_area_km2": {int(c): round(int((out == c).sum()) * PIXEL_AREA_M2 / 1e6, 3)
                           for c in range(5)},
    }
    return out, meta


def steep_layer(slope: np.ndarray, threshold: float = STEEP_SLOPE_MIN):
    m = (np.isfinite(slope) & (slope > threshold))
    return m.astype("uint8"), {
        "threshold_deg": threshold,
        "n_pixels": int(m.sum()),
        "area_km2": round(int(m.sum()) * PIXEL_AREA_M2 / 1e6, 3),
        "note": "Geometry only. Avalanche terrain classification needs snowpack, "
                "wind transport, start/runout zones and local expertise.",
    }
