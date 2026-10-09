"""Radio occultation against the colocated ECMWF and NCEP profiles, and the
three-cornered hat (cosmic2/nwp.py)."""
import json
import os
import urllib.request

import numpy as np
import pytest

from cosmic2 import nwp

BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def test_tch_recovers_known_independent_errors():
    """Three noisy copies of the same truth with independent errors of known
    size: the estimator returns those variances, and the bootstrap interval
    used by the app covers them."""
    rng = np.random.default_rng(5)
    truth = rng.normal(0, 3, size=(3000, 4))
    sig = np.array([0.5, 0.3, 0.8])
    x, y, z = (truth + rng.normal(0, s, truth.shape) for s in sig)
    var = nwp.tch_variances(x, y, z)
    assert np.allclose(var.mean(axis=1), sig ** 2, rtol=0.08, atol=0.01)
    # missing values: each level uses the profiles that have all three
    x[::3, 1] = np.nan
    assert np.allclose(nwp.tch_variances(x, y, z)[:, 1], sig ** 2, rtol=0.12, atol=0.02)


def test_tch_bias_from_correlated_errors_is_as_documented():
    """With covariances c, the first estimate is s1^2 - c12 - c13 + c23 (the
    docstring's caveat about models that assimilate the observations)."""
    rng = np.random.default_rng(6)
    n = 200000
    shared = rng.normal(0, 0.4, n)                 # an error common to datasets 2 and 3
    e1 = rng.normal(0, 0.5, n)
    e2 = rng.normal(0, 0.3, n) + shared
    e3 = rng.normal(0, 0.6, n) + shared
    var = nwp.tch_variances(e1[:, None], e2[:, None], e3[:, None])[:, 0]
    c23 = 0.4 ** 2
    assert var[0] == pytest.approx(0.5 ** 2 + c23, abs=0.01)                 # inflated
    assert var[1] == pytest.approx(0.3 ** 2 + 0.4 ** 2 - c23, abs=0.01)      # deflated


def test_stamp_groups_pair_the_four_products():
    rows = [{"product": p, "stamp": s, "good": g}
            for p in ("atmPrf", "wetPf2", "echPrf", "avnPrf") for s, g in (("A", True), ("B", True))]
    rows.append({"product": "echPrf", "stamp": "C", "good": False})
    sel = [r for r in rows if r["product"] == "wetPf2"] + [{"product": "atmPrf", "stamp": "A"}]
    groups = nwp.stamp_groups(sel, rows)
    assert [sorted(g) for g in groups] == [["atmPrf", "avnPrf", "echPrf", "wetPf2"]] * 2
    assert nwp.stamp_groups([{"product": "echPrf", "stamp": "C"}], rows) == []


def test_model_comparison_endpoint_on_bundled_samples():
    """The two bundled occultations come with their echPrf and avnPrf."""
    post("/api/local/load-samples", {})
    res = post("/api/compare/models", {"search": {"products": ["atmPrf"]},
                                       "kind": "differences", "quantity": "refractivity",
                                       "min_count": 1})
    assert res["n_profiles"] == 2
    for model in ("echPrf", "avnPrf"):
        d = res["models"][model]
        g = res["grid"]
        v = [d["mean"][g.index(z)] for z in (10.0, 15.0, 20.0)]
        assert all(x is not None and abs(x) < 2 for x in v)        # percent
    res = post("/api/compare/models", {"search": {"products": ["wetPf2"]},
                                       "kind": "differences", "quantity": "temperature",
                                       "min_count": 1})
    assert res["units"] == "K" and res["models"]["echPrf"]["n_profiles"] == 2
    res = post("/api/compare/models", {"search": {"products": ["atmPrf"]}, "kind": "tch"})
    assert res["n_triplets"] == 2 and all(v is None for v in res["variance"][0])   # too few


def test_impact_height_relation_matches_atmprf():
    """atmPrf's Impact_height is n (Rc + z) - Rc of its own MSL_alt and Ref."""
    from cosmic2 import readers
    from cosmic2.config import sampledata_dir
    for f in sampledata_dir().glob("atmPrf_*"):
        g = readers.load(str(f), "atmPrf")
        x = nwp.model_impact_height(g.data["MSL_alt"], g.data["Ref"], float(g.attrs["rfict"]))
        ok = np.isfinite(x) & np.isfinite(g.data["Impact_height"])
        assert ok.sum() > 1000
        assert np.max(np.abs(x[ok] - g.data["Impact_height"][ok])) < 1e-3     # km


def test_bending_angle_against_ecmwf_on_bundled_samples():
    post("/api/local/load-samples", {})
    res = post("/api/compare/models", {"search": {"products": ["atmPrf"]},
                                       "kind": "differences", "quantity": "bending_angle",
                                       "min_count": 1, "top_km": 35})
    assert list(res["models"]) == ["echPrf"] and res["models"]["echPrf"]["n_profiles"] == 2
    assert res["vertical_label"].startswith("Impact height")
    g = res["grid"]
    m = [res["models"]["echPrf"]["mean"][g.index(z)] for z in (12.0, 20.0, 30.0)]
    assert all(v is not None and abs(v) < 5 for v in m)


def test_ducting_differences_split_by_the_model_duct(monkeypatch):
    """Made-up occultations: where echPrf diagnoses a duct the RO refractivity
    is 8 % low below its centre, elsewhere it equals ECMWF's.  The duct and
    no-duct composites and the composite around the duct come out exactly."""
    from cosmic2 import readers
    z = np.linspace(0.0, 8.0, 801)
    model = 320.0 * np.exp(-z / 7.5)
    cases = {"d1": (1, 1.5), "d2": (3, 1.0), "n1": (0, -999.0), "n2": (0, -999.0)}

    class G:
        def __init__(self, path):
            key, prod = path.split(":")
            duct, zsr = cases[key]
            ref = model * np.where((duct > 0) & (z < zsr), 0.92, 1.0) if prod == "atm" else model
            self.data = {"MSL_alt": z, "Ref": ref, "ductid": np.array([duct], float),
                         "zsr": np.array([zsr])}
    monkeypatch.setattr(readers, "load", lambda path, product: G(path))
    groups = [{"atmPrf": {"path": f"{k}:atm"}, "echPrf": {"path": f"{k}:ech"}} for k in cases]
    out = nwp.ducting_differences(groups, top_km=6, step_km=0.1, min_count=1, workers=1)
    assert out["n_profiles"] == 4 and out["n_duct"] == 2
    assert out["duct_classes"] == {"0": 2, "1": 1, "2": 0, "3": 1}
    g = np.array(out["grid"])
    duct, none = out["models"]["duct"], out["models"]["no_duct"]
    assert duct["mean"][np.argmin(abs(g - 0.5))] == pytest.approx(-8.0, abs=1e-6)
    assert duct["mean"][np.argmin(abs(g - 1.2))] == pytest.approx(-4.0, abs=1e-6)   # one of two below
    assert duct["mean"][np.argmin(abs(g - 3.0))] == pytest.approx(0.0, abs=1e-9)
    assert np.nanmax(np.abs(none["mean"])) < 1e-9
    around = nwp.ducting_differences(groups, top_km=6, step_km=0.1, around_duct=True,
                                     min_count=1, workers=1)
    r = np.array(around["grid"]); st = around["models"]["duct"]
    assert list(around["models"]) == ["duct"] and st["n_profiles"] == 2
    assert st["mean"][np.argmin(abs(r + 0.5))] == pytest.approx(-8.0, abs=1e-6)
    assert st["mean"][np.argmin(abs(r - 0.5))] == pytest.approx(0.0, abs=1e-9)


def test_ducting_endpoint_on_bundled_samples():
    post("/api/local/load-samples", {})
    for kind in ("ducting", "ducting_rel"):
        res = post("/api/compare/models", {"kind": kind, "quantity": "refractivity", "top_km": 6,
                                           "step_km": 0.1, "search": {"products": ["atmPrf"]}})
        assert res["n_profiles"] == 2 and sum(res["duct_classes"].values()) == 2
        assert res["models"] and res["around_duct"] == (kind == "ducting_rel")
