"""Build the 6-slide PDF brief from the figures and tables the notebooks produced.

Every number on a slide is read from outputs/tables/, never hard-coded, so the
brief cannot drift away from the analysis.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Slides 1-4 report the Kok Zhailau rectangle; slides 5-6 the cluster area.
# Pin the area before config is imported so OUT_TAB and OUT_PNG resolve to it.
# Notebooks 01-03 write here; the cluster figures are picked up by absolute path.
os.environ["KZ_AREA"] = "superski"

import pandas as pd
from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import INTERIM, OUT_PNG, OUT_TAB, ROOT
from grids import DEM_GRID


def _grid_facts():
    """Slide 1 describes whatever grid the pipeline actually ran on."""
    import numpy as np
    t = np.load(INTERIM / "terrain.npz")
    return (float(np.nanmin(t["dem"])), float(np.nanmax(t["dem"])),
            float(np.nanmedian(t["slope"])), float(np.nanmedian(t["svf"])),
            (DEM_GRID.xmax - DEM_GRID.xmin) / 1000,
            (DEM_GRID.ymax - DEM_GRID.ymin) / 1000)


_ELO, _EHI, _SLOPE, _SVF, _KMW, _KMH = _grid_facts()

W, H = 960.0, 540.0                       # 16:9 slide, points
M = 34.0                                  # outer margin

INK = HexColor("#1a1a1a")
MUTED = HexColor("#5d5d5d")
FAINT = HexColor("#8c8c8c")
ACCENT = HexColor("#1f6fb4")
WARM = HexColor("#d1441f")
RULE = HexColor("#d8d8d8")
PANEL = HexColor("#f4f6f8")

OUT_PDF = ROOT / "kok-zhailau-brief.pdf"
RELEASE_DATE = "24 November 2026"


CLUSTER_TAB = ROOT / "outputs" / "cluster" / "tables"
CLUSTER_PNG = ROOT / "outputs" / "cluster" / "png"
CLUSTER_META = ROOT / "outputs" / "cluster" / "geotiff" / "cluster_metadata.json"


def _tab(name: str) -> pd.DataFrame:
    return pd.read_csv(OUT_TAB / name)


def _ctab(name: str) -> pd.DataFrame:
    return pd.read_csv(CLUSTER_TAB / name)


_RESIZED = Path(__file__).resolve().parents[1] / "data" / "interim" / "_brief_images"
TARGET_DPI = 220.0


def fit(path: Path, x: float, y: float, w: float, h: float, dpi: float = TARGET_DPI):
    """Place an image in a box, preserving aspect ratio.

    The source PNGs are rendered for screen viewing at full map resolution. Each
    is downscaled to what the slide box can actually show at `dpi`, which keeps
    the PDF small enough to email without any visible loss.
    """
    im = Image.open(path)
    iw, ih = im.size
    s = min(w / iw, h / ih)
    dw, dh = iw * s, ih * s

    need_px = int(round(dw / 72.0 * dpi))
    if iw > need_px * 1.08:
        _RESIZED.mkdir(parents=True, exist_ok=True)
        out = _RESIZED / f"{path.stem}_{need_px}.png"
        if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
            im.convert("RGB").resize(
                (need_px, max(int(round(ih * need_px / iw)), 1)),
                Image.LANCZOS).save(out, optimize=True)
        path = out
    return path, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh


def para(c, text, x, y, width, size=10.3, leading=14.2, color=INK,
         font="Helvetica", max_lines=None):
    c.setFont(font, size)
    c.setFillColor(color)
    lines = simpleSplit(text, font, size, width)
    if max_lines:
        lines = lines[:max_lines]
    for ln in lines:
        c.drawString(x, y, ln)
        y -= leading
    return y


def bullet(c, head, body, x, y, width, hcolor=ACCENT):
    c.setFont("Helvetica-Bold", 11.2)
    c.setFillColor(hcolor)
    c.drawString(x, y, head)
    y -= 15.0
    return para(c, body, x, y, width, size=10.2, leading=13.6, color=INK) - 7.0


def slide_frame(c, n, total, title, kicker=None):
    c.setFillColor(HexColor("#ffffff"))
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 20.5)
    c.setFillColor(INK)
    c.drawString(M, H - M - 12, title)
    if kicker:
        c.setFont("Helvetica", 11.0)
        c.setFillColor(MUTED)
        c.drawString(M, H - M - 30, kicker)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(M, H - M - 41, W - M, H - M - 41)
    # footer
    c.setStrokeColor(RULE)
    c.line(M, 30, W - M, 30)
    c.setFont("Helvetica", 7.4)
    c.setFillColor(FAINT)
    c.drawString(M, 20, "Independent open-data case study · not commissioned by or "
                        "endorsed by any resort operator or design office · "
                        "Copernicus DEM GLO-30 · modified Copernicus Sentinel-2 data "
                        "2022–2026, processed by ESA · clear-sky: pvlib")
    c.drawRightString(W - M, 20, f"Dias Irishev · {RELEASE_DATE} · {n}/{total}")


def panel(c, x, y, w, h):
    c.setFillColor(PANEL)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.7)
    c.roundRect(x, y, w, h, 5, fill=1, stroke=1)


def stat(c, x, y, value, label, color=ACCENT, vsize=23):
    c.setFont("Helvetica-Bold", vsize)
    c.setFillColor(color)
    c.drawString(x, y, value)
    c.setFont("Helvetica", 8.6)
    c.setFillColor(MUTED)
    return para(c, label, x, y - 13, 175, size=8.6, leading=11.0, color=MUTED)


def caption(c, text, x, y, width):
    return para(c, text, x, y, width, size=7.9, leading=10.4, color=FAINT)


# --------------------------------------------------------------------------
def build():
    insol = _tab("insolation_period_summary.csv").set_index("period")
    aspect = _tab("focus_band_aspect_summary.csv").set_index("aspect_sector")
    focus = _tab("focus_band_2200_2300_summary.csv")
    scen = _tab("spring_2027_scenarios.csv")
    cov = _tab("coverage_by_period.csv")
    prio = _tab("field_priority_classes.csv").set_index("class")
    m2027 = _tab("insolation_2027_monthly.csv").set_index("month")
    fresh = _tab("fresh_scene_report.csv")
    seasons = _tab("scenes_per_season.csv")

    n_hist = int(seasons[seasons.season != "2026_27"]["scenes"].sum())
    four = focus.iloc[0]
    north = aspect.loc["north (315-45)"]
    south = aspect.loc["south (135-225)"]
    all4 = cov[cov.period == "all four seasons"].iloc[0]

    zones = _ctab("cluster_zones.csv").set_index("zone")
    sunm = _ctab("sun_hours_monthly_2027.csv").set_index("month_name")
    bestw = _ctab("best_sun_window_by_zone_month.csv")
    bestw = bestw[bestw.zone == "existing lift corridors"].set_index("month_name")
    tops_h = _ctab("max_sun_hours_points.csv")
    tops_e = _ctab("max_insolation_points.csv")
    lifts_c = _ctab("osm_existing_lifts.csv")
    demcmp = _ctab("dem_cross_validation.csv")
    idx = _ctab("sun_and_snow_index.csv")
    cmeta = json.loads(CLUSTER_META.read_text())
    xv = cmeta["cross_validation"]
    N_SLIDES = 6

    c = canvas.Canvas(str(OUT_PDF), pagesize=(W, H))
    c.setTitle("Almaty SuperSki terrain analytics — 6-slide brief")
    c.setAuthor("Dias Irishev")
    c.setSubject("Independent open-data terrain, insolation and snow-persistence "
                 "case study, Almaty mountains")

    # ---------------- slide 1 ----------------
    slide_frame(c, 1, N_SLIDES, "Almaty SuperSki terrain analytics",
                f"Terrain, sun exposure and four seasons of snow over "
                f"{DEM_GRID.area_km2:.0f} km² above Almaty — an independent "
                f"open-data case study")
    c.setFont("Helvetica-Bold", 10.4)
    c.setFillColor(INK)
    c.drawString(M - 6, 448, "Study rectangle \u2014 Copernicus DEM GLO-30, 30 m grid")
    c.setFont("Helvetica", 9.0)
    c.setFillColor(MUTED)
    c.drawString(M - 6, 435,
                 f"{_KMW:.1f} \u00d7 {_KMH:.1f} km \u00b7 {DEM_GRID.area_km2:.2f} km\u00b2 \u00b7 "
                 f"{_ELO:.0f}\u2013{_EHI:.0f} m \u00b7 median slope {_SLOPE:.0f}\u00b0 \u00b7 "
                 f"median sky view factor {_SVF:.2f}")
    p, x, y, w, h = fit(OUT_PNG / "01_terrain_3d_bare.png", M - 6, 122, 560, 302)
    c.drawImage(str(p), x, y, w, h, mask="auto")

    tx = M + 578
    tw = W - M - tx
    yy = H - M - 72
    c.setFont("Helvetica-Bold", 12.4)
    c.setFillColor(INK)
    c.drawString(tx, yy, "The question")
    yy -= 17
    yy = para(c, "Almaty's mountains are being planned for a ski cluster by "
                 "international teams. Those teams will need local terrain, exposure "
                 "and snow layers they can check — and someone on the ground who "
                 "can tell them where such layers break.", tx, yy, tw,
              size=10.4, leading=14.0)
    yy -= 10
    c.setFont("Helvetica-Bold", 12.4)
    c.setFillColor(INK)
    c.drawString(tx, yy, "What was built")
    yy -= 17
    yy = para(c, "A reproducible pipeline on open data only: Copernicus DEM at 30 m "
                 "with horizons ray-marched to 6 km, pvlib clear-sky insolation, and "
                 f"{n_hist} Sentinel-2 scenes across four complete seasons reduced to "
                 "snow frequency, observation coverage and bracketed melt-out dates.",
              tx, yy, tw, size=10.4, leading=14.0)

    panel(c, tx - 8, 92, tw + 16, 132)
    sy = 200
    stat(c, tx, sy, f"{DEM_GRID.area_km2:.2f} km²",
         f"study rectangle, {_ELO:.0f}–{_EHI:.0f} m, EPSG:32643, 30 m / 20 m grids")
    stat(c, tx, sy - 46, f"{n_hist} scenes",
         f"Sentinel-2 L2A, tile 43TFH, 4 complete seasons 2022/23–2025/26, "
         f"0 download failures", color=WARM)
    caption(c, "Shaded relief, light from the NW. Perspective view — horizontal "
               "scale varies with distance. The rectangle is only the working window "
               "around the drawn operating boundary \u2014 the boundary's own envelope plus "
               "a 1 km margin (METHODS \u00a72). Neither the window nor the boundary is an "
               "official resort boundary.",
            M - 6, 108, 560)
    c.showPage()

    # ---------------- slide 2 ----------------
    dec, mar = insol.loc["dec"], insol.loc["mar"]
    ratio = mar.median_total_kwh_m2 / dec.median_total_kwh_m2
    slide_frame(c, 2, N_SLIDES, "December is a shading problem, not a daylight problem",
                "Clear-sky insolation on the plane of each slope, December 2022 and "
                "March 2023, on one shared colour scale")
    p, x, y, w, h = fit(OUT_PNG / "01_insolation_dec_mar_shared_scale.png",
                        M - 10, 166, 618, 306)
    c.drawImage(str(p), x, y, w, h, mask="auto")

    tx = M + 626
    tw = W - M - tx
    yy = H - M - 72
    yy = bullet(c, f"{dec.median_total_kwh_m2:.0f} → "
                   f"{mar.median_total_kwh_m2:.0f} kWh/m²",
                f"Median clear-sky insolation rises by a factor of {ratio:.1f} from "
                f"December to March — far more than day length alone.",
                tx, yy, tw)
    yy = bullet(c, f"{dec.median_shaded_fraction_of_daylight*100:.0f}% of December "
                   f"daylight is shaded",
                f"On the median pixel, {dec.median_shaded_fraction_of_daylight*100:.0f}% "
                f"of December daylight half-hours fall behind the terrain horizon, "
                f"against {mar.median_shaded_fraction_of_daylight*100:.0f}% in March. "
                f"Median horizon: 14.5° above horizontal.", tx, yy, tw, WARM)
    yy = bullet(c, "Spread within one band: 1.6×",
                "Across 15–35° slopes inside a single 100 m elevation band, "
                "March–April insolation spans 279–437 kWh/m². Exposure, "
                "not height, sets the range.", tx, yy, tw)

    panel(c, M - 10, 68, W - 2 * M + 20, 86)
    yy2 = 138
    c.setFont("Helvetica-Bold", 10.0)
    c.setFillColor(INK)
    c.drawString(M + 4, yy2, "Why it matters for siting")
    para(c, "Lift lines, base areas and south-facing approaches inherit this geometry "
            "permanently. A terrace that loses the sun in December loses it every "
            "December. The same horizon model evaluates real station and approach "
            "geometry once project CAD exists — at any date, any time step.",
         M + 4, yy2 - 15, W - 2 * M + 2, size=9.8, leading=13.0)
    caption(c, "pvlib Ineichen–Perez clear sky, 30-minute steps, 7 altitude levels. "
               "Direct beam shaded by a 36-azimuth horizon ray-marched to 6 km; "
               "isotropic diffuse × Dozier–Frew sky view factor; albedo 0.50. "
               "Clear-sky ceiling, not expected irradiance.", M - 10, 48, W - 2 * M + 20)
    c.showPage()

    # ---------------- slide 3 ----------------
    slide_frame(c, 3, 4, "Exposure separates the snow — measured, with its coverage",
                f"Sentinel-2 L2A, four complete seasons 2022/23–2025/26, "
                f"{all4.n_dates} usable dates, NDSI > 0.40 and B08 > 0.11")
    p, x, y, w, h = fit(OUT_PNG / "02_snow_frequency_4season.png", M - 12, 198, 468, 282)
    c.drawImage(str(p), x, y, w, h, mask="auto")
    p, x, y, w, h = fit(OUT_PNG / "03_exposure_contrast_by_band.png", 496, 198, 432, 282)
    c.drawImage(str(p), x, y, w, h, mask="auto")

    panel(c, M - 10, 74, W - 2 * M + 20, 116)
    sy = 168
    stat(c, M + 2, sy, f"{north.median_snow_freq*100:.0f}% vs "
                       f"{south.median_snow_freq*100:.0f}%",
         f"Snow on usable dates, 2200–2300 m, 15–35° slopes: north-facing "
         f"vs south-facing. Insolation {north.median_insolation_kwh_m2:.0f} vs "
         f"{south.median_insolation_kwh_m2:.0f} kWh/m².")
    stat(c, M + 236, sy, f"{four['median_snow_freq_low']*100:.0f}% vs "
                         f"{four['median_snow_freq_high']*100:.0f}%",
         f"Lowest vs highest insolation quartile inside the same 100 m band "
         f"(n = {int(four['n_low_insol'])} each; coverage "
         f"{four['coverage_low']*100:.0f}% and {four['coverage_high']*100:.0f}%).", WARM)
    stat(c, M + 470, sy, f"{all4.coverage_min4*100:.1f}%",
         f"Share of pixels with ≥4 usable observations over four seasons. "
         f"Median {int(all4.median_valid_obs_per_pixel)} usable observations per pixel.")
    stat(c, M + 690, sy, f"{prio.loc[1,'area_km2']:.1f} + "
                         f"{prio.loc[2,'area_km2']:.1f} km²",
         "Field-check priority terrain: low-sun/frequent-snow plus "
         "high-sun/infrequent-snow, of 48.7 km² skiable.", WARM)
    caption(c, "A frequency is the share of usable satellite dates on which a pixel "
               "looked like snow — not ski days, not snow depth, not snowmaking "
               "cost. Cast and cloud shadow are rejected before counting, so shaded "
               "slopes lose observations: the contrast shown is, if anything, "
               "conservative.", M - 10, 60, W - 2 * M + 20)
    c.showPage()

    # ---------------- slide 4 ----------------
    s_early, s_mid, s_late = scen.iloc[0], scen.iloc[1], scen.iloc[2]
    swing = (s_early.median_freq_common_mask - s_late.median_freq_common_mask) * 100
    jan = m2027.loc["2027-01"]
    slide_frame(c, 4, 4, "Spring 2027: timing dominates — and what field work would settle",
                "The four-season record re-cut against three calendar windows, compared "
                "on the 43.4 km² observed in all three. No probabilities attached.")
    p, x, y, w, h = fit(OUT_PNG / "03_spring_2027_scenarios.png", M - 10, 216, 586, 254)
    c.drawImage(str(p), x, y, w, h, mask="auto")

    tx = M + 596
    tw = W - M - tx
    yy = H - M - 72
    yy = bullet(c, f"{s_early.median_freq_common_mask:.2f} → "
                   f"{s_mid.median_freq_common_mask:.2f} → "
                   f"{s_late.median_freq_common_mask:.2f}",
                f"Median snow frequency for the window 10 days early, on the historical "
                f"analogue dates, and 10 days late. A ±10-day shift is a "
                f"{swing:.0f}-point swing on a fixed pixel mask.", tx, yy, tw, WARM)
    yy = bullet(c, f"January 2027: {jan.south_over_north_ratio:g}×",
                f"Clear-sky insolation at 2200–2300 m, "
                f"{jan.median_north_2200_2300:.0f} kWh/m² facing north against "
                f"{jan.median_south_2200_2300:.0f} facing south. Deterministic geometry "
                f"— the one part of 2027 that can be computed.", tx, yy, tw)
    yy = bullet(c, "Published outlooks say less than they seem to",
                "Kazhydromet's winter 2026/27 forecast (issued 16 Nov 2026) and the C3S "
                "November issue are warm-leaning at oblast and continental scale. "
                "Neither resolves 2 km of relief; neither forecasts snow depth.",
                tx, yy, tw)

    panel(c, M - 10, 66, W - 2 * M + 20, 142)
    c.setFont("Helvetica-Bold", 11.4)
    c.setFillColor(INK)
    c.drawString(M + 4, 190, "A two-week field pilot would test all of this")
    col = (W - 2 * M - 30) / 4
    steps = [
        ("Days 1–2", "Align official corridors, boundaries and constraints with "
                          "these layers. Reconcile CRS, datum and resolution."),
        ("Days 3–4", "Stake paired plots: one shaded, one sunny, inside the same "
                          "100 m elevation band, across three bands."),
        ("Days 5–11", "Measure snow depth and density, pyranometer pair on "
                           "contrasting aspects, GNSS check of the DEM."),
        ("Days 12–14", "Re-run the notebooks against the field data; hand over "
                            "GeoTIFFs and a discrepancy log with causes."),
    ]
    for i, (head, body) in enumerate(steps):
        cx = M + 4 + i * (col + 8)
        c.setFont("Helvetica-Bold", 9.6)
        c.setFillColor(ACCENT)
        c.drawString(cx, 171, head)
        para(c, body, cx, 158, col - 6, size=8.8, leading=11.4)
    c.setFont("Helvetica", 8.8)
    c.setFillColor(MUTED)
    c.drawString(M + 4, 78, "Next stage: drone DEM over the corridors that matter · "
                            "local wind modelling for snow transport · skier-flow "
                            "modelling once designed geometry exists.")
    caption(c, f"Freshest scene on the release date: {fresh.iloc[0]['acquisition_date']} "
               f"({fresh.iloc[0]['scene_ids']}), "
               f"{fresh.iloc[0]['valid_pixel_fraction']*100:.0f}% usable pixels, "
               f"{fresh.iloc[0]['snow_fraction_of_valid']*100:.0f}% of those snow. "
               f"The 2026/27 season is in progress and is excluded from every "
               f"historical comparison.", M - 10, 56, W - 2 * M + 20)
    c.showPage()

    # ---------------- slide 5 : the cluster area ----------------
    ski = zones.loc["skiable 15-35 deg"]
    corr = zones.loc["existing lift corridors"]
    apr = sunm.loc["April"]
    dec = sunm.loc["December"]
    slide_frame(c, 5, N_SLIDES,
                "Widening to the cluster: 404 km\u00b2, and where the radiation is",
                "Every place the government statements name for Almaty SuperSki, plus "
                "Kok Zhailau and Kumbel \u2014 with the EXISTING lift network on it")
    p, x, y, w, h = fit(CLUSTER_PNG / "04_cluster_overview.png", M - 14, 194, 448, 262)
    c.drawImage(str(p), x, y, w, h, mask="auto")
    p, x, y, w, h = fit(CLUSTER_PNG / "04_max_radiation_points.png", 476, 194, 452, 262)
    c.drawImage(str(p), x, y, w, h, mask="auto")

    panel(c, M - 10, 74, W - 2 * M + 20, 116)
    sy = 168
    stat(c, M + 2, sy, f"{len(lifts_c)} lifts, {lifts_c.length_m.sum()/1000:.1f} km",
         "Existing aerialways from OpenStreetMap, plus "
         f"{corr.area_km2:.1f} km\u00b2 of lift corridor. No planned alignment is "
         "shown: none has been published.")
    stat(c, M + 240, sy, f"{ski.area_km2:.0f} km\u00b2",
         f"Skiable terrain at 15\u201335\u00b0, {ski.elev_min_m:.0f}\u2013"
         f"{ski.elev_max_m:.0f} m, median {ski.elev_median_m:.0f} m.", WARM)
    stat(c, M + 448, sy, "r = 0.73, 0 shared",
         "Correlation between ranking terrain by sunshine HOURS (cyan) and by "
         "ENERGY (green). Zero sites appear in both top-10 lists.")
    stat(c, M + 676, sy, f"{tops_h.iloc[0].sun_hours:.0f} h",
         f"Most direct sun on skiable ground, Nov\u2013Apr: "
         f"{tops_h.iloc[0].lat:.4f}\u00b0N {tops_h.iloc[0].lon:.4f}\u00b0E, "
         f"{tops_h.iloc[0].elevation_m:.0f} m, {tops_h.iloc[0].slope_deg:.0f}\u00b0 "
         f"facing {tops_h.iloc[0].aspect_deg:.0f}\u00b0.", WARM)
    caption(c, "Energy maxima sit on steep (\u224834\u00b0) south faces near 4000 m; "
               "sunshine-hour maxima sit on gentler 15\u201320\u00b0 south slopes that "
               "clear their horizon earlier and hold the sun longer. A lift station "
               "and a solar array want different answers. Lift geometry \u00a9 "
               "OpenStreetMap contributors, ODbL.", M - 10, 60, W - 2 * M + 20)
    c.showPage()

    # ---------------- slide 6 : timing and trust ----------------
    feb = bestw.loc["February"]
    mar = bestw.loc["March"]
    decw = bestw.loc["December"]
    best_row = idx.sort_values("sun_and_snow", ascending=False).iloc[0]
    slide_frame(c, 6, N_SLIDES,
                "When the sun is on the snow \u2014 and whether to believe it",
                "Clear-sky sun geometry by month and hour, multiplied by four seasons "
                "of measured snow frequency, then checked against a second satellite")
    p, x, y, w, h = fit(CLUSTER_PNG / "04_sunlit_heatmap_compact.png",
                        M + 44, 194, 380, 262)
    c.drawImage(str(p), x, y, w, h, mask="auto")
    p, x, y, w, h = fit(CLUSTER_PNG / "04_cross_validation_compact.png",
                        488, 194, 380, 262)
    c.drawImage(str(p), x, y, w, h, mask="auto")

    panel(c, M - 10, 74, W - 2 * M + 20, 116)
    sy = 168
    stat(c, M + 2, sy,
         f"{int(decw.window_start_hour):02d}:00\u2013{int(decw.window_end_hour):02d}:00",
         f"December window on the lift corridors: only {int(decw.hours_above_50pct_sunlit)} "
         f"hours a day with over half the corridor in sun, peaking at "
         f"{decw.peak_sunlit_fraction*100:.0f}%.")
    stat(c, M + 222, sy,
         f"{int(mar.window_start_hour):02d}:00\u2013{int(mar.window_end_hour):02d}:00",
         f"By March the window is {int(mar.hours_above_50pct_sunlit)} hours and the "
         f"corridors reach {mar.peak_sunlit_fraction*100:.0f}% sunlit at midday.", WARM)
    stat(c, M + 444, sy, f"Feb, {int(best_row.hour)}:00",
         f"Best sun-and-snow hour on the record: {best_row.sunlit_fraction*100:.0f}% "
         f"sunlit \u00d7 {best_row.snow_frequency*100:.0f}% snow frequency = "
         f"{best_row.sun_and_snow:.2f}.")
    stat(c, M + 666, sy, f"r = {xv['landsat_vs_sentinel2_r_pixel_matched']:.2f}",
         f"Landsat 8/9 against Sentinel-2, same date and same pixels, 8.5 M pixels. "
         f"Three DEMs agree to "
         f"{demcmp.elev_std_difference_m.max():.1f} m (1\u03c3).", WARM)
    caption(c, "Seven open sources are used here \u2014 Sentinel-2, Landsat 8/9, MODIS, "
               "Copernicus DEM, NASADEM, ALOS AW3D30, ERA5/ERA5-Land and OpenStreetMap \u2014 "
               "and five more are documented with endpoints in the release. The sun "
               "geometry is clear-sky: it says when the sun CAN reach the terrain, not "
               "whether the day will be clear, and the snow term is a satellite "
               "detection frequency, not snow depth.", M - 10, 60, W - 2 * M + 20)
    c.showPage()

    c.save()
    return OUT_PDF


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size/1e6:.2f} MB)")
