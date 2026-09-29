"""Comprehensive API smoke test - checks all endpoints the frontend calls."""
import json
import urllib.request
import sys

BASE = "http://127.0.0.1:8992"
PASS = []
FAIL = []


def get(path, label=None):
    label = label or path
    try:
        r = urllib.request.urlopen(BASE + path, timeout=10)
        d = json.loads(r.read())
        PASS.append(label)
        return d
    except Exception as e:
        FAIL.append((label, str(e)))
        return None


def post(path, body, label=None):
    label = label or path
    try:
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        r = urllib.request.urlopen(req, timeout=30)
        d = json.loads(r.read())
        PASS.append(label)
        return d
    except Exception as e:
        FAIL.append((label, str(e)))
        return None


def check(cond, label):
    if cond:
        PASS.append(label)
    else:
        FAIL.append((label, "assertion failed"))


def run_tests():
    # --- health and meta ---
    health = get("/api/health")
    check(health and health.get("status") == "ok", "health.status==ok")

    meta = get("/api/meta")
    check(meta is not None, "meta returns data")
    check(meta and "streams" in meta, "meta has streams")
    check(meta and "vocabulary" in meta, "meta has vocabulary")
    check(meta and "settings" in meta, "meta has settings")
    check(meta and "group_by_options" in meta, "meta has group_by_options")
    check(meta and "sample_data_available" in meta, "meta has sample_data_available")
    check(meta and meta.get("app", {}).get("version"), "meta.app.version present")
    check(meta and meta.get("citation"), "meta.citation present")
    check(meta and "default_stream" in (meta.get("settings") or {}), "settings.default_stream")
    check(meta and "warn_download_mb" in (meta.get("settings") or {}), "settings.warn_download_mb")
    check(meta and "plot_dpi" in (meta.get("settings") or {}), "settings.plot_dpi")

    # --- local ---
    summary = get("/api/local/summary")
    check(summary is not None, "local/summary returns data")
    check(summary and "n_granules" in summary, "summary.n_granules")
    check(summary and "cache_bytes_on_disk" in summary, "summary.cache_bytes_on_disk")
    check(summary and "cache_quota_bytes" in summary, "summary.cache_quota_bytes")
    check(summary and "by_product" in summary, "summary.by_product")

    datasets = get("/api/local/datasets")
    check(datasets and "datasets" in datasets, "local/datasets has datasets key")

    facets = get("/api/local/facets")
    check(facets and "products" in facets, "facets has products")
    check(facets and "sats" in facets, "facets has sats")
    check(facets and "date_min" in facets, "facets has date_min")
    check(facets and "date_max" in facets, "facets has date_max")

    # --- load samples ---
    loaded = post("/api/local/load-samples", {})
    check(loaded and "indexed" in loaded, "load-samples returns indexed count")
    if loaded:
        print(f"  Indexed {loaded['indexed']} sample granules")

    # --- search ---
    search_res = post("/api/profiles/search", {"good_only": False, "limit": 8})
    check(search_res and "granules" in search_res, "search returns granules")
    check(search_res and "total" in search_res, "search returns total")
    granules = (search_res or {}).get("granules", [])
    check(len(granules) > 0, "search found at least 1 granule")

    sample_id = granules[0]["id"] if granules else None

    # --- single profile ---
    if sample_id:
        p = get(f"/api/profiles/{sample_id}")
        check(p is not None, "profiles/{id} returns profile")
        check(p and "meta" in p, "profile has meta")
        check(p and "data" in p, "profile has data")
        check(p and "variables" in p, "profile has variables")
        check(p and "MSL_alt" in p.get("data", {}), "profile has MSL_alt")

        diag = get(f"/api/profiles/{sample_id}/diagnostics")
        check(diag is not None, "diagnostics endpoint returns")
        check(diag and "tropopause" in diag, "diagnostics has tropopause")

    # --- plot profiles (overlay) ---
    plot_data = post("/api/plot/profiles", {
        "search": {"good_only": False, "limit": 4},
        "field": "Temp",
        "vertical": "MSL_alt",
        "logx": False,
        "convert_kelvin": False,
    })
    check(plot_data and "traces" in plot_data, "plot/profiles returns traces")
    check(plot_data and "field_label" in plot_data, "plot/profiles returns field_label")
    check(plot_data and "vertical_label" in plot_data, "plot/profiles returns vertical_label")

    # --- composite ---
    composite = post("/api/plot/composite", {
        "search": {"good_only": False, "limit": 8},
        "field": "Temp",
        "vertical": "MSL_alt",
        "group_by": "lat_band",
        "spread": "std",
        "top_km": 40.0,
        "step_km": 0.5,
        "min_count": 1,
        "logx": False,
        "convert_kelvin": False,
    })
    check(composite and "groups" in composite, "composite returns groups")
    check(composite and "grid" in composite, "composite returns grid")
    check(composite and "field_label" in composite, "composite returns field_label")
    check(composite and "vertical_label" in composite, "composite returns vertical_label")
    check(composite and "min_count" in composite, "composite returns min_count")
    check(composite and "dropped_groups" in composite, "composite returns dropped_groups")
    if composite and composite.get("groups"):
        g = list(composite["groups"].values())[0]
        for key in ["mean", "std", "p10", "p90", "n"]:
            check(key in g, f"composite group has {key}")

    # --- diagnostics table ---
    diag_table = post("/api/diagnostics/table", {
        "search": {"good_only": False, "limit": 8}
    })
    check(diag_table and "rows" in diag_table, "diagnostics/table returns rows")
    check(diag_table and "columns" in diag_table, "diagnostics/table returns columns")
    check(diag_table and "n" in diag_table, "diagnostics/table returns n")
    check(diag_table and "unreadable" in diag_table, "diagnostics/table returns unreadable")

    # --- exports ---
    exports = get("/api/exports")
    check(exports and "exports" in exports, "exports returns exports key")

    # --- reveal folder ---
    reveal = get("/api/reveal-folder?which=cache")
    check(reveal and "opened" in reveal, "reveal-folder returns opened path")

    # --- jobs ---
    jobs = get("/api/jobs")
    check(jobs and "jobs" in jobs, "jobs returns jobs list")

    # --- static files ---
    for path in ["/", "/js/main.js", "/js/api.js", "/css/app.css", "/vendor/plotly.min.js"]:
        try:
            r = urllib.request.urlopen(BASE + path, timeout=5)
            content = r.read()
            PASS.append(f"static:{path}")
            if path == "/vendor/plotly.min.js":
                check(len(content) > 1_000_000, "plotly.min.js is large enough (>1MB)")
        except Exception as e:
            FAIL.append((f"static:{path}", str(e)))

    # --- summary ---
    print(f"\n{'='*60}")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("\nFAILED:")
        for label, reason in FAIL:
            print(f"  FAIL: {label}: {reason}")
    print("=" * 60)
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    run_tests()
