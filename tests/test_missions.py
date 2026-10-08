"""COSMIC-2 against PAZ / KOMPSAT-5 (cosmic2/missions.py): telling missions
apart, one-to-one collocation, and the two difference estimates."""
import json
import os
import urllib.request

import numpy as np
import pytest

from cosmic2 import missions, nwp

BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")


def _row(sat, lat, lon, hours, name=None):
    return {"sat": sat, "lat": lat, "lon": lon, "epoch": 1.8e9 + hours * 3600.0,
            "product": "wetPf2", "good": True, "file_name": name or f"{sat}_{lat}_{lon}_{hours}",
            "stamp": name or f"{sat}.{lat}.{lon}.{hours}"}


def test_missions_are_told_apart_by_satellite_code():
    assert missions.mission_of_sat("C2E3") == "cosmic2"
    assert missions.mission_of_sat("PAZ1") == "paz"
    assert missions.mission_of_sat("KOM5") == "kompsat5"
    assert missions.mission_of_sat("G25") is None and missions.mission_of_sat(None) is None


def test_collocation_is_one_to_one_within_the_window():
    c2 = [_row("C2E1", 10.0, 20.0, 0.0, "a"), _row("C2E2", 10.0, 21.0, 2.5, "b"),
          _row("C2E3", 40.0, 20.0, 0.0, "far")]
    other = [_row("PAZ1", 10.0, 20.5, 0.5, "p1"),      # 55 km from a, 0.5 h; 55 km from b, 2 h
             _row("PAZ1", 10.0, 21.2, 2.4, "p2"),      # 22 km from b, 0.1 h
             _row("PAZ1", -30.0, 0.0, 0.0, "p3")]      # nothing near
    pairs = missions.collocate(c2, other, max_km=300, max_hours=3)
    got = sorted((a["file_name"], o["file_name"]) for a, o, _, _ in pairs)
    assert got == [("a", "p1"), ("b", "p2")]           # each profile used once, best match first
    for a, o, d, dt in pairs:
        assert d <= 300 and dt <= 3
    # a tighter time window drops the 0.5 h pair only when it exceeds it
    assert len(missions.collocate(c2, other, max_km=300, max_hours=0.2)) == 1


def test_compare_aggregates_pairs_and_the_double_difference(monkeypatch):
    """With fixed per-pair differences and fixed model differences the two
    estimates are exact: collocated mean = mean of the pair differences, and
    through ECMWF = mean(C2 - ECMWF) - mean(other - ECMWF)."""
    grid_n = 61                                         # 0-30 km by 0.5 km
    c2 = [_row("C2E1", 0.0, float(i), 0.0, f"c{i}") for i in range(4)]
    other = [_row("PAZ1", 0.0, float(i) + 0.5, 0.2, f"o{i}") for i in range(4)]
    vals = iter([0.1, 0.3, -0.1, 0.5])
    monkeypatch.setattr(missions, "_pair_diff", lambda task: np.full(grid_n, next(vals)))

    def fake_model_differences(groups, q, **kw):
        sats = {next(iter(g.values()))["sat"] for g in groups}
        mean = 0.4 if sats == {"C2E1"} else 0.1
        return {"models": {"echPrf": {"n_profiles": len(groups), "mean": np.full(grid_n, mean),
                                      "sem": np.full(grid_n, 0.05)}}}
    monkeypatch.setattr(nwp, "model_differences", fake_model_differences)
    index = c2 + other
    res = missions.compare(c2 + other, index, other="paz", quantity="temperature",
                           top_km=30, step_km=0.5, min_count=2, workers=1)
    col, via = res["collocated"], res["via_ecmwf"]
    assert res["n_cosmic2"] == 4 and res["n_other"] == 4 and col["n_pairs"] == 4
    assert col["mean"][10] == pytest.approx(0.2) and col["n"][10] == 4
    assert col["std"][10] == pytest.approx(np.std([0.1, 0.3, -0.1, 0.5], ddof=1))
    assert via["available"] and via["mean"][10] == pytest.approx(0.3)
    assert via["ci95_hi"][10] - 0.3 == pytest.approx(1.96 * np.hypot(0.05, 0.05))


def test_mission_endpoint_without_the_other_mission():
    """The bundled samples are COSMIC-2 only: the answer says so instead of
    failing, so the card can tell the user what to download."""
    urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/local/load-samples", data=b"{}", headers={"Content-Type": "application/json"}),
        timeout=60).read()
    for q in ("temperature", "refractivity"):
        req = urllib.request.Request(BASE + "/api/compare/missions",
                                     data=json.dumps({"search": {}, "other": "paz", "quantity": q}).encode(),
                                     headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=60).read())
        assert res["n_cosmic2"] == 2 and res["n_other"] == 0
        assert res["collocated"]["n_pairs"] == 0 and res["via_ecmwf"]["available"] is False
