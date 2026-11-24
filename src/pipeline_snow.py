"""Load cached S2 windows, build daily observations, derive snow products."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (CURRENT_SEASON, INTERIM, MIN_SEASONS_MULTIYEAR, MIN_VALID_OBS,
                    OUT_TAB, SEASONS, SPRING_SHIFT_DAYS, SPRING_WINDOW)
from s2 import fetch_all, merge_same_date


def load_days(verbose: bool = True):
    recs = json.load(open(INTERIM / "stac_records.json"))
    flat = [r for v in recs.values() for r in v]
    res = fetch_all(flat, verbose=verbose)
    scenes = res["scenes"]
    manifest = pd.DataFrame([s["meta"] for s in scenes])
    days = merge_same_date(scenes)
    return days, manifest, res["failed"]


def historical_days(days):
    """Observations inside the four completed seasons only."""
    from snow import season_of, _d
    return [d for d in days if season_of(_d(d["date"])) is not None]


def current_season_days(days):
    name, s, e = CURRENT_SEASON
    return [d for d in days if s <= d["date"] <= e]


def coverage_table(days_by_label: dict, min_valid=MIN_VALID_OBS) -> pd.DataFrame:
    from snow import snow_frequency
    rows = []
    for label, dl in days_by_label.items():
        if not dl:
            rows.append({"period": label, "n_dates": 0, "coverage_min4": np.nan})
            continue
        r = snow_frequency(dl, min_valid=min_valid)
        rows.append({
            "period": label,
            "n_dates": r["n_dates"],
            "n_seasons": len(r["seasons"]),
            "median_valid_obs_per_pixel": int(np.median(r["n_valid"])),
            "coverage_min4": round(r["coverage"], 4),
            "first_date": min(r["dates"]), "last_date": max(r["dates"]),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    days, manifest, failed = load_days()
    print(f"scenes: {len(manifest)}, unique dates: {len(days)}, failed: {len(failed)}")
    manifest.to_csv(OUT_TAB / "scene_manifest.csv", index=False)

    hist = historical_days(days)
    cur = current_season_days(days)
    print(f"historical dates: {len(hist)}  current-season dates: {len(cur)}")

    from snow import select_days, snow_frequency, meltout_interval

    labels = {}
    for s in SEASONS:
        labels[f"season {s.replace('_','/')}"] = select_days(hist, seasons=[s])
    labels["Mar-Apr 2023 (pilot check)"] = select_days(
        hist, start="2023-03-01", end="2023-04-30")
    labels["spring window, 4 seasons"] = select_days(
        hist, month_day_window=SPRING_WINDOW)
    print(coverage_table(labels).to_string(index=False))
