"""Ski-terrain gradient classes, and arithmetic that checks the published figures.

Class boundaries are the percent grades used in the British Columbia All Season
Resort Guidelines, Chapter II (Mountain Resorts) - the published source closest
to the practice of the planners named on this project - converted to degrees
here. Skier densities are the per-hectare ranges from the same document.

These are a planning convention from another jurisdiction, not a Kazakh
standard, and not the project's own design criteria. They are used only to ask
whether the published mix of runs is consistent with the ground.
"""
from __future__ import annotations

import numpy as np

# (label, grade from %, grade to %, skiers per hectare low, high)
GRADIENT_CLASSES_PCT = [
    ("Beginner",              0.0,  15.0, 35, 75),
    ("Novice",               15.0,  25.0, 30, 60),
    ("Low intermediate",     25.0,  35.0, 20, 40),
    ("Intermediate",         35.0,  40.0, 15, 30),
    ("Advanced intermediate", 40.0, 60.0, 10, 20),
    ("Expert",               60.0, 1e4,    5, 10),
]


def _deg(pct: float) -> float:
    return float(np.degrees(np.arctan(pct / 100.0)))


GRADIENT_CLASSES = [(lab, _deg(a), _deg(b), lo, hi)
                    for lab, a, b, lo, hi in GRADIENT_CLASSES_PCT]

# "Green and blue" in the operator's wording maps to beginner through low
# intermediate, i.e. grades up to 35 % (19.3 deg).
GREEN_BLUE_MAX_DEG = _deg(35.0)


def class_index(slope: np.ndarray) -> np.ndarray:
    """Gradient class per pixel, 0..5; -1 where slope is undefined."""
    out = np.full(slope.shape, -1, dtype="int8")
    for i, (_, lo, hi, _, _) in enumerate(GRADIENT_CLASSES):
        out[np.isfinite(slope) & (slope >= lo) & (slope < hi)] = i
    return out


def class_table(slope: np.ndarray, grid, masks: dict):
    """Area and share of every gradient class, for each named mask."""
    import pandas as pd
    ha = grid.res ** 2 / 1e4
    rows = []
    for name, m in masks.items():
        m = m & np.isfinite(slope)
        if not m.any():
            continue
        tot = float(m.sum())
        for lab, lo, hi, dlo, dhi in GRADIENT_CLASSES:
            sel = m & (slope >= lo) & (slope < hi)
            rows.append({
                "area": name, "gradient_class": lab,
                "slope_from_deg": round(lo, 1),
                "slope_to_deg": round(hi, 1) if hi < 1e3 else 90.0,
                "grade_from_pct": round(100 * np.tan(np.radians(lo)), 0),
                "grade_to_pct": (round(100 * np.tan(np.radians(hi)), 0)
                                 if hi < 80 else None),
                "area_ha": round(sel.sum() * ha, 1),
                "share": round(sel.sum() / tot, 4),
                "skiers_per_ha_low": dlo, "skiers_per_ha_high": dhi,
            })
    return pd.DataFrame(rows)


def green_blue_share(slope: np.ndarray, masks: dict, grid):
    """Share and area of ground at green/blue gradients, per named mask."""
    import pandas as pd
    ha = grid.res ** 2 / 1e4
    rows = []
    for name, m in masks.items():
        m = m & np.isfinite(slope)
        if not m.any():
            continue
        gb = m & (slope < GREEN_BLUE_MAX_DEG)
        rows.append({
            "area": name,
            "area_ha": round(m.sum() * ha, 1),
            "green_blue_ha": round(gb.sum() * ha, 1),
            "green_blue_share": round(gb.sum() / float(m.sum()), 4),
            "slope_median_deg": round(float(np.nanmedian(slope[m])), 1),
            "above_31deg_share": round(
                float((slope[m] >= GRADIENT_CLASSES[-1][1]).mean()), 4),
        })
    return pd.DataFrame(rows)


def piste_area_demand(piste_km: float, green_blue_share_target: float,
                      widths_m=(30.0, 40.0, 50.0)):
    """Piste hectares implied by a stated network length, for several widths.

    The operator publishes a length (60 km) and a mix (about 70 % green and
    blue) but no width, and width is what converts one into an area. Three
    plausible widths are carried through instead of one assumed value.
    """
    import pandas as pd
    rows = []
    for w in widths_m:
        total = piste_km * 1000.0 * w / 1e4
        rows.append({
            "assumed_mean_piste_width_m": w,
            "piste_area_ha": round(total, 1),
            "green_blue_piste_ha": round(total * green_blue_share_target, 1),
        })
    return pd.DataFrame(rows)


def feasibility(demand, available_ha: float, label: str):
    """What share of the available gentle ground each width option would consume."""
    d = demand.copy()
    d["available_green_blue_ha"] = round(available_ha, 1)
    d["share_of_available_consumed"] = (
        d["green_blue_piste_ha"] / available_ha).round(3)
    d["footprint"] = label
    return d
