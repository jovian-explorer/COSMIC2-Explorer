"""Inspect sample granules."""
import sys
sys.path.insert(0, 'backend')
from cosmic2.config import sampledata_dir
from cosmic2 import readers

d = sampledata_dir()
for p in list(d.iterdir())[:10]:
    if not (p.name.endswith('_nc') or p.suffix == '.nc'):
        continue
    parsed = readers.parse_filename(p.name)
    prod = parsed['product']
    if not prod:
        continue
    g = readers.load(str(p), prod)
    nlev = g.meta['n_levels']
    good = g.meta['good']
    print(f"{p.name[:50]} product={prod} vertical={g.vertical} n_levels={nlev} good={good}")
    print(f"  data keys: {list(g.data.keys())[:8]}")
    if 'Temp' in g.data:
        t = g.data['Temp']
        import numpy as np
        print(f"  Temp: {np.nanmin(t):.1f} to {np.nanmax(t):.1f} C, {np.isfinite(t).sum()} valid")
