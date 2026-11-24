"""Everything that is reported over the hand-drawn operating boundary.

The boundary moves whenever someone redraws it, so this runs end to end from
`qgis/operating_area.geojson` and rewrites every table and figure that depends
on it. It recomputes nothing that the boundary cannot change: terrain, horizon,
insolation and sunshine hours belong to the compute rectangle and are read from
the cache, which is also why the boundary must sit inside that rectangle.

    KZ_AREA=superski python src/pipeline_operating_area.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import footprint
import operating_area as oa
import ski_terrain as st
import viz
from config import (AREA, INTERIM, MIN_VALID_OBS, OUT_TAB, PROJECT_AREA_HA,
                    PROJECT_GREEN_BLUE_SHARE, PROJECT_GREEN_BLUE_SHARE_PRESS,
                    PROJECT_PISTE_KM, S2_RES_M)
from grids import DEM_GRID as G, Grid, make_grid

MONTHS = {11: "November", 12: "December", 1: "January",
          2: "February", 3: "March", 4: "April"}
DAYS = {11: 30, 12: 31, 1: 31, 2: 28, 3: 31, 4: 30}
PX_HA = G.res ** 2 / 1e4


def _terrain():
    z = np.load(INTERIM / "terrain.npz")
    return z["dem"], z["slope"], z["svf"]


def _components(mask: np.ndarray):
    """(n pieces, sorted piece areas in ha)."""
    from scipy import ndimage
    lab, k = ndimage.label(mask)
    if k == 0:
        return 0, np.array([0.0])
    return k, np.sort(np.bincount(lab.ravel())[1:] * PX_HA)[::-1]


# --------------------------------------------------------------------------
def shape_and_terrain(poly, dem, slope, mask) -> pd.DataFrame:
    """The boundary against two same-area reconstructions of the same site.

    A drawn boundary is only interesting if it beats what a rule would pick:
    a disc on the plateau (what you get with no terrain knowledge) and the
    gentlest ground available (what you get optimising slope alone).
    """
    area_ha = float(mask.sum() * PX_HA)
    alts = {"Drawn boundary": mask,
            "A - disc of the same area at the plateau": footprint.disc(G, area_ha, None)[0],
            "B - gentlest ground of the same area within 3.5 km":
                footprint.gentlest(G, slope, area_ha, None, 3500.0, 150.0)}
    rows = []
    for label, m in alts.items():
        m = m & np.isfinite(dem) & np.isfinite(slope)
        d, s = dem[m], slope[m]
        k, sizes = _components(m)
        gb = m & (slope <= st.GREEN_BLUE_MAX_DEG)
        gk, gsizes = _components(gb)
        rows.append({
            "footprint": label, "area_ha": round(m.sum() * PX_HA, 1), "pieces": k,
            "elev_min_m": round(float(d.min())), "elev_max_m": round(float(d.max())),
            "vertical_m": round(float(d.max() - d.min())),
            "median_elev_m": round(float(np.median(d))),
            "median_slope_deg": round(float(np.median(s)), 1),
            "above_31deg_share": round(float(np.mean(s > 31.0)), 4),
            "green_blue_ha": round(float(gb.sum() * PX_HA), 1),
            "green_blue_share": round(float(np.mean(s <= st.GREEN_BLUE_MAX_DEG)), 4),
            "green_blue_pieces": gk,
            "green_blue_largest_ha": round(float(gsizes[0]), 1),
            "green_blue_largest_share": round(float(gsizes[0] / gsizes.sum()), 4),
        })
    return pd.DataFrame(rows), alts


def gradients(slope, alts) -> pd.DataFrame:
    return st.class_table(slope, G, alts)


def feasibility(green_blue_ha: float) -> pd.DataFrame:
    """Can the stated network of runs fit on the gentle ground that exists?

    Both published mixes are carried: the operator's own general-plan sheet
    (60.9 % green and blue) and the round figure reported in the press (70 %).
    """
    out = []
    for share, src in ((PROJECT_GREEN_BLUE_SHARE, "general plan (10.6 % green + 50.3 % blue)"),
                       (PROJECT_GREEN_BLUE_SHARE_PRESS, "press statement (about 70 %)")):
        d = st.feasibility(st.piste_area_demand(PROJECT_PISTE_KM, share),
                           green_blue_ha, "drawn boundary")
        d.insert(0, "green_blue_source", src)
        d.insert(1, "green_blue_share", share)
        out.append(d)
    return pd.concat(out, ignore_index=True)


def sun(mask, slope) -> pd.DataFrame:
    gb = mask & (slope <= st.GREEN_BLUE_MAX_DEG)
    rows = []
    for mo in (11, 12, 1, 2, 3, 4):
        h = np.load(INTERIM / "sunhours" / f"sun_2027_{mo:02d}.npz")["hours"]
        ins = np.load(INTERIM / "insolation" / f"2027_{mo:02d}.npz")
        med = float(np.median(h[mask]))
        rows.append({
            "month": MONTHS[mo], "days": DAYS[mo],
            "median_sun_h": round(med, 1), "median_h_per_day": round(med / DAYS[mo], 2),
            "p10_sun_h": round(float(np.percentile(h[mask], 10)), 1),
            "p90_sun_h": round(float(np.percentile(h[mask], 90)), 1),
            "median_sun_h_green_blue": round(float(np.median(h[gb])), 1),
            "median_h_per_day_green_blue": round(float(np.median(h[gb])) / DAYS[mo], 2),
            "median_total_kwh_m2": round(float(np.median(ins["total"][mask])), 1),
            "median_shaded_fraction": round(float(np.median(ins["shaded_fraction"][mask])), 3),
        })
    return pd.DataFrame(rows)


def snow(poly, dem, slope) -> tuple[pd.DataFrame, dict]:
    """Monthly snow frequency inside the boundary, with its own coverage audit.

    A monthly snow map is built only from pixels with enough cloud-free looks.
    When few qualify, the survivors are the sunniest and flattest ground, and
    the median then describes that ground rather than the site. The bias
    columns measure exactly that instead of leaving it to a caveat.
    """
    from pipeline_snow import historical_days, load_days
    from snow import snow_frequency

    days, _, failed = load_days(verbose=False)
    hist = historical_days(days)
    S2 = make_grid(S2_RES_M)
    m20 = oa.mask(S2, poly)

    xs, ys = S2.xy_centers()                      # lift 30 m terrain to the 20 m grid
    cc = np.clip(((xs - G.xmin) / G.res).astype(int), 0, G.width - 1)
    rr = np.clip(((G.ymax - ys) / G.res).astype(int), 0, G.height - 1)
    slope20 = slope[np.ix_(rr, cc)]
    dec20 = np.load(INTERIM / "insolation" / "2027_12.npz")["total"][np.ix_(rr, cc)]

    rows, planes = [], {}
    for mo in (11, 12, 1, 2, 3, 4):
        sel = [d for d in hist if int(d["date"][5:7]) == mo]
        r = snow_frequency(sel)
        freq, nval = r["frequency"], r["n_valid"]
        ok = m20 & (nval >= MIN_VALID_OBS)
        planes[mo] = (freq, ok)
        rows.append({
            "month": MONTHS[mo], "dates": len(sel),
            "qualifying_share": round(float(ok.sum() / m20.sum()), 3),
            "median_valid_obs": int(np.median(nval[m20])),
            "median_snow_frequency": round(float(np.nanmedian(freq[ok])), 3) if ok.any() else None,
            "dec_insolation_bias_kwh": round(float(np.median(dec20[ok]) - np.median(dec20[m20])), 1) if ok.any() else None,
            "slope_bias_deg": round(float(np.median(slope20[ok]) - np.median(slope20[m20])), 1) if ok.any() else None,
        })
    return pd.DataFrame(rows), {"planes": planes, "grid": S2, "mask": m20,
                                "n_scenes": len(days), "failed": len(failed)}


def figure(poly, props, dem, slope, mask, snow_ctx) -> Path:
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from pyproj import Transformer
    from scipy import ndimage

    rs, cs = np.where(mask)
    pad = 16
    r0, r1 = max(rs.min() - pad, 0), min(rs.max() + pad + 1, G.height)
    c0, c1 = max(cs.min() - pad, 0), min(cs.max() + pad + 1, G.width)
    CG = Grid(G.xmin + c0 * G.res, G.ymax - r1 * G.res,
              G.xmin + c1 * G.res, G.ymax - r0 * G.res, G.res, G.crs)
    cut = lambda a: a[r0:r1, c0:c1]
    dm, sl, mk = cut(dem), cut(slope), cut(mask)

    tr = Transformer.from_crs("EPSG:4326", G.crs, always_xy=True)
    bx, by = tr.transform(*zip(*poly.exterior.coords))
    bx, by = np.array(bx) / 1000, np.array(by) / 1000
    outline = lambda ax: ax.plot(bx, by, color="#ff6a00", lw=2.3, zorder=12,
                                 path_effects=[pe.withStroke(linewidth=3.8, foreground="white")])

    fig, axes = plt.subplots(1, 3, figsize=(17.4, 5.0))

    cls = np.full(sl.shape, np.nan)
    cls[np.isfinite(sl)] = 3
    cls[sl <= 31.0] = 2
    cls[sl <= st.GREEN_BLUE_MAX_DEG] = 1
    cls = np.where(mk, cls, 0)
    viz.map_panel(axes[0], cls, CG, cmap=ListedColormap(["#e9e9e9", "#1f9d55", "#6aa9d8", "#c2563a"]),
                  norm=BoundaryNorm([-.5, .5, 1.5, 2.5, 3.5], 4), dem=dm, shade=0.45,
                  mark_plateau=False, cbar_label="",
                  title=f"Gradient inside the boundary — {mask.sum() * PX_HA:,.0f} ha",
                  discrete_labels={0: "outside", 1: "green / blue\n≤19.3°",
                                   2: "red\n19.3–31°", 3: "black\n>31°"})
    gb = mk & (sl <= st.GREEN_BLUE_MAX_DEG) & np.isfinite(sl)
    lab, k = ndimage.label(gb)
    big = lab == (np.bincount(lab.ravel())[1:].argmax() + 1)
    axes[0].contour(big.astype(float), levels=[0.5], colors=["#0b3d20"], linewidths=1.6,
                    extent=(CG.xmin / 1000, CG.xmax / 1000, CG.ymin / 1000, CG.ymax / 1000),
                    origin="upper", zorder=11)
    axes[0].annotate(f"largest unbroken gentle field: {big.sum() * PX_HA:,.0f} ha\n"
                     f"({100 * big.sum() / gb.sum():.0f} % of all gentle ground here)",
                     (0.03, 0.04), xycoords="axes fraction", fontsize=8, fontweight="bold",
                     color="#0b3d20", zorder=14,
                     path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
    outline(axes[0])

    h = cut(np.load(INTERIM / "sunhours" / "sun_2027_12.npz")["hours"])
    hm = np.where(mk, h, np.nan)
    med = float(np.nanmedian(hm))
    viz.map_panel(axes[1], hm, CG, cmap="inferno", vmin=0, vmax=float(np.nanpercentile(hm, 99)),
                  dem=dm, shade=0.42, mark_plateau=False,
                  title=f"December direct sun — median {med:.0f} h ({med / 31:.1f} h/day)",
                  cbar_label="hours of direct sun in December")
    gbh = float(np.nanmedian(np.where(gb, h, np.nan)))
    axes[1].annotate(f"on the gentle ground: {gbh:.0f} h ({gbh / 31:.1f} h/day)",
                     (0.03, 0.04), xycoords="axes fraction", fontsize=8, fontweight="bold",
                     color="#111", zorder=14,
                     path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
    outline(axes[1])

    S2, m20 = snow_ctx["grid"], snow_ctx["mask"]
    freq, ok = snow_ctx["planes"][3]
    rs2, cs2 = np.where(m20)
    p2 = 24
    a0, a1 = max(rs2.min() - p2, 0), min(rs2.max() + p2 + 1, S2.height)
    b0, b1 = max(cs2.min() - p2, 0), min(cs2.max() + p2 + 1, S2.width)
    S2C = Grid(S2.xmin + b0 * S2.res, S2.ymax - a1 * S2.res,
               S2.xmin + b1 * S2.res, S2.ymax - a0 * S2.res, S2.res, S2.crs)
    xs, ys = S2C.xy_centers()
    cc = np.clip(((xs - G.xmin) / G.res).astype(int), 0, G.width - 1)
    rr = np.clip(((G.ymax - ys) / G.res).astype(int), 0, G.height - 1)
    frm = np.where(m20[a0:a1, b0:b1], np.where(ok, freq, np.nan)[a0:a1, b0:b1], np.nan)
    viz.map_panel(axes[2], frm, S2C, cmap="Blues", vmin=0.5, vmax=1.0,
                  dem=dem[np.ix_(rr, cc)], shade=0.40, mark_plateau=False,
                  title=f"March snow frequency — median {np.nanmedian(frm):.2f}, 4 seasons",
                  cbar_label="share of usable satellite dates with snow")
    outline(axes[2])

    fig.tight_layout()
    return viz.save(fig, "06_operating_area.png", subtitle=(
        oa.provenance(props) + "  Sentinel-2 L2A, NDSI>0.40 and B08>0.11, at least "
        f"{MIN_VALID_OBS} valid observations per pixel. Gradient classes: "
        "BC All Season Resort Guidelines, Ch. II."))


def published_parameters() -> pd.DataFrame:
    """What the operator has published, with the source of each figure named.

    Two sources disagree on the lift count and on the green/blue share; both are
    listed rather than silently reconciled. See METHODS section 28.
    """
    from config import (PROJECT_BUILT_HA, PROJECT_CABLEWAYS_POMA,
                        PROJECT_DIFFICULTY_PLAN, PROJECT_LAUNCH, PROJECT_LIFTS,
                        PROJECT_LIFTS_PRESS, PROJECT_SKIERS_PER_DAY,
                        PROJECT_SNOWMAKING_SHARE, PROJECT_TOURISTS_PER_YEAR)
    d = PROJECT_DIFFICULTY_PLAN
    rows = [
        ("piste length", f"{PROJECT_PISTE_KM:.0f} km", "both sources agree"),
        ("lifts", f"{PROJECT_LIFTS}", "general plan, sheet 3"),
        ("lifts", f"{PROJECT_LIFTS_PRESS}", "press, April 2026 statement"),
        ("cableways by POMA", f"{PROJECT_CABLEWAYS_POMA}", "statement, 18 Nov 2026"),
        ("runs green and blue",
         f"{100 * PROJECT_GREEN_BLUE_SHARE:.1f} % ({100*d['green']:.1f} green + {100*d['blue']:.1f} blue)",
         "general plan, sheet 3"),
        ("runs red and black",
         f"{100 * (d['red'] + d['black']):.1f} % ({100*d['red']:.1f} red + {100*d['black']:.1f} black)",
         "general plan, sheet 3"),
        ("runs green and blue", f"about {100 * PROJECT_GREEN_BLUE_SHARE_PRESS:.0f} %",
         "press, April 2026 statement"),
        ("runs with snowmaking", f"{100 * PROJECT_SNOWMAKING_SHARE:.0f} %", "general plan, sheet 3"),
        ("designed daily capacity", f"up to {PROJECT_SKIERS_PER_DAY:,} skiers/day", "general plan, sheet 3"),
        ("designed annual capacity", f"{PROJECT_TOURISTS_PER_YEAR:,} tourists/year", "general plan, sheet 3"),
        ("project territory", f"{PROJECT_AREA_HA:,.0f} ha", "statement, 18 Nov 2026"),
        ("built-up area", f"about {PROJECT_BUILT_HA:.0f} ha "
                          f"({100 * PROJECT_BUILT_HA / PROJECT_AREA_HA:.1f} % of the territory)",
         "statement, 18 Nov 2026"),
        ("launch", PROJECT_LAUNCH, "statement, 18 Nov 2026"),
        ("boundary / lift alignments / station coordinates", "not published", "—"),
        ("lift capacity (persons per hour)", "not published", "—"),
        ("piste length by difficulty (km)", "not published; only the percentage split", "—"),
    ]
    return pd.DataFrame(rows, columns=["parameter", "published", "source"])


def figure_reconstructions(dem, slope, alts) -> Path:
    """Why the drawn boundary is worth having: gentle ground, three placements."""
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from scipy import ndimage

    union = np.zeros_like(next(iter(alts.values())))
    for m in alts.values():
        union |= m
    rs, cs = np.where(union)
    pad = 10
    r0, r1 = max(rs.min() - pad, 0), min(rs.max() + pad + 1, G.height)
    c0, c1 = max(cs.min() - pad, 0), min(cs.max() + pad + 1, G.width)
    CG = Grid(G.xmin + c0 * G.res, G.ymax - r1 * G.res,
              G.xmin + c1 * G.res, G.ymax - r0 * G.res, G.res, G.crs)
    cut = lambda a: a[r0:r1, c0:c1]
    dm, sl = cut(dem), cut(slope)

    titles = {"Drawn boundary": "Drawn boundary",
              "A - disc of the same area at the plateau": "A — disc, no terrain input",
              "B - gentlest ground of the same area within 3.5 km": "B — gentlest ground"}
    fig, axes = plt.subplots(1, 3, figsize=(16.2, 5.2))
    for ax, (key, m) in zip(axes, alts.items()):
        mk = cut(m)
        gb = mk & (sl <= st.GREEN_BLUE_MAX_DEG) & np.isfinite(sl)
        plane = np.where(gb, 2.0, np.where(mk, 1.0, 0.0))
        viz.map_panel(ax, plane, CG, cmap=ListedColormap(["#efefef", "#c9c2b6", "#1f9d55"]),
                      vmin=0, vmax=2, dem=dm, shade=0.5, mark_plateau=False, cbar=False,
                      title=titles[key])
        lab, k = ndimage.label(gb)
        sizes = np.bincount(lab.ravel())[1:] * PX_HA
        big = lab == (sizes.argmax() + 1)
        ax.contour(big.astype(float), levels=[0.5], colors=["#0b3d20"], linewidths=1.6,
                   extent=(CG.xmin / 1000, CG.xmax / 1000, CG.ymin / 1000, CG.ymax / 1000),
                   origin="upper", zorder=11)
        ax.annotate(f"{gb.sum() * PX_HA:,.0f} ha gentle, {k} pieces\n"
                    f"largest {sizes.max():,.0f} ha = {100 * sizes.max() / sizes.sum():.0f} %",
                    (0.03, 0.04), xycoords="axes fraction", fontsize=8.6, fontweight="bold",
                    color="#0b3d20", zorder=14,
                    path_effects=[pe.withStroke(linewidth=2.8, foreground="white")])
    fig.tight_layout()
    return viz.save(fig, "07_boundary_vs_reconstructions.png", subtitle=(
        "Green is ground at green/blue gradients (\u226419.3\u00b0); the dark outline is the largest "
        "unbroken piece of it. All three cover exactly the same area, so only the placement differs. "
        "B maximises gentle hectares and minimises how much of them are in one place."))


def run(verbose: bool = True) -> dict:
    if AREA != "superski":
        raise SystemExit("run with KZ_AREA=superski: the boundary lives in that rectangle")
    poly, props = oa.load()
    dem, slope, svf = _terrain()
    mask = oa.mask(G, poly)
    if not mask.any():
        raise SystemExit("the boundary does not intersect the compute grid")

    shape = oa.summary(poly, G, dem, slope)
    shape["stated_territory_ha"] = PROJECT_AREA_HA
    shape["share_of_stated"] = round(shape["raster_area_ha"] / PROJECT_AREA_HA, 3)
    shape["provenance"] = oa.provenance(props)
    pd.DataFrame([shape]).to_csv(OUT_TAB / "operating_area_summary.csv", index=False)

    cmp_df, alts = shape_and_terrain(poly, dem, slope, mask)
    cmp_df.to_csv(OUT_TAB / "operating_area_vs_reconstructions.csv", index=False)

    gradients(slope, alts).to_csv(OUT_TAB / "operating_area_gradient_classes.csv", index=False)

    gb_ha = float(cmp_df.loc[cmp_df.footprint == "Drawn boundary", "green_blue_ha"].iloc[0])
    feasibility(gb_ha).to_csv(OUT_TAB / "operating_area_piste_feasibility.csv", index=False)

    sun_df = sun(mask, slope)
    sun_df.to_csv(OUT_TAB / "operating_area_sun_by_month.csv", index=False)

    snow_df, ctx = snow(poly, dem, slope)
    snow_df.to_csv(OUT_TAB / "operating_area_snow_by_month.csv", index=False)

    published_parameters().to_csv(OUT_TAB / "published_project_parameters.csv", index=False)
    png = figure(poly, props, dem, slope, mask, ctx)
    png2 = figure_reconstructions(dem, slope, alts)

    if verbose:
        print(f"boundary       {shape['raster_area_ha']:,.0f} ha, {shape['n_vertices']} vertices, "
              f"{shape['elev_min_m']:.0f}-{shape['elev_max_m']:.0f} m "
              f"({shape['share_of_stated'] * 100:.0f} % of the stated {PROJECT_AREA_HA:,.0f} ha)")
        print(f"sky view       median {np.median(svf[mask]):.3f}")
        print("\n" + cmp_df.to_string(index=False))
        print("\n" + sun_df.to_string(index=False))
        print("\n" + snow_df.to_string(index=False))
        print(f"\nfigures -> {png}\n            {png2}")
        print(f"tables -> {OUT_TAB}")
    return {"summary": shape, "comparison": cmp_df, "sun": sun_df, "snow": snow_df, "png": png}


if __name__ == "__main__":
    run()
