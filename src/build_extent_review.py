"""One figure for how the study area narrowed to the drawn boundary.

Three releases, three study areas. This draws all of them on the cluster DEM so
the retraction can be seen rather than read: the first release's 69 km2 box, the
second's 125 km2 control-point envelope, the working window that replaced both,
and the polygon that is the actual study area.

    KZ_AREA=cluster python src/build_extent_review.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import operating_area as oa
from config import CRS_WGS84, DOCS, ROOT
from grids import grid_from_raster

# The three rectangles, west/south/east/north in EPSG:4326. The first two are
# retired and no longer exist in config.py; they are literals so the record can
# be checked without resurrecting them.
RECTS = {
    "1st release - 69 km² box around the plateau": ((76.960, 43.105, 77.065, 43.174), "#c0392b", ":"),
    "2nd release - 125 km² control-point envelope": ((76.955, 43.078, 77.095, 43.172), "#8e44ad", "--"),
    "this release - 70 km² working window": ((76.950, 43.085, 77.055, 43.155), "#1a1a1a", "-"),
}


def main() -> Path:
    import matplotlib.pyplot as plt
    from pyproj import Transformer
    from rasterio.warp import transform_bounds

    import viz

    tif = ROOT / "outputs" / "cluster" / "geotiff" / "cluster_elevation_m.tif"
    if not tif.exists():
        raise SystemExit(f"build the cluster first: {tif} is missing")
    import rasterio
    with rasterio.open(tif) as src:
        dem = src.read(1).astype("float32")
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
    grid = grid_from_raster(tif)
    poly, props = oa.load()
    mask = oa.mask(grid, poly)
    px_ha = grid.res ** 2 / 1e4

    tr = Transformer.from_crs(CRS_WGS84, grid.crs, always_xy=True)
    boxes = {}
    for label, (bb, colour, ls) in RECTS.items():
        (x0, x1), (y0, y1) = tr.transform([bb[0], bb[2]], [bb[1], bb[3]])
        gx, gy = grid.xy_centers()
        m = ((gx >= x0) & (gx <= x1))[None, :] & ((gy >= y0) & (gy <= y1))[:, None]
        boxes[label] = (x0, y0, x1, y1, colour, ls, m)

    fig, axes = plt.subplots(1, 2, figsize=(15.6, 5.8))

    # --- left: where each study area sits -----------------------------------
    ax = axes[0]
    viz.map_panel(ax, dem, grid, cmap=viz.ELEV_CMAP, cbar_label="m",
                  mark_plateau=False, title="Three releases, three study areas")
    ext = (grid.xmin / 1000, grid.xmax / 1000, grid.ymin / 1000, grid.ymax / 1000)
    for label, (x0, y0, x1, y1, colour, ls, _m) in boxes.items():
        ax.add_patch(plt.Rectangle((x0 / 1000, y0 / 1000), (x1 - x0) / 1000,
                                   (y1 - y0) / 1000, fill=False, ec=colour,
                                   lw=1.5, ls=ls, zorder=8, label=label))
    ax.contourf(mask.astype(float), levels=[0.5, 1.5], colors=["#e8590c"],
                alpha=0.55, extent=ext, origin="upper", zorder=9)
    ax.contour(mask.astype(float), levels=[0.5], colors=["#9c3a00"], linewidths=1.8,
               extent=ext, origin="upper", zorder=10)
    ax.plot([], [], color="#e8590c", lw=6, alpha=0.7,
            label=f"the study area - drawn boundary, {mask.sum() * px_ha / 100:.1f} km²")
    ax.legend(fontsize=7.0, loc="lower left", framealpha=0.92)
    ax.set_xlim(657.5, 672.0)
    ax.set_ylim(4769.5, 4784.0)

    # --- right: what each one contains, by elevation ------------------------
    ax = axes[1]
    bins = np.arange(1200, 4000, 100)
    for label, (_x0, _y0, _x1, _y1, colour, ls, m) in boxes.items():
        d = dem[m & np.isfinite(dem)]
        ax.hist(d, bins=bins, histtype="step", color=colour, ls=ls, lw=1.5,
                weights=np.full(d.size, px_ha),
                label=f"{label} ({d.size * px_ha / 100:.0f} km²)")
    d = dem[mask & np.isfinite(dem)]
    ax.hist(d, bins=bins, histtype="stepfilled", color="#e8590c", alpha=0.55,
            weights=np.full(d.size, px_ha),
            label=f"drawn boundary ({d.size * px_ha / 100:.1f} km²)")
    ytop = ax.get_ylim()[1]
    for ele, txt in ((1450, "lowest station on the plan"),
                     (1951, "plateau reference"),
                     (3400, "top station on the plan")):
        ax.axvline(ele, color="#148f77", lw=0.9, ls=":")
        ax.annotate(f"{txt}, {ele:,} m", (ele - 35, 0.47 * ytop), rotation=90,
                    va="center", ha="center", fontsize=6.6, color="#148f77")
    ax.set_xlabel("elevation (m)", fontsize=8.5)
    ax.set_ylabel("area per 100 m band (ha)", fontsize=8.5)
    ax.tick_params(labelsize=8)
    ax.grid(alpha=0.25, lw=0.5)
    ax.legend(fontsize=7.0, framealpha=0.92)
    ax.set_title("What each one contains, by elevation", fontsize=10)

    fig.tight_layout()
    out = DOCS / "extent_review.png"
    fig.savefig(out, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")
    print(f"  drawn boundary  {mask.sum() * px_ha:,.0f} ha, "
          f"{np.nanmin(dem[mask]):.0f}-{np.nanmax(dem[mask]):.0f} m")
    for label, (*_rest, m) in boxes.items():
        inside = (m & mask).sum() / max(m.sum(), 1)
        print(f"  {label:48s} {m.sum() * px_ha / 100:6.1f} km2, "
              f"boundary is {100 * inside:4.1f} % of it")
    return out


if __name__ == "__main__":
    main()
