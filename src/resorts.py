"""Comparable operating areas for the three places the cluster actually uses.

The release first compared Kok Zhailau against the OSM `landuse=winter_sports`
polygons for Shymbulak and Oi-Qaragai. Those polygons are 2.2 and 1.0 km2,
which is far smaller than either resort really operates, so the comparison was
between a 10 km2 territory and a pair of map labels. This module replaces it
with one rule applied to all three places:

  an operating area is the ground within LIFT_CORRIDOR_M of that place's lift
  lines, unioned with the ground within PISTE_CORRIDOR_M of its pistes.

Kok Zhailau has neither, because nothing is built there yet, so its operating
area is the hand-drawn operating boundary instead. That asymmetry cannot be
removed - it is the difference between a working resort and a plan - so the
elevation-matched comparison below is the one that carries the conclusions, and
every table prints each area's size next to its numbers.
"""
from __future__ import annotations

import numpy as np
from pyproj import Transformer

import osm as _osm
from config import CRS_UTM, CRS_WGS84, LIFT_CORRIDOR_M

PISTE_CORRIDOR_M = 100.0
ASSIGN_RADIUS_M = 3500.0

# The two operating places named in the cluster statements that OSM also maps,
# with the anchor each one's lifts are grouped around.
PLACES = {
    "Shymbulak": (77.08, 43.13),
    "Oi-Qaragai": (77.1431, 43.22878),
}


def _xy(lon, lat):
    tr = Transformer.from_crs(CRS_WGS84, CRS_UTM, always_xy=True)
    return tr.transform(lon, lat)


def _centroid_xy(f) -> tuple[float, float]:
    x, y = f.xy
    return float(np.mean(x)), float(np.mean(y))


def assign(features: dict, places: dict | None = None,
           radius_m: float = ASSIGN_RADIUS_M) -> dict:
    """Group lifts and pistes by the nearest named place within `radius_m`."""
    places = places or PLACES
    anchors = {k: _xy(*v) for k, v in places.items()}
    out = {k: {"lift": [], "piste": []} for k in places}
    unassigned = {"lift": [], "piste": []}
    for kind in ("lift", "piste"):
        for f in features.get(kind, []):
            if kind == "lift" and f.length_m <= 150:
                continue
            cx, cy = _centroid_xy(f)
            best, bd = None, np.inf
            for name, (ax, ay) in anchors.items():
                d = float(np.hypot(cx - ax, cy - ay))
                if d < bd:
                    best, bd = name, d
            if bd <= radius_m:
                out[best][kind].append(f)
            else:
                unassigned[kind].append(f)
    out["_unassigned"] = unassigned
    return out


def envelopes(grid, features: dict | None = None, places: dict | None = None,
              lift_m: float = LIFT_CORRIDOR_M,
              piste_m: float = PISTE_CORRIDOR_M) -> dict:
    """One operating-area mask per named place, built by the same rule."""
    f = features or _osm.clip(_osm.load())
    groups = assign(f, places)
    masks = {}
    for name in (places or PLACES):
        g = groups[name]
        m = np.zeros(grid.shape, dtype=bool)
        if g["lift"]:
            m |= _osm.corridor_mask(g["lift"], grid, lift_m)
        if g["piste"]:
            m |= _osm.corridor_mask(g["piste"], grid, piste_m)
        if m.any():
            masks[f"{name} operating area"] = m
    return masks


def inventory(features: dict | None = None, places: dict | None = None):
    """What was assigned to each place: lines, km and names."""
    import pandas as pd
    f = features or _osm.clip(_osm.load())
    groups = assign(f, places)
    rows = []
    for name in list(places or PLACES) + ["_unassigned"]:
        g = groups[name]
        rows.append({
            "place": "unassigned" if name == "_unassigned" else name,
            "lifts": len(g["lift"]),
            "lift_km": round(sum(x.length_m for x in g["lift"]) / 1000, 2),
            "pistes": len(g["piste"]),
            "piste_km": round(sum(x.length_m for x in g["piste"]) / 1000, 2),
            "named_lifts": "; ".join(sorted({x.name for x in g["lift"] if x.name})),
        })
    return pd.DataFrame(rows)


def elevation_bands(dem: np.ndarray, masks: dict, step_m: float = 200.0):
    """Shared elevation bands, so areas are compared at like altitudes."""
    lo = min(float(np.nanmin(dem[m])) for m in masks.values() if m.any())
    hi = max(float(np.nanmax(dem[m])) for m in masks.values() if m.any())
    edges = np.arange(np.floor(lo / step_m) * step_m,
                      np.ceil(hi / step_m) * step_m + step_m, step_m)
    return edges


def band_table(masks: dict, dem: np.ndarray, layers: dict, grid,
               step_m: float = 200.0, min_pixels: int = 50):
    """Median of each layer, per area, per elevation band.

    A band is reported for an area only when that area has at least
    `min_pixels` pixels in it, so a band that an area barely touches cannot
    produce a number that looks comparable but is not.
    """
    import pandas as pd
    edges = elevation_bands(dem, masks, step_m)
    ha = grid.res ** 2 / 1e4
    rows = []
    for name, m in masks.items():
        if not m.any():
            continue
        for a, b in zip(edges[:-1], edges[1:]):
            sel = m & np.isfinite(dem) & (dem >= a) & (dem < b)
            if sel.sum() < min_pixels:
                continue
            rec = {"area": name, "band_m": f"{int(a)}-{int(b)}",
                   "band_low_m": int(a), "pixels": int(sel.sum()),
                   "area_ha": round(sel.sum() * ha, 1)}
            for lab, arr in layers.items():
                v = arr[sel]
                v = v[np.isfinite(v)]
                rec[lab] = round(float(np.median(v)), 3) if v.size else np.nan
                rec[f"{lab}__n"] = int(v.size)
            rows.append(rec)
    return pd.DataFrame(rows)


def matched_pairs(bands, layer: str, reference: str):
    """Difference between each area and a reference area, band by band."""
    import pandas as pd
    ref = bands[bands.area == reference].set_index("band_low_m")[layer]
    rows = []
    for name, d in bands.groupby("area"):
        if name == reference:
            continue
        d = d.set_index("band_low_m")
        common = d.index.intersection(ref.index)
        if not len(common):
            rows.append({"area": name, "reference": reference, "layer": layer,
                         "shared_bands": 0})
            continue
        diff = (d.loc[common, layer] - ref.loc[common]).astype(float)
        rows.append({
            "area": name, "reference": reference, "layer": layer,
            "shared_bands": int(len(common)),
            "band_low_min_m": int(common.min()), "band_low_max_m": int(common.max()),
            "median_difference": round(float(np.median(diff)), 3),
            "min_difference": round(float(diff.min()), 3),
            "max_difference": round(float(diff.max()), 3),
        })
    return pd.DataFrame(rows)
