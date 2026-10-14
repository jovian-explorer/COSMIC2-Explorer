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
    assert missions.mission_of_sat("MTPC") == "metopc" and missions.mission_of_sat("C006") == "cosmic1"
    assert missions.mission_of_sat("MTPA") == "metopa" and missions.mission_of_sat("TDMX") == "tdx"
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
    monkeypatch.setattr(missions, "_pair_diff", lambda task: (np.full(grid_n, next(vals)), None))

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


def test_double_difference_uses_the_latitudes_both_missions_cover(monkeypatch):
    """COSMIC-2 reaches about 45 degrees, PAZ the poles: the profiles through
    ECMWF are limited to the common latitudes (RO minus ECMWF changes with
    latitude), the collocated pairs are not affected."""
    c2 = [_row("C2E1", lat, 0.0, 0.0, f"c{lat}") for lat in (-40.0, 0.0, 40.0)]
    other = [_row("PAZ1", lat, 0.5, 0.2, f"o{lat}") for lat in (-80.0, -40.0, 10.0, 70.0)]
    monkeypatch.setattr(missions, "_pair_diff", lambda task: (np.zeros(61), None))
    seen = []

    def fake_model_differences(groups, q, **kw):
        seen.append(sorted(next(iter(g.values()))["lat"] for g in groups))
        return {"models": {"echPrf": {"n_profiles": len(groups), "mean": np.zeros(61),
                                      "sem": np.zeros(61)}}}
    monkeypatch.setattr(nwp, "model_differences", fake_model_differences)
    res = missions.compare(c2 + other, c2 + other, other="paz", min_count=1, workers=1)
    assert seen == [[-40.0, 0.0, 40.0], [-40.0, 10.0]]
    via = res["via_ecmwf"]
    assert via["lat_range"] == [-40.0, 40.0] and via["n_cosmic2"] == 3 and via["n_other"] == 2
    assert res["n_other"] == 4 and res["collocated"]["n_pairs"] == 1   # the pair at 40S


def test_pair_difference_corrected_with_ecmwf(monkeypatch):
    """Each pair's difference minus ECMWF's difference between its two
    occultations (Gilpin et al. 2018): exact on made-up profiles, in K and
    in percent, and left out when an echPrf is missing."""
    from cosmic2 import readers

    z = np.linspace(0.0, 30.0, 61)
    temp = {"a": 1.0, "o": 0.2, "ea": 0.5, "eo": -0.1}            # offsets in K
    ref = {"a": 1.02, "o": 1.00, "ea": 1.01, "eo": 0.99}         # factors

    class G:
        def __init__(self, key):
            n = 300.0 * np.exp(-z / 7.0) * ref[key]
            self.data = {"MSL_alt": z, "Temp": -50.0 + temp[key] + 0 * z, "ref": n, "Ref": n}
    monkeypatch.setattr(readers, "load", lambda path, product: G(path))
    grid = np.arange(0.0, 30.01, 0.5)
    raw, cor = missions._pair_diff(({"path": "a"}, {"path": "o"}, "temperature", grid,
                                    ({"path": "ea"}, {"path": "eo"})))
    assert raw[10] == pytest.approx(0.8) and cor[10] == pytest.approx((1.0 - 0.5) - (0.2 + 0.1))
    raw, cor = missions._pair_diff(({"path": "a"}, {"path": "o"}, "refractivity_1dvar", grid,
                                    ({"path": "ea"}, {"path": "eo"})))
    assert raw[10] == pytest.approx(2.0)
    assert cor[10] == pytest.approx(100 * (1.02 / 1.01 - 1) - 100 * (1.00 / 0.99 - 1))
    raw, cor = missions._pair_diff(({"path": "a"}, {"path": "o"}, "temperature", grid,
                                    ({"path": "ea"}, None)))
    assert raw[10] == pytest.approx(0.8) and cor is None


def test_compare_reports_the_corrected_pairs(monkeypatch):
    c2 = [_row("C2E1", 0.0, float(i), 0.0, f"c{i}") for i in range(3)]
    other = [_row("PAZ1", 0.0, float(i) + 0.5, 0.2, f"o{i}") for i in range(3)]
    out = iter([(np.full(61, 0.4), np.full(61, 0.1)), (np.full(61, 0.2), None),
                (np.full(61, 0.6), np.full(61, 0.3))])
    monkeypatch.setattr(missions, "_pair_diff", lambda task: next(out))
    monkeypatch.setattr(nwp, "model_differences",
                        lambda groups, q, **kw: {"models": {"echPrf": {"n_profiles": 0}}})
    col = missions.compare(c2 + other, c2 + other, other="paz", min_count=2,
                           workers=1)["collocated"]
    assert col["n_pairs"] == 3 and col["mean"][10] == pytest.approx(0.4)
    assert col["corrected"]["n_pairs"] == 2 and col["corrected"]["mean"][10] == pytest.approx(0.2)


def test_statistics_say_which_missions_they_mix():
    """The weather-model and tropopause answers count profiles per mission,
    so their captions can say when PAZ or KOMPSAT-5 are mixed in."""
    from cosmic2 import api
    # LEO002: a COSMIC-2 scintillation file indexed before scnLv2 files were
    # named C2E1-C2E6 (it is FM2)
    rows = [{"sat": "C2E1"}, {"sat": "C2E5"}, {"sat": "PAZ1"}, {"sat": "KOM5"}, {"sat": "LEO002"}]
    assert api._missions_of(rows) == {"COSMIC-2": 3, "PAZ": 1, "KOMPSAT-5": 1}
    urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/local/load-samples", data=b"{}", headers={"Content-Type": "application/json"}),
        timeout=60).read()
    for path, body in (("/api/climatology/tropopause", {"search": {"products": ["atmPrf"]}}),
                       ("/api/compare/models", {"search": {"products": ["atmPrf"]}})):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=60).read())
        assert res["missions"] == {"COSMIC-2": 2}, path


def test_every_other_mission_has_a_name_a_data_set_and_a_stream():
    from cosmic2 import catalog, config
    others = set(catalog.MISSION_SATS)
    assert others == set(missions.MISSION_NAMES) - {"cosmic2"}
    assert others | {"cosmic2"} == set(config.MISSION_DATASETS)
    assert others == {s.get("mission") for s in catalog.STREAMS.values()} - {None}
