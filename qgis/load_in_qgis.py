"""Open everything needed to redraw the operating area, in one paste.

QGIS -> Plugins -> Python Console -> paste this whole file -> Enter.
Nothing here writes to disk; it only adds layers to the current project.
"""
import os
from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer,
                       QgsCoordinateReferenceSystem, QgsFillSymbol,
                       QgsLineSymbol, QgsMarkerSymbol)
from qgis.utils import iface

D = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else \
    "/Users/diasirishev/Desktop/CodeBase/kok-zhailay/kok-zhailau-ski-terrain-analytics/qgis"

proj = QgsProject.instance()
proj.setCrs(QgsCoordinateReferenceSystem("EPSG:32643"))   # UTM 43N: metres, not degrees

def add_raster(path, name, visible=True):
    lyr = QgsRasterLayer(os.path.join(D, path), name)
    if not lyr.isValid():
        print("  ! could not load", path); return None
    proj.addMapLayer(lyr)
    proj.layerTreeRoot().findLayer(lyr.id()).setItemVisibilityChecked(visible)
    return lyr

def add_vector(path, name, symbol=None, visible=True):
    lyr = QgsVectorLayer(os.path.join(D, path), name, "ogr")
    if not lyr.isValid():
        print("  ! could not load", path); return None
    if symbol is not None:
        lyr.renderer().setSymbol(symbol); lyr.triggerRepaint()
    proj.addMapLayer(lyr)
    proj.layerTreeRoot().findLayer(lyr.id()).setItemVisibilityChecked(visible)
    return lyr

# --- basemap: Esri satellite imagery (public tile service) -------------------
esri = ("type=xyz&zmin=0&zmax=19&url=https://server.arcgisonline.com/ArcGIS/rest/"
        "services/World_Imagery/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D")
sat = QgsRasterLayer(esri, "Esri satellite imagery", "wms")
if sat.isValid():
    proj.addMapLayer(sat)
else:
    print("  ! satellite basemap unavailable (offline?) - the hillshade below still works")

# --- our own terrain ---------------------------------------------------------
add_raster("slope_deg.tif", "slope (deg) - gentle ground is where runs go", visible=False)
add_raster("hillshade.tif", "hillshade (Copernicus DEM GLO-30)")

# --- reference layers --------------------------------------------------------
add_vector("04_osm_lifts_and_pistes.geojson", "existing lifts and pistes (OSM)",
           QgsLineSymbol.createSimple({"color": "20,20,20,255", "width": "0.5"}))
add_vector("03_reference_extents.geojson", "reference extents",
           QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "120,120,120,255",
                                       "outline_width": "0.3", "outline_style": "dash"}))
add_vector("02_masterplan_control_points.geojson", "general-plan control points",
           QgsMarkerSymbol.createSimple({"name": "circle", "color": "255,212,0,255",
                                         "outline_color": "0,0,0,255", "size": "3.4"}))
edit = add_vector("operating_area.geojson", ">>> EDIT ME: operating area <<<",
                  QgsFillSymbol.createSimple({"color": "204,34,0,40", "outline_color": "204,34,0,255",
                                              "outline_width": "1.0"}))

# label the control points so you can see which is which.
# The placement enum moved between QGIS releases, so this is best-effort only.
try:
    from qgis.core import (QgsPalLayerSettings, QgsTextFormat,
                           QgsTextBufferSettings, QgsVectorLayerSimpleLabeling)
    cp = proj.mapLayersByName("general-plan control points")[0]
    st = QgsPalLayerSettings(); st.fieldName = "label"
    fmt = QgsTextFormat(); fmt.setSize(9)
    tb = QgsTextBufferSettings(); tb.setEnabled(True); tb.setSize(1.0)
    fmt.setBuffer(tb); st.setFormat(fmt)
    cp.setLabeling(QgsVectorLayerSimpleLabeling(st))
    cp.setLabelsEnabled(True); cp.triggerRepaint()
except Exception as exc:
    print("  (labels skipped:", exc, ")")

if edit is not None:
    iface.setActiveLayer(edit)
    iface.mapCanvas().setExtent(edit.extent()); iface.mapCanvas().refresh()
    iface.zoomToActiveLayer()

print("""
Loaded. Now:
  1. the layer '>>> EDIT ME: operating area <<<' is already selected
  2. Layer menu -> Toggle Editing  (pencil icon)
  3. Edit menu -> Vertex Tool -> drag the 8 corner points where they belong
     (double-click an edge to add a vertex; right-click a vertex to delete it)
  4. Layer menu -> Save Layer Edits
  5. tell Claude it is saved - the file path has not changed
""")
