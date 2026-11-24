import sys, json, time
sys.path.insert(0, '.')
from config import INTERIM, SEASONS, CURRENT_SEASON, AREA
from grids import S2_GRID
from alt_sources import landsat_scenes, fetch_landsat_all
import datetime

f = INTERIM / "landsat_records.json"
if not f.exists():
    recs = []
    for name, (s, e) in SEASONS.items():
        r = landsat_scenes(s, e)
        print(f"  {name}: {len(r)} Landsat 8/9 scenes", flush=True)
        recs += r
    cname, cs, ce = CURRENT_SEASON
    r = landsat_scenes(cs, min(ce, datetime.date.today().isoformat()))
    print(f"  {cname}: {len(r)} scenes", flush=True)
    recs += r
    json.dump(recs, open(f, "w"), indent=1)
recs = json.load(open(f))
print(f"area={AREA}  {len(recs)} Landsat records, grid {S2_GRID.shape}", flush=True)
t0 = time.time()
res = fetch_landsat_all(recs, grid=S2_GRID, workers=6, verbose=True)
print(f"\nOK: {len(res['scenes'])}  FAILED: {len(res['failed'])}  [{time.time()-t0:.0f}s]")
for x in res["failed"][:20]:
    print("  FAIL", x["date"], x["scene_id"], x["error"][:100])
json.dump(res["failed"], open(INTERIM / "landsat_failures.json", "w"), indent=1)
