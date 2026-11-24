"""The joint 20 m analysis stack: terrain + insolation + snow on one grid."""
from __future__ import annotations

import numpy as np

from grids import DEM_GRID, S2_GRID
from resample import aspect_to_grid, to_grid


def build(terrain: dict, insolation: dict) -> dict:
    """Terrain and insolation resampled from the 30 m DEM grid to the 20 m S2 grid.

    Aspect is interpolated as a unit vector; everything else bilinearly.
    """
    st = {
        "dem": to_grid(terrain["dem"]),
        "slope": to_grid(terrain["slope"]),
        "aspect": aspect_to_grid(terrain["aspect"]),
        "svf": to_grid(terrain["svf"]),
    }
    for label, r in insolation.items():
        st[f"insol_{label}"] = to_grid(r["total"])
        st[f"insol_{label}_direct"] = to_grid(r["direct"])
    st["grid"] = S2_GRID
    st["source_grid"] = DEM_GRID
    return st
