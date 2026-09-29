"""Static analysis: cross-check element IDs between HTML and JS."""
import re, os

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend = os.path.join(base, "frontend")

with open(os.path.join(frontend, "index.html")) as f:
    html = f.read()

ids_defined = set(re.findall(r'id="([^"]+)"', html))
print("IDs defined in HTML:", sorted(ids_defined))
print()

js_ids_used = set()
for jsfile in ["main.js", "tabs_data.js", "tabs_science.js", "ui.js", "api.js"]:
    with open(os.path.join(frontend, "js", jsfile)) as f:
        js = f.read()
    found = re.findall(r"['\"]#([a-zA-Z0-9_-]+)['\"]", js)
    for fid in found:
        js_ids_used.add(fid)

print("IDs used in JS:", sorted(js_ids_used))
print()

missing = js_ids_used - ids_defined
extra = ids_defined - js_ids_used
print("IDs used in JS but NOT in HTML:", sorted(missing))
print("IDs in HTML but NOT in JS:", sorted(extra))
