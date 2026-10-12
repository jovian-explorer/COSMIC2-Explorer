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


def test_clean_float_arrays_match_elementwise():
    import numpy as np
    from cosmic2 import api
    a = np.array([1.5, np.nan, -np.inf, 2.0, np.inf], dtype="f4")
    assert api._clean(a) == [1.5, None, None, 2.0, None]
    b = np.array([[1.0, np.nan], [2.0, 3.0]])
    assert api._clean(b) == [[1.0, None], [2.0, 3.0]]
    assert api._clean(np.array([1, 2])) == [1, 2]
    assert all(isinstance(x, float) for x in api._clean(np.arange(3.0)))


def test_composite_figure_uses_the_requested_grid(monkeypatch):
    from cosmic2 import api, plotting, readers
    from cosmic2.config import sampledata_dir
    seen = {}
    monkeypatch.setattr(plotting, "composite_figure",
                        lambda comp, **kw: seen.setdefault("comp", comp))
    rows = [dict(readers.quick_meta(str(p)), id="x", date="2026-07-19")
            for p in sampledata_dir().glob("ionPrf_*")]
    req = api.FigureRequest(kind="composite", field="ELEC_dens", group_by="all",
                            top_km=600, step_km=10)
    api._build_figure(req, rows)
    grid = seen["comp"]["grid"]
    assert grid[-1] == 600 and grid[1] - grid[0] == 10


def test_composite_of_ivm_says_what_the_selection_holds():
    """ivmL2m files are a day of in-situ samples at one height: the composite is
    empty and the response names the product, so the Compare tab can say why."""
    res = post("/api/composite", {"search": {"products": ["ivmL2m"], "limit": 10},
                                  "field": "ion_dens", "vertical": "alt",
                                  "top_km": 40, "step_km": 0.5})
    assert res["n_profiles"] == 0 and res["products"] == {"ivmL2m": res["selected"]}
    res = post("/api/composite", {"search": {"products": ["wetPf2"], "limit": 10},
                                  "field": "Temp", "top_km": 30, "step_km": 1})
    assert res["n_profiles"] > 0 and set(res["products"]) == {"wetPf2"}


def test_download_range_queues_one_job_per_day(monkeypatch):
    """With date_end, one download of the same product is queued for every
    day through that date (across a month end), at most 31; a single day
    answers as before, with its job."""
    from fastapi import HTTPException
    from cosmic2 import api, fetch
    calls = []

    class Job:
        def __init__(self, day):
            self.day = day

        def snapshot(self):
            return {"id": self.day}

    class Manager:
        def submit_download(self, **kw):
            calls.append(kw)
            return Job(kw["date"])

    monkeypatch.setattr(fetch, "manager", lambda: Manager())
    res = api.start_download(api.DownloadRequest(product="ionPrf", date="2026-02-27",
                                                 date_end="2026-03-02", max_profiles=0))
    assert [c["date"] for c in calls] == ["2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02"]
    assert all(c["product"] == "ionPrf" and c["max_profiles"] == 0 for c in calls)
    assert res["n_days"] == 4 and [j["id"] for j in res["jobs"]] == [c["date"] for c in calls]
    calls.clear()
    assert api.start_download(api.DownloadRequest(date="2026-06-01")) == {"id": "2026-06-01"}
    assert len(calls) == 1
    calls.clear()
    for bad in ({"date": "2026-06-02", "date_end": "2026-06-01"},
                {"date": "2026-01-01", "date_end": "2026-02-01"},
                {"date": "2026-6-1"}):
        with pytest.raises(HTTPException) as err:
            api.start_download(api.DownloadRequest(**bad))
        assert err.value.status_code == 400
    assert not calls


def test_overlay_of_atmprf_and_wetpf2_temperature_names_both():
    from cosmic2 import api
    assert api._overlay_title("Temp", {"atmPrf", "wetPf2"}, "C") == \
        "Dry temperature (atmPrf); Temperature (wetPf2) [°C]"
    assert api._overlay_title("Temp", {"wetPf2"}, "C") == "Temperature [°C]"


def test_file_unit_strings_read_unambiguously():
    from cosmic2 import vocab
    assert vocab.axis_title("Ref", "N") == "Refractivity [N-units]"      # not newton
    assert vocab.axis_title("s4_L1", "unitless") == "S4 index, L1"
    assert vocab.axis_title("ion_dens", "N/cc") == "Ion density (in-situ) [ions/cm³]"
    assert vocab.normalise_units("seconds since 1980-1-6 00:00:00") == "s of GPS time since 1980-01-06"


def test_unexpected_error_is_explained_not_a_bare_500(monkeypatch):
    from cosmic2 import store
    monkeypatch.setattr(store, "summary", lambda: 1 / 0)    # the test server shares this process
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(os.environ["COSMIC2_TEST_BASE"] + "/api/local/summary", timeout=60)
    assert err.value.code == 500
    msg = json.loads(err.value.read())["detail"]
    assert "ZeroDivisionError" in msg and "errors.log" in msg


def test_map_leaves_out_flagged_profiles_of_a_selection(monkeypatch):
    from cosmic2 import api, climatology
    seen = {}
    monkeypatch.setattr(api, "_resolve_selection", lambda ids, search, n: [
        {"id": "a", "good": True}, {"id": "b", "good": False}])
    monkeypatch.setattr(climatology, "diagnostic_map",
                        lambda rows, *a, **k: seen.setdefault("rows", rows) and {"n": len(rows)})
    post("/api/climatology/map", {"granule_ids": ["a", "b"], "column": "x"})
    assert [r["id"] for r in seen["rows"]] == ["a"]


def test_profile_overlay_says_which_products_it_left_out():
    post("/api/local/load-samples", {})
    ids = {r["product"]: r["id"] for r in post("/api/profiles/search", {"limit": 50})["granules"]}
    res = post("/api/plot/profiles", {"granule_ids": [ids["wetPf2"], ids["ionPrf"]],
                                      "field": "Temp", "vertical": "MSL_alt"})
    assert len(res["series"]) == 1
    (sk,) = res["skipped"]
    assert sk["product"] == "ionPrf" and "has no temperature (Temp)" in sk["why"]


def test_averages_section_and_map_say_which_missions_they_pool():
    post("/api/local/load-samples", {})
    s = {"search": {"products": ["wetPf2"]}}
    for path, extra in (("/api/composite", {"field": "Temp", "top_km": 10, "step_km": 1}),
                        ("/api/climatology/section", {"field": "Temp", "top_km": 10, "step_km": 1}),
                        ("/api/climatology/map", {"column": "tropopause.height_km"})):
        assert post(path, dict(s, **extra))["missions"] == {"COSMIC-2": 2}, path
