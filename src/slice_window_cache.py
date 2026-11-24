"""Give the working window its Sentinel-2 cache by slicing the cluster's.

The window sits inside the cluster window and both 20 m grids are snapped to
the same multiples of 20 m in EPSG:32643, so nothing is downloaded and nothing
is resampled: the alignment is asserted and the arrays are sliced.

    KZ_AREA=superski python src/slice_window_cache.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reuse_cache as RC
from config import AREA, DATA, ROOT
from grids import S2_GRID, grid_from_raster

if AREA == "cluster":
    raise SystemExit("nothing to slice: the cluster is the source cache")

ref = ROOT / "outputs" / "cluster" / "geotiff" / "cluster_snow_frequency_month_03.tif"
if not ref.exists():
    raise SystemExit(f"build the cluster first: {ref} is missing")

print(f"{RC.copy_stac_records(DATA / 'interim' / 'cluster')} STAC records copied")
print(RC.slice_scene_cache(grid_from_raster(ref), S2_GRID))
