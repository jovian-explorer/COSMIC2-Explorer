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
