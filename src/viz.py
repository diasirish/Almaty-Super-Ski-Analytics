"""Consistent map and figure styling for the release."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import (BoundaryNorm, LightSource, LinearSegmentedColormap,
                               ListedColormap)

from config import OUT_PNG, PLATEAU_POINT
from grids import DEM_GRID

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 200, "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "savefig.facecolor": "white",
    "figure.facecolor": "white",
})

def _truncate(cmap_name, lo=0.0, hi=1.0, n=256):
    base = plt.get_cmap(cmap_name)
    return LinearSegmentedColormap.from_list(
        f"{cmap_name}_{lo}_{hi}", base(np.linspace(lo, hi, n)))


# matplotlib's "terrain" starts with ocean blues; drop them for a mountain map.
ELEV_CMAP = _truncate("terrain", 0.26, 1.0)

ATTRIB = ("Copernicus DEM GLO-30 · Sentinel-2 L2A (Copernicus/ESA) · "
          "clear-sky: pvlib · analysis: D. Irishev")


def hillshade(dem, res=30.0, azdeg=315, altdeg=45, vert_exag=1.5):
    ls = LightSource(azdeg=azdeg, altdeg=altdeg)
    return ls.hillshade(np.nan_to_num(dem, nan=float(np.nanmean(dem))),
                        vert_exag=vert_exag, dx=res, dy=res)


def _plateau_xy(grid=DEM_GRID):
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True)
    return tr.transform(*PLATEAU_POINT)


def _extent(grid):
    return (grid.xmin / 1000, grid.xmax / 1000, grid.ymin / 1000, grid.ymax / 1000)


def map_panel(ax, arr, grid, cmap="viridis", vmin=None, vmax=None, title="",
              cbar_label="", dem=None, shade=0.35, norm=None, mark_plateau=True,
              discrete_labels=None, cbar=True):
    ext = _extent(grid)
    if dem is not None and shade > 0:
        hs = hillshade(dem, grid.res)
        ax.imshow(hs, extent=ext, cmap="gray", vmin=0, vmax=1, origin="upper")
    kw = dict(extent=ext, origin="upper", interpolation="nearest")
    if norm is not None:
        im = ax.imshow(arr, cmap=cmap, norm=norm, alpha=1 - shade if dem is not None else 1, **kw)
    else:
        im = ax.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax,
                       alpha=1 - shade if dem is not None else 1, **kw)
    if mark_plateau:
        px, py = _plateau_xy(grid)
        ax.plot(px / 1000, py / 1000, marker="^", ms=7, mfc="none",
                mec="black", mew=1.4, zorder=5)
        ax.annotate("plateau ref.", (px / 1000, py / 1000),
                    textcoords="offset points", xytext=(7, 4), fontsize=7.5)
    ax.set_title(title)
    ax.set_xlabel("UTM 43N easting (km)")
    ax.set_ylabel("northing (km)")
    ax.set_aspect("equal")
    if not cbar:
        return im
    cb = plt.colorbar(im, ax=ax, fraction=0.042, pad=0.02)
    if discrete_labels:
        cb.set_ticks(list(discrete_labels.keys()))
        cb.set_ticklabels(list(discrete_labels.values()))
        cb.ax.tick_params(labelsize=7.5)
    cb.set_label(cbar_label, fontsize=8)
    return im


def save(fig, name: str, subtitle: str | None = None) -> Path:
    if subtitle:
        fig.text(0.005, -0.015, subtitle, fontsize=6.5, color="#444", va="top")
    fig.text(0.005, -0.055 if subtitle else -0.015, ATTRIB, fontsize=6, color="#777",
             va="top")
    p = OUT_PNG / name
    fig.savefig(p)
    plt.close(fig)
    try:                                  # embed the saved PNG when run in a notebook
        from IPython import get_ipython
        from IPython.display import Image, display
        if get_ipython() is not None:
            display(Image(filename=str(p)))
    except Exception:
        pass
    return p


PRIORITY_CMAP = ListedColormap(["#eeeeee", "#1f6fb4", "#d1441f", "#f2e9d8", "#9a9a9a"])
PRIORITY_LABELS = {0.4: "outside 15\u201335\u00b0", 1.2: "low sun /\nfrequent snow",
                   2.0: "high sun /\ninfrequent snow", 2.8: "other skiable",
                   3.6: "no coverage"}
PRIORITY_NORM = BoundaryNorm([0, 0.9, 1.9, 2.9, 3.9, 4.9], 5)


def render_3d_relief(dem, grid, step: int = 2, elev: float = 36, azim: float = -122,
                     vert_exag: float = 1.5, size=(11.0, 6.6), dpi: int = 220,
                     pad: int = 6) -> np.ndarray:
    """Render a bare shaded-relief surface and trim the surrounding whitespace.

    Returning an image lets the caller compose title, scale bar and north arrow in
    ordinary 2D axes coordinates, where they can be placed exactly.
    """
    import io
    from PIL import Image

    fig = plt.figure(figsize=size, dpi=dpi)
    ax = fig.add_subplot(111, projection="3d", computed_zorder=False)
    xs, ys = grid.xy_centers()
    Xg, Yg = np.meshgrid(xs[::step] / 1000, ys[::step] / 1000)
    Zg = dem[::step, ::step]
    ls = LightSource(azdeg=315, altdeg=40)
    rgb = ls.shade(Zg, cmap=ELEV_CMAP, vert_exag=vert_exag, blend_mode="soft",
                   dx=grid.res * step, dy=grid.res * step)
    ax.plot_surface(Xg, Yg, Zg, facecolors=rgb, rstride=1, cstride=1,
                    linewidth=0, antialiased=False, shade=False)
    ax.set_zlim(float(np.nanmin(Zg)) - 50, float(np.nanmax(Zg)) + 150)
    ax.view_init(elev=elev, azim=azim)
    ax.set_box_aspect((1, 0.9, 0.34))
    ax.set_axis_off()
    fig.subplots_adjust(0, 0, 1, 1)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches=None, pad_inches=0,
                facecolor="white")
    plt.close(fig)
    buf.seek(0)
    im = np.array(Image.open(buf).convert("RGB"))
    nonwhite = (im < 247).any(axis=2)
    rows = np.where(nonwhite.any(axis=1))[0]
    cols = np.where(nonwhite.any(axis=0))[0]
    r0, r1 = max(rows[0] - pad, 0), min(rows[-1] + pad + 1, im.shape[0])
    c0, c1 = max(cols[0] - pad, 0), min(cols[-1] + pad + 1, im.shape[1])
    return im[r0:r1, c0:c1]


# --------------------------------------------------------------------------
# OpenStreetMap overlays
# --------------------------------------------------------------------------
LIFT_STYLE = {
    "cable_car":    dict(color="#111111", lw=2.0, ls="-"),
    "gondola":      dict(color="#111111", lw=1.8, ls="-"),
    "mixed_lift":   dict(color="#1a1a1a", lw=1.6, ls="-"),
    "chair_lift":   dict(color="#262626", lw=1.3, ls="-"),
    "t-bar":        dict(color="#333333", lw=1.0, ls="--"),
    "platter":      dict(color="#333333", lw=1.0, ls="--"),
    "drag_lift":    dict(color="#333333", lw=1.0, ls="--"),
    "rope_tow":     dict(color="#444444", lw=0.9, ls=":"),
    "magic_carpet": dict(color="#555555", lw=0.8, ls=":"),
}


def draw_osm(ax, features: dict, grid, lifts=True, pistes=True, stations=False,
             labels=(), label_kinds=("peak", "place"), min_lift_m=150.0,
             halo="white", lift_label_min_m=700.0, fontsize=7.0):
    """Overlay existing OSM infrastructure on a map panel (axes in km)."""
    import matplotlib.patheffects as pe
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True)
    fx = [pe.withStroke(linewidth=2.0, foreground=halo)]

    if pistes:
        for f in features.get("piste", []):
            x, y = tr.transform(f.lon, f.lat)
            ax.plot(np.asarray(x) / 1000, np.asarray(y) / 1000,
                    color="#2f7fd0", lw=0.7, alpha=0.75, zorder=4,
                    solid_capstyle="round")
    if lifts:
        for f in features.get("lift", []):
            if f.length_m < min_lift_m:
                continue
            st = LIFT_STYLE.get(f.subkind, dict(color="#222222", lw=1.0, ls="-"))
            x, y = tr.transform(f.lon, f.lat)
            x = np.asarray(x) / 1000
            y = np.asarray(y) / 1000
            ax.plot(x, y, zorder=6, solid_capstyle="round",
                    path_effects=[pe.withStroke(linewidth=st["lw"] + 1.6,
                                                foreground=halo)], **st)
            if f.name and f.length_m >= lift_label_min_m:
                i = len(x) // 2
                ax.annotate(f.name, (x[i], y[i]), fontsize=fontsize - 0.7,
                            textcoords="offset points", xytext=(4, 3),
                            zorder=7, path_effects=fx)
    if stations:
        for f in features.get("station", []):
            x, y = tr.transform(f.lon[0], f.lat[0])
            ax.plot(x / 1000, y / 1000, marker="s", ms=2.6, mfc="white",
                    mec="black", mew=0.7, zorder=7)

    drawn = set()
    for nm in labels:
        for kind in label_kinds:
            for f in features.get(kind, []):
                if f.name.lower() == nm.lower() and f.name.lower() not in drawn:
                    drawn.add(f.name.lower())
                    x, y = tr.transform(float(f.lon.mean()), float(f.lat.mean()))
                    ax.plot(x / 1000, y / 1000, marker="^", ms=5.5, mfc="none",
                            mec="black", mew=1.2, zorder=7)
                    ax.annotate(f.name, (x / 1000, y / 1000), fontsize=fontsize,
                                fontweight="bold", textcoords="offset points",
                                xytext=(6, 3), zorder=8, path_effects=fx)


def lift_legend(ax, loc="lower left", fontsize=7.2):
    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], color="#111111", lw=1.9, label="gondola / cable car"),
        Line2D([], [], color="#262626", lw=1.3, label="chairlift"),
        Line2D([], [], color="#333333", lw=1.0, ls="--", label="surface lift"),
        Line2D([], [], color="#2f7fd0", lw=0.9, label="mapped piste"),
    ]
    lg = ax.legend(handles=handles, loc=loc, fontsize=fontsize, frameon=True,
                   framealpha=0.9, edgecolor="none", borderpad=0.5)
    lg.set_zorder(9)
    return lg
