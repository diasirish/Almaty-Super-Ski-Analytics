"""Sentinel-2 L2A search, windowed COG reads, NDSI snow mask, scene cache."""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds

from config import (MAX_CLOUD_PCT, MGRS_TILE, NDSI_THRESHOLD, NIR_THRESHOLD,
                    SCENE_CACHE, SCL_NEVER_SNOW, SCL_REJECT, SCL_SNOW,
                    STAC_COLLECTION, STAC_URL)
from grids import S2_GRID

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.jp2")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")

# Earth Search v1 asset keys -> our band names
ASSETS = {"green": "B03", "nir": "B08", "swir16": "B11", "scl": "SCL"}


def search_scenes(start: str, end: str, max_cloud: float = MAX_CLOUD_PCT,
                  tile: str = MGRS_TILE, url: str = STAC_URL,
                  collection: str = STAC_COLLECTION) -> list[dict]:
    """STAC search for one date range, restricted to a single MGRS tile."""
    from pystac_client import Client

    client = Client.open(url)
    search = client.search(
        collections=[collection],
        datetime=f"{start}T00:00:00Z/{end}T23:59:59Z",
        query={"eo:cloud_cover": {"lt": max_cloud},
               "grid:code": {"eq": f"MGRS-{tile}"}},
        max_items=None,
    )
    items = list(search.items())
    out = []
    for it in items:
        d = it.properties.get("datetime", "")[:10]
        rec = {
            "scene_id": it.id,
            "date": d,
            "datetime": it.properties.get("datetime"),
            "cloud_cover_pct": round(float(it.properties.get("eo:cloud_cover", np.nan)), 2),
            "tile": tile,
            "platform": it.properties.get("platform"),
            "processing_baseline": it.properties.get("s2:processing_baseline")
                                   or it.properties.get("processing:version"),
            "collection": collection,
            "stac_url": url,
            "assets": {},
        }
        for key, band in ASSETS.items():
            if key not in it.assets:
                continue
            a = it.assets[key]
            scale, offset = 1.0, 0.0
            rb = (a.extra_fields or {}).get("raster:bands")
            if rb:
                scale = float(rb[0].get("scale", 1.0) or 1.0)
                offset = float(rb[0].get("offset", 0.0) or 0.0)
            rec["assets"][band] = {"href": a.href, "scale": scale, "offset": offset}
        if all(b in rec["assets"] for b in ("B03", "B08", "B11", "SCL")):
            out.append(rec)
    out.sort(key=lambda r: (r["date"], r["scene_id"]))
    return out


def _read_window(href: str, grid, resampling: Resampling, dtype="float32"):
    """Read only the AOI window of a COG and resample onto `grid`."""
    with rasterio.open(href) as src:
        # The AOI bounds are in the TARGET crs; the window must be computed in the
        # SOURCE crs. Skipping this works only while the two happen to match, and
        # silently reads the wrong place for anything else (MODIS sinusoidal, a
        # neighbouring UTM zone, geographic rasters).
        if src.crs == grid.crs:
            src_bounds = grid.bounds
        else:
            src_bounds = transform_bounds(grid.crs, src.crs, *grid.bounds,
                                          densify_pts=21)
        win = from_bounds(*src_bounds, transform=src.transform)
        win = win.round_offsets().round_lengths()
        pad = 4
        win = rasterio.windows.Window(
            win.col_off - pad, win.row_off - pad,
            win.width + 2 * pad, win.height + 2 * pad)
        data = src.read(1, window=win, boundless=True,
                        fill_value=0).astype("float32")
        src_transform = src.window_transform(win)
        dst = np.zeros(grid.shape, dtype="float32")
        reproject(
            source=data, destination=dst,
            src_transform=src_transform, src_crs=src.crs,
            dst_transform=grid.transform, dst_crs=grid.crs,
            resampling=resampling,
        )
    return dst.astype(dtype)


def grid_tag(grid=S2_GRID) -> str:
    """Short, stable id for a grid, so caches for different study areas coexist."""
    return (f"{int(grid.xmin)}_{int(grid.ymin)}_{grid.width}x{grid.height}"
            f"_{int(grid.res)}m")


def scene_cache_path(rec: dict, grid=S2_GRID) -> Path:
    d = SCENE_CACHE / grid_tag(grid)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{rec['scene_id']}.npz"


def fetch_scene(rec: dict, grid=S2_GRID, force: bool = False) -> dict | None:
    """Download the AOI window of one scene and reduce it to snow / valid masks.

    Cached as a small npz (two uint8 planes) so a failed run can be resumed.
    """
    p = scene_cache_path(rec, grid)
    if p.exists() and not force:
        try:
            z = np.load(p, allow_pickle=True)
            return {"snow": z["snow"], "valid": z["valid"],
                    "meta": json.loads(str(z["meta"][0]))}
        except Exception:
            p.unlink(missing_ok=True)

    a = rec["assets"]
    try:
        scl = _read_window(a["SCL"]["href"], grid, Resampling.nearest).astype("uint8")
        b03 = _read_window(a["B03"]["href"], grid, Resampling.average)
        b08 = _read_window(a["B08"]["href"], grid, Resampling.average)
        b11 = _read_window(a["B11"]["href"], grid, Resampling.bilinear)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    def to_refl(arr, info):
        return arr * info["scale"] + info["offset"]

    g = to_refl(b03, a["B03"])
    n = to_refl(b08, a["B08"])
    s = to_refl(b11, a["B11"])

    with np.errstate(invalid="ignore", divide="ignore"):
        ndsi = (g - s) / (g + s)
    ndsi = np.where(np.isfinite(ndsi), ndsi, -1.0)

    reject = np.isin(scl, SCL_REJECT)
    never_snow = np.isin(scl, SCL_NEVER_SNOW)
    filled = (b03 == 0) & (b11 == 0) & (b08 == 0)
    valid = (~reject) & (~filled)

    snow = (ndsi > NDSI_THRESHOLD) & (n > NIR_THRESHOLD) & valid & (~never_snow)

    meta = {
        "scene_id": rec["scene_id"], "date": rec["date"],
        "datetime": rec["datetime"], "cloud_cover_pct": rec["cloud_cover_pct"],
        "platform": rec.get("platform"),
        "processing_baseline": rec.get("processing_baseline"),
        "collection": rec.get("collection"), "stac_url": rec.get("stac_url"),
        "scale": a["B03"]["scale"], "offset": a["B03"]["offset"],
        "href_B03": a["B03"]["href"], "href_B08": a["B08"]["href"],
        "href_B11": a["B11"]["href"], "href_SCL": a["SCL"]["href"],
        "valid_fraction": round(float(valid.mean()), 4),
        "snow_fraction_of_valid": round(float(snow.sum() / max(valid.sum(), 1)), 4),
        "scl_snow_fraction_of_valid": round(
            float((scl == SCL_SNOW)[valid].mean()) if valid.any() else 0.0, 4),
    }
    np.savez_compressed(p, snow=snow.astype("uint8"), valid=valid.astype("uint8"),
                        meta=np.array([json.dumps(meta)], dtype=object))
    return {"snow": snow.astype("uint8"), "valid": valid.astype("uint8"), "meta": meta}


def fetch_all(records: list[dict], workers: int = 6, verbose: bool = True,
              grid=S2_GRID) -> dict:
    """Fetch every scene window, resuming from cache. Returns successes + failures."""
    ok, failed = [], []
    t0 = time.time()
    todo = [r for r in records if not scene_cache_path(r, grid).exists()]
    cached = len(records) - len(todo)
    if verbose:
        print(f"  {len(records)} scenes: {cached} cached, {len(todo)} to download",
              flush=True)
    results = {}
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(fetch_scene, r, grid): r for r in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                r = futs[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"error": f"{type(e).__name__}: {e}"}
                if res is None or "error" in (res or {}):
                    failed.append({"scene_id": r["scene_id"], "date": r["date"],
                                   "error": (res or {}).get("error", "unknown")})
                else:
                    results[r["scene_id"]] = res
                if verbose and i % 10 == 0:
                    print(f"    {i}/{len(todo)} downloaded "
                          f"({time.time()-t0:.0f}s)", flush=True)
    for r in records:
        if r["scene_id"] in results:
            ok.append(results[r["scene_id"]])
        elif scene_cache_path(r, grid).exists():
            res = fetch_scene(r, grid)
            if res and "error" not in res:
                ok.append(res)
    ok.sort(key=lambda d: (d["meta"]["date"], d["meta"]["scene_id"]))
    return {"scenes": ok, "failed": failed}


def merge_same_date(scenes: list[dict]) -> list[dict]:
    """Collapse duplicate acquisition dates (tile overlaps / twin platforms).

    A pixel is valid if valid in any scene of that date; snow if snow in any
    scene where it was valid.
    """
    by_date: dict[str, list[dict]] = {}
    for s in scenes:
        by_date.setdefault(s["meta"]["date"], []).append(s)
    out = []
    for date in sorted(by_date):
        group = by_date[date]
        if len(group) == 1:
            g = group[0]
            out.append({"date": date, "snow": g["snow"].astype(bool),
                        "valid": g["valid"].astype(bool),
                        "scene_ids": [g["meta"]["scene_id"]]})
            continue
        valid = np.zeros_like(group[0]["valid"], dtype=bool)
        snow = np.zeros_like(valid)
        for g in group:
            v = g["valid"].astype(bool)
            snow |= v & g["snow"].astype(bool)
            valid |= v
        out.append({"date": date, "snow": snow, "valid": valid,
                    "scene_ids": [g["meta"]["scene_id"] for g in group]})
    return out


def fetch_scene_raw(rec: dict, grid=S2_GRID) -> dict:
    """Reflectance bands + SCL for one scene, for threshold sensitivity work.

    Not cached: used on a handful of scenes only.
    """
    a = rec["assets"]
    scl = _read_window(a["SCL"]["href"], grid, Resampling.nearest).astype("uint8")
    b03 = _read_window(a["B03"]["href"], grid, Resampling.average)
    b08 = _read_window(a["B08"]["href"], grid, Resampling.average)
    b11 = _read_window(a["B11"]["href"], grid, Resampling.bilinear)
    g = b03 * a["B03"]["scale"] + a["B03"]["offset"]
    n = b08 * a["B08"]["scale"] + a["B08"]["offset"]
    s = b11 * a["B11"]["scale"] + a["B11"]["offset"]
    with np.errstate(invalid="ignore", divide="ignore"):
        ndsi = (g - s) / (g + s)
    ndsi = np.where(np.isfinite(ndsi), ndsi, -1.0)
    reject = np.isin(scl, SCL_REJECT)
    filled = (b03 == 0) & (b11 == 0) & (b08 == 0)
    return {"ndsi": ndsi, "nir": n, "green": g, "swir": s, "scl": scl,
            "valid": (~reject) & (~filled),
            "never_snow": np.isin(scl, SCL_NEVER_SNOW),
            "date": rec["date"], "scene_id": rec["scene_id"]}
