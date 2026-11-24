"""Compute-and-cache terrain + insolation layers. Idempotent: safe to re-run."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (GROUND_ALBEDO, HORIZON_BUFFER_M, INSOLATION_PERIODS, INTERIM,
                    OUTLOOK_MONTHS_2027, OUTLOOK_YEAR, PLATEAU_POINT)
from dem import build_dem, horizon_angles, sky_view_factor, slope_aspect
from grids import DEM_GRID

CACHE = INTERIM / "terrain.npz"
INSOL_CACHE = INTERIM / "insolation"
INSOL_CACHE.mkdir(parents=True, exist_ok=True)


def terrain(force: bool = False) -> dict:
    if CACHE.exists() and not force:
        z = np.load(CACHE, allow_pickle=True)
        return {k: z[k] for k in z.files}

    t0 = time.time()
    print("[1/4] DEM on the 30 m analysis grid", flush=True)
    dem_aoi, meta = build_dem(DEM_GRID)

    print("[2/4] DEM on the buffered grid (horizon search)", flush=True)
    grid_buf = DEM_GRID.buffered(HORIZON_BUFFER_M)
    dem_buf, _ = build_dem(grid_buf, verbose=False)

    print("[3/4] slope / aspect (Horn 3x3)", flush=True)
    slope, aspect = slope_aspect(dem_aoi, DEM_GRID.res)

    print("[4/4] horizon angles + sky view factor", flush=True)
    az, hz = horizon_angles(dem_buf, grid_buf, DEM_GRID)
    svf = sky_view_factor(az, hz, slope, aspect)

    out = dict(dem=dem_aoi, slope=slope, aspect=aspect, svf=svf,
               azimuths=az, horizon=hz,
               meta=np.array([json.dumps(meta)], dtype=object))
    np.savez_compressed(CACHE, **out)
    print(f"terrain cached in {time.time()-t0:.0f}s -> {CACHE}", flush=True)
    return out


def insolation_period(label: str, start: str, end: str, t: dict,
                      force: bool = False) -> dict:
    from insolation import accumulate_insolation
    p = INSOL_CACHE / f"{label}.npz"
    if p.exists() and not force:
        z = np.load(p, allow_pickle=True)
        d = {k: z[k] for k in z.files}
        d["meta"] = json.loads(str(d["meta"][0]))
        return d

    lon, lat = DEM_GRID.lonlat_centers()
    clat, clon = float(np.mean(lat)), float(np.mean(lon))
    t0 = time.time()
    print(f"  insolation {label}: {start} .. {end}", flush=True)
    res = accumulate_insolation(
        start, end, t["dem"], t["slope"], t["aspect"], t["svf"],
        t["azimuths"], t["horizon"], clat, clon, verbose=False)
    meta = res.pop("meta")
    meta["centroid_lat"] = round(clat, 5)
    meta["centroid_lon"] = round(clon, 5)
    np.savez_compressed(p, meta=np.array([json.dumps(meta)], dtype=object), **res)
    res["meta"] = meta
    print(f"    done in {time.time()-t0:.0f}s  "
          f"median total = {np.nanmedian(res['total']):.1f} kWh/m2", flush=True)
    return res


def all_insolation(t: dict, force: bool = False) -> dict:
    out = {}
    for label, (s, e) in INSOLATION_PERIODS.items():
        out[label] = insolation_period(label, s, e, t, force=force)
    # 2027 outlook: one raster per month
    import calendar
    for m in OUTLOOK_MONTHS_2027:
        last = calendar.monthrange(OUTLOOK_YEAR, m)[1]
        label = f"{OUTLOOK_YEAR}_{m:02d}"
        out[label] = insolation_period(
            label, f"{OUTLOOK_YEAR}-{m:02d}-01", f"{OUTLOOK_YEAR}-{m:02d}-{last:02d}",
            t, force=force)
    return out


if __name__ == "__main__":
    t = terrain(force="--force" in sys.argv)
    print(f"DEM range: {np.nanmin(t['dem']):.0f} .. {np.nanmax(t['dem']):.0f} m")
    print(f"slope median {np.nanmedian(t['slope']):.1f} deg, "
          f"SVF median {np.nanmedian(t['svf']):.3f}")
    all_insolation(t)
    print("terrain pipeline complete")
