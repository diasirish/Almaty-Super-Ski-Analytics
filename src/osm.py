"""OpenStreetMap reference layers: existing lifts, pistes and named features.

OSM is the only open, georeferenced record of what is actually on this mountain
today. No official GIS for the planned Almaty SuperSki cableways has been
published, so nothing here is a plan: it is the existing state, used as the
anchor for where the cluster's work is happening.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
from pyproj import Transformer

from config import AOI_BBOX_WGS84, CRS_UTM, CRS_WGS84, LIFT_CORRIDOR_M, OSM_FILE

# Aerialway values that carry skiers or passengers uphill.
LIFT_KINDS = ("cable_car", "gondola", "chair_lift", "mixed_lift", "t-bar",
              "platter", "drag_lift", "rope_tow", "magic_carpet", "funicular")

_TR = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True)


def _name(tags: dict) -> str:
    return (tags.get("name:en") or tags.get("name") or tags.get("name:ru") or "")


@dataclass
class Feature:
    kind: str
    subkind: str
    name: str
    lon: np.ndarray
    lat: np.ndarray
    tags: dict = field(default_factory=dict)

    @property
    def xy(self):
        return _TR.transform(self.lon, self.lat)

    @property
    def length_m(self) -> float:
        x, y = self.xy
        return float(np.hypot(np.diff(x), np.diff(y)).sum())

    def inside(self, bbox=AOI_BBOX_WGS84) -> bool:
        w, s, e, n = bbox
        return bool(((self.lon >= w) & (self.lon <= e) &
                     (self.lat >= s) & (self.lat <= n)).any())


def load(path=None) -> dict[str, list[Feature]]:
    """Parse the cached Overpass response into typed features."""
    path = path or OSM_FILE
    data = json.load(open(path))
    out: dict[str, list[Feature]] = {"lift": [], "station": [], "piste": [],
                                     "peak": [], "saddle": [], "area": [],
                                     "river": [], "place": []}
    for el in data["elements"]:
        t = el.get("tags", {})
        if el["type"] == "way":
            g = el.get("geometry") or []
            if len(g) < 2:
                continue
            lon = np.array([p["lon"] for p in g])
            lat = np.array([p["lat"] for p in g])
        elif el["type"] == "node":
            lon = np.array([el["lon"]])
            lat = np.array([el["lat"]])
        else:
            continue

        aw = t.get("aerialway")
        if aw in LIFT_KINDS and el["type"] == "way":
            out["lift"].append(Feature("lift", aw, _name(t), lon, lat, t))
        elif aw == "station":
            out["station"].append(Feature("station", "station", _name(t), lon, lat, t))
        elif t.get("piste:type") == "downhill":
            out["piste"].append(Feature("piste", "downhill", _name(t), lon, lat, t))
        elif t.get("landuse") == "winter_sports":
            out["area"].append(Feature("area", "winter_sports", _name(t), lon, lat, t))
        elif t.get("natural") == "peak":
            out["peak"].append(Feature("peak", "peak", _name(t), lon, lat, t))
        elif t.get("natural") == "saddle":
            out["saddle"].append(Feature("saddle", "saddle", _name(t), lon, lat, t))
        elif t.get("waterway") == "river":
            out["river"].append(Feature("river", "river", _name(t), lon, lat, t))
        elif "place" in t:
            out["place"].append(Feature("place", t["place"], _name(t), lon, lat, t))
    return out


def clip(features: dict, bbox=AOI_BBOX_WGS84) -> dict:
    return {k: [f for f in v if f.inside(bbox)] for k, v in features.items()}


def densify(f: Feature, step_m: float = 25.0):
    """Resample a line to roughly even spacing, in projected metres."""
    x, y = f.xy
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 2:
        return x, y
    seg = np.hypot(np.diff(x), np.diff(y))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] < 1e-6:
        return x, y
    n = max(int(s[-1] / step_m) + 1, 2)
    si = np.linspace(0, s[-1], n)
    return np.interp(si, s, x), np.interp(si, s, y)


def sample_along(f: Feature, arr: np.ndarray, grid, step_m: float = 25.0):
    """Sample a raster along a line feature; returns (distance_m, values)."""
    x, y = densify(f, step_m)
    col = (x - grid.xmin) / grid.res - 0.5
    row = (grid.ymax - y) / grid.res - 0.5
    from scipy.ndimage import map_coordinates
    inside = (col >= 0) & (col <= grid.width - 1) & (row >= 0) & (row <= grid.height - 1)
    vals = np.full(x.shape, np.nan)
    if inside.any():
        a = np.where(np.isfinite(arr), arr, np.nan)
        vals[inside] = map_coordinates(np.nan_to_num(a, nan=0.0),
                                       [row[inside], col[inside]], order=1,
                                       mode="nearest")
        mask = map_coordinates(np.isfinite(a).astype("float32"),
                               [row[inside], col[inside]], order=1, mode="nearest")
        vals[inside] = np.where(mask > 0.5, vals[inside], np.nan)
    d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    return d, vals


def corridor_mask(features: list[Feature], grid, half_width_m: float = LIFT_CORRIDOR_M,
                  step_m: float = 20.0) -> np.ndarray:
    """Boolean raster of everything within `half_width_m` of any given line."""
    from scipy.ndimage import distance_transform_edt
    seeds = np.zeros(grid.shape, dtype=bool)
    for f in features:
        x, y = densify(f, step_m)
        col = np.round((x - grid.xmin) / grid.res - 0.5).astype(int)
        row = np.round((grid.ymax - y) / grid.res - 0.5).astype(int)
        ok = (col >= 0) & (col < grid.width) & (row >= 0) & (row < grid.height)
        seeds[row[ok], col[ok]] = True
    if not seeds.any():
        return seeds
    dist = distance_transform_edt(~seeds, sampling=(grid.res, grid.res))
    return dist <= half_width_m


def to_geojson(features: dict, path, bbox=AOI_BBOX_WGS84) -> str:
    feats = []
    for kind, lst in features.items():
        for f in lst:
            geom = ({"type": "Point", "coordinates": [float(f.lon[0]), float(f.lat[0])]}
                    if f.lon.size == 1 else
                    {"type": "LineString",
                     "coordinates": [[float(a), float(b)] for a, b in zip(f.lon, f.lat)]})
            feats.append({
                "type": "Feature", "geometry": geom,
                "properties": {"kind": kind, "subkind": f.subkind, "name": f.name,
                               "length_m": round(f.length_m, 1) if f.lon.size > 1 else None,
                               "ele": f.tags.get("ele"),
                               "osm_id": f.tags.get("@id")},
            })
    gj = {"type": "FeatureCollection",
          "bbox": list(bbox),
          "properties": {
              "source": "OpenStreetMap contributors, via the Overpass API",
              "licence": "ODbL 1.0",
              "note": "Existing infrastructure only. No official GIS for the planned "
                      "Almaty SuperSki cableways has been published.",
          },
          "features": feats}
    json.dump(gj, open(path, "w"), indent=1)
    return str(path)
