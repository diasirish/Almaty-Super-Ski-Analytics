"""Clear-sky insolation on real terrain.

Direct beam is shaded by the ray-marched terrain horizon and by the slope itself.
Diffuse is isotropic, scaled by the Dozier & Frew sky view factor. Terrain-reflected
irradiance uses a (1 - SVF) configuration factor and a fixed seasonal albedo.
All three assumptions are stated in METHODS.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib

from config import GROUND_ALBEDO, TIME_STEP_MIN, TIMEZONE


def clearsky_levels(times: pd.DatetimeIndex, lat: float, lon: float,
                    altitudes: np.ndarray) -> dict:
    """Ineichen/Perez clear-sky DNI, DHI, GHI at a set of altitude levels."""
    linke = pvlib.clearsky.lookup_linke_turbidity(times, lat, lon)
    solpos = pvlib.solarposition.get_solarposition(
        times, lat, lon, altitude=float(np.mean(altitudes)))
    app_zen = solpos["apparent_zenith"].to_numpy()
    az = solpos["azimuth"].to_numpy()
    elev = solpos["apparent_elevation"].to_numpy()

    dni = np.zeros((len(altitudes), len(times)))
    dhi = np.zeros_like(dni)
    ghi = np.zeros_like(dni)
    for i, alt in enumerate(altitudes):
        pressure = pvlib.atmosphere.alt2pres(alt)
        am = pvlib.atmosphere.get_relative_airmass(app_zen)
        am_abs = pvlib.atmosphere.get_absolute_airmass(am, pressure)
        cs = pvlib.clearsky.ineichen(
            app_zen, am_abs, linke, altitude=float(alt),
            dni_extra=pvlib.irradiance.get_extra_radiation(times).to_numpy(),
        )
        dni[i] = np.nan_to_num(cs["dni"].to_numpy())
        dhi[i] = np.nan_to_num(cs["dhi"].to_numpy())
        ghi[i] = np.nan_to_num(cs["ghi"].to_numpy())
    return dict(times=times, azimuth=az, elevation=elev, zenith=app_zen,
                altitudes=np.asarray(altitudes), dni=dni, dhi=dhi, ghi=ghi,
                linke_mean=float(np.mean(linke)))


def _elev_weights(elevation: np.ndarray, levels: np.ndarray):
    """Pre-compute per-pixel linear interpolation weights in the altitude axis."""
    e = np.clip(np.nan_to_num(elevation, nan=float(np.nanmean(elevation))),
                levels[0], levels[-1])
    idx = np.clip(np.searchsorted(levels, e, side="right") - 1, 0, len(levels) - 2)
    lo = levels[idx]
    hi = levels[idx + 1]
    w = (e - lo) / np.maximum(hi - lo, 1e-9)
    return idx.astype("int16"), w.astype("float32")


def _horizon_at(azimuths: np.ndarray, horizon: np.ndarray, sun_az: float) -> np.ndarray:
    """Linear interpolation of the horizon surface at one solar azimuth."""
    n = len(azimuths)
    step = 360.0 / n
    pos = (sun_az % 360.0) / step
    i0 = int(np.floor(pos)) % n
    i1 = (i0 + 1) % n
    f = pos - np.floor(pos)
    return horizon[i0] * (1.0 - f) + horizon[i1] * f


def accumulate_insolation(start: str, end: str, elevation: np.ndarray,
                          slope: np.ndarray, aspect: np.ndarray,
                          svf: np.ndarray, azimuths: np.ndarray,
                          horizon: np.ndarray, lat: float, lon: float,
                          albedo: float = GROUND_ALBEDO,
                          step_min: int = TIME_STEP_MIN,
                          n_levels: int = 7, verbose: bool = True) -> dict:
    """Integrate plane-of-array clear-sky irradiance over [start, end] inclusive.

    Returns kWh/m^2 rasters for total, direct, diffuse and reflected components,
    plus the number of shaded daylight steps per pixel.
    """
    t0 = pd.Timestamp(start, tz=TIMEZONE)
    t1 = pd.Timestamp(end, tz=TIMEZONE) + pd.Timedelta(days=1)
    edges = pd.date_range(t0, t1, freq=f"{step_min}min", inclusive="left")
    times = edges + pd.Timedelta(minutes=step_min / 2)      # interval mid-points

    valid_elev = elevation[np.isfinite(elevation)]
    levels = np.linspace(float(valid_elev.min()), float(valid_elev.max()), n_levels)
    cs = clearsky_levels(times, lat, lon, levels)

    idx, w = _elev_weights(elevation, levels)
    cos_b = np.cos(np.radians(np.nan_to_num(slope, nan=0.0)))
    sin_b = np.sin(np.radians(np.nan_to_num(slope, nan=0.0)))
    asp = np.radians(np.nan_to_num(aspect, nan=0.0))

    hours = step_min / 60.0
    shp = elevation.shape
    direct = np.zeros(shp, dtype="float64")
    diffuse = np.zeros(shp, dtype="float64")
    reflected = np.zeros(shp, dtype="float64")
    shaded_steps = np.zeros(shp, dtype="int32")
    daylight_steps = 0

    day = cs["elevation"] > 0.5
    n_day = int(day.sum())
    done = 0
    for t in np.nonzero(day)[0]:
        sun_el = float(cs["elevation"][t])
        sun_az = float(cs["azimuth"][t])
        zen = np.radians(90.0 - sun_el)

        dni = cs["dni"][idx, t] * (1 - w) + cs["dni"][idx + 1, t] * w
        dhi = cs["dhi"][idx, t] * (1 - w) + cs["dhi"][idx + 1, t] * w
        ghi = cs["ghi"][idx, t] * (1 - w) + cs["ghi"][idx + 1, t] * w

        cos_aoi = (np.cos(zen) * cos_b
                   + np.sin(zen) * sin_b * np.cos(np.radians(sun_az) - asp))
        hz = _horizon_at(azimuths, horizon, sun_az)
        lit = (sun_el > hz) & (cos_aoi > 0)

        direct += np.where(lit, dni * cos_aoi, 0.0) * hours
        diffuse += dhi * svf * hours
        reflected += ghi * albedo * (1.0 - svf) * hours
        shaded_steps += (~lit).astype("int32")
        daylight_steps += 1
        done += 1
        if verbose and done % 500 == 0:
            print(f"    insolation step {done}/{n_day}", flush=True)

    out = {k: (v / 1000.0).astype("float32")
           for k, v in dict(direct=direct, diffuse=diffuse, reflected=reflected).items()}
    out["total"] = (out["direct"] + out["diffuse"] + out["reflected"]).astype("float32")
    out["shaded_fraction"] = (shaded_steps / max(daylight_steps, 1)).astype("float32")
    out["meta"] = dict(start=start, end=end, step_min=step_min,
                       daylight_steps=daylight_steps, albedo=albedo,
                       linke_mean=round(cs["linke_mean"], 3),
                       altitude_levels=[round(float(x), 1) for x in levels],
                       model="pvlib Ineichen-Perez clear sky")
    return out
