"""Use COSMIC-2 Explorer's readers and diagnostics from Python, no window.

    python examples/headless.py                 # the bundled example files
    python examples/headless.py path/to/folder  # your own CDAAC files

Prints each profile's time, place and tropopause, the mean wetPf2
temperature profile, and writes the profiles to a CSV in the app's exports
folder (set COSMIC2_EXPLORER_HOME to put it elsewhere).
"""
import sys
from pathlib import Path

from cosmic2 import analysis, exporters, readers
from cosmic2.config import sampledata_dir

folder = Path(sys.argv[1]) if len(sys.argv) > 1 else sampledata_dir()
rows = []
for path in sorted(folder.iterdir()):
    meta, error = readers.quick_meta_safe((str(path), None))
    if meta is None:
        print(f"skipped {path.name}: {error}")
        continue
    rows.append(meta)

for r in rows:
    if r["product"] not in ("atmPrf", "wetPf2"):
        continue
    g = readers.load(r["path"])              # all variables as numpy arrays
    trop = analysis.diagnostics(g)["tropopause"]
    where = f"{r['lat']:6.1f} {r['lon']:7.1f}"
    height = f"{trop['height_km']:.1f} km" if trop["found"] else "none"
    print(f"{r['product']} {r['time_utc']} {where}  tropopause {height}")

wet = [(r["path"], r) for r in rows if r["product"] == "wetPf2"]
if wet:
    comp = analysis.composite(wet, "Temp", top_km=30, step_km=1, min_count=1,
                               convert_kelvin=True)
    mean = comp.groups["all"]["mean"]
    for z, t in list(zip(comp.grid, mean))[::5]:
        if t == t:                           # NaN below the lowest profile
            print(f"{z:4.0f} km  {t:6.1f} K")

out = exporters.export_profiles_csv(rows, basename="headless_example")
print("wrote", out["path"])
