"""Cut an existing scene cache down to a smaller, pixel-aligned grid.

The project-scale window sits inside the cluster window and both 20 m grids are
snapped to the same multiples of 20 m in EPSG:32643, so the project-scale snow
record can be taken from the scenes already read for the cluster instead of
downloading them again. Nothing is resampled: the alignment is asserted and the
arrays are sliced, so a project pixel is exactly the cluster pixel that covers
it. Re-reading the same COG windows would produce the same numbers at the cost
of another 115 scene downloads.
"""
from __future__ import annotations

import json
import shutil

import numpy as np

from config import INTERIM, SCENE_CACHE
from s2 import grid_tag


def offsets(src_grid, dst_grid) -> tuple[int, int]:
    """(row, col) of dst's top-left pixel inside src. Raises if not aligned."""
    if src_grid.res != dst_grid.res:
        raise ValueError(f"resolutions differ: {src_grid.res} vs {dst_grid.res}")
    if src_grid.crs != dst_grid.crs:
        raise ValueError(f"CRS differ: {src_grid.crs} vs {dst_grid.crs}")
    r = src_grid.res
    dx, dy = dst_grid.xmin - src_grid.xmin, src_grid.ymax - dst_grid.ymax
    if abs(dx / r - round(dx / r)) > 1e-6 or abs(dy / r - round(dy / r)) > 1e-6:
        raise ValueError("grids are not pixel-aligned; slicing would shift pixels")
    row0, col0 = int(round(dy / r)), int(round(dx / r))
    if (row0 < 0 or col0 < 0
            or row0 + dst_grid.height > src_grid.height
            or col0 + dst_grid.width > src_grid.width):
        raise ValueError("destination grid is not contained in the source grid")
    return row0, col0


def slice_scene_cache(src_grid, dst_grid, verbose: bool = True) -> dict:
    """Write dst-grid scene caches by slicing the src-grid ones."""
    row0, col0 = offsets(src_grid, dst_grid)
    src_dir = SCENE_CACHE / grid_tag(src_grid)
    dst_dir = SCENE_CACHE / grid_tag(dst_grid)
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.is_dir():
        raise FileNotFoundError(f"no source cache at {src_dir}")

    h, w = dst_grid.height, dst_grid.width
    made = skipped = 0
    for p in sorted(src_dir.glob("*.npz")):
        out = dst_dir / p.name
        if out.exists():
            skipped += 1
            continue
        z = np.load(p, allow_pickle=True)
        sl = (slice(row0, row0 + h), slice(col0, col0 + w))
        np.savez_compressed(out, snow=z["snow"][sl], valid=z["valid"][sl],
                            meta=z["meta"])
        made += 1
    if verbose:
        print(f"scene cache {src_dir.name} -> {dst_dir.name}: "
              f"{made} written, {skipped} already present "
              f"(offset row {row0}, col {col0}; window {h}x{w})")
    return {"written": made, "skipped": skipped, "row0": row0, "col0": col0,
            "source": src_dir.name, "dest": dst_dir.name}


def copy_stac_records(src_interim, verbose: bool = True) -> int:
    """Reuse the source area's STAC record list for this area.

    The scenes are the same MGRS tile (43TFH) and every one of them covers the
    smaller window, so a second STAC search would return the same list.
    """
    src = src_interim / "stac_records.json"
    dst = INTERIM / "stac_records.json"
    if not src.exists():
        raise FileNotFoundError(src)
    if not dst.exists():
        shutil.copy2(src, dst)
    n = sum(len(v) for v in json.load(open(dst)).values())
    if verbose:
        print(f"STAC records: {n} scenes (reused from {src.parent.name})")
    return n
