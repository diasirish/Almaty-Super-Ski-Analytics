"""Reconstructing the stated 1,022 ha project territory inside the project window.

Kazakh Tourism Development states a project territory of 1,022 ha with about
20 ha built up. No boundary has been published, so no footprint here is the
project's own. Two are derived instead, and every project-scale number is
reported against both, so the reader can see how much the answer depends on
where the line was drawn:

  disc      the 1,022 ha closest to the plateau reference point. It uses no
            terrain information at all, so it cannot flatter the terrain.
  gentlest  the 1,022 ha of gentlest ground within FOOTPRINT_SEARCH_RADIUS_M of
            the same point. This is the most favourable territory a planner
            could choose. A gradient conclusion that survives on this footprint
            is therefore not an artefact of the boundary.
"""
from __future__ import annotations

import numpy as np
from pyproj import Transformer

from config import (CRS_WGS84, FOOTPRINT_SEARCH_RADIUS_M, FOOTPRINT_SMOOTH_M,
                    PLATEAU_POINT, PROJECT_AREA_HA)


def _centre_xy(grid, centre=None) -> tuple[float, float]:
    lon, lat = centre or PLATEAU_POINT
    tr = Transformer.from_crs(CRS_WGS84, grid.crs, always_xy=True)
    x, y = tr.transform(lon, lat)
    return float(x), float(y)


def radius_field(grid, centre=None) -> np.ndarray:
    """Distance from the centre point to every pixel centre, in metres."""
    cx, cy = _centre_xy(grid, centre)
    gx, gy = grid.xy_centers()
    XX, YY = np.meshgrid(gx, gy)
    return np.hypot(XX - cx, YY - cy)


def n_pixels(grid, area_ha: float = PROJECT_AREA_HA) -> int:
    """How many grid pixels make up `area_ha`."""
    return int(round(area_ha * 1e4 / grid.res ** 2))


def _take_lowest(score: np.ndarray, n: int) -> np.ndarray:
    idx = np.argsort(score.ravel(), kind="stable")[:n]
    m = np.zeros(score.size, dtype=bool)
    m[idx] = True
    return m.reshape(score.shape)


def disc(grid, area_ha: float = PROJECT_AREA_HA, centre=None):
    """The `area_ha` pixels nearest the centre. Returns (mask, outer radius in m)."""
    R = radius_field(grid, centre)
    n = n_pixels(grid, area_ha)
    m = _take_lowest(R, n)
    return m, float(R[m].max())


def _smooth(a: np.ndarray, grid, window_m: float) -> np.ndarray:
    from scipy.ndimage import uniform_filter
    k = max(1, int(round(window_m / grid.res)))
    if k % 2 == 0:
        k += 1
    fill = float(np.nanmax(a)) if np.isfinite(a).any() else 0.0
    return uniform_filter(np.nan_to_num(a, nan=fill).astype("float64"),
                          size=k, mode="nearest")


def gentlest(grid, slope: np.ndarray, area_ha: float = PROJECT_AREA_HA,
             centre=None, radius_m: float = FOOTPRINT_SEARCH_RADIUS_M,
             smooth_m: float = FOOTPRINT_SMOOTH_M):
    """The `area_ha` of gentlest ground within `radius_m`.

    Slope is mean-filtered over `smooth_m` first, so a single flat pixel inside
    a cliff band cannot be selected ahead of a genuine bench.
    """
    R = radius_field(grid, centre)
    s = _smooth(slope, grid, smooth_m)
    s = np.where(R <= radius_m, s, np.inf)
    return _take_lowest(s, n_pixels(grid, area_ha))


def components(mask: np.ndarray):
    """(number of connected pieces, pixels in the largest, mask of the largest)."""
    from scipy.ndimage import label
    lab, k = label(mask)
    if k == 0:
        return 0, 0, np.zeros_like(mask)
    sizes = np.bincount(lab.ravel())[1:]
    big = 1 + int(np.argmax(sizes))
    return int(k), int(sizes.max()), lab == big


def build(grid, slope: np.ndarray, area_ha: float = PROJECT_AREA_HA,
          centre=None) -> dict:
    """Both footprints plus the surrounding window, as named masks."""
    d, r = disc(grid, area_ha, centre)
    gq = gentlest(grid, slope, area_ha, centre)
    return {
        f"project window ({grid.area_km2:.0f} km2)": np.isfinite(slope),
        f"footprint A: {area_ha:.0f} ha disc (r={r/1000:.2f} km)": d,
        f"footprint B: gentlest {area_ha:.0f} ha": gq,
    }


def summary(masks: dict, grid, dem: np.ndarray, slope: np.ndarray):
    """Area, elevation and slope of each footprint, with contiguity."""
    import pandas as pd
    rows = []
    ha = grid.res ** 2 / 1e4
    for name, m in masks.items():
        if not m.any():
            continue
        k, big, _ = components(m)
        rows.append({
            "footprint": name,
            "area_ha": round(float(m.sum()) * ha, 1),
            "pieces": k,
            "largest_piece_ha": round(big * ha, 1),
            "largest_piece_share": round(big / float(m.sum()), 3),
            "elev_min_m": round(float(np.nanmin(dem[m])), 0),
            "elev_median_m": round(float(np.nanmedian(dem[m])), 0),
            "elev_max_m": round(float(np.nanmax(dem[m])), 0),
            "vertical_m": round(float(np.nanmax(dem[m]) - np.nanmin(dem[m])), 0),
            "slope_median_deg": round(float(np.nanmedian(slope[m])), 1),
            "slope_p90_deg": round(float(np.nanpercentile(slope[m], 90)), 1),
        })
    return pd.DataFrame(rows)
