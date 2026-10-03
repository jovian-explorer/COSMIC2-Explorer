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
