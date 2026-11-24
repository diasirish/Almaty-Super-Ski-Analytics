# Redrawing the operating area

The Kazakh Tourism Development general-plan sheet is a perspective panorama. It
carries no projection, no scale bar and no graticule, so it cannot be
georeferenced: an affine or polynomial transform assumes a plan view, and this
is not one. Tracing it would manufacture a precision that is not in the source.

What the sheet does carry is **named features**. Those are real places and they
can be located independently. The extent used by the analysis is therefore the
envelope of seven labels on the sheet — Medeu, Kokgailau plateau 1951 m, Three
Brothers Rocks, Mountain Kumbel 3250 m, the Kumbeltau range, Kimasar saddle and
Shymbulak — each resolved against OpenStreetMap peaks, saddles and places, plus
a 1.5 km working buffer. Provenance for every vertex, and no tracing.

A rectangle is still a blunt instrument. Where a boundary that follows the
ground is wanted, this folder lets one be drawn by hand on top of the same
terrain the analysis runs on. The hand-drawn polygon becomes the **reporting
mask**; the rectangle stays the compute grid.

## Files

| file | what it is |
|---|---|
| `00_same_view_as_the_plan.png` | the DEM rendered from the general plan's own viewpoint — looking south from Almaty, east on the left — so the sheet and the terrain can be compared feature by feature |
| `operating_area.geojson` | the operating-area boundary, 21 vertices, EPSG:4326. Reshape it here to change what every number is reported over |
| `02_masterplan_control_points.geojson` | the seven labels, located in OSM |
| `03_reference_extents.geojson` | the two retired rectangles (69 and 125 km²) and the current working window, for reference only |
| `04_osm_lifts_and_pistes.geojson` | existing lifts, pistes and stations (OpenStreetMap, ODbL) |
| `hillshade.tif`, `dem_30m.tif`, `slope_deg.tif` | the analysis terrain itself, EPSG:32643 |
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

Ground that will plausibly carry a lift line or a piste. Not the low forest
below the base village — 37 % of the superseded rectangle sat below 1,900 m,
which is what prompted the redraw. Not the ridge above the top station either:
the plan's highest station is near 3,400 m.
