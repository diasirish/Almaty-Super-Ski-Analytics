"""The hand-drawn operating-area boundary, and what the analysis does with it.

The compute grid is a rectangle because every raster step needs one. The
*reporting* boundary does not have to be: a polygon drawn on the terrain in
QGIS (see qgis/README.md) is carried through as a mask, so areas, shares and
medians can be quoted for the ground that will actually carry lifts and pistes
rather than for a rectangle that happens to contain it.

Nothing here is traced from the operator's perspective render. The polygon is
either the control-point envelope or a boundary a human drew against the DEM,
and `provenance()` says which.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

from config import CRS_UTM, CRS_WGS84, ROOT

PATH = ROOT / "qgis" / "01_EDIT_ME_operating_area.geojson"
DRAFT_MARK = "DRAFT"


def load(path: Path | str = PATH):
    """Return (shapely polygon in lon/lat, properties dict)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no operating-area polygon at {path}")
    gj = json.loads(path.read_text())
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    if len(feats) != 1:
        raise ValueError(f"expected exactly one polygon in {path.name}, found {len(feats)}")
    poly = shape(feats[0]["geometry"])
    if not poly.is_valid:
        poly = poly.buffer(0)                      # repair a self-intersection
    if poly.geom_type != "Polygon":
        raise ValueError(f"expected a single Polygon, got {poly.geom_type}")
    return poly, dict(feats[0].get("properties") or {})


def is_draft(props: dict) -> bool:
    """True while the polygon is still the machine-generated starting shape."""
    return DRAFT_MARK in str(props.get("status", "")).upper()


def provenance(props: dict) -> str:
    who = str(props.get("drawn_by") or "").strip()
    if is_draft(props):
        return ("Envelope of the seven features named on the Kazakh Tourism Development "
                "general-plan sheet, located independently in OpenStreetMap, plus a "
                "1.5 km working buffer. Not traced from the render.")
    return (f"Boundary digitised by {who or 'the author'} in QGIS against Copernicus DEM "
            f"GLO-30 shaded relief and OpenStreetMap lift and piste lines, using the "
            f"general-plan sheet as a visual reference. Not traced from the render.")


def _to_utm(poly):
    tr = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True)
    return shp_transform(lambda x, y, z=None: tr.transform(x, y), poly)


def bbox(poly, buffer_km: float = 1.0, snap_deg: float = 0.005):
    """A compute rectangle around the polygon: buffered, then snapped outward.

    The buffer exists because slope, horizon and sky view factor all read
    neighbours; a boundary pixel computed without them is wrong.
    """
    w, s, e, n = poly.bounds
    dlat = buffer_km / 111.32
    dlon = buffer_km / (111.32 * math.cos(math.radians((s + n) / 2)))
    f = lambda v, d: math.floor(v / snap_deg) * snap_deg if d < 0 else math.ceil(v / snap_deg) * snap_deg
    return (round(f(w - dlon, -1), 6), round(f(s - dlat, -1), 6),
            round(f(e + dlon, +1), 6), round(f(n + dlat, +1), 6))


def mask(grid, poly, all_touched: bool = False) -> np.ndarray:
    """Rasterise the polygon onto an analysis grid. True = inside the boundary."""
    utm = _to_utm(poly)
    return rasterize([(utm, 1)], out_shape=grid.shape, transform=grid.transform,
                     fill=0, all_touched=all_touched, dtype="uint8").astype(bool)


def summary(poly, grid=None, dem=None, slope=None) -> dict:
    """Area, shape and — when terrain is supplied — what the boundary contains."""
    utm = _to_utm(poly)
    out = {"area_ha": round(utm.area / 1e4, 1),
           "area_km2": round(utm.area / 1e6, 2),
           "perimeter_km": round(utm.length / 1000, 2),
           "n_vertices": len(utm.exterior.coords) - 1,
           "bounds_wgs84": tuple(round(v, 5) for v in poly.bounds)}
    if grid is not None and dem is not None:
        m = mask(grid, poly) & np.isfinite(dem)
        px_ha = grid.res ** 2 / 1e4
        out.update({"pixels": int(m.sum()),
                    "raster_area_ha": round(float(m.sum() * px_ha), 1),
                    "elev_min_m": round(float(np.nanmin(dem[m])), 0),
                    "elev_max_m": round(float(np.nanmax(dem[m])), 0),
                    "vertical_m": round(float(np.nanmax(dem[m]) - np.nanmin(dem[m])), 0),
                    "median_elev_m": round(float(np.nanmedian(dem[m])), 0)})
        if slope is not None:
            from ski_terrain import GREEN_BLUE_MAX_DEG
            out["median_slope_deg"] = round(float(np.nanmedian(slope[m])), 1)
            out["green_blue_ha"] = round(float((m & (slope <= GREEN_BLUE_MAX_DEG)).sum() * px_ha), 1)
            out["green_blue_share"] = round(float(np.nanmean(slope[m] <= GREEN_BLUE_MAX_DEG)), 4)
    return out
