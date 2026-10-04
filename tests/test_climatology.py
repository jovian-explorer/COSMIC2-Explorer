"""Statistics over many profiles: sampling, quality and penetration depth;
latitude-height sections; gridded diagnostics."""
import json
import os
import urllib.request

import numpy as np
import pytest

from cosmic2 import climatology

BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")


def post(path, body):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=120).read())


def _row(i, product="atmPrf", lat=0.0, alt_min=0.5, good=True, **kw):
    r = {"product": product, "lat": lat, "local_time": (i % 24) + 0.5,
         "time_utc": f"2026-06-20T{i % 24:02d}:30:00Z", "good": good,
         "bad_code": "0.0" if good else "1.0", "n_levels": 3800,
         "alt_min": alt_min, "file_name": f"atmPrf_{i}", "extras": {}}
    r.update(kw)
    return r


def test_sampling_counts_flags_and_penetration_by_hand():
    rows = [_row(0, lat=-5, alt_min=0.05), _row(1, lat=5, alt_min=0.4),
            _row(2, lat=15, alt_min=1.5), _row(3, lat=15, alt_min=4.0),
            _row(4, lat=25, alt_min=0.2, good=False)]
    s = climatology.sampling_statistics(rows, lat_step=10)
    p = s["products"]["atmPrf"]
    assert (p["n"], p["n_good"], p["n_bad"]) == (5, 4, 1)
    assert p["bad_codes"] == {"1.0": 1}
    assert sum(p["lat_counts"]) == 5 and sum(p["lat_counts_good"]) == 4
    assert p["local_time_counts"][:5] == [1, 1, 1, 1, 1]
    pen = p["penetration"]
    # flagged profile excluded; 4 good lowest levels 0.05, 0.4, 1.5, 4.0
    assert pen["n"] == 4 and pen["median_km"] == pytest.approx(0.95)
    assert pen["fraction_below"]["1"] == 0.5
    assert pen["fraction_below"]["0.1"] == 0.25
    i15 = s["lat_edges"].index(10.0)
    assert pen["lat_median_km"][i15] == pytest.approx(2.75)
    assert pen["lat_n"][i15] == 2


def test_penetration_above_ground_uses_wetpf2_terrain():
    rows = [_row(0, alt_min=1.2), _row(1, alt_min=0.3),
            {"product": "wetPf2", "lat": 0.0, "good": True, "alt_min": 0.0,
             "extras": {"source_atmPrf": "atmPrf_0", "terrain_height_km": 0.9}}]
    agl = climatology.sampling_statistics(rows)["products"]["atmPrf"][
        "penetration"]["above_ground"]
    # only atmPrf_0 has terrain: 1.2 km above sea level is 0.3 km above ground
    assert agl["n"] == 1 and agl["median_km"] == pytest.approx(0.3)
    assert agl["fraction_below"]["0.5"] == 1.0


def test_stats_endpoint_on_bundled_samples():
    post("/api/local/load-samples", {})
    res = post("/api/stats/sampling", {"search": {}})
    assert res["n"] >= 8
    atm = res["products"]["atmPrf"]
    assert sum(atm["lat_counts"]) == atm["n"]
    if atm["penetration"]["archive_check"]["n"]:
        # the index's lowest level is CDAAC's profile_bottom_km
        assert atm["penetration"]["archive_check"]["max_abs_diff_km"] < 1e-3


def test_cross_section_band_means_and_departure_by_hand(monkeypatch):
    """Columns are binned by latitude and averaged; the departure is from
    the mean of all profiles at each height."""
    from cosmic2 import analysis
    grid = analysis.make_grid(2.0, 1.0)          # 0, 1, 2 km
    cols = {"a": [10, 20, 30], "b": [12, 22, 32],   # lat 2, 4   -> band 0-5
            "c": [20, 40, np.nan], "d": [22, 44, np.nan]}  # lat 12, 14 -> band 10-15
    lats = {"a": 2.0, "b": 4.0, "c": 12.0, "d": 14.0}

    def fake(task):
        path = task[0]
        return "all", np.array(cols[path], float), "N", "Ref"
    monkeypatch.setattr(analysis, "_composite_column", fake)
    rows = [(p, {"lat": lats[p], "good": True}) for p in cols]
    s = climatology.cross_section(rows, "Ref", lat_step=5, top_km=2, step_km=1,
                                  min_count=2, workers=1)
    assert s["lat_centres"] == [2.5, 7.5, 12.5]
    assert s["profiles_per_band"] == [2, 0, 2]
    mean = np.asarray(s["mean"], float)
    assert np.allclose(mean[0], [11, 21, 31])
    assert np.isnan(mean[1]).all()
    assert np.allclose(mean[2][:2], [21, 42]) and np.isnan(mean[2][2])
    overall = np.asarray(s["overall_mean"], float)
    assert np.allclose(overall, [16, 31.5, 31])
    dep = np.asarray(s["departure_pct"], float)
    assert np.allclose(dep[0], 100 * (np.array([11, 21, 31]) - overall) / overall)
    assert np.asarray(s["count"])[2].tolist() == [2, 2, 0]
    assert np.allclose(np.asarray(s["std"], float)[0], [np.sqrt(2)] * 3)


def test_cross_section_refuses_dry_and_moist_temperature(monkeypatch):
    from cosmic2 import analysis
    qty = {"a": "temp_dry", "b": "Temp"}
    monkeypatch.setattr(analysis, "_composite_column",
                        lambda t: ("all", np.ones(3), "K", qty[t[0]]))
    with pytest.raises(ValueError, match="different quantities"):
        climatology.cross_section([("a", {"lat": 0.0}), ("b", {"lat": 1.0})],
                                  "Temp", top_km=2, step_km=1, workers=1)


def test_section_endpoint_on_bundled_samples():
    post("/api/local/load-samples", {})
    res = post("/api/climatology/section", {
        "search": {"products": ["wetPf2"]}, "field": "Temp", "min_count": 1,
        "top_km": 30, "step_km": 1})
    assert res["n_profiles"] >= 1 and res["units"] == "K"
    m = np.array([[np.nan if v is None else v for v in row] for row in res["mean"]])
    assert np.nanmin(m) > 150 and np.nanmax(m) < 320


def test_diagnostic_map_cells_and_zonal_mean_by_hand(monkeypatch):
    pts = [(5, 10, 2.0), (6, 12, 4.0), (5, 100, 9.0), (-25, -170, 1.0), (None, 0, 5.0)]
    monkeypatch.setattr(climatology, "_map_value",
                        lambda t: None if t[0]["lat"] is None else
                        (t[0]["lat"], t[0]["lon"], t[0]["v"]))
    rows = [{"lat": a, "lon": b, "v": v} for a, b, v in pts]
    m = climatology.diagnostic_map(rows, "x", lat_step=10, lon_step=20, workers=1)
    assert m["n"] == 4
    i0 = m["lat_centres"].index(5.0)
    j10 = m["lon_centres"].index(10.0)
    j100 = m["lon_centres"].index(110.0)
    assert m["mean"][i0][j10] == pytest.approx(3.0) and m["count"][i0][j10] == 2
    assert m["mean"][i0][j100] == pytest.approx(9.0)
    assert m["zonal"]["mean"][i0] == pytest.approx(5.0)
    assert m["zonal"]["median"][i0] == pytest.approx(4.0)
    assert m["zonal"]["n"][i0] == 3
    assert m["zonal"]["std"][i0] == pytest.approx(np.std([2, 4, 9], ddof=1))
    # min_count blanks thin cells but not the zonal mean
    m2 = climatology.diagnostic_map(rows, "x", lat_step=10, lon_step=20,
                                    min_count=2, workers=1)
    assert np.isnan(m2["mean"][i0][j100]) and m2["zonal"]["n"][i0] == 3


def test_map_and_coastline_endpoints_on_bundled_samples():
    post("/api/local/load-samples", {})
    res = post("/api/climatology/map", {
        "search": {"products": ["atmPrf", "wetPf2"]},
        "gw_method": "highpass", "gw_z_lo": 20, "gw_z_hi": 30})
    assert res["n"] >= 1 and res["gw"]["method"] == "highpass"
    assert res["title"].startswith("Gravity-wave potential energy")
    tp = post("/api/climatology/map", {"search": {}, "column": "tropopause.height_km"})
    assert tp["gw"] is None and 5 < tp["overall"]["mean"] < 20
    coast = json.loads(urllib.request.urlopen(BASE + "/api/coastlines", timeout=60).read())
    assert len(coast["lon"]) == len(coast["lat"]) > 1000 and None in coast["lon"]
