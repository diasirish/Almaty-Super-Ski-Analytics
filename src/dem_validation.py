"""Does the choice of open DEM change the planning answer?

Comparing elevations is the easy half of a DEM check and the half that flatters
every product: three global DEMs agree to a few metres almost everywhere, so a
table of elevation differences says little about whether a slope, a horizon or
an insolation map built on one of them can be trusted.

This module therefore runs the whole chain - slope, aspect, ray-marched
horizon, sky view factor, clear-sky insolation, direct sunshine duration -
separately on each DEM, and compares the products a planner would actually read.
Differences are reported as distributions, not single numbers, because the
disagreement is strongly terrain dependent.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from rasterio.warp import transform_bounds

from config import CRS_WGS84, HORIZON_BUFFER_M, INTERIM
from dem import horizon_angles, sky_view_factor, slope_aspect
from grids import DEM_GRID

# Microsoft Planetary Computer collection ids.
COLLECTIONS = {
    "NASADEM": "nasadem",
    "ALOS AW3D30": "alos-dem",
}
CACHE = INTERIM / "dem_validation"


def wgs84_bbox(grid) -> tuple[float, float, float, float]:
    return transform_bounds(grid.crs, CRS_WGS84, *grid.bounds, densify_pts=21)


def _fill(a: np.ndarray) -> np.ndarray:
    """Replace gaps with the nearest finite value so slope stays defined."""
    if np.isfinite(a).all():
        return a
    from scipy.ndimage import distance_transform_edt
    bad = ~np.isfinite(a)
    idx = distance_transform_edt(bad, return_distances=False, return_indices=True)
    return a[tuple(idx)]


def terrain_from(name: str, grid=None, buffer_m: float = HORIZON_BUFFER_M,
                 n_azimuth: int | None = None, force: bool = False,
                 verbose: bool = True) -> dict:
    """The full terrain chain built on one alternative DEM."""
    from alt_sources import alternative_dem
    grid = grid or DEM_GRID
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name.replace(' ', '_')}_{grid.width}x{grid.height}.npz"
    if p.exists() and not force:
        z = np.load(p, allow_pickle=True)
        d = {k: z[k] for k in z.files}
        d["meta"] = json.loads(str(d["meta"][0]))
        return d

    t0 = time.time()
    coll = COLLECTIONS[name]
    if verbose:
        print(f"  {name}: AOI grid ...", flush=True)
    dem_aoi, meta = alternative_dem(coll, grid, wgs84_bbox(grid))
    grid_buf = grid.buffered(buffer_m)
    if verbose:
        print(f"  {name}: buffered grid for the horizon ...", flush=True)
    dem_buf, _ = alternative_dem(coll, grid_buf, wgs84_bbox(grid_buf))

    gaps = int((~np.isfinite(dem_aoi)).sum())
    dem_aoi_f, dem_buf_f = _fill(dem_aoi), _fill(dem_buf)
    slope, aspect = slope_aspect(dem_aoi_f, grid.res)
    kw = {"n_az": n_azimuth} if n_azimuth else {}
    az, hz = horizon_angles(dem_buf_f, grid_buf, grid, verbose=False, **kw)
    svf = sky_view_factor(az, hz, slope, aspect)
    meta.update({"gap_pixels_filled": gaps, "seconds": round(time.time() - t0, 1)})
    out = dict(dem=dem_aoi_f, slope=slope, aspect=aspect, svf=svf,
               azimuths=az, horizon=hz,
               meta=np.array([json.dumps(meta)], dtype=object))
    np.savez_compressed(p, **out)
    out["meta"] = meta
    if verbose:
        print(f"  {name}: done in {time.time()-t0:.0f}s, {gaps} gap pixels filled",
              flush=True)
    return out


def _stats(d: np.ndarray, mask: np.ndarray | None = None) -> dict:
    v = d[mask] if mask is not None else d
    v = v[np.isfinite(v)]
    if not v.size:
        return {}
    return {
        "median": round(float(np.median(v)), 3),
        "mean": round(float(np.mean(v)), 3),
        "std": round(float(np.std(v)), 3),
        "p05": round(float(np.percentile(v, 5)), 3),
        "p95": round(float(np.percentile(v, 95)), 3),
        "p95_abs": round(float(np.percentile(np.abs(v), 95)), 3),
        "max_abs": round(float(np.max(np.abs(v))), 3),
    }


def compare_layer(ref: np.ndarray, others: dict, label: str,
                  mask: np.ndarray | None = None,
                  relative: bool = False) -> pd.DataFrame:
    """Difference statistics for one derived layer, alternative minus reference."""
    rows = []
    for name, arr in others.items():
        d = arr - ref
        ok = np.isfinite(d) & np.isfinite(ref)
        if mask is not None:
            ok &= mask
        rec = {"layer": label, "dem": name, "n_pixels": int(ok.sum())}
        rec.update({f"diff_{k}": v for k, v in _stats(d, ok).items()})
        if relative:
            with np.errstate(invalid="ignore", divide="ignore"):
                rel = 100.0 * d / np.where(np.abs(ref) > 1e-6, ref, np.nan)
            rec.update({f"pct_{k}": v for k, v in _stats(rel, ok).items()})
        r2 = np.corrcoef(ref[ok], arr[ok])[0, 1] if ok.sum() > 2 else np.nan
        rec["correlation"] = round(float(r2), 6)
        rows.append(rec)
    return pd.DataFrame(rows)


def aspect_difference(ref: np.ndarray, other: np.ndarray) -> np.ndarray:
    """Signed smallest angle between two aspect rasters, in degrees."""
    d = (other - ref + 180.0) % 360.0 - 180.0
    return d


def rank_shift(ref: np.ndarray, other: np.ndarray, mask: np.ndarray,
               top_fraction: float = 0.10) -> dict:
    """How much the DEM choice reshuffles the ranking a planner would read.

    A planner does not use the absolute kWh value; they use "which ground is in
    the top tenth". This measures whether that set survives a change of DEM.
    """
    ok = mask & np.isfinite(ref) & np.isfinite(other)
    n = int(ok.sum())
    if n < 100:
        return {}
    k = max(1, int(round(top_fraction * n)))
    ri = np.argsort(-ref[ok])[:k]
    oi = np.argsort(-other[ok])[:k]
    inter = len(set(ri.tolist()) & set(oi.tolist()))
    from scipy.stats import spearmanr
    rho = float(spearmanr(ref[ok], other[ok]).statistic)
    return {"n_pixels": n, "top_fraction": top_fraction, "top_n": k,
            "overlap": inter, "overlap_share": round(inter / k, 4),
            "spearman_rho": round(rho, 6)}
