"""Move terrain layers onto the 20 m Sentinel-2 analysis grid."""
from __future__ import annotations

import numpy as np
from rasterio.enums import Resampling
from rasterio.warp import reproject

from grids import DEM_GRID, S2_GRID, Grid


def to_grid(arr: np.ndarray, src: Grid = DEM_GRID, dst: Grid = S2_GRID,
            resampling: Resampling = Resampling.bilinear) -> np.ndarray:
    out = np.full(dst.shape, np.nan, dtype="float32")
    reproject(
        source=np.asarray(arr, dtype="float32"), destination=out,
        src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
        dst_transform=dst.transform, dst_crs=dst.crs, dst_nodata=np.nan,
        resampling=resampling,
    )
    return out


def aspect_to_grid(aspect: np.ndarray, src: Grid = DEM_GRID,
                   dst: Grid = S2_GRID) -> np.ndarray:
    """Aspect must be interpolated as a unit vector, not as degrees (0/360 wrap)."""
    a = np.radians(aspect)
    u = to_grid(np.sin(a), src, dst)
    v = to_grid(np.cos(a), src, dst)
    out = (np.degrees(np.arctan2(u, v))) % 360.0
    out[~np.isfinite(u) | ~np.isfinite(v)] = np.nan
    mag = np.hypot(u, v)
    out[mag < 0.2] = np.nan        # interpolation across opposing aspects: undefined
    return out.astype("float32")


def mask_to_grid(mask: np.ndarray, src: Grid = DEM_GRID, dst: Grid = S2_GRID,
                 threshold: float = 0.5) -> np.ndarray:
    """Move a boolean zone mask between grids by nearest-neighbour resampling."""
    out = to_grid(mask.astype("float32"), src, dst, Resampling.nearest)
    return np.nan_to_num(out, nan=0.0) >= threshold
