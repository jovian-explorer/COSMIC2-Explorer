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
    cols = {"a": [10, 20, 30], "b": [12, 22, 32],   # lat 2, 4   -> band 0-5
            "c": [20, 40, np.nan], "d": [22, 44, np.nan]}  # lat 12, 14 -> band 10-15
    lats = {"a": 2.0, "b": 4.0, "c": 12.0, "d": 14.0}

    def fake(task):
        path = task[0]
        return "all", np.array(cols[path], float), "N", "Ref", ""
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
    # standard error of each cell's mean: std / sqrt(n)
    assert np.allclose(np.asarray(s["sem"], float)[0], [1.0] * 3)


def test_cross_section_refuses_dry_and_moist_temperature(monkeypatch):
    from cosmic2 import analysis
    qty = {"a": "temp_dry", "b": "Temp"}
    monkeypatch.setattr(analysis, "_composite_column",
                        lambda t: ("all", np.ones(3), "K", qty[t[0]], qty[t[0]]))
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
    from cosmic2 import analysis
    monkeypatch.setattr(analysis, "diagnostics_rows",
                        lambda rows, workers=None: [{"x": r["v"]} for r in rows])
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
    # 95 % interval of the zonal mean: t(0.975, 2) = 4.303 (t table)
    se = np.std([2, 4, 9], ddof=1) / np.sqrt(3)
    assert m["zonal"]["sem"][i0] == pytest.approx(se)
    assert m["zonal"]["ci95_hi"][i0] - 5.0 == pytest.approx(4.303 * se, rel=1e-3)
    assert 5.0 - m["zonal"]["ci95_lo"][i0] == pytest.approx(4.303 * se, rel=1e-3)
    i25 = m["lat_centres"].index(-25.0)
    assert m["zonal"]["n"][i25] == 1 and m["zonal"]["ci95_lo"][i25] is None
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


def test_pair_rows_matches_by_source_file():
    atm = [{"product": "atmPrf", "file_name": "atmPrf_A", "good": True},
           {"product": "atmPrf", "file_name": "atmPrf_B", "good": True},
           {"product": "atmPrf", "file_name": "atmPrf_C", "good": False}]
    wet = [{"product": "wetPf2", "file_name": "wetPf2_A", "good": True, "extras": {"source_atmPrf": "atmPrf_A"}},
           {"product": "wetPf2", "file_name": "wetPf2_C", "good": True, "extras": {"source_atmPrf": "atmPrf_C"}},
           {"product": "wetPf2", "file_name": "wetPf2_X", "good": True, "extras": {"source_atmPrf": "atmPrf_X"}}]
    # either product selects the pair, each pair once, bad atmPrf left out
    got = climatology.pair_rows(wet + atm, atm, wet)
    assert [(a["file_name"], w["file_name"]) for a, w in got] == [("atmPrf_A", "wetPf2_A")]
    assert len(climatology.pair_rows(wet + atm, atm, wet, good_only=False)) == 2


def test_compare_products_endpoint_on_bundled_samples():
    """The bundled atmPrf and wetPf2 are the same two occultations: both files
    carry the same dry retrieval, so their dry temperatures agree aloft, and
    the moisture effect is large near the ground and nil in the stratosphere."""
    post("/api/local/load-samples", {})
    res = post("/api/compare/products", {"search": {"products": ["wetPf2"]},
                                         "quantity": "dry_temperature", "min_count": 1})
    assert res["n_pairs"] == 2 and res["units"] == "K"
    g = res["grid"]
    hi = [abs(res["mean"][g.index(z)]) for z in (10.0, 15.0) if res["mean"][g.index(z)] is not None]
    assert hi and max(hi) < 0.5
    res = post("/api/compare/products", {"search": {"products": ["atmPrf"]},
                                         "quantity": "moisture_effect", "min_count": 1})
    assert res["n_pairs"] == 2
    m = [v for v in res["mean"] if v is not None]
    assert max(m) > 5 and abs(res["mean"][g.index(20.0)]) < 0.2


def test_tropopause_table_by_hand(monkeypatch):
    """Band statistics of the per-profile diagnostics, with CDAAC's own values."""
    from cosmic2 import analysis
    diag = {"a": (5.0, 16.0, 190.0), "b": (6.0, 17.0, 192.0), "c": (7.0, 16.5, 191.0),
            "d": (45.0, 11.0, 215.0)}
    monkeypatch.setattr(analysis, "diagnostics_rows", lambda rows, workers=None: [{
        "lat": diag[r["file_name"]][0], "tropopause.height_km": diag[r["file_name"]][1],
        "tropopause.temp_K": diag[r["file_name"]][2], "cold_point.height_km": None,
        "cold_point.temp_K": None} for r in rows])
    rows = [{"file_name": k, "product": "atmPrf", "good": True, "lat": v[0],
             "extras": {"tropopause_height_wmo_km": v[1] - 0.1, "tropopause_temp_wmo_C": v[2] - 273.15}}
            for k, v in diag.items()]
    rows.append({"file_name": "x", "product": "ionPrf", "good": True, "lat": 1.0})
    t = climatology.tropopause_table(rows, lat_step=10, min_count=2, workers=1)
    assert t["n_profiles"] == 4 and t["products"] == ["atmPrf"]
    b0 = t["bands"][0]
    assert (b0["lat_lo"], b0["lat_hi"], b0["n_profiles"]) == (0.0, 10.0, 3)
    assert b0["wmo_height_km"]["mean"] == pytest.approx(16.5)
    # t(0.975, 2) = 4.303, s = 0.5, n = 3
    assert b0["wmo_height_km"]["ci95_hi"] - 16.5 == pytest.approx(4.303 * 0.5 / np.sqrt(3), rel=1e-3)
    assert b0["archive"]["wmo_height_km"]["mean"] == pytest.approx(16.4)
    assert b0["archive"]["wmo_temp_K"]["mean"] == pytest.approx(191.0)
    assert b0["cp_height_km"]["n"] == 0 and b0["cp_height_km"]["mean"] is None
    assert t["bands"][1]["wmo_height_km"]["mean"] is None     # one profile < min_count


def test_tropopause_table_counts_each_occultation_once(monkeypatch):
    from cosmic2 import analysis
    seen = []
    monkeypatch.setattr(analysis, "diagnostics_rows", lambda rows, workers=None: [
        seen.append(r["product"]) or {
            "lat": 5.0, "tropopause.height_km": 16.0, "tropopause.temp_K": 190.0,
            "cold_point.height_km": None, "cold_point.temp_K": None} for r in rows])
    rows = [{"file_name": f"{p}_{s}", "product": p, "stamp": s, "good": True, "lat": 5.0,
             "extras": {}} for s in ("s1", "s2") for p in ("atmPrf", "wetPf2")]
    rows.append({"file_name": "atmPrf_s3", "product": "atmPrf", "stamp": "s3", "good": True,
                 "lat": 5.0, "extras": {}})
    t = climatology.tropopause_table(rows, lat_step=10, min_count=1, workers=1)
    assert t["n_profiles"] == 3 and t["bands"][0]["n_profiles"] == 3


def test_diagnostic_map_counts_each_occultation_once(monkeypatch):
    from cosmic2 import analysis
    vals = {"wetPf2": 16.0, "atmPrf": 17.0}
    monkeypatch.setattr(analysis, "diagnostics_rows", lambda rows, workers=None: [
        {"x": vals[r["product"]] if r["stamp"] != "s2" or r["product"] == "atmPrf" else None}
        for r in rows])
    rows = [{"product": p, "stamp": s, "lat": 5.0, "lon": 10.0}
            for s in ("s1", "s2") for p in ("atmPrf", "wetPf2")]
    m = climatology.diagnostic_map(rows, "x", lat_step=10, lon_step=20, workers=1)
    # s1 by its wetPf2 (16), s2 by its atmPrf (17), as wetPf2 has no value there
    assert m["n"] == 2 and m["overall"]["mean"] == pytest.approx(16.5)


def test_once_per_occultation_prefers_wetpf2_then_atmprf():
    rows = [{"product": "atmPrf", "stamp": "a"}, {"product": "wetPf2", "stamp": "a"},
            {"product": "atmPrf", "stamp": "b"}, {"product": "wetPf2", "stamp": "b"},
            {"product": "ionPrf", "stamp": "a"}]
    assert climatology.once_per_occultation(rows, [1, 2, 3, None, 5]) == [2, 3, 5]
