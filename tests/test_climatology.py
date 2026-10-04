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
