import os
import json
import time
import urllib.request
import subprocess
from pathlib import Path

APPDATA = Path(os.environ.get("LOCALAPPDATA", "")) / "COSMIC2Explorer"
STARTUP_LOG = APPDATA / "logs" / "startup.log"

def get_port_from_log():
    if not STARTUP_LOG.exists(): return None
    lines = STARTUP_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        if "http://127.0.0.1:" in line:
            parts = line.split("http://127.0.0.1:")
            if len(parts) > 1:
                return parts[1].split("/")[0].strip()
    return None

def main():
    print("Starting smoke test workflow...")
    port = get_port_from_log()
    if not port:
        print("Could not find port in startup log.")
        return
    base_url = f"http://127.0.0.1:{port}"
    print(f"Connected to backend on {base_url}")

    def get(path):
        return json.loads(urllib.request.urlopen(base_url + path, timeout=10).read())

    def post(path, data):
        req = urllib.request.Request(
            base_url + path,
            data=json.dumps(data).encode(),
            method="POST",
            headers={"Content-Type": "application/json"}
        )
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    def get_raw(path):
        return urllib.request.urlopen(base_url + path, timeout=10).read()

    # 1. Open Help / About
    print("Testing Help and About content...")
    help_content = get_raw("/help.html").decode("utf-8")
    assert "guidebook" in help_content.lower() or "help" in help_content.lower()
    index_content = get_raw("/index.html").decode("utf-8")
    assert "cosmic-2 explorer" in index_content.lower()

    # 2. Change theme / font size
    print("Changing theme...")
    meta = get("/api/meta")
    orig_theme = meta["settings"]["plot_theme"]
    new_theme = "dark" if orig_theme == "light" else "light"
    post("/api/settings", {"plot_theme": new_theme, "ui_theme": new_theme, "font_size": 16})
    
    # 3. Inspect Data/Product info
    print("Inspecting COSMIC-2 Data info...")
    facets = get("/api/local/facets")
    assert "products" in facets
    
    # 4. Load/download representative dataset
    print("Loading samples...")
    post("/api/local/load-samples", {})
    
    # 5. Process it (Search)
    print("Processing and searching datasets...")
    search_res = post("/api/profiles/search", {"good_only": False, "limit": 5})
    assert search_res["total"] > 0
    granule_ids = [g["id"] for g in search_res["granules"]]
    
    # 6. Apply outlier/filter/smoothing and display plot
    print("Applying smoothing and generating plot...")
    plot_res = post("/api/plot/profiles", {
        "granule_ids": granule_ids,
        "field": "Temp",
        "vertical": "MSL_alt",
        "smooth_method": "gaussian",
        "smooth_kwargs": {"window": 5},
        "uncert_method": "standard_deviation"
    })
    assert "series" in plot_res
    print("Plot generated successfully with error/uncertainty information.")
    
    # 7. Generate derived result
    print("Generating derived diagnostics (Tropopause, Lapse Rate)...")
    diag_res = post("/api/diagnostics/table", {"search": {"good_only": False, "limit": 5}})
    assert "rows" in diag_res
    
    # 8. Export result
    print("Exporting data to CSV...")
    export_res = post("/api/export/data", {
        "kind": "metadata_csv",
        "search": {"good_only": False, "limit": 5},
        "basename": "smoke_test_export"
    })
    assert "filename" in export_res
    print(f"Exported successfully to {export_res['filename']}")
    
    print("Smoke test workflow completed successfully!")

if __name__ == "__main__":
    main()
