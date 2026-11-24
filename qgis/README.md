# Redrawing the operating area

The Kazakh Tourism Development general-plan sheet is a perspective panorama. It
carries no projection, no scale bar and no graticule, so it cannot be
georeferenced: an affine or polynomial transform assumes a plan view, and this
is not one. Tracing it would manufacture a precision that is not in the source.

What the sheet does carry is **named features**. Those are real places and they
can be located independently: Medeu, Kokgailau plateau 1951 m, Three Brothers
Rocks, Mountain Kumbel 3250 m, the Kumbeltau range, Kimasar saddle and
Shymbulak, each resolved against OpenStreetMap peaks, saddles and places. Two
earlier releases used rectangles — the envelope of those seven points, and
before it an author-chosen box — and **both are retired**: the control points
include Medeu and Kimasar at the city edge, so the envelope reached about 3 km
north of anywhere skiing is planned.

**The study area is the hand-drawn polygon in this folder.** The rasters here
are the analysis grid itself: the polygon's own envelope plus a 1 km margin,
70 km² at 30 m. Reshape `operating_area.geojson` and every number in the release
is re-derived over the new shape. Rebuild this pack with
`KZ_AREA=superski python src/build_qgis_pack.py` whenever the window changes.

## Files

| file | what it is |
|---|---|
| `00_same_view_as_the_plan.png` | the DEM rendered from the general plan's own viewpoint — looking south from Almaty, east on the left — so the sheet and the terrain can be compared feature by feature |
| `operating_area.geojson` | **the study area**, 24 vertices, EPSG:4326. Reshape it here to change what every number is reported over |
| `02_masterplan_control_points.geojson` | the seven labels, located in OSM |
| `03_reference_extents.geojson` | the current working window plus the two retired rectangles (69 and 125 km²), for reference only |
| `04_osm_lifts_and_pistes.geojson` | existing lifts, pistes and stations (OpenStreetMap, ODbL) |
| `hillshade.tif`, `dem_30m.tif`, `slope_deg.tif` | the analysis terrain itself, 292 × 267 @ 30 m, EPSG:32643 |
| `load_in_qgis.py` | adds all of the above plus a satellite basemap in one paste |

## Fast path

QGIS → `Plugins` → `Python Console` → paste `load_in_qgis.py` → Enter.

## Manual path

1. `Layer` → `Add Layer` → `Add Raster Layer` → `hillshade.tif`.
2. Drag the four `.geojson` files onto the map canvas.
3. Satellite imagery, optional: Browser panel → right-click `XYZ Tiles` → `New
   Connection`, name `Esri satellite`, URL
   `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
   then drag it to the bottom of the layer list.
4. Select `operating_area` → `Layer` → `Toggle Editing`.
5. `Edit` → `Vertex Tool`. Drag vertices; double-click an edge to add one;
   right-click a vertex to remove it.
6. `Layer` → `Save Layer Edits`, then `Toggle Editing` off.

Keep the file at this path and in GeoJSON. Keep it a single polygon.

## What the boundary should enclose

Ground that will plausibly carry a lift line or a piste.

Not the low forest and dacha plots below the base village: the first rectangle
put 37 % of its area below 1,900 m and the second reached down to 1,255 m, and
that is what prompted the redraw. Not the ridge above the top station either —
the plan's highest station is near 3,400 m. The boundary as drawn spans
1,775–3,291 m.

If you move it far enough that it leaves the current window, change the
`superski` bbox in `src/config.py` to `operating_area.bbox(poly)`, rebuild this
pack, and re-run `run_all.sh`. The pipeline refuses to report a clipped site
rather than quietly truncating one.
