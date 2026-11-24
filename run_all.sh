#!/usr/bin/env bash
# End-to-end reproduction. Safe to re-run: every heavy step is cached.
#
# Four study areas are produced:
#   kok_zhailau  the superseded 69 km2 rectangle -> outputs/
#   cluster      the 404 km2 SuperSki area       -> outputs/cluster/
#   superski     the 125 km2 masterplan area     -> outputs/superski/
#   kz_project   the 42 km2 project window       -> outputs/kz_project/
# Run order matters: superski and kz_project reuse the cluster's Sentinel-2
# scene cache by slicing it, so the cluster must be built first.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -d .venv ]]; then source .venv/bin/activate; fi
python -c "import rasterio, pvlib, pystac_client, planetary_computer" || {
  echo "Missing dependencies. Run: pip install -r requirements.txt" >&2; exit 1; }

echo "== 1/6  terrain, horizon and insolation =="
(cd src && KZ_AREA=kok_zhailau python pipeline_terrain.py)
(cd src && KZ_AREA=cluster     python pipeline_terrain.py)
(cd src && KZ_AREA=superski    python pipeline_terrain.py)
(cd src && KZ_AREA=kz_project  python pipeline_terrain.py)

echo "== 2/6  sunshine hours =="
(cd src && KZ_AREA=cluster    python pipeline_sun.py 2027)
(cd src && KZ_AREA=superski   python pipeline_sun.py 2027)
(cd src && KZ_AREA=kz_project python pipeline_sun.py 2027)

echo "== 3/6  the drawn operating boundary =="
(cd src && KZ_AREA=superski python pipeline_operating_area.py)

echo "== 4/6  notebooks =="
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

echo "== 5/6  PDFs =="
python src/build_brief.py
python src/build_demo.py

echo "== 6/6  done =="
echo "GeoTIFFs (Kok Zhailau) : $(ls outputs/geotiff/*.tif | wc -l | tr -d ' ')"
echo "GeoTIFFs (cluster)     : $(ls outputs/cluster/geotiff/*.tif | wc -l | tr -d ' ')"
echo "GeoTIFFs (project)     : $(ls outputs/kz_project/geotiff/*.tif | wc -l | tr -d ' ')"
echo "operating-area tables  : $(ls outputs/superski/tables/operating_area_*.csv | wc -l | tr -d ' ')"
echo "figures                : $(ls outputs/png/*.png outputs/cluster/png/*.png outputs/kz_project/png/*.png outputs/superski/png/*.png | wc -l | tr -d ' ')"
echo "tables                 : $(ls outputs/tables/*.csv outputs/cluster/tables/*.csv outputs/kz_project/tables/*.csv | wc -l | tr -d ' ')"
echo "brief                  : kok-zhailau-brief.pdf"
echo "demo                   : almaty-superski-gis-demo.pdf"
