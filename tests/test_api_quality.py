"""API behaviour: honest provenance, input validation, local-only access."""
import json
import os
import urllib.error
import urllib.request

import pytest

BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")


def _req(path, body=None, method=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    r = urllib.request.Request(BASE + path, data=data, headers=h,
                               method=method or ("POST" if data else "GET"))
    return urllib.request.urlopen(r, timeout=60)


def post(path, body):
    return json.loads(_req(path, body).read())


@pytest.fixture(autouse=True)
def samples():
    post("/api/local/load-samples", {})


def test_export_provenance_says_plot_processing_was_not_applied():
    res = post("/api/export/data", {
        "kind": "metadata_csv", "search": {"limit": 3},
        "basename": "prov_test", "outlier_method": "mad",
        "smooth_method": "gaussian"})
    pp = res["provenance"]["processing_parameters"]
    assert pp["outlier_method"] == "mad"
    assert pp["applied_to_exported_values"] is False


def _preflight(origin):
    try:
        r = _req("/api/exports/x.csv", method="OPTIONS", headers={
            "Origin": origin, "Access-Control-Request-Method": "DELETE"})
        return r.status, r.headers.get("access-control-allow-origin")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("access-control-allow-origin")


def test_foreign_web_origin_is_refused_by_cors():
    status, allow = _preflight("https://example.com")
    assert allow is None
    assert status >= 400


def test_loopback_origin_is_allowed_by_cors():
    status, allow = _preflight("http://127.0.0.1:5173")
    assert status == 200 and allow == "http://127.0.0.1:5173"


def _status(path, body):
    try:
        return _req(path, body).status
    except urllib.error.HTTPError as e:
        return e.code


def test_zero_grid_step_is_rejected_not_a_server_error():
    assert _status("/api/composite", {"search": {"limit": 3}, "field": "Temp",
                                      "step_km": 0}) == 422


def test_invalid_settings_are_not_persisted():
    assert _status("/api/settings", {"grid_step_km": 0}) == 422
    meta = json.loads(_req("/api/meta").read())
    assert meta["settings"]["grid_step_km"] > 0


def test_panels_figure_for_a_granule_without_position(tmp_path):
    import numpy as np
    from scipy.io import netcdf_file
    from cosmic2 import api
    p = tmp_path / "atmPrf_C2E1.2026.200.01.02.G01_0001.0001_nc"
    f = netcdf_file(str(p), "w")
    f.year, f.month, f.day, f.hour, f.minute, f.second = 2026, 7, 19, 1, 2, 3.0
    f.createDimension("n", 3)
    for name, vals in (("MSL_alt", [1.0, 2.0, 3.0]), ("Temp", [10.0, 5.0, 0.0])):
        v = f.createVariable(name, "d", ("n",))
        v[:] = vals
    f.close()
    req = api.FigureRequest(kind="panels", panels=["Temp"])
    fig = api._build_figure(req, [{"path": str(p), "product": "atmPrf"}])
    assert fig is not None


def test_default_stream_setting_is_saved_and_validated():
    try:
        res = post("/api/settings", {"default_stream": "rapid"})
        assert res["default_stream"] == "rapid"
        assert _status("/api/settings", {"default_stream": "postcal"}) == 422
    finally:
        post("/api/settings", {"default_stream": "nrt"})


def test_settings_drawer_offers_only_real_streams():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "src" / "cosmic2" / "frontend"
          / "js" / "main.js").read_text(encoding="utf-8")
    assert "value: 'postcal'" not in js


def test_profile_figure_export_uses_every_level(monkeypatch):
    from cosmic2 import api, plotting, store
    rows = [r for r in store.query_granules(products=["atmPrf"], limit=5)["granules"]]
    assert rows
    seen = {}
    real = plotting.profile_figure

    def spy(items, *a, **k):
        seen["n"] = max(len(i["x"]) for i in items)
        return real(items, *a, **k)

    monkeypatch.setattr(plotting, "profile_figure", spy)
    api._build_figure(api.FigureRequest(kind="profiles", field="Ref"), rows)
    assert seen["n"] > 3000          # atmPrf has ~3800 levels; display cap is 900
