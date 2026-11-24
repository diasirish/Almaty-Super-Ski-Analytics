"""Named zones inside the cluster area, built from OSM anchors, not from guesswork."""
from __future__ import annotations

import numpy as np

import osm as _osm
from config import LIFT_CORRIDOR_M, SKIABLE_SLOPE_MAX, SKIABLE_SLOPE_MIN


def _poly_mask(feature, grid) -> np.ndarray:
    from matplotlib.path import Path as MplPath
    x, y = feature.xy
    pts = np.column_stack([np.asarray(x), np.asarray(y)])
    gx, gy = grid.xy_centers()
    XX, YY = np.meshgrid(gx, gy)
    return MplPath(pts).contains_points(
        np.column_stack([XX.ravel(), YY.ravel()])).reshape(grid.shape)


def build(grid, slope: np.ndarray, features: dict | None = None) -> dict:
    """Boolean masks for the terrain groups the read-outs are reported over."""
    f = features or _osm.clip(_osm.load())
    lifts = [x for x in f["lift"] if x.length_m > 150]
    pistes = f["piste"]

    masks = {
        "all terrain": np.isfinite(slope),
        "skiable 15-35 deg": (np.isfinite(slope) & (slope >= SKIABLE_SLOPE_MIN)
                              & (slope <= SKIABLE_SLOPE_MAX)),
    }
    if lifts:
        masks["existing lift corridors"] = _osm.corridor_mask(lifts, grid,
                                                              LIFT_CORRIDOR_M)
    if pistes:
        masks["mapped pistes"] = _osm.corridor_mask(pistes, grid, 100.0)

    for area in f["area"]:
        nm = area.name or "winter sports area"
        try:
            masks[f"{nm} (OSM area)"] = _poly_mask(area, grid)
        except Exception:
            pass
    return masks


def zone_table(masks: dict, grid, dem: np.ndarray, slope: np.ndarray) -> "object":
    import pandas as pd
    rows = []
    px = grid.res ** 2 / 1e6
    for name, m in masks.items():
        if not m.any():
            continue
        rows.append({
            "zone": name, "pixels": int(m.sum()),
            "area_km2": round(float(m.sum()) * px, 3),
            "elev_min_m": round(float(np.nanmin(dem[m])), 0),
            "elev_median_m": round(float(np.nanmedian(dem[m])), 0),
            "elev_max_m": round(float(np.nanmax(dem[m])), 0),
            "slope_median_deg": round(float(np.nanmedian(slope[m])), 1),
        })
    return pd.DataFrame(rows)
