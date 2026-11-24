"""Direct sunshine duration on real terrain, and when the sun is actually on it.

Energy (kWh/m2) and duration (hours of direct sun) answer different questions.
A north slope in December can receive a little diffuse energy all day and never
once see the sun; a skier cares about the second number.

A pixel counts as sunlit at an instant when all three hold:
  * the sun is above the astronomical horizon,
  * the sun is above the ray-marched terrain horizon at its azimuth,
  * the slope faces the sun (cos of the incidence angle > 0).
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd
import pvlib

from config import SUN_HOUR_STEP_MIN, SUN_MIN_ELEVATION_DEG, TIMEZONE
from insolation import _horizon_at


def _solar_track(start: str, end: str, lat: float, lon: float, alt: float,
                 step_min: int):
    t0 = pd.Timestamp(start, tz=TIMEZONE)
    t1 = pd.Timestamp(end, tz=TIMEZONE) + pd.Timedelta(days=1)
    edges = pd.date_range(t0, t1, freq=f"{step_min}min", inclusive="left")
    times = edges + pd.Timedelta(minutes=step_min / 2)
    sp = pvlib.solarposition.get_solarposition(times, lat, lon, altitude=alt)
    return times, sp["apparent_elevation"].to_numpy(), sp["azimuth"].to_numpy()


def sunshine_hours(start: str, end: str, t: dict, lat: float, lon: float,
                   step_min: int = SUN_HOUR_STEP_MIN,
                   min_elev: float = SUN_MIN_ELEVATION_DEG,
                   by_month: bool = True, masks: dict | None = None,
                   verbose: bool = False) -> dict:
    """Direct sunshine duration per pixel over [start, end] inclusive.

    `masks` maps a label to a boolean raster; for each one the function also
    returns a month x hour-of-day table of the mean sunlit fraction, which is
    what "when is the sun on this terrain" actually means.
    """
    slope = np.nan_to_num(t["slope"], nan=0.0)
    aspect = np.nan_to_num(t["aspect"], nan=0.0)
    cos_b = np.cos(np.radians(slope))
    sin_b = np.sin(np.radians(slope))
    asp = np.radians(aspect)
    azimuths, horizon = t["azimuths"], t["horizon"]
    shape = slope.shape

    times, elev, az = _solar_track(start, end, lat, lon,
                                   float(np.nanmean(t["dem"])), step_min)
    hours_per_step = step_min / 60.0

    total = np.zeros(shape, dtype="float32")
    months: dict[int, np.ndarray] = {}
    masks = masks or {}
    prof = {k: {} for k in masks}          # label -> (month, hour) -> [sum, n]

    day_idx = np.nonzero(elev > min_elev)[0]
    for n, i in enumerate(day_idx):
        sun_el = float(elev[i])
        sun_az = float(az[i])
        zen = np.radians(90.0 - sun_el)
        cos_aoi = (np.cos(zen) * cos_b
                   + np.sin(zen) * sin_b * np.cos(np.radians(sun_az) - asp))
        lit = (sun_el > _horizon_at(azimuths, horizon, sun_az)) & (cos_aoi > 0)

        total += lit * hours_per_step
        if by_month:
            m = times[i].month
            if m not in months:
                months[m] = np.zeros(shape, dtype="float32")
            months[m] += lit * hours_per_step
        for label, mk in masks.items():
            key = (times[i].month, times[i].hour)
            acc = prof[label].setdefault(key, [0.0, 0])
            acc[0] += float(lit[mk].mean()) if mk.any() else 0.0
            acc[1] += 1
        if verbose and n % 2000 == 0:
            print(f"    sun step {n}/{len(day_idx)}", flush=True)

    tables = {}
    for label, d in prof.items():
        rows = [{"month": m, "hour": h, "sunlit_fraction": round(v[0] / v[1], 4),
                 "n_steps": v[1]} for (m, h), v in sorted(d.items())]
        tables[label] = pd.DataFrame(rows)

    return {"hours": total, "hours_by_month": months, "profiles": tables,
            "meta": {"start": start, "end": end, "step_min": step_min,
                     "min_sun_elevation_deg": min_elev,
                     "daylight_steps": int(len(day_idx)),
                     "definition": "sun above the astronomical horizon, above the "
                                   "ray-marched terrain horizon, and in front of "
                                   "the slope plane"}}


def monthly_sun_hours(year: int, months: list[int], t: dict, lat: float, lon: float,
                      step_min: int = SUN_HOUR_STEP_MIN,
                      masks: dict | None = None) -> tuple[dict, pd.DataFrame]:
    """Sunshine hours for a list of calendar months, plus a summary table."""
    out, rows = {}, []
    for m in months:
        last = calendar.monthrange(year, m)[1]
        r = sunshine_hours(f"{year}-{m:02d}-01", f"{year}-{m:02d}-{last:02d}",
                           t, lat, lon, step_min=step_min, by_month=False,
                           masks=masks)
        out[m] = r
        h = r["hours"]
        rows.append({"year": year, "month": m, "month_name": calendar.month_name[m],
                     "days": last,
                     "median_sun_hours": round(float(np.nanmedian(h)), 1),
                     "mean_sun_hours": round(float(np.nanmean(h)), 1),
                     "p95_sun_hours": round(float(np.nanpercentile(h, 95)), 1),
                     "max_sun_hours": round(float(np.nanmax(h)), 1),
                     "median_hours_per_day": round(float(np.nanmedian(h)) / last, 2)})
    return out, pd.DataFrame(rows)


def top_points(arr: np.ndarray, grid, n: int = 10, mask: np.ndarray | None = None,
               min_separation_m: float = 400.0, extra: dict | None = None):
    """The n highest-valued pixels, thinned so they are not all one hilltop."""
    from pyproj import Transformer
    a = np.where(np.isfinite(arr), arr, -np.inf)
    if mask is not None:
        a = np.where(mask, a, -np.inf)
    order = np.argsort(a, axis=None)[::-1]
    tr = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
    picks, rows = [], []
    for flat in order:
        if len(picks) >= n:
            break
        r, c = np.unravel_index(flat, a.shape)
        if not np.isfinite(a[r, c]) or a[r, c] == -np.inf:
            break
        x = grid.xmin + (c + 0.5) * grid.res
        y = grid.ymax - (r + 0.5) * grid.res
        if any(np.hypot(x - px, y - py) < min_separation_m for px, py in picks):
            continue
        picks.append((x, y))
        lon, lat = tr.transform(x, y)
        rec = {"rank": len(picks), "lon": round(float(lon), 5),
               "lat": round(float(lat), 5), "easting": round(x, 1),
               "northing": round(y, 1), "value": round(float(arr[r, c]), 2)}
        if extra:
            for k, v in extra.items():
                rec[k] = (round(float(v[r, c]), 2) if np.isfinite(v[r, c])
                          else None)
        rows.append(rec)
    return pd.DataFrame(rows)


def best_window(profile: pd.DataFrame, snow_by_month: dict[int, float],
                min_sunlit: float = 0.5) -> pd.DataFrame:
    """Join the sunlit-fraction profile to monthly snow frequency.

    The score is simply sunlit_fraction x snow_frequency: the share of the target
    terrain that is, at that hour in that month, both sunlit and (on the satellite
    record) usually snow-covered. It is a screening index, not a forecast.
    """
    df = profile.copy()
    df["snow_frequency"] = df["month"].map(snow_by_month)
    df["sun_and_snow"] = (df["sunlit_fraction"] * df["snow_frequency"]).round(4)
    df["meets_sun_threshold"] = df["sunlit_fraction"] >= min_sunlit
    return df
