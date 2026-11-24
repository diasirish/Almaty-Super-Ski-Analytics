"""Independent satellite and elevation sources, for cross-checking.

A single sensor and a single DEM are a single point of failure. Everything here
is open and needs no account: Landsat 8/9 surface reflectance, MODIS daily snow
cover, NASADEM and ALOS AW3D30 elevation, all through the Microsoft Planetary
Computer STAC (which signs asset URLs anonymously).

`SOURCE_REGISTRY` at the bottom lists further sources worth digging into, with
the endpoint, what it adds, and what it costs to use.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling

from config import (AOI_BBOX_WGS84, NDSI_THRESHOLD, NIR_THRESHOLD, RAW,
                    SCENE_CACHE)
from grids import DEM_GRID, S2_GRID
from s2 import _read_window, grid_tag

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"

# Landsat Collection 2 QA_PIXEL bit flags
L_FILL, L_DILATED, L_CIRRUS, L_CLOUD, L_SHADOW, L_SNOW, L_CLEAR, L_WATER = range(8)


def _pc_client(sign: bool = True):
    import planetary_computer as pc
    from pystac_client import Client
    return Client.open(PC_STAC, modifier=pc.sign_inplace if sign else None)


def _sign(href: str) -> str:
    """Sign a Planetary Computer blob URL at the moment of use.

    SAS tokens expire within the hour, so a long download must sign per scene
    rather than reuse the tokens handed out by the original search.
    """
    import planetary_computer as pc
    try:
        return pc.sign(href)
    except Exception:
        return href


# --------------------------------------------------------------------------
# Landsat 8/9 Collection 2 Level-2 surface reflectance
# --------------------------------------------------------------------------
def landsat_scenes(start: str, end: str, max_cloud: float = 20.0,
                   bbox=None) -> list[dict]:
    """Landsat 8/9 L2 scenes over the study area. Landsat 7 is excluded: its
    scan-line corrector failed in 2003 and the striping corrupts area statistics."""
    bbox = bbox or AOI_BBOX_WGS84
    c = _pc_client(sign=False)          # keep hrefs unsigned; sign at fetch time
    items = list(c.search(
        collections=["landsat-c2-l2"], bbox=bbox, datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud},
               "platform": {"in": ["landsat-8", "landsat-9"]}},
        max_items=None).items())
    out = []
    for it in items:
        a = it.assets
        if not all(k in a for k in ("green", "swir16", "nir08", "qa_pixel")):
            continue
        def so(key):
            rb = (a[key].extra_fields or {}).get("raster:bands") or [{}]
            return float(rb[0].get("scale", 1.0) or 1.0), float(rb[0].get("offset", 0.0) or 0.0)
        sc, off = so("green")
        out.append({
            "scene_id": it.id, "date": it.properties["datetime"][:10],
            "datetime": it.properties["datetime"],
            "platform": it.properties.get("platform"),
            "cloud_cover_pct": round(float(it.properties.get("eo:cloud_cover", np.nan)), 2),
            "wrs_path": it.properties.get("landsat:wrs_path"),
            "wrs_row": it.properties.get("landsat:wrs_row"),
            "collection": "landsat-c2-l2", "stac_url": PC_STAC,
            "scale": sc, "offset": off,
            "assets": {k: a[k].href for k in ("green", "swir16", "nir08", "qa_pixel")},
        })
    out.sort(key=lambda r: r["date"])
    return out


def _landsat_cache(rec, grid):
    d = SCENE_CACHE / f"landsat_{grid_tag(grid)}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{rec['scene_id']}.npz"


def fetch_landsat(rec: dict, grid=None, force: bool = False) -> dict | None:
    """Window one Landsat scene and reduce it to snow / valid masks.

    Native resolution is 30 m; it is resampled onto the 20 m analysis grid so the
    result sits on the same grid as the Sentinel-2 record. That resampling cannot
    create detail Landsat does not have.
    """
    grid = grid or S2_GRID
    p = _landsat_cache(rec, grid)
    if p.exists() and not force:
        try:
            z = np.load(p, allow_pickle=True)
            return {"snow": z["snow"], "valid": z["valid"], "qa_snow": z["qa_snow"],
                    "meta": json.loads(str(z["meta"][0]))}
        except Exception:
            p.unlink(missing_ok=True)
    try:
        qa = _read_window(_sign(rec["assets"]["qa_pixel"]), grid,
                          Resampling.nearest).astype("uint16")
        g = _read_window(_sign(rec["assets"]["green"]), grid, Resampling.average)
        s = _read_window(_sign(rec["assets"]["swir16"]), grid, Resampling.average)
        n = _read_window(_sign(rec["assets"]["nir08"]), grid, Resampling.average)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    sc, off = rec["scale"], rec["offset"]
    gr, sw, ni = g * sc + off, s * sc + off, n * sc + off
    with np.errstate(invalid="ignore", divide="ignore"):
        ndsi = (gr - sw) / (gr + sw)
    ndsi = np.where(np.isfinite(ndsi), ndsi, -1.0)

    bit = lambda b: (qa >> b) & 1
    reject = (bit(L_FILL) | bit(L_DILATED) | bit(L_CIRRUS) | bit(L_CLOUD)
              | bit(L_SHADOW)).astype(bool)
    filled = (g == 0) & (s == 0) & (n == 0)
    valid = (~reject) & (~filled)
    water = bit(L_WATER).astype(bool)
    snow = (ndsi > NDSI_THRESHOLD) & (ni > NIR_THRESHOLD) & valid & (~water)
    qa_snow = bit(L_SNOW).astype(bool) & valid

    meta = {**{k: rec[k] for k in ("scene_id", "date", "datetime", "platform",
                                   "cloud_cover_pct", "wrs_path", "wrs_row",
                                   "collection", "scale", "offset")},
            "valid_fraction": round(float(valid.mean()), 4),
            "snow_fraction_of_valid": round(float(snow.sum() / max(valid.sum(), 1)), 4),
            "qa_snow_fraction_of_valid": round(float(qa_snow.sum() / max(valid.sum(), 1)), 4),
            "native_resolution_m": 30,
            "resampled_to_m": grid.res}
    np.savez_compressed(p, snow=snow.astype("uint8"), valid=valid.astype("uint8"),
                        qa_snow=qa_snow.astype("uint8"),
                        meta=np.array([json.dumps(meta)], dtype=object))
    return {"snow": snow.astype("uint8"), "valid": valid.astype("uint8"),
            "qa_snow": qa_snow.astype("uint8"), "meta": meta}


def fetch_landsat_all(records, grid=None, workers: int = 6, verbose: bool = True):
    grid = grid or S2_GRID
    ok, failed = [], []
    todo = [r for r in records if not _landsat_cache(r, grid).exists()]
    if verbose:
        print(f"  {len(records)} Landsat scenes: {len(records)-len(todo)} cached, "
              f"{len(todo)} to download", flush=True)
    t0 = time.time()
    got = {}
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(fetch_landsat, r, grid): r for r in todo}
            for i, f in enumerate(as_completed(futs), 1):
                r = futs[f]
                try:
                    res = f.result()
                except Exception as e:
                    res = {"error": f"{type(e).__name__}: {e}"}
                if res is None or "error" in (res or {}):
                    failed.append({"scene_id": r["scene_id"], "date": r["date"],
                                   "error": (res or {}).get("error", "unknown")})
                else:
                    got[r["scene_id"]] = res
                if verbose and i % 10 == 0:
                    print(f"    {i}/{len(todo)} ({time.time()-t0:.0f}s)", flush=True)
    for r in records:
        if r["scene_id"] in got:
            ok.append(got[r["scene_id"]])
        elif _landsat_cache(r, grid).exists():
            res = fetch_landsat(r, grid)
            if res and "error" not in res:
                ok.append(res)
    ok.sort(key=lambda d: d["meta"]["date"])
    return {"scenes": ok, "failed": failed}


# --------------------------------------------------------------------------
# Alternative elevation models
# --------------------------------------------------------------------------
def alternative_dem(collection: str, grid=None, bbox=None) -> tuple[np.ndarray, dict]:
    """Mosaic an alternative DEM collection onto the analysis grid."""
    from rasterio.merge import merge
    from rasterio.warp import reproject

    grid = grid or DEM_GRID
    bbox = bbox or AOI_BBOX_WGS84
    c = _pc_client()
    items = list(c.search(collections=[collection], bbox=bbox, max_items=20).items())
    if not items:
        raise RuntimeError(f"no items for {collection}")
    key = "elevation" if "elevation" in items[0].assets else "data"
    srcs = [rasterio.open(it.assets[key].href) for it in items]
    try:
        mosaic, transform = merge(srcs, resampling=Resampling.bilinear)
        src_crs, src_nodata = srcs[0].crs, srcs[0].nodata
    finally:
        for s in srcs:
            s.close()
    dst = np.full(grid.shape, np.nan, dtype="float32")
    reproject(source=mosaic[0], destination=dst, src_transform=transform,
              src_crs=src_crs, src_nodata=src_nodata, dst_transform=grid.transform,
              dst_crs=grid.crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
    meta = {"collection": collection, "n_tiles": len(items),
            "item_ids": [it.id for it in items], "asset": key,
            "source": "Microsoft Planetary Computer STAC"}
    return dst, meta


def compare_dems(reference: np.ndarray, others: dict, grid=None) -> pd.DataFrame:
    """Elevation and slope agreement between the reference DEM and alternatives."""
    from dem import slope_aspect
    grid = grid or DEM_GRID
    ref_slope, _ = slope_aspect(reference, grid.res)
    rows = []
    for name, arr in others.items():
        d = arr - reference
        ok = np.isfinite(d)
        sl, _ = slope_aspect(np.where(np.isfinite(arr), arr,
                                      np.nanmean(arr)), grid.res)
        ds = sl - ref_slope
        rows.append({
            "dem": name,
            "n_valid_pixels": int(ok.sum()),
            "elev_mean_difference_m": round(float(np.nanmean(d[ok])), 2),
            "elev_median_difference_m": round(float(np.nanmedian(d[ok])), 2),
            "elev_std_difference_m": round(float(np.nanstd(d[ok])), 2),
            "elev_p95_abs_difference_m": round(float(np.nanpercentile(np.abs(d[ok]), 95)), 2),
            "slope_mean_difference_deg": round(float(np.nanmean(ds[ok])), 3),
            "slope_std_difference_deg": round(float(np.nanstd(ds[ok])), 3),
            "correlation": round(float(np.corrcoef(reference[ok], arr[ok])[0, 1]), 6),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# MODIS daily snow cover
# --------------------------------------------------------------------------
def modis_snow_scenes(start: str, end: str, bbox=None) -> list[dict]:
    bbox = bbox or AOI_BBOX_WGS84
    c = _pc_client(sign=False)
    items = list(c.search(collections=["modis-10A1-061"], bbox=bbox,
                          datetime=f"{start}/{end}", max_items=None).items())
    return [{"scene_id": it.id, "date": (it.properties.get("datetime")
                                         or it.properties.get("start_datetime") or "")[:10],
             "assets": {"NDSI_Snow_Cover": it.assets["NDSI_Snow_Cover"].href}
             if "NDSI_Snow_Cover" in it.assets else {}}
            for it in items]


def modis_snow_fraction(records: list[dict], grid=None, limit: int | None = None):
    """Area-mean MODIS snow cover per date. 500 m pixels: regional context only."""
    grid = grid or DEM_GRID
    rows = []
    for rec in (records[:limit] if limit else records):
        if not rec["assets"]:
            continue
        try:
            a = _read_window(_sign(rec["assets"]["NDSI_Snow_Cover"]), grid,
                             Resampling.nearest)
        except Exception as e:
            rows.append({"date": rec["date"], "error": f"{type(e).__name__}"})
            continue
        # 0-100 = NDSI snow cover; 200+ are fill / cloud / other flags
        valid = (a >= 0) & (a <= 100)
        rows.append({
            "date": rec["date"], "scene_id": rec["scene_id"],
            "valid_fraction": round(float(valid.mean()), 4),
            "mean_ndsi_snow_cover": (round(float(a[valid].mean()), 2)
                                     if valid.any() else np.nan),
            "snow_fraction_gt40": (round(float((a[valid] > 40).mean()), 4)
                                   if valid.any() else np.nan),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Further sources worth digging into
# --------------------------------------------------------------------------
SOURCE_REGISTRY = [
    {"name": "Sentinel-2 L2A", "role": "primary optical snow record", "used": True,
     "resolution": "10-20 m", "revisit": "5 days (2 satellites)",
     "endpoint": "https://earth-search.aws.element84.com/v1 (sentinel-2-l2a)",
     "access": "open, no account",
     "adds": "the finest routinely available optical snow mapping for this terrain",
     "costs": "cloud gaps; cast shadow removes exactly the slopes of interest"},
    {"name": "Landsat 8/9 Collection 2 L2", "role": "independent optical cross-check",
     "used": True, "resolution": "30 m", "revisit": "8 days (two satellites)",
     "endpoint": "https://planetarycomputer.microsoft.com/api/stac/v1 (landsat-c2-l2)",
     "access": "open, anonymous SAS signing via the planetary-computer package",
     "adds": "a second sensor, a second atmospheric correction and the USGS QA snow "
             "flag; extends the record back to 2013",
     "costs": "coarser and less frequent; different spectral response from Sentinel-2"},
    {"name": "MODIS MOD10A1 / MYD10A1 v061", "role": "daily regional snow context",
     "used": True, "resolution": "500 m", "revisit": "daily, two platforms",
     "endpoint": "https://planetarycomputer.microsoft.com/api/stac/v1 (modis-10A1-061)",
     "access": "open, anonymous",
     "adds": "a daily time series that fills the gaps between clear Sentinel-2 dates",
     "costs": "500 m cannot see an individual slope in this relief"},
    {"name": "NASADEM", "role": "elevation cross-check", "used": True,
     "resolution": "30 m", "revisit": "single epoch (SRTM 2000, reprocessed)",
     "endpoint": "https://planetarycomputer.microsoft.com/api/stac/v1 (nasadem)",
     "access": "open, anonymous",
     "adds": "an independent DEM with different voids and a different vertical datum",
     "costs": "EGM96 geoid, radar shadow in steep terrain, 2000 epoch"},
    {"name": "ALOS World 3D-30m (AW3D30)", "role": "elevation cross-check", "used": True,
     "resolution": "30 m", "revisit": "single epoch (optical stereo, 2006-2011)",
     "endpoint": "https://planetarycomputer.microsoft.com/api/stac/v1 (alos-dem)",
     "access": "open, anonymous",
     "adds": "optical-stereo elevation, so its errors are uncorrelated with radar DEMs",
     "costs": "cloud-related voids; EGM96"},
    {"name": "Sentinel-1 GRD (SAR)", "role": "wet-snow detection, cloud-independent",
     "used": False, "resolution": "10-20 m", "revisit": "6-12 days",
     "endpoint": "https://earth-search.aws.element84.com/v1 (sentinel-1-grd)",
     "access": "open, no account",
     "adds": "sees through cloud and at night; backscatter drop identifies WET snow, "
             "which is what matters for spring melt timing",
     "costs": "needs radiometric terrain correction and a dry-snow reference; "
              "layover and shadow in steep terrain; does not see dry snow well"},
    {"name": "Copernicus HR-S&I (snow & ice products)",
     "role": "ready-made fractional snow cover", "used": False,
     "resolution": "20 m", "revisit": "Sentinel-2 cadence",
     "endpoint": "https://cryo.land.copernicus.eu/ (CLMS Cryosphere)",
     "access": "free registration required",
     "adds": "an operational, validated fractional snow cover product; removes the "
             "need to justify one's own thresholds",
     "costs": "account required; coverage is pan-European, so Kazakhstan must be "
              "checked before relying on it"},
    {"name": "VIIRS VNP10A1", "role": "daily snow, MODIS successor", "used": False,
     "resolution": "375-750 m", "revisit": "daily",
     "endpoint": "https://nsidc.org/data/vnp10a1 (NASA Earthdata)",
     "access": "free Earthdata login",
     "adds": "continuity after MODIS end-of-life",
     "costs": "login; coarse"},
    {"name": "ERA5-Land hourly", "role": "meteorological reanalysis", "used": True,
     "resolution": "~9 km", "revisit": "hourly",
     "endpoint": "Copernicus CDS, or the Open-Meteo archive API without an account",
     "access": "open (CDS needs an account; Open-Meteo does not)",
     "adds": "temperature, wind and radiation context for every date",
     "costs": "9 km orography is not this mountain; no precipitation at this point "
              "through the Open-Meteo archive"},
    {"name": "Kazhydromet station observations",
     "role": "ground truth, the only real one", "used": False,
     "resolution": "point", "revisit": "daily to hourly",
     "endpoint": "https://www.kazhydromet.kz/ (published bulletins; archive on request)",
     "access": "bulletins public; station time series by request",
     "adds": "actual measured snow depth and temperature, which no satellite gives",
     "costs": "sparse in the mountains; archive access needs a request"},
    {"name": "OpenStreetMap", "role": "existing lifts, pistes, place names", "used": True,
     "resolution": "vector", "revisit": "continuous community editing",
     "endpoint": "https://overpass-api.de/api/interpreter",
     "access": "open, ODbL licence",
     "adds": "the only open georeferenced record of what is on the mountain today",
     "costs": "community-maintained, completeness varies, and it holds nothing about "
              "what is planned"},
    {"name": "Drone photogrammetry / lidar", "role": "the resolution gap", "used": False,
     "resolution": "0.1-1 m", "revisit": "on demand",
     "endpoint": "field survey",
     "adds": "terrain detail the 30 m DEM smooths away entirely, which is the scale "
             "lift towers and pistes are actually designed at",
     "costs": "flight permissions, field time, processing"},
]


def registry_table() -> pd.DataFrame:
    return pd.DataFrame(SOURCE_REGISTRY)[
        ["name", "role", "used", "resolution", "revisit", "access", "endpoint",
         "adds", "costs"]]
