"""Verify profile plot data integrity."""
import urllib.request, json

BASE = "http://127.0.0.1:8991"

def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())

# Load samples
post("/api/local/load-samples", {})

# Search
d = post("/api/profiles/search", {"good_only": False, "limit": 8})
granules = d["granules"]
print("Granules:", len(granules))

# Required fields
required = ["id","file_name","product","lat","lon","local_time","sat","occ_prn","n_levels","alt_max","good","time_utc"]
for g in granules:
    for f in required:
        if f not in g:
            print(f"MISSING in search: {f}")

# Test plot profiles
ids = [g["id"] for g in granules[:3]]
plot = post("/api/plot/profiles", {"granule_ids": ids, "field": "Temp", "vertical": "MSL_alt"})
print("Plot series:", len(plot["series"]), "skipped:", len(plot.get("skipped", [])))
print("field_label:", plot.get("field_label"))
print("vertical_label:", plot.get("vertical_label"))
if plot["series"]:
    s = plot["series"][0]
    nones_x = sum(1 for v in s["x"] if v is None)
    nones_y = sum(1 for v in s["y"] if v is None)
    print(f"x: {len(s['x'])} pts, {nones_x} None; y: {len(s['y'])} pts, {nones_y} None")
    print(f"lat={s['lat']}, local_time={s['local_time']}, good={s['good']}")

# Test composite with all group-by options
for gb in ["all", "lat_band", "hemisphere", "day_night", "date", "product", "satellite"]:
    res = post("/api/composite", {
        "search": {"good_only": False, "limit": 8},
        "field": "Temp", "vertical": "MSL_alt", 
        "group_by": gb, "convert_kelvin": False,
    })
    print(f"composite group_by={gb}: {len(res.get('groups', {}))} groups, n_profiles={res.get('n_profiles')}")

# Test diagnostics table
diag = post("/api/diagnostics/table", {"search": {"good_only": False, "limit": 8}})
print(f"diag_table: n={diag['n']}, columns={len(diag['columns'])}")
cols = diag["columns"]
# Check scatter x/y defaults
print("lat in columns:", "lat" in cols)
print("tropopause.height_km in columns:", "tropopause.height_km" in cols)
print("local_time in columns:", "local_time" in cols)

# Test exports
exports = get("/api/exports")
print("exports:", len(exports["exports"]))

print("\nAll checks done.")
