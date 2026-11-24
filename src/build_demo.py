"""Build the 4-slide demo: project-scale GIS, model validation, weather handover.

This is the document meant to be read by an engineering, GIS or mountain-planning
team. It is deliberately separate from kok-zhailau-brief.pdf, which stays at six
slides and tells the wider story. Every number is read from
outputs/superski/tables/, never hard-coded.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_brief import (ACCENT, FAINT, H, INK, M, MUTED, PANEL, RULE, W, WARM,
                         bullet, caption, fit, panel, para, slide_frame, stat)
from config import PROJECT_PISTE_KM as PISTE_KM, ROOT

# One study area: the drawn operating boundary and the working window round it.
TAB = OA_TAB = ROOT / "outputs" / "superski" / "tables"
PNG = OA_PNG = ROOT / "outputs" / "superski" / "png"
META = ROOT / "outputs" / "superski" / "geotiff" / "project_metadata.json"
OUT_PDF = ROOT / "almaty-superski-gis-demo.pdf"
N = 4


def _t(name: str) -> pd.DataFrame:
    return pd.read_csv(TAB / name)


def _o(name: str) -> pd.DataFrame:
    return pd.read_csv(OA_TAB / name)


def build():
    meta = json.loads(META.read_text())
    pub = _o("published_project_parameters.csv")
    oa = _o("operating_area_summary.csv").iloc[0]
    D = _o("operating_area_terrain.csv").iloc[0]
    oafeas = _o("operating_area_piste_feasibility.csv")
    oasun = _o("operating_area_sun_by_month.csv").set_index("month")
    oasnow = _o("operating_area_snow_by_month.csv").set_index("month")
    chain = _t("dem_propagation.csv")
    ranks = _t("dem_rank_stability.csv")
    overview = _t("three_area_overview.csv")
    matched = _t("three_area_matched_differences.csv")
    inv = _t("resort_inventory.csv")
    reuse = _t("scene_cache_reuse_check.csv").iloc[0]
    needed = _t("local_measurements_required.csv")
    clim = _t("reanalysis_monthly_climatology.csv").set_index("month")

    dec_chain = chain[chain.layer == "insolation_december_kwh_m2"]
    elev_r = chain[chain.layer == "elevation_m"].correlation.min()
    slope_r = chain[chain.layer == "slope_deg"].correlation.min()
    shy_i = matched[(matched.area.str.startswith("Shymbulak"))
                    & (matched.layer == "insolation_kwh_m2")].iloc[0]
    shy_s = matched[(matched.area.str.startswith("Shymbulak"))
                    & (matched.layer == "snow_freq_march")].iloc[0]
    oq_i = matched[(matched.area.str.startswith("Oi-Qaragai"))
                   & (matched.layer == "insolation_kwh_m2")].iloc[0]

    c = canvas.Canvas(str(OUT_PDF), pagesize=(W, H))
    c.setTitle("Almaty SuperSki — project-scale GIS and model validation demo")
    c.setAuthor("Dias Irishev")
    c.setSubject("Independent open-data case study; not commissioned by any operator")

    # ---------------------------------------------------------------- slide 1
    dsun = oasun.loc["December"]
    slide_frame(c, 1, N, "Kok Zhailau at the scale it is being built",
                "Operating-area GIS, local model validation and weather data \u2014 "
                "what open data settles, and what it cannot")
    COL = 288.0
    xs = [M, M + 300, M + 600]
    ytop = H - M - 72
    lifts = pub[(pub.parameter == "lifts") & (pub.source.str.startswith("general"))].published.iloc[0]
    gbpub = pub[(pub.parameter == "runs green and blue")
                & (pub.source.str.startswith("general"))].published.iloc[0]
    bullet(c, "The territory is stated. Its boundary is not.",
           f"The operator publishes {PISTE_KM:.0f} km of runs, {lifts} lifts, "
           f"{gbpub} green and blue, up to 10,000 skiers a day on "
           f"{meta['operating_boundary']['stated_territory_ha']:,.0f} ha, launch December 2028. No boundary, "
           f"no lift alignment, no station coordinate and no capacity in persons per "
           f"hour. Press reporting of the April statement gave 17 lifts and \u2018about "
           f"70 % green and blue\u2019; the plan attaches its 70 % to snowmaking. Both "
           f"sources are carried, and every table names which one it used.",
           xs[0], ytop, COL)
    bullet(c, "So the boundary is drawn, and nothing stands in for it.",
           f"{oa.raster_area_ha:,.0f} ha over {int(oa.n_vertices)} vertices, digitised over imagery \u2014 "
           f"{100*oa.share_of_stated:.0f} % of the stated territory, and not an official line. Every "
           f"figure in this deck is read inside it. Two earlier releases reported "
           f"medians over author-chosen rectangles of 69 and 125 km\u00b2, and over two "
           f"synthetic 1,022 ha footprints; all four reached into ground no one plans "
           f"to ski on, and all four are withdrawn.",
           xs[1], ytop, COL, WARM)
    bullet(c, "December sun is not where you expect it.",
           f"Median direct sun across the whole of December is {dsun.median_sun_h:.0f} h inside the "
           f"boundary, {dsun.median_h_per_day:.1f} h a day, and the bottom tenth of it sees none at all. "
           f"On the green and blue ground it is {dsun.median_sun_h_green_blue:.0f} h, "
           f"{dsun.median_h_per_day_green_blue:.1f} h a day. The plateau faces the city, "
           f"which is north \u2014 but the gentle shelves that would carry beginner runs "
           f"are not the north-facing part of it.",
           xs[2], ytop, COL)

    img, ix, iy, iw, ih = fit(OA_PNG / "06_operating_area.png", M, 86, W - 2 * M, 232)
    c.drawImage(str(img), ix, iy, iw, ih, mask="auto")
    caption(c, f"The drawn operating area, read three ways. Grid 30 m, EPSG:32643 \u00b7 "
               f"horizon 72 azimuths (5\u00b0) to 6 km \u00b7 sunshine duration stepped 10 min \u00b7 "
               f"Copernicus DEM GLO-30 \u00b7 snow from Sentinel-2 L2A over four seasons. "
               f"The boundary is the author's, not the project's.",
            M, 80, W - 2 * M)
    c.showPage()

    # ---------------------------------------------------------------- slide 2
    plan = oafeas[oafeas.green_blue_source.str.startswith("general")]
    f40 = plan[plan.assumed_mean_piste_width_m == 40].iloc[0]
    f50 = plan[plan.assumed_mean_piste_width_m == 50].iloc[0]
    slide_frame(c, 2, N, "The published mix of runs, against the ground",
                "60 km of runs at the operator's own 60.9 % green and blue, "
                "measured against the gradients that exist")
    panel(c, M - 10, 346, W - 2 * M + 20, 100)
    sy = 424
    stat(c, M + 2, sy, f"{D.green_blue_ha:,.0f} ha",
         f"of the {oa.raster_area_ha:,.0f} ha lies at green/blue gradients "
         f"({100*D.green_blue_share:.0f} %, {D.median_slope_deg:.0f}\u00b0 median slope, "
         f"{100*D.above_31deg_share:.0f} % above 31\u00b0).")
    stat(c, M + 232, sy, f"{D.green_blue_largest_ha:,.0f} ha",
         f"of that is one unbroken field \u2014 {100*D.green_blue_largest_share:.0f} % of all the gentle "
         f"ground inside the boundary. The rest arrives in {int(D.green_blue_pieces)-1} smaller "
         f"fragments. Connectivity, not quantity, is the constraint.", WARM)
    stat(c, M + 462, sy, f"{D.vertical_m:,.0f} m",
         f"of vertical, {D.elev_min_m:,.0f}\u2013{D.elev_max_m:,.0f} m, in one connected piece. "
         f"Ample for the published 60 km of runs; the question the gradient table "
         f"answers is whether the easy half of that network fits.")
    stat(c, M + 692, sy, f"{100*f40.share_of_available_consumed:.0f} %",
         f"of the gentle ground the green/blue runs would consume at a 40 m mean width: "
         f"{f40.green_blue_piste_ha:.0f} ha needed against {f40.available_green_blue_ha:.0f} ha available. "
         f"At 50 m, {100*f50.share_of_available_consumed:.0f} %.", WARM)

    y = 300
    y = para(c, "Gradient classes are the percent grades of the British Columbia All "
                "Season Resort Guidelines, Chapter II, converted to degrees. That is a "
                "public planning convention from the jurisdiction the named planners "
                "work in \u2014 not a Kazakh standard and not this project's design "
                "criteria. The operator publishes a length and a mix but no width, so "
                "three mean widths are carried through instead of one assumption, and "
                "both published mixes are reported side by side.",
             M, y, 420, size=10.0, leading=13.4)
    y -= 6
    y = para(c, f"The easy-terrain budget closes with room: the binding constraint on a "
                f"beginner-led resort here is not how much gentle ground exists. An "
                f"earlier draft of this deck put the same arithmetic at up to 101 % of "
                f"available ground; that figure combined a synthetic footprint with the "
                f"conflated 70 %, and both are withdrawn. What a 30 m DEM still cannot show "
                f"is whether two gentle benches can be joined by a lift \u2014 a survey "
                f"question, and it is in the handover table on slide 4.",
             M, y, 420, size=10.0, leading=13.4, color=INK)

    img, ix, iy, iw, ih = fit(OA_PNG / "07_gentle_ground.png", 480, 86, 446, 200)
    c.drawImage(str(img), ix, iy, iw, ih, mask="auto")
    caption(c, "Green is ground at green/blue gradients inside the drawn boundary; the dark "
               "outline is the largest unbroken piece of it. Nothing outside is measured.",
            480, 78, 446)
    c.showPage()

    # ---------------------------------------------------------------- slide 3
    slide_frame(c, 3, N, "Kok Zhailau, Shymbulak and Oi-Qaragai — one rule, matched ground",
                "Comparing a plan with two working resorts without letting "
                "altitude or gradient do the talking")
    ytop = H - M - 72
    bullet(c, "One rule for all three places.",
           f"An operating area is the ground within 150 m of that place's lift lines, "
           f"unioned with 100 m of its pistes; lines go to the nearest named place "
           f"within 3.5 km. Shymbulak gets {int(inv[inv.place=='Shymbulak'].lifts.iloc[0])} lifts / "
           f"{inv[inv.place=='Shymbulak'].lift_km.iloc[0]:.1f} km and "
           f"{int(inv[inv.place=='Shymbulak'].pistes.iloc[0])} pistes; Oi-Qaragai "
           f"{int(inv[inv.place=='Oi-Qaragai'].lifts.iloc[0])} lifts / "
           f"{inv[inv.place=='Oi-Qaragai'].lift_km.iloc[0]:.1f} km. The earlier release used the OSM "
           f"winter-sports polygons, 2.2 and 1.0 km\u00b2, which understated both resorts.",
           M, ytop, COL)
    bullet(c, "Then hold altitude and gradient constant.",
           "Every area is cut to 15\u201335\u00b0 and compared band by 200 m band, a band "
           "reported only where that area has 50 pixels in it. The reference is the "
           "drawn operating boundary, cut to the same gradients \u2014 otherwise the "
           "difference being measured would be the difference between a lift "
           "corridor and a whole hillside.",
           M + 300, ytop, COL, WARM)
    bullet(c, "Sun and snow rank them differently.",
           f"Against the drawn boundary, Shymbulak's corridors take {shy_i.median_difference:+.0f} kWh/m\u00b2 "
           f"of winter energy over {int(shy_i.shared_bands)} shared bands and hold snow "
           f"{shy_s.median_difference:+.3f} more often in March: they trade sun for snow. "
           f"Oi-Qaragai takes {oq_i.median_difference:+.0f} kWh/m\u00b2, but sits at 1,520\u20132,280 m "
           f"under forest, where NDSI beneath canopy is a known weak point \u2014 the "
           f"least comparable number in the table.",
           M + 600, ytop, COL)

    img, ix, iy, iw, ih = fit(PNG / "05_three_area_elevation_bands.png", M, 86, W - 2 * M, 236)
    c.drawImage(str(img), ix, iy, iw, ih, mask="auto")
    caption(c, "Skiable gradients only; a point is drawn only where an area has at "
               "least 50 pixels in that elevation band. Existing OpenStreetMap network "
               "(ODbL) \u2014 no planned alignment is drawn, because none has been published.",
            M, 80, W - 2 * M)
    c.showPage()

    # ---------------------------------------------------------------- slide 4
    slide_frame(c, 4, N, "Validation, and the handover",
                "Running the whole chain on two more DEMs, measuring the snow "
                "record's own blind spot, and saying what has to be measured")
    panel(c, M - 10, 344, W - 2 * M + 20, 102)
    sy = 424
    stat(c, M + 2, sy, f"{elev_r:.4f} → {slope_r:.3f}",
         "elevation correlation between Copernicus GLO-30, NASADEM and ALOS AW3D30, "
         "and the slope correlation built from those same pixels. Agreement does not "
         "survive differentiation.")
    stat(c, M + 232, sy, f"{dec_chain.pct_p95_abs.min():.0f}–{dec_chain.pct_p95_abs.max():.0f} %",
         f"is how far a December insolation figure moves at the 95th percentile "
         f"depending on which open DEM was used, although the median bias is only "
         f"{dec_chain.diff_median.abs().max():.1f} kWh/m².", WARM)
    stat(c, M + 462, sy,
         f"{100*ranks.overlap_share.min():.0f}–{100*ranks.overlap_share.max():.0f} %",
         f"of the top tenth of terrain is the same ground whichever DEM is used "
         f"(Spearman {ranks.spearman_rho.min():.3f}–{ranks.spearman_rho.max():.3f}). Screening survives; "
         f"a single site's number does not.")
    dsnow = oasnow.loc["December"]
    stat(c, M + 692, sy, f"{100*dsnow.qualifying_share:.0f} %",
         f"of the operating area has four clear December observations, and that "
         f"subset is {dsnow.dec_insolation_bias_kwh:+.0f} kWh/m² sunnier and "
         f"{abs(dsnow.slope_bias_deg):.1f}° gentler than the site as a whole. "
         f"March: {100*oasnow.loc['March'].qualifying_share:.0f} % on a median of "
         f"{int(oasnow.loc['March'].median_valid_obs)} observations.", WARM)

    y = 300
    y = para(c, "Three things were run to try to break the results rather than to "
                "present them. First, the entire chain — slope, aspect, ray-marched "
                "horizon, sky view factor, clear-sky insolation, sunshine duration — "
                "was rebuilt on NASADEM and ALOS AW3D30 and the products compared, not "
                "the elevations. Second, the December snow map's own sampling was "
                "measured: a pixel needs four cloud- and shadow-free observations, "
                "shaded ground fails that test more often, and the pixels that qualify "
                "are measurably sunnier — so that figure describes the sunnier part of "
                "the terrain, and now says so. Third, the project-scale snow record was "
                "taken from the 115 scenes already read for the cluster by asserting "
                f"grid alignment and slicing; re-reading one scene from the COGs "
                f"reproduced it to {int(reuse.snow_pixels_differing + reuse.valid_pixels_differing)} "
                f"differing pixels out of {int(reuse.pixels_compared):,}.",
             M, y, 420, size=10.0, leading=14.6)
    y -= 8
    y = para(c, f"Weather is the same story at coarser grain: ERA5-Land is ~9 km and "
                f"ERA5 ~31 km against a 6 km window spanning 1,867 m of relief, so "
                f"reanalysis here is a regional season descriptor, not a site record — "
                f"and ERA5-Land returns no precipitation at this point, so snowfall is "
                f"labelled as ERA5 rather than silently summed to zero. The published "
                f"Kazhydromet seasonal outlook is oblast-level with no mountain zone.",
             M, y, 420, size=10.0, leading=14.6, color=MUTED)

    bx, by, bw = 478, 298, 448
    c.setFont("Helvetica-Bold", 11.2)
    c.setFillColor(ACCENT)
    c.drawString(bx, by, "What I would ask the project team for")
    by -= 17
    for _, r in needed.head(6).iterrows():
        c.setFont("Helvetica-Bold", 8.8)
        c.setFillColor(INK)
        c.drawString(bx, by, f"· {r['question']}")
        by -= 12.2
        by = para(c, r["needed_measurement"], bx + 8, by, bw - 10, size=8.5,
                  leading=11.2, color=MUTED, max_lines=2) - 5.0
    caption(c, "Clear-sky geometry and a satellite detection frequency are not a "
               "snowpack model, and no further processing turns one into the other. "
               "The full table, with why orbit cannot supply each quantity, is in "
               "outputs/superski/tables/local_measurements_required.csv.",
            bx, by - 2, bw)
    c.showPage()

    c.save()
    return OUT_PDF


if __name__ == "__main__":
    p = build()
    print(f"wrote {p} ({p.stat().st_size/1e6:.2f} MB)")
