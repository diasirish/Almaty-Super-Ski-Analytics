#!/usr/bin/env bash
# End-to-end reproduction. Safe to re-run: every heavy step is cached.
#
# Two areas are produced:
#   cluster   the 404 km2 SuperSki cluster            -> outputs/cluster/
#   superski  the drawn operating boundary and the
#             70 km2 working window around it         -> outputs/superski/
# Run order matters: superski reuses the cluster's Sentinel-2 scene cache by
# slicing it, so the cluster must be built first.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then source .venv/bin/activate; fi
python -c "import rasterio, pvlib, pystac_client, planetary_computer" || {
  echo "Missing dependencies. Run: pip install -r requirements.txt" >&2; exit 1; }

echo "== 1/7  terrain, horizon and insolation =="
(cd src && KZ_AREA=cluster  python pipeline_terrain.py)
(cd src && KZ_AREA=superski python pipeline_terrain.py)

echo "== 2/7  sunshine hours =="
(cd src && KZ_AREA=cluster  python pipeline_sun.py 2027)
(cd src && KZ_AREA=superski python pipeline_sun.py 2027)

echo "== 3/7  Sentinel-2 cache for the window, sliced from the cluster =="
KZ_AREA=superski python src/slice_window_cache.py

echo "== 4/7  the drawn operating boundary and the QGIS pack =="
(cd src && KZ_AREA=superski python build_qgis_pack.py)
(cd src && KZ_AREA=superski python pipeline_operating_area.py)

echo "== 5/7  notebooks =="
for nb in 01_dem_terrain_and_insolation \
          02_sentinel2_snow_persistence \
          03_resort_planning_insights \
          04_cluster_radiation_and_timing \
          05_project_scale_and_validation \
          06_operating_boundary; do
  echo "   executing $nb"
  jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=5400 "notebooks/$nb.ipynb"
done

echo "== 6/7  PDFs and the extent review =="
KZ_AREA=cluster python src/build_extent_review.py
python src/build_brief.py
python src/build_demo.py

echo "== 7/7  done =="
echo "GeoTIFFs (cluster)     : $(ls outputs/cluster/geotiff/*.tif | wc -l | tr -d ' ')"
echo "GeoTIFFs (superski)    : $(ls outputs/superski/geotiff/*.tif | wc -l | tr -d ' ')"
echo "operating-area tables  : $(ls outputs/superski/tables/operating_area_*.csv | wc -l | tr -d ' ')"
echo "figures                : $(ls outputs/cluster/png/*.png outputs/superski/png/*.png | wc -l | tr -d ' ')"
echo "tables                 : $(ls outputs/cluster/tables/*.csv outputs/superski/tables/*.csv | wc -l | tr -d ' ')"
echo "brief                  : kok-zhailau-brief.pdf"
echo "demo                   : almaty-superski-gis-demo.pdf"
