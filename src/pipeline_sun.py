"""Sunshine-hour products for the active study area. Cached, safe to re-run."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import AREA, INTERIM, OUT_TAB, OUTLOOK_YEAR, SUN_HOUR_STEP_MIN
from grids import DEM_GRID
from pipeline_terrain import terrain

CACHE = INTERIM / "sunhours"
CACHE.mkdir(parents=True, exist_ok=True)

SEASON_MONTHS = [11, 12, 1, 2, 3, 4]


def centroid():
    lon, lat = DEM_GRID.lonlat_centers()
    return float(np.mean(lat)), float(np.mean(lon))


def run(year: int = OUTLOOK_YEAR, months=None, force: bool = False):
    from sunhours import monthly_sun_hours
    from zones import build as build_zones

    months = months or SEASON_MONTHS
    t = terrain()
    masks = build_zones(DEM_GRID, t["slope"])
    if AREA == "kz_project":
        # At project scale the reported zones are the reconstructed footprints,
        # because the window itself is context and carries no OSM network.
        import footprint
        masks = {**footprint.build(DEM_GRID, t["slope"]), **masks}
    clat, clon = centroid()

    out, rows, profiles = {}, [], []
    for m in months:
        p = CACHE / f"sun_{year}_{m:02d}.npz"
        if p.exists() and not force:
            z = np.load(p, allow_pickle=True)
            out[m] = {"hours": z["hours"], "meta": json.loads(str(z["meta"][0]))}
            prof = json.loads(str(z["profiles"][0]))
        else:
            t0 = time.time()
            print(f"  sun hours {year}-{m:02d} ...", flush=True)
            r, _ = monthly_sun_hours(year, [m], t, clat, clon,
                                     step_min=SUN_HOUR_STEP_MIN, masks=masks)
            r = r[m]
            prof = {k: v.to_dict(orient="records") for k, v in r["profiles"].items()}
            np.savez_compressed(p, hours=r["hours"],
                                meta=np.array([json.dumps(r["meta"])], dtype=object),
                                profiles=np.array([json.dumps(prof)], dtype=object))
            out[m] = {"hours": r["hours"], "meta": r["meta"]}
            print(f"    median {np.nanmedian(r['hours']):.1f} h  "
                  f"max {np.nanmax(r['hours']):.1f} h  [{time.time()-t0:.0f}s]", flush=True)
        h = out[m]["hours"]
        import calendar
        days = calendar.monthrange(year, m)[1]
        rec = {"year": year, "month": m, "month_name": calendar.month_name[m],
               "days": days,
               "median_sun_hours": round(float(np.nanmedian(h)), 1),
               "mean_sun_hours": round(float(np.nanmean(h)), 1),
               "p95_sun_hours": round(float(np.nanpercentile(h, 95)), 1),
               "max_sun_hours": round(float(np.nanmax(h)), 1),
               "median_hours_per_day": round(float(np.nanmedian(h)) / days, 2),
               "max_hours_per_day": round(float(np.nanmax(h)) / days, 2)}
        for zone, mk in masks.items():
            if mk.any():
                rec[f"median_h__{zone}"] = round(float(np.nanmedian(h[mk])), 1)
        rows.append(rec)
        for zone, recs in prof.items():
            for d in recs:
                profiles.append({"zone": zone, **d})

    summary = pd.DataFrame(rows)
    prof_df = pd.DataFrame(profiles)
    OUT_TAB.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_TAB / f"sun_hours_monthly_{year}.csv", index=False)
    prof_df.to_csv(OUT_TAB / f"sun_hours_hourly_profile_{year}.csv", index=False)
    return out, summary, prof_df, masks, t


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else OUTLOOK_YEAR
    out, summary, prof, masks, t = run(year)
    print(summary.to_string(index=False))
    print(f"\nzones: {', '.join(k for k,v in masks.items() if v.any())}")
