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

from config import DOCS, INTERIM, PLATEAU_POINT

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
# Hourly reanalysis: wet-bulb temperature and the snowmaking window.
#
# Snow frequency from orbit answers "was there snow on that date". It cannot
# answer "will there be enough snow on the pistes", because that question is
# about how long cover lasts, how often it breaks, and - on ground where nature
# does not deliver - how many hours the weather allows snow to be made. The
# first two come from the satellite record (see snow.py); the third needs
# hourly temperature and humidity, which is what these functions fetch.
# --------------------------------------------------------------------------

HOURLY_LAND_VARS = "temperature_2m,relative_humidity_2m,dew_point_2m,snow_depth"
# Surface pressure and precipitation both come from ERA5: ERA5-Land serves
# neither at this point through the archive API. Pressure is dominated by
# elevation, and the two models report the same 2,235 m here, so the coarser
# grid costs nothing for that one variable.
HOURLY_ERA5_VARS = "precipitation,rain,snowfall,surface_pressure"


def _archive_hourly(start, end, lat, lon, hourly, model, timeout=600):
    q = dict(latitude=lat, longitude=lon, start_date=start, end_date=end,
             hourly=hourly, timezone="Asia/Almaty", models=model)
    url = f"{ERA5_ARCHIVE}?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def era5_hourly(start: str, end: str, lat: float = PLATEAU_POINT[1],
                lon: float = PLATEAU_POINT[0], cache: bool = True) -> pd.DataFrame:
    """Hourly reanalysis at the plateau reference point, one cell, its own height.

    ERA5-Land (~9 km) carries temperature, relative humidity, dew point, surface
    pressure and modelled snow depth. It returns no precipitation at this point
    through the archive API, so rain and snowfall come from ERA5 (~31 km) and are
    labelled as such.

    Nothing is corrected to any other height here. `at_elevation()` does that
    explicitly, with the lapse rate it is handed, because that correction is the
    largest assumption in everything downstream and it should be visible.
    """
    key = INTERIM / f"reanalysis_hourly_{start}_{end}.csv"
    meta_key = INTERIM / f"reanalysis_hourly_{start}_{end}.meta.json"
    if cache and key.exists():
        df = pd.read_csv(key, parse_dates=["time"])
        df.attrs.update(json.load(open(meta_key)))
        return df

    land = _archive_hourly(start, end, lat, lon, HOURLY_LAND_VARS, "era5_land")
    df = pd.DataFrame(land["hourly"]).rename(columns={"time": "time"})
    era5 = _archive_hourly(start, end, lat, lon, HOURLY_ERA5_VARS, "era5")
    df = df.merge(pd.DataFrame(era5["hourly"]), on="time", how="left")
    df["time"] = pd.to_datetime(df["time"])

    meta = {
        "temperature_dataset": "ERA5-Land hourly via Open-Meteo Historical Weather "
                               "API (~9 km grid)",
        "precipitation_dataset": "ERA5 hourly (~31 km) - ERA5-Land returns "
                                 "neither precipitation nor surface pressure at "
                                 "this point",
        "request_point_lon": lon, "request_point_lat": lat,
        "era5_land_cell_elevation_m": land.get("elevation"),
        "era5_cell_elevation_m": era5.get("elevation"),
        "era5_land_cell": [land.get("latitude"), land.get("longitude")],
        "era5_cell": [era5.get("latitude"), era5.get("longitude")],
        "timezone": land.get("timezone"),
        "units": {**land.get("hourly_units", {}), **era5.get("hourly_units", {})},
        "retrieved": date.today().isoformat(),
        "caveat": ("One reanalysis cell at one model elevation. Snow depth is the "
                   "model's own snowpack in a 9 km cell whose orography is far "
                   "smoother than this valley: it says what kind of winter a season "
                   "was, not how deep the snow was on any slope."),
    }
    if cache:
        df.to_csv(key, index=False)
        json.dump(meta, open(meta_key, "w"), indent=1)
    df.attrs.update(meta)
    return df


def saturation_vapour_pressure_hpa(t_c):
    """Buck (1996) saturation vapour pressure over liquid water, hPa."""
    t = np.asarray(t_c, dtype="float64")
    return 6.1121 * np.exp((18.678 - t / 234.5) * t / (257.14 + t))


def wet_bulb_c(t_c, rh_pct, p_hpa, psychrometric_const=6.6e-4, iters: int = 40):
    """Wet-bulb temperature from the psychrometric equation, solved numerically.

        e_s(Tw) - e = A * p * (T - Tw),      A = 6.6e-4 per K over water

    Bisection on Tw in [T - 50, T], vectorised. Pressure is carried explicitly
    because it moves the answer: holding T and RH fixed, the wet bulb at the
    ~800 hPa of 2,000 m runs 0.2-0.35 C below its sea-level value, since thinner
    air evaporates more water per degree of cooling. Stull's (2011) closed form
    is both a sea-level fit and a least-squares fit that degrades in the cold,
    dry corner; over the conditions here it reads 0.4-0.7 C colder than this
    solution, which would over-count snowmaking hours. `stull_wet_bulb_c` is
    kept alongside so the comparison can be reported rather than asserted -
    METHODS section 22 does that.
    """
    t = np.asarray(t_c, dtype="float64")
    rh = np.clip(np.asarray(rh_pct, dtype="float64"), 1.0, 100.0)
    p = np.asarray(p_hpa, dtype="float64")
    e = saturation_vapour_pressure_hpa(t) * rh / 100.0
    lo, hi = t - 50.0, t.copy()
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        f = saturation_vapour_pressure_hpa(mid) - e - psychrometric_const * p * (t - mid)
        too_cold = f < 0                      # e_s(mid) too low -> Tw is higher
        lo = np.where(too_cold, mid, lo)
        hi = np.where(too_cold, hi, mid)
    return 0.5 * (lo + hi)


def stull_wet_bulb_c(t_c, rh_pct):
    """Stull (2011) closed-form wet bulb, a sea-level fit. For comparison only."""
    t = np.asarray(t_c, dtype="float64")
    rh = np.clip(np.asarray(rh_pct, dtype="float64"), 5.0, 99.0)
    return (t * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
            + np.arctan(t + rh) - np.arctan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh) - 4.686035)


def at_elevation(df: pd.DataFrame, target_m: float, cell_m: float,
                 lapse_c_per_km: float, offset_c: float = 0.0) -> pd.DataFrame:
    """Move the cell's hourly temperature to a target elevation, explicitly.

    Temperature is shifted by `lapse_c_per_km`, pressure by the hypsometric
    formula, and **relative humidity is carried across unchanged** - an
    assumption, not a measurement. `offset_c` is the sensitivity handle: the
    whole series is shifted by it so the reader can see how much a wrong lapse
    rate moves the answer.

    This is a fixed gradient applied to a 9 km reanalysis cell. It is not a
    measured local lapse rate, and winter inversions in the Almaty valley break
    it. METHODS section 22 says so, and names what would replace it.
    """
    dz_km = (target_m - cell_m) / 1000.0
    out = df.copy()
    out["elevation_m"] = target_m
    out["temperature_2m"] = df["temperature_2m"] - lapse_c_per_km * dz_km + offset_c
    # hypsometric: p2 = p1 * exp(-g*dz / (R*Tbar)), Tbar in kelvin
    tbar = 0.5 * (df["temperature_2m"] + out["temperature_2m"]) + 273.15
    out["surface_pressure"] = df["surface_pressure"] * np.exp(
        -9.80665 * (target_m - cell_m) / (287.05 * tbar))
    out["wet_bulb_c"] = wet_bulb_c(out["temperature_2m"], out["relative_humidity_2m"],
                                   out["surface_pressure"])
    return out


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
    # DOCS is absolute (config derives it from __file__), so this is the same
    # path whichever study area is active. Deriving it by walking up from
    # INTERIM is not: that path depends on which area is active.
    path = path or (DOCS / "seasonal_outlooks.json")
    json.dump(SEASONAL_OUTLOOKS, open(path, "w"), indent=1, ensure_ascii=False)
    return str(path)
