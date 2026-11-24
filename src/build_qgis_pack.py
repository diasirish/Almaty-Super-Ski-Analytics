"""Rebuild the QGIS layer pack so the boundary is redrawn on the current terrain.

`qgis/` exists for one job: let a person reshape `operating_area.geojson` on top
of exactly the ground the analysis runs on. That only works if the rasters in it
are the analysis grid. Whenever the study window changes, run this.

    KZ_AREA=superski python src/build_qgis_pack.py

`00_same_view_as_the_plan.png` and `operating_area.geojson` are not touched: the
first is a one-off render for comparing with the operator's panorama, and the
second is the boundary itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import osm
from config import AOI_BBOX_WGS84, AREA, CRS_WGS84, ROOT
from dem import write_geotiff
from grids import DEM_GRID as G
from pipeline_terrain import terrain
from viz import hillshade

QGIS = ROOT / "qgis"

# The rectangles earlier releases reported over, kept as literals so a reader can
# see where they sat without them existing in config.py any more.
RETIRED = {
    "retired: 1st release, 69 km2 box around the plateau":
        (76.960, 43.105, 77.065, 43.174),
    "retired: 2nd release, 125 km2 control-point envelope":
        (76.955, 43.078, 77.095, 43.172),
}


def _ring(bb):
    w, s, e, n = bb
    return [[[w, s], [e, s], [e, n], [w, n], [w, s]]]


def main() -> None:
    if AREA != "superski":
        raise SystemExit("run with KZ_AREA=superski: the pack is the study window")
    t = terrain()
    write_geotiff(QGIS / "dem_30m.tif", t["dem"], G, nodata=-9999,
                  description="Copernicus DEM GLO-30 on the study window")
    write_geotiff(QGIS / "slope_deg.tif", t["slope"], G, nodata=-9999,
                  description="slope in degrees, Horn 3x3")
    write_geotiff(QGIS / "hillshade.tif", hillshade(t["dem"], G.res).astype("float32"),
                  G, nodata=-9999, description="hillshade for drawing on")

    feats = [{"type": "Feature",
              "properties": {"label": "current working window (the compute grid)",
                             "status": "current",
                             "note": "the drawn boundary's own envelope plus a 1 km margin"},
              "geometry": {"type": "Polygon", "coordinates": _ring(AOI_BBOX_WGS84)}}]
    for label, bb in RETIRED.items():
        feats.append({"type": "Feature",
                      "properties": {"label": label, "status": "retired",
                                     "note": "not a study area; kept for reference only"},
                      "geometry": {"type": "Polygon", "coordinates": _ring(bb)}})
    (QGIS / "03_reference_extents.geojson").write_text(json.dumps(
        {"type": "FeatureCollection",
         "crs": {"type": "name", "properties": {"name": CRS_WGS84}},
         "features": feats}, indent=1))

    # OSM context, clipped to the window plus a 2 km margin so nearby lifts show.
    w, s, e, n = AOI_BBOX_WGS84
    pad_lon, pad_lat = 2.0 / 81.4, 2.0 / 110.6
    wide = (w - pad_lon, s - pad_lat, e + pad_lon, n + pad_lat)
    f = osm.clip(osm.load(), bbox=wide)
    osm.to_geojson(f, QGIS / "04_osm_lifts_and_pistes.geojson", bbox=wide)
    n_feat = sum(len(v) for v in f.values())

    print(f"window   {G.width} x {G.height} @ {G.res:.0f} m, "
          f"{[round(v) for v in G.bounds]}, {G.crs}")
    print(f"rasters  dem_30m.tif, slope_deg.tif, hillshade.tif")
    print(f"extents  {len(feats)} rectangles written "
          f"(1 current, {len(RETIRED)} retired)")
    print(f"osm      {n_feat} features clipped to the window + 2 km")


if __name__ == "__main__":
    main()
