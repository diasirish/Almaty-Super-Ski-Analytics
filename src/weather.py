"""Weather context: ERA5-Land reanalysis + officially published seasonal outlooks.

Reanalysis is fetched live. The seasonal outlooks are transcribed from the
primary documents cited in `SEASONAL_OUTLOOKS` and are never paraphrased into
numbers of our own.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date

import numpy as np
import pandas as pd

from config import INTERIM, PLATEAU_POINT

ERA5_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"


def _archive(start, end, lat, lon, daily, model):
    q = dict(latitude=lat, longitude=lon, start_date=start, end_date=end,
             daily=daily, timezone="Asia/Almaty", models=model)
    url = f"{ERA5_ARCHIVE}?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(url, timeout=180) as r:
        return json.load(r)


def era5_land_daily(start: str, end: str, lat: float = PLATEAU_POINT[1],
                    lon: float = PLATEAU_POINT[0], cache: bool = True) -> pd.DataFrame:
    """Daily reanalysis at the plateau reference point.

    Temperature comes from ERA5-Land (~9 km). ERA5-Land returns no precipitation
    at this point through the archive API, so snowfall and precipitation come from
    ERA5 (~31 km) instead and are labelled as such — a coarser grid again, and one
    whose orography is far smoother than the real valley.
    """
    key = INTERIM / f"reanalysis_{start}_{end}.csv"
    meta_key = INTERIM / f"reanalysis_{start}_{end}.meta.json"
    if cache and key.exists():
        df = pd.read_csv(key, parse_dates=["date"])
        df.attrs.update(json.load(open(meta_key)))
        return df

    land = _archive(start, end, lat, lon,
                    "temperature_2m_mean,temperature_2m_min,temperature_2m_max",
                    "era5_land")
    df = pd.DataFrame(land["daily"]).rename(columns={"time": "date"})

    precip_source = "era5_land"
    pr = _archive(start, end, lat, lon, "snowfall_sum,precipitation_sum", "era5_land")
    pdf = pd.DataFrame(pr["daily"]).rename(columns={"time": "date"})
    if pdf["precipitation_sum"].isna().all():
        pr = _archive(start, end, lat, lon, "snowfall_sum,precipitation_sum", "era5")
        pdf = pd.DataFrame(pr["daily"]).rename(columns={"time": "date"})
        precip_source = "era5"
    df = df.merge(pdf, on="date", how="left")
    df["date"] = pd.to_datetime(df["date"])

    meta = {
        "temperature_dataset": "ERA5-Land daily via Open-Meteo Historical Weather API "
                               "(~9 km grid)",
        "precipitation_dataset": ("ERA5-Land (~9 km)" if precip_source == "era5_land"
                                  else "ERA5 (~31 km) - ERA5-Land returned no "
                                       "precipitation at this point"),
        "precip_model_used": precip_source,
        "request_point_lon": lon, "request_point_lat": lat,
        "model_grid_elevation_m": land.get("elevation"),
        "timezone": land.get("timezone"),
        "units": {**land.get("daily_units", {}), **pr.get("daily_units", {})},
        "retrieved": date.today().isoformat(),
        "caveat": ("Both reanalyses are far coarser than this study's 20-30 m grid "
                   "and smooth the orography heavily. They say what kind of winter a "
                   "season was; they are not evidence about any individual slope, and "
                   "ERA5 precipitation over complex terrain carries large errors."),
    }
    if cache:
        df.to_csv(key, index=False)
        json.dump(meta, open(meta_key, "w"), indent=1)
    df.attrs.update(meta)
    return df


def current_conditions(lat: float = PLATEAU_POINT[1],
                       lon: float = PLATEAU_POINT[0]) -> dict:
    q = dict(latitude=lat, longitude=lon,
             current="temperature_2m,snowfall,weather_code",
             daily="snowfall_sum,temperature_2m_min,temperature_2m_max",
             timezone="Asia/Almaty", forecast_days=7)
    url = f"{FORECAST_API}?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.load(r)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    d["retrieved"] = date.today().isoformat()
    d["source"] = "Open-Meteo forecast API (ECMWF/DWD blend)"
    return d


def season_summary(df: pd.DataFrame, seasons: dict) -> pd.DataFrame:
    rows = []
    for name, (s, e) in seasons.items():
        m = (df["date"] >= s) & (df["date"] <= e)
        sub = df[m]
        if sub.empty:
            continue
        rows.append({
            "season": name.replace("_", "/"),
            "n_days": len(sub),
            "mean_T_C": round(float(sub["temperature_2m_mean"].mean()), 2),
            "days_Tmax_below_0C": int((sub["temperature_2m_max"] < 0).sum()),
            "snowfall_sum_cm": (round(float(sub["snowfall_sum"].sum()), 1)
                                if sub["snowfall_sum"].notna().any() else np.nan),
            "precip_sum_mm": (round(float(sub["precipitation_sum"].sum()), 1)
                              if sub["precipitation_sum"].notna().any() else np.nan),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Officially published seasonal outlooks, transcribed from primary documents.
# --------------------------------------------------------------------------
SEASONAL_OUTLOOKS = {
    "kazhydromet_winter_2026_27": {
        "issuer": "RSE Kazhydromet, Hydrometeorological Centre "
                  "(Ministry of Ecology and Natural Resources, Kazakhstan)",
        "document": "СЕЗОННЫЙ ПРОГНОЗ ПОГОДЫ. Декабрь 2026 года – февраль 2027 года",
        "url": "https://www.kazhydromet.kz/uploads/files_calendar/13401/file/"
               "6afacdf27e503sp-na-zimu-2026-2027-gg-ot-16-11-2026g.pdf",
        "landing_page": "https://www.kazhydromet.kz/ru/weather/"
                        "konsultativnyy-prognoz-pogody-na-sezon",
        "issued": "2026-11-16",
        "retrieved": "2026-11-19",
        "period": "2026-12-01 .. 2027-02-28",
        "spatial_scale": "17 oblasts of Kazakhstan; no separate mountain-zone forecast",
        "status": "advisory (консультативный)",
        "analogue_years": "December 2005; January-February 2026",
        "normals_period": "1991-2020",
        "almaty_oblast_normals": {
            "december": {"T_C": "-0.7 .. -10.6", "precip_mm": "10 .. 52"},
            "january": {"T_C": "-2.6 .. -13.0", "precip_mm": "8 .. 38"},
            "february": {"T_C": "-1.8 .. -10.7", "precip_mm": "8 .. 50"},
        },
        "almaty_city_normals": {
            "december": {"T_C": -2.7, "precip_mm": 44},
            "january": {"T_C": -4.6, "precip_mm": 35},
            "february": {"T_C": -2.4, "precip_mm": 43},
        },
        "outlook_for_almaty_area": {
            "december_2026": {
                "temperature": "above normal by 1-2 C over most of the country; "
                               "near normal in the east of Almaty oblast",
                "precipitation": "near normal across the whole country",
            },
            "january_2027": {
                "temperature": "above normal by 1-2 C over most of the country "
                               "(Almaty oblast not listed among near-normal areas)",
                "precipitation": "below normal in the northern half of Almaty oblast",
            },
            "february_2027": {
                "temperature": "above normal by 1-3 C over most of the country "
                               "(Almaty oblast not listed among near-normal areas)",
                "precipitation": "above normal over most of the country "
                                 "(Almaty oblast not listed among the exceptions)",
            },
        },
        "issue_schedule": "six issues per year; the winter (Dec-Feb) issue on 15 November",
        "caveat": "Oblast-scale and advisory. Almaty oblast spans roughly 500-5000 m; "
                  "a single oblast statement cannot be read as a forecast for the "
                  "1271-3318 m study area, and it says nothing about snow depth.",
    },
    "c3s_november_2026": {
        "issuer": "Copernicus Climate Change Service (C3S) multi-system seasonal forecast",
        "url": "https://climate.copernicus.eu/seasonal-forecasts",
        "charts_t2m": "https://climate.copernicus.eu/charts/packages/c3s_seasonal/products/"
                      "c3s_seasonal_spatial_mm_2mtm_3m?area=area01&base_time=202611010000"
                      "&type=tsum&valid_time=202612010000",
        "charts_precip": "https://climate.copernicus.eu/charts/packages/c3s_seasonal/products/"
                         "c3s_seasonal_spatial_mm_rain_3m?area=area08&base_time=202611010000"
                         "&type=tsum&valid_time=202612010000",
        "issued": "2026-11-10",
        "retrieved": "2026-11-19",
        "base_time": "2026-11-01 initialisation",
        "period": "DJF 2026/27 onward, at least six months ahead",
        "contributing_systems": ["ECMWF", "Met Office", "Meteo-France", "DWD", "CMCC",
                                 "NCEP", "JMA", "ECCC", "BOM"],
        "published_highlights": "ENSO expected to peak around the end of 2026; "
                                "eastern Asia listed among wetter-than-average regions",
        "what_we_could_not_read": "The C3S anomaly charts are rendered client-side; no "
                                  "Central Asia / Kazakhstan anomaly value could be read "
                                  "programmatically on 2026-11-19. The chart URLs above "
                                  "are given so a reader can check them directly.",
        "caveat": "Seasonal forecasts are probabilistic and coarse-resolution. C3S "
                  "publishes verification plots; skill over Central Asia in winter is "
                  "limited and must be checked before any operational use.",
    },
}


def write_sources(path=None) -> str:
    path = path or (INTERIM.parent.parent / "docs" / "seasonal_outlooks.json")
    json.dump(SEASONAL_OUTLOOKS, open(path, "w"), indent=1, ensure_ascii=False)
    return str(path)
