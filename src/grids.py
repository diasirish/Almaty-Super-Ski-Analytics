"""Analysis grids in EPSG:32643 derived from the WGS84 study rectangle."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from rasterio.transform import from_origin

from config import AOI_BBOX_WGS84, CRS_UTM, CRS_WGS84, DEM_RES_M, S2_RES_M


@dataclass(frozen=True)
class Grid:
    """A regular north-up raster grid."""
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    res: float
    crs: str

    @property
    def width(self) -> int:
        return int(round((self.xmax - self.xmin) / self.res))

    @property
    def height(self) -> int:
        return int(round((self.ymax - self.ymin) / self.res))

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    @property
    def transform(self):
        return from_origin(self.xmin, self.ymax, self.res, self.res)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    @property
    def area_km2(self) -> float:
        return self.width * self.height * self.res ** 2 / 1e6

    def xy_centers(self):
        x = self.xmin + (np.arange(self.width) + 0.5) * self.res
        y = self.ymax - (np.arange(self.height) + 0.5) * self.res
        return x, y

    def lonlat_centers(self):
        x, y = self.xy_centers()
        xx, yy = np.meshgrid(x, y)
        tr = Transformer.from_crs(self.crs, CRS_WGS84, always_xy=True)
        lon, lat = tr.transform(xx, yy)
        return lon, lat

    def buffered(self, buffer_m: float) -> "Grid":
        return Grid(
            self.xmin - buffer_m, self.ymin - buffer_m,
            self.xmax + buffer_m, self.ymax + buffer_m,
            self.res, self.crs,
        )

    def profile(self, dtype="float32", nodata=None, count=1):
        return dict(
            driver="GTiff", height=self.height, width=self.width, count=count,
            dtype=dtype, crs=CRS.from_user_input(self.crs), transform=self.transform,
            nodata=nodata, compress="deflate", predictor=2 if "float" in str(dtype) else 1,
            tiled=True, blockxsize=256, blockysize=256,
        )


def _utm_bbox_of_wgs84_rect(bbox, crs_utm=CRS_UTM, n=200):
    """Axis-aligned UTM bounding box of the WGS84 rectangle.

    The rectangle is densified along its edges before projection so that
    meridian convergence (~1.4 deg here) is captured exactly.
    """
    w, s, e, n_ = bbox
    lons = np.linspace(w, e, n)
    lats = np.linspace(s, n_, n)
    edge_lon = np.concatenate([lons, lons, np.full(n, w), np.full(n, e)])
    edge_lat = np.concatenate([np.full(n, s), np.full(n, n_), lats, lats])
    tr = Transformer.from_crs(CRS_WGS84, crs_utm, always_xy=True)
    x, y = tr.transform(edge_lon, edge_lat)
    return float(x.min()), float(y.min()), float(x.max()), float(y.max())


def make_grid(res: float) -> Grid:
    """Grid snapped outward to whole multiples of `res`."""
    xmin, ymin, xmax, ymax = _utm_bbox_of_wgs84_rect(AOI_BBOX_WGS84)
    xmin = np.floor(xmin / res) * res
    ymin = np.floor(ymin / res) * res
    xmax = np.ceil(xmax / res) * res
    ymax = np.ceil(ymax / res) * res
    return Grid(xmin, ymin, xmax, ymax, res, CRS_UTM)


DEM_GRID = make_grid(DEM_RES_M)
S2_GRID = make_grid(S2_RES_M)


def grid_from_raster(path) -> Grid:
    """Rebuild a Grid from a north-up raster on disk.

    Lets one area's notebook read another area's products without hard-coding
    that area's extent: the grid comes from the file, not from a literal.
    """
    import rasterio
    with rasterio.open(path) as s:
        t = s.transform
        if abs(t.b) > 1e-9 or abs(t.d) > 1e-9 or t.e >= 0:
            raise ValueError(f"{path}: not a north-up raster")
        return Grid(t.c, t.f + t.e * s.height, t.c + t.a * s.width, t.f,
                    float(t.a), str(s.crs))


def wgs84_rect_area_km2() -> float:
    """True area of the WGS84 study rectangle on the ellipsoid (geodesic)."""
    from pyproj import Geod
    w, s, e, n = AOI_BBOX_WGS84
    geod = Geod(ellps="WGS84")
    lons = [w, e, e, w]
    lats = [s, s, n, n]
    area, _ = geod.polygon_area_perimeter(lons, lats)
    return abs(area) / 1e6
