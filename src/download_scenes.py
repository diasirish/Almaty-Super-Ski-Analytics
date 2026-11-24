import sys, json, time
sys.path.insert(0, '.')
from config import INTERIM, AREA, AREA_LABEL
from grids import S2_GRID
from s2 import fetch_all, search_scenes, grid_tag
from config import SEASONS, CURRENT_SEASON
import datetime

rec_file = INTERIM / "stac_records.json"
if not rec_file.exists():
    print(f"searching STAC for {AREA}: {AREA_LABEL}", flush=True)
    allrec = {}
    for name, (s, e) in SEASONS.items():
        allrec[name] = search_scenes(s, e)
        print(f"  {name}: {len(allrec[name])} scenes", flush=True)
    cname, cs, ce = CURRENT_SEASON
    allrec[cname] = search_scenes(cs, min(ce, datetime.date.today().isoformat()))
    print(f"  {cname}: {len(allrec[cname])} scenes", flush=True)
    rec_file.parent.mkdir(parents=True, exist_ok=True)
    json.dump(allrec, open(rec_file, "w"), indent=1)

recs = json.load(open(rec_file))
flat = [r for v in recs.values() for r in v]
print(f"area={AREA}  grid={S2_GRID.shape} tag={grid_tag(S2_GRID)}", flush=True)
print(f"total scene records: {len(flat)}", flush=True)
t0 = time.time()
res = fetch_all(flat, workers=8, verbose=True, grid=S2_GRID)
print(f"\nOK: {len(res['scenes'])}  FAILED: {len(res['failed'])}  [{time.time()-t0:.0f}s]")
for f in res['failed']:
    print("  FAIL", f['date'], f['scene_id'], f['error'][:120])
json.dump(res['failed'], open(INTERIM / "download_failures.json", "w"), indent=1)
