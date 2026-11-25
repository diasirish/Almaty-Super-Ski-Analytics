"""Snow frequency, observation coverage and melt-out intervals from S2 daily masks."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np

from config import MIN_SEASONS_MULTIYEAR, MIN_VALID_OBS, SEASONS


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def season_of(day: date) -> str | None:
    for name, (s, e) in SEASONS.items():
        if _d(s) <= day <= _d(e):
            return name
    return None


def select_days(days: list[dict], start: str | None = None, end: str | None = None,
                month_day_window: tuple[str, str] | None = None,
                shift_days: int = 0, seasons: list[str] | None = None) -> list[dict]:
    """Filter daily observations by absolute range or by a calendar window.

    `month_day_window` is ("MM-DD", "MM-DD") applied inside every season; a
    positive `shift_days` moves the window later in the calendar.
    """
    out = []
    for rec in days:
        day = _d(rec["date"])
        sname = season_of(day)
        if seasons is not None and sname not in seasons:
            continue
        if start and day < _d(start):
            continue
        if end and day > _d(end):
            continue
        if month_day_window is not None:
            m0, m1 = month_day_window
            y = day.year
            w0 = _d(f"{y}-{m0}") + timedelta(days=shift_days)
            w1 = _d(f"{y}-{m1}") + timedelta(days=shift_days)
            if not (w0 <= day <= w1):
                continue
        out.append(rec)
    return sorted(out, key=lambda r: r["date"])


def snow_frequency(days: list[dict], equal_season_weight: bool = True,
                   min_valid: int = MIN_VALID_OBS,
                   min_seasons: int | None = None) -> dict:
    """Per-pixel snow detection frequency over a set of daily observations.

    With `equal_season_weight` each season contributes equally, so a season with
    many clear dates cannot dominate the mean.
    """
    if not days:
        raise ValueError("no days selected")
    shape = days[0]["valid"].shape
    by_season: dict[str, dict] = {}
    for rec in days:
        sname = season_of(_d(rec["date"])) or "other"
        acc = by_season.setdefault(
            sname, {"valid": np.zeros(shape, "int16"),
                    "snow": np.zeros(shape, "int16"), "dates": []})
        acc["valid"] += rec["valid"].astype("int16")
        acc["snow"] += (rec["snow"] & rec["valid"]).astype("int16")
        acc["dates"].append(rec["date"])

    valid_total = np.zeros(shape, "int16")
    snow_total = np.zeros(shape, "int16")
    n_seasons = np.zeros(shape, "int8")
    weighted = np.zeros(shape, "float64")
    for sname, acc in by_season.items():
        valid_total += acc["valid"]
        snow_total += acc["snow"]
        has = acc["valid"] > 0
        n_seasons += has.astype("int8")
        with np.errstate(invalid="ignore", divide="ignore"):
            f = np.where(has, acc["snow"] / np.maximum(acc["valid"], 1), 0.0)
        weighted += f * has

    with np.errstate(invalid="ignore", divide="ignore"):
        freq_season = np.where(n_seasons > 0, weighted / np.maximum(n_seasons, 1), np.nan)
        freq_pooled = np.where(valid_total > 0,
                               snow_total / np.maximum(valid_total, 1), np.nan)

    freq = freq_season if equal_season_weight else freq_pooled
    ok = valid_total >= min_valid
    if min_seasons is not None:
        ok &= n_seasons >= min_seasons
    freq = np.where(ok, freq, np.nan).astype("float32")

    return {
        "frequency": freq,
        "frequency_pooled": np.where(ok, freq_pooled, np.nan).astype("float32"),
        "n_valid": valid_total.astype("int16"),
        "n_snow": snow_total.astype("int16"),
        "n_seasons": n_seasons,
        "coverage": float(ok.mean()),
        "n_dates": len(days),
        "dates": [r["date"] for r in days],
        "seasons": sorted(by_season),
        "seasons_dates": {k: v["dates"] for k, v in by_season.items()},
        "min_valid": min_valid,
        "min_seasons": min_seasons,
        "equal_season_weight": equal_season_weight,
    }


def meltout_interval(days: list[dict], season: str) -> dict:
    """Bracket the snow disappearance date per pixel within one season.

    Returns the last day-of-year with a snow detection, the first later snow-free
    valid observation, the interval midpoint and its width. Pixels without both
    bounds are left unestimated (NaN).
    """
    s, e = SEASONS[season]
    sel = sorted([r for r in days if _d(s) <= _d(r["date"]) <= _d(e)],
                 key=lambda r: r["date"])
    if not sel:
        raise ValueError(f"no observations in season {season}")
    shape = sel[0]["valid"].shape
    origin = _d(s)

    last_snow = np.full(shape, np.nan, "float32")
    first_free = np.full(shape, np.nan, "float32")
    n_valid = np.zeros(shape, "int16")

    for rec in sel:
        t = float((_d(rec["date"]) - origin).days)
        v = rec["valid"].astype(bool)
        sn = rec["snow"].astype(bool) & v
        n_valid += v.astype("int16")
        last_snow = np.where(sn, t, last_snow)
        # a snow-free valid observation resets the "first free after snow" marker
        free = v & ~sn
        first_free = np.where(free & (~np.isnan(last_snow)) &
                              (np.isnan(first_free) | (first_free < last_snow)),
                              t, first_free)

    has_both = (~np.isnan(last_snow)) & (~np.isnan(first_free)) & (first_free > last_snow)
    mid = np.where(has_both, (last_snow + first_free) / 2.0, np.nan).astype("float32")
    width = np.where(has_both, first_free - last_snow, np.nan).astype("float32")
    return {
        "season": season, "origin": s,
        "last_snow_day": np.where(has_both, last_snow, np.nan).astype("float32"),
        "first_snowfree_day": np.where(has_both, first_free, np.nan).astype("float32"),
        "meltout_mid_day": mid, "interval_width_days": width,
        "n_valid": n_valid, "n_dates": len(sel),
        "estimated_fraction": float(has_both.mean()),
    }


def season_span(days: list[dict], season: str) -> dict:
    """Bracket the whole snow season per pixel, and count how often it broke.

    `meltout_interval` brackets one end. This brackets both and reports what
    happened in between, because "will there be enough snow on the pistes" is a
    question about the length of cover and its continuity, not about the date it
    vanished.

    Per pixel, from the valid observations of one season:

    * `first_snow_day`, `last_snow_day` - the observed extent of snow cover
    * `onset_bracket_days` - gap between the last snow-free look before the
      first snow look; `meltout_bracket_days`, the same on the other side
    * `span_days` = last_snow_day - first_snow_day, the **observed** span. It is
      not an interpolated count of snow-covered days: with ~28 looks a season,
      that interpolation would invent days nobody saw
    * `breaks` - snow-free valid observations *inside* the span. This is the
      continuity measure: a span of 150 days with 4 breaks is not a season
    * `left_censored` / `right_censored` - no snow-free look exists before the
      first, or after the last, snow detection, so the real season starts
      earlier or ends later than the record can show. At the top of this site
      that is the normal case in spring and must be reported, not averaged in
    """
    s, e = SEASONS[season]
    sel = sorted([r for r in days if _d(s) <= _d(r["date"]) <= _d(e)],
                 key=lambda r: r["date"])
    if not sel:
        raise ValueError(f"no observations in season {season}")
    shape = sel[0]["valid"].shape
    origin = _d(s)
    offs = [float((_d(r["date"]) - origin).days) for r in sel]

    nan = lambda: np.full(shape, np.nan, "float32")
    first_snow, last_snow = nan(), nan()
    n_valid = np.zeros(shape, "int16")
    n_snow = np.zeros(shape, "int16")

    for t_off, rec in zip(offs, sel):                       # pass 1: snow extent
        v = rec["valid"].astype(bool)
        sn = rec["snow"].astype(bool) & v
        n_valid += v.astype("int16")
        n_snow += sn.astype("int16")
        first_snow = np.where(sn & np.isnan(first_snow), t_off, first_snow)
        last_snow = np.where(sn, t_off, last_snow)

    last_free_before, first_free_after = nan(), nan()
    breaks = np.zeros(shape, "int16")
    snow_in_span = np.zeros(shape, "int16")
    for t_off, rec in zip(offs, sel):                       # pass 2: edges and gaps
        v = rec["valid"].astype(bool)
        sn = rec["snow"].astype(bool) & v
        free = v & ~sn
        before = free & (t_off < first_snow)
        last_free_before = np.where(before, t_off, last_free_before)
        after = free & (t_off > last_snow) & np.isnan(first_free_after)
        first_free_after = np.where(after, t_off, first_free_after)
        inside = (t_off > first_snow) & (t_off < last_snow)
        breaks += (free & inside).astype("int16")
        snow_in_span += (sn & inside).astype("int16")

    has = ~np.isnan(first_snow)
    span = np.where(has, last_snow - first_snow, np.nan).astype("float32")
    with np.errstate(invalid="ignore", divide="ignore"):
        continuity = np.where(has & ((snow_in_span + breaks) > 0),
                              snow_in_span / np.maximum(snow_in_span + breaks, 1),
                              np.nan).astype("float32")
    return {
        "season": season, "origin": s, "n_dates": len(sel),
        "first_snow_day": first_snow, "last_snow_day": last_snow,
        "onset_bracket_days": np.where(has, first_snow - last_free_before,
                                       np.nan).astype("float32"),
        "meltout_bracket_days": np.where(has, first_free_after - last_snow,
                                         np.nan).astype("float32"),
        "span_days": span, "breaks": breaks, "continuity": continuity,
        "left_censored": has & np.isnan(last_free_before),
        "right_censored": has & np.isnan(first_free_after),
        "n_valid": n_valid, "n_snow": n_snow,
        "has_snow": has,
        "estimated_fraction": float(has.mean()),
    }


def day_to_date(day_offset: float, origin: str) -> str:
    return (_d(origin) + timedelta(days=float(day_offset))).isoformat()

def coverage_bias(days: list[dict], layers: dict, months=None,
                  min_valid: int = MIN_VALID_OBS):
    """Is the set of pixels that qualify for a snow map a fair sample of the area?

    A pixel enters a snow-frequency map only once it has at least `min_valid`
    cloud- and shadow-free observations. Steep, shaded ground fails that test
    more often than open, sunlit ground, so the pixels that do qualify can be
    systematically sunnier and gentler than the terrain as a whole - and in a
    mid-winter month, where valid observations are scarcest, that skew lands
    exactly on the quantity being measured. This reports its size rather than
    leaving it implicit: for each month it gives the share of the area that
    qualifies and the median of each supplied layer over the qualifying pixels
    against its median over the whole area.
    """
    import pandas as pd
    months = months or [11, 12, 1, 2, 3, 4]
    rows = []
    for m in months:
        sel = [d for d in days if int(d["date"][5:7]) == m]
        if not sel:
            continue
        r = snow_frequency(sel, min_valid=min_valid)
        ok = np.isfinite(r["frequency"])
        rec = {"month": m, "n_dates": r["n_dates"], "n_seasons": len(r["seasons"]),
               "qualifying_share": round(float(ok.mean()), 4),
               "median_valid_obs": int(np.median(r["n_valid"]))}
        for lab, arr in layers.items():
            a = np.asarray(arr, dtype="float64")
            allv = a[np.isfinite(a)]
            selv = a[ok & np.isfinite(a)]
            if not allv.size or not selv.size:
                continue
            rec[f"{lab}__qualifying"] = round(float(np.median(selv)), 2)
            rec[f"{lab}__whole_area"] = round(float(np.median(allv)), 2)
            rec[f"{lab}__skew"] = round(float(np.median(selv) - np.median(allv)), 2)
        rows.append(rec)
    return pd.DataFrame(rows)
