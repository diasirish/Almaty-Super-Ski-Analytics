#!/usr/bin/env bash
# End-to-end reproduction. Safe to re-run: every heavy step is cached.
#
# Three study areas are produced:
#   kok_zhailau  the original 69 km2 rectangle   -> outputs/
#   cluster      the 404 km2 SuperSki area       -> outputs/cluster/
#   kz_project   the 42 km2 project window       -> outputs/kz_project/
# Run order matters once: kz_project reuses the cluster's Sentinel-2 scene
# cache by slicing it, so the cluster must be built first.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then source .venv/bin/activate; fi
python -c "import rasterio, pvlib, pystac_client, planetary_computer" || {
  echo "Missing dependencies. Run: pip install -r requirements.txt" >&2; exit 1; }

echo "== 1/5  terrain, horizon and insolation =="
(cd src && KZ_AREA=kok_zhailau python pipeline_terrain.py)
(cd src && KZ_AREA=cluster     python pipeline_terrain.py)
(cd src && KZ_AREA=kz_project  python pipeline_terrain.py)

echo "== 2/5  sunshine hours =="
(cd src && KZ_AREA=cluster    python pipeline_sun.py 2027)
(cd src && KZ_AREA=kz_project python pipeline_sun.py 2027)

echo "== 3/5  notebooks =="
for nb in 01_dem_terrain_and_insolation \
          02_sentinel2_snow_persistence \
          03_resort_planning_insights \
          04_cluster_radiation_and_timing \
          05_project_scale_and_validation; do
  echo "   executing $nb"
  jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=5400 "notebooks/$nb.ipynb"
done

echo "== 4/5  PDFs =="
python src/build_brief.py
python src/build_demo.py

echo "== 5/5  done =="
echo "GeoTIFFs (Kok Zhailau) : $(ls outputs/geotiff/*.tif | wc -l | tr -d ' ')"
echo "GeoTIFFs (cluster)     : $(ls outputs/cluster/geotiff/*.tif | wc -l | tr -d ' ')"
echo "GeoTIFFs (project)     : $(ls outputs/kz_project/geotiff/*.tif | wc -l | tr -d ' ')"
echo "figures                : $(ls outputs/png/*.png outputs/cluster/png/*.png outputs/kz_project/png/*.png | wc -l | tr -d ' ')"
echo "tables                 : $(ls outputs/tables/*.csv outputs/cluster/tables/*.csv outputs/kz_project/tables/*.csv | wc -l | tr -d ' ')"
echo "brief                  : kok-zhailau-brief.pdf"
echo "demo                   : almaty-superski-gis-demo.pdf"
