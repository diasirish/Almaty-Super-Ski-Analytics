"""Shared configuration: area of interest, grids, periods, thresholds, paths.

Every number that controls the analysis lives here so that notebooks, scripts and
the written report cannot drift apart.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Study areas
# --------------------------------------------------------------------------
# Which rectangle the pipeline runs on. Set KZ_AREA before importing this
# module (the notebooks do it explicitly on their first line).
#
#   superski   the drawn operating boundary and the 1 km working window
#              around it; this is the study area
#   cluster    the Almaty SuperSki cluster area: every place named in the
#              government statements plus Kok Zhailau and Kumbel
STUDY_AREAS = {
    "superski": {
        "bbox": (76.950, 43.085, 77.055, 43.155),
        "label": "Almaty SuperSki - the drawn operating boundary and its working window",
        "note": ("The study area is the boundary in qgis/operating_area.geojson, "
                 "hand-digitised over satellite imagery. This rectangle is nothing "
                 "more than that boundary's own envelope plus the 1 km working "
                 "buffer operating_area.bbox() returns: rasters need a margin for "
                 "hillshade and for the horizon to have surroundings, and a map "
                 "needs context around its subject. Every figure reported for the "
                 "operating area is masked to the boundary. Earlier releases ran on "
                 "two larger author-chosen rectangles - a 69 km2 box around the "
                 "plateau and a 125 km2 envelope of the general-plan control points "
                 "- and both reached about 3 km north of the boundary into the "
                 "dacha belt below 1,775 m, which is ground this study has no "
                 "business measuring. Both are withdrawn."),
        "horizon_n_azimuth": 72,
        "sun_hour_step_min": 10,
    },
    "cluster": {
        "bbox": (76.950, 43.070, 77.200, 43.240),
        "label": "Almaty SuperSki cluster area",
        "note": ("Chosen to contain every place the government statements name "
                 "for the cluster (Shymbulak, Kimasar, Butakovka, Pioneer, "
                 "Oi-Qaragai) plus Kok Zhailau and Kumbel. No official project "
                 "boundary has been published; this rectangle is derived, not given."),
    },
}
AREA = os.environ.get("KZ_AREA", "cluster")
if AREA not in STUDY_AREAS:
    raise SystemExit(f"KZ_AREA={AREA!r} unknown; choose from {list(STUDY_AREAS)}")
AREA_LABEL = STUDY_AREAS[AREA]["label"]
AREA_NOTE = STUDY_AREAS[AREA]["note"]
_AREA_CFG = STUDY_AREAS[AREA]

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
# Every area gets its own subtree so runs never overwrite each other.
_SUB = AREA
INTERIM = DATA / "interim" / _SUB
PROCESSED = DATA / "processed" / _SUB
OUT = ROOT / "outputs" / _SUB
OUT_TIF = OUT / "geotiff"
OUT_PNG = OUT / "png"
OUT_TAB = OUT / "tables"
DOCS = ROOT / "docs"

# Large Sentinel-2 window cache lives OUTSIDE the release folder so the ZIP stays small.
SCENE_CACHE = Path(
    os.environ.get("KZ_SCENE_CACHE", ROOT.parent / "kok-zhailau-scene-cache")
)

for _p in (RAW, INTERIM, PROCESSED, OUT_TIF, OUT_PNG, OUT_TAB, DOCS, SCENE_CACHE):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Study area
# --------------------------------------------------------------------------
# WGS84 bounding box, order = west, south, east, north.
AOI_BBOX_WGS84 = STUDY_AREAS[AREA]["bbox"]

# Stated project territory (Kazakh Tourism Development, 18 Nov 2026 board
# meeting): 1,022 ha in total, about 20 ha of it built up.
PROJECT_AREA_HA = 1022.0
PROJECT_BUILT_HA = 20.0
PROJECT_PISTE_KM = 60.0
PROJECT_CABLEWAYS_POMA = 11
PROJECT_SKIERS_PER_DAY = 10000
PROJECT_LAUNCH = "2028-12"

# Two sources disagree and the project carries both rather than picking silently.
#
#   PRESS  the government statement reported in April 2026: 17 lifts and "about
#          70 % of runs green and blue".
#   PLAN   sheet 3 of the Kazakh Tourism Development general plan, supplied by
#          the project owner: 16 lifts; a difficulty split of 10.6 % green /
#          50.3 % blue / 22.7 % red / 16.4 % black; and 70 % of runs equipped
#          with SNOWMAKING. The plan's 70 % therefore belongs to snowmaking, and
#          its green+blue share is 60.9 %, not 70 %.
#
# The plan is the operator's own drawing and gives a four-way split rather than a
# round number, so it is the default; the press figure is carried for comparison.
PROJECT_DIFFICULTY_PLAN = {"green": 0.106, "blue": 0.503, "red": 0.227, "black": 0.164}
PROJECT_GREEN_BLUE_SHARE = round(
    PROJECT_DIFFICULTY_PLAN["green"] + PROJECT_DIFFICULTY_PLAN["blue"], 4)   # 0.609
PROJECT_GREEN_BLUE_SHARE_PRESS = 0.70
PROJECT_LIFTS = 16
PROJECT_LIFTS_PRESS = 17
PROJECT_SNOWMAKING_SHARE = 0.70
PROJECT_TOURISTS_PER_YEAR = 9_000_000
# Reference point on the plateau (lon, lat). Used only as a QA landmark.
PLATEAU_POINT = (77.00433, 43.14239)

CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32643"           # UTM zone 43N, the working projection

DEM_RES_M = 30.0                 # terrain / insolation grid
S2_RES_M = 20.0                  # Sentinel-2 snow grid
HORIZON_BUFFER_M = 6000.0        # terrain included around the AOI for horizon search
# 10 deg azimuth spacing by default; a small area can afford finer sampling.
HORIZON_N_AZIMUTH = int(_AREA_CFG.get("horizon_n_azimuth", 36))
HORIZON_STEP_M = 30.0            # first ray-march step along each azimuth
HORIZON_STEP_GROWTH = 1.02       # geometric growth of the step with distance
HORIZON_STEP_MAX_M = 120.0       # cap on the step length

# Copernicus DEM GLO-30 tiles covering the AOI (AWS Open Data, public).
DEM_TILES = [
    "Copernicus_DSM_COG_10_N43_00_E076_00_DEM",
    "Copernicus_DSM_COG_10_N43_00_E077_00_DEM",
]
DEM_BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"

# --------------------------------------------------------------------------
# Insolation
# --------------------------------------------------------------------------
TIMEZONE = "Asia/Almaty"         # UTC+5, no DST
TIME_STEP_MIN = 30
GROUND_ALBEDO = 0.50             # mixed snow / rock / forest winter value; see METHODS
REFERENCE_SEASON_YEAR = 2023     # insolation reference = 2022-11-01 .. 2023-04-30
OUTLOOK_YEAR = 2027

# Named accumulation windows for the historical reference season.
# (label, start month/day of first year, end month/day) resolved against the season.
INSOLATION_PERIODS = {
    "dec":      ("2022-12-01", "2022-12-31"),
    "mar":      ("2023-03-01", "2023-03-31"),
    "nov_dec":  ("2022-11-01", "2022-12-31"),
    "jan_feb":  ("2023-01-01", "2023-02-28"),
    "mar_apr":  ("2023-03-01", "2023-04-30"),
}

OUTLOOK_MONTHS_2027 = [1, 2, 3, 4, 11, 12]

# --------------------------------------------------------------------------
# Sentinel-2 / snow
# --------------------------------------------------------------------------
STAC_URL = "https://earth-search.aws.element84.com/v1"
STAC_COLLECTION = "sentinel-2-l2a"
STAC_FALLBACK_URL = "https://catalogue.dataspace.copernicus.eu/stac"
STAC_FALLBACK_COLLECTION = "SENTINEL-2"
MGRS_TILE = "43TFH"
MAX_CLOUD_PCT = 15.0

SEASONS = {
    "2022_23": ("2022-11-01", "2023-04-30"),
    "2023_24": ("2023-11-01", "2024-04-30"),
    "2024_25": ("2024-11-01", "2025-04-30"),
    "2025_26": ("2025-11-01", "2026-04-30"),
}
CURRENT_SEASON = ("2026_27", "2026-11-01", "2027-04-30")

# Snow decision rule (surface reflectance, 0-1)
NDSI_THRESHOLD = 0.40
NIR_THRESHOLD = 0.11

# Scene Classification Layer codes (Sen2Cor)
SCL_NO_DATA = 0
SCL_SATURATED = 1
SCL_CAST_SHADOW = 2
SCL_CLOUD_SHADOW = 3
SCL_VEGETATION = 4
SCL_NOT_VEGETATED = 5
SCL_WATER = 6
SCL_UNCLASSIFIED = 7
SCL_CLOUD_MEDIUM = 8
SCL_CLOUD_HIGH = 9
SCL_THIN_CIRRUS = 10
SCL_SNOW = 11

# Pixels that cannot support a snow / no-snow decision at all.
SCL_REJECT = (
    SCL_NO_DATA, SCL_SATURATED, SCL_CAST_SHADOW, SCL_CLOUD_SHADOW,
    SCL_UNCLASSIFIED, SCL_CLOUD_MEDIUM, SCL_CLOUD_HIGH, SCL_THIN_CIRRUS,
)
# Water is a valid observation but can never be counted as snow.
SCL_NEVER_SNOW = (SCL_WATER,)

MIN_VALID_OBS = 4                # per pixel, per period, for a frequency value
MIN_SEASONS_MULTIYEAR = 3        # seasons that must support a multi-year pixel

# Spring comparison window (historical analogue used for the 2027 outlook)
SPRING_WINDOW = ("03-11", "04-20")
SPRING_SHIFT_DAYS = 10

# --------------------------------------------------------------------------
# Terrain / planning bands
# --------------------------------------------------------------------------
SKIABLE_SLOPE_MIN = 15.0
SKIABLE_SLOPE_MAX = 35.0
STEEP_SLOPE_MIN = 30.0
ELEV_BAND_M = 100.0
FOCUS_BAND = (2200.0, 2300.0)    # headline elevation band
NORTHY = (315.0, 45.0)           # aspect sector counted as "north"
SOUTHY = (135.0, 225.0)          # aspect sector counted as "south"

NODATA = -9999.0


# --------------------------------------------------------------------------
# OpenStreetMap reference layers (existing lifts, pistes, named features)
# --------------------------------------------------------------------------
OSM_FILE = RAW / "osm" / "overpass_almaty_mountains.json"
OSM_BBOX = (76.85, 43.00, 77.30, 43.25)      # w, s, e, n of the Overpass query
LIFT_CORRIDOR_M = 150.0                       # half-width of a lift study corridor

# Sunshine-hour accounting
SUN_MIN_ELEVATION_DEG = 0.0      # sun must clear the terrain horizon by this much
# Time step for direct-sunshine duration. A small area can afford a finer one.
SUN_HOUR_STEP_MIN = int(_AREA_CFG.get("sun_hour_step_min", 15))
