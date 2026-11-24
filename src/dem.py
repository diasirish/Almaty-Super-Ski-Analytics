"""Copernicus DEM GLO-30 download, reprojection, terrain derivatives and horizon."""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.warp import reproject
from scipy.ndimage import map_coordinates

from config import (DEM_BASE_URL, DEM_RES_M, DEM_TILES, HORIZON_BUFFER_M,
                    HORIZON_N_AZIMUTH, HORIZON_STEP_GROWTH, HORIZON_STEP_M,
                    HORIZON_STEP_MAX_M, INTERIM, RAW)
from grids import DEM_GRID, Grid

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")


def download_dem_tiles(verbose: bool = True) -> list[Path]:
    """Fetch the GLO-30 tiles covering the AOI into data/raw (cached)."""
    paths = []
    for tile in DEM_TILES:
        dst = RAW / f"{tile}.tif"
        if not dst.exists() or dst.stat().st_size < 1_000_000:
            url = f"{DEM_BASE_URL}/{tile}/{tile}.tif"
            if verbose:
                print(f"  downloading {tile} ...", flush=True)
            tmp = dst.with_suffix(".tif.part")
            with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            tmp.rename(dst)
        paths.append(dst)
        if verbose:
            print(f"  {tile}: {dst.stat().st_size/1e6:.1f} MB")
    return paths


def build_dem(grid: Grid, verbose: bool = True) -> tuple[np.ndarray, dict]:
    """Merge the GLO-30 tiles and reproject onto `grid` (bilinear)."""
    paths = download_dem_tiles(verbose=verbose)
    srcs = [rasterio.open(p) for p in paths]
    try:
        mosaic, src_transform = merge(srcs, resampling=Resampling.bilinear)
        src_crs = srcs[0].crs
        src_nodata = srcs[0].nodata
    finally:
        for s in srcs:
            s.close()

    dst = np.full(grid.shape, np.nan, dtype="float32")
    reproject(
        source=mosaic[0], destination=dst,
        src_transform=src_transform, src_crs=src_crs, src_nodata=src_nodata,
        dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    meta = {
        "source": "Copernicus DEM GLO-30 (AWS Open Data)",
        "tiles": DEM_TILES,
        "vertical_datum": "EGM2008 geoid",
        "resampling": "bilinear",
        "target_crs": grid.crs,
        "target_res_m": grid.res,
    }
    return dst, meta


def slope_aspect(dem: np.ndarray, res: float) -> tuple[np.ndarray, np.ndarray]:
    """Horn (1981) 3x3 slope and aspect.

    Returns slope in degrees and aspect in degrees clockwise from true north
    (0 = N, 90 = E). Flat cells get aspect = nan.
    """
    z = np.pad(dem.astype("float64"), 1, mode="edge")
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    d, _, f = z[1:-1, :-2], z[1:-1, 1:-1], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]

    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * res)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * res)   # +y = south in array space

    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    # Aspect: direction of steepest descent, clockwise from north.
    aspect = np.degrees(np.arctan2(dzdy, -dzdx))
    aspect = (90.0 - aspect) % 360.0
    aspect = np.where(np.hypot(dzdx, dzdy) < 1e-9, np.nan, aspect)
    return slope.astype("float32"), aspect.astype("float32")


def ray_distances(step: float = HORIZON_STEP_M,
                  max_dist: float = HORIZON_BUFFER_M,
                  growth: float = HORIZON_STEP_GROWTH,
                  step_max: float = HORIZON_STEP_MAX_M) -> np.ndarray:
    """Sample distances along a horizon ray, with a geometrically growing step.

    The angular size of a terrain cell seen from the origin falls as 1/d, so a
    uniform 30 m step oversamples the far field badly. Growing the step keeps the
    angular sampling roughly constant and cuts the sample count several-fold for
    the same horizon. `growth = 1.0` reproduces uniform stepping exactly.
    """
    d, cur, out = 0.0, step, []
    while d < max_dist:
        d += cur
        out.append(min(d, max_dist))
        cur = min(cur * growth, step_max)
    return np.asarray(out, dtype="float64")


def horizon_angles(dem_buf: np.ndarray, grid_buf: Grid, grid: Grid,
                   n_az: int = HORIZON_N_AZIMUTH,
                   max_dist: float = HORIZON_BUFFER_M,
                   step: float = HORIZON_STEP_M,
                   growth: float = HORIZON_STEP_GROWTH,
                   verbose: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Terrain horizon elevation angle per pixel and azimuth.

    Ray-marches outward from every AOI pixel over the buffered DEM and keeps the
    maximum angular elevation of the terrain. Earth curvature is applied as a
    drop of d^2 / (2 * R_eff) with R_eff = 7/6 * R_earth (standard refraction).

    Returns (azimuths_deg, horizon_deg) with horizon shaped (n_az, H, W).
    """
    azimuths = np.arange(n_az) * (360.0 / n_az)
    H, W = grid.shape

    # Pixel coordinates of AOI centres inside the buffered array.
    col0 = (grid.xmin - grid_buf.xmin) / grid_buf.res
    row0 = (grid_buf.ymax - grid.ymax) / grid_buf.res
    rr, cc = np.meshgrid(np.arange(H, dtype="float64"), np.arange(W, dtype="float64"),
                         indexing="ij")
    rows0 = rr + row0 + 0.5 - 0.5
    cols0 = cc + col0 + 0.5 - 0.5

    z0 = map_coordinates(dem_buf, [rows0, cols0], order=1, mode="nearest")
    dists = ray_distances(step, max_dist, growth)
    R_eff = 6371000.0 * 7.0 / 6.0
    curv = dists ** 2 / (2.0 * R_eff)

    out = np.zeros((n_az, H, W), dtype="float32")
    for ai, az in enumerate(azimuths):
        dx = np.sin(np.radians(az))      # +x = east
        dy = np.cos(np.radians(az))      # +y = north
        best = np.full((H, W), -np.inf)
        for di, dist in enumerate(dists):
            r = rows0 - (dist * dy) / grid_buf.res
            c = cols0 + (dist * dx) / grid_buf.res
            z = map_coordinates(dem_buf, [r, c], order=1, mode="nearest")
            ang = np.arctan2(z - z0 - curv[di], dist)
            np.maximum(best, ang, out=best)
        out[ai] = np.degrees(np.maximum(best, 0.0)).astype("float32")
        if verbose and (ai + 1) % 6 == 0:
            print(f"    horizon azimuth {ai+1}/{n_az}", flush=True)
    return azimuths, out


def sky_view_factor(azimuths: np.ndarray, horizon: np.ndarray,
                    slope: np.ndarray, aspect: np.ndarray) -> np.ndarray:
    """Dozier & Frew (1990) sky view factor for a tilted, horizon-obstructed surface.

        Vd = (1/2pi) * INTEGRAL[ cos(b) sin^2(H) + sin(b) cos(phi - A) (H - sin H cos H) ] dphi

    H is the horizon angle measured FROM THE ZENITH (H = 90 deg for an
    unobstructed horizontal surface). In each azimuth the surface is limited by
    whichever blocks more sky: the ray-marched terrain horizon, or the slope
    plane itself. Reduces to 1.0 for flat unobstructed ground and to
    (1 + cos b)/2 for an unobstructed plane of slope b.
    """
    b = np.radians(np.nan_to_num(slope, nan=0.0).astype("float64"))
    A = np.radians(np.nan_to_num(aspect, nan=0.0).astype("float64"))
    n_az = len(azimuths)
    dphi = 2.0 * np.pi / n_az
    acc = np.zeros(b.shape, dtype="float64")
    for ai, az in enumerate(azimuths):
        phi = np.radians(float(az))
        cosd = np.cos(phi - A)
        # terrain horizon, from zenith
        H_terr = np.pi / 2.0 - np.radians(horizon[ai].astype("float64"))
        # the slope plane's own horizon, from zenith
        H_plane = np.pi / 2.0 + np.arctan(np.tan(b) * cosd)
        H = np.minimum(H_terr, H_plane)
        acc += (np.cos(b) * np.sin(H) ** 2
                + np.sin(b) * cosd * (H - np.sin(H) * np.cos(H))) * dphi
    svf = acc / (2.0 * np.pi)
    return np.clip(svf, 0.0, 1.0).astype("float32")


def write_geotiff(path: Path, arr: np.ndarray, grid: Grid, nodata=None,
                  dtype=None, description: str | None = None, **tags):
    dtype = dtype or ("float32" if arr.dtype.kind == "f" else str(arr.dtype))
    prof = grid.profile(dtype=dtype, nodata=nodata)
    data = arr.astype(dtype)
    if nodata is not None and arr.dtype.kind == "f":
        data = np.where(np.isfinite(arr), arr, nodata).astype(dtype)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(data, 1)
        if description:
            ds.set_band_description(1, description)
        if tags:
            ds.update_tags(**{k: json.dumps(v) if not isinstance(v, str) else v
                              for k, v in tags.items()})
    return path
