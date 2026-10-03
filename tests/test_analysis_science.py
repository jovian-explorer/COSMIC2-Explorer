"""Science checks on synthetic profiles with known answers."""
import numpy as np
import pytest

from cosmic2 import analysis, readers
from cosmic2.config import sampledata_dir


# ---------------------------------------------------------------------------
# numerical helpers
# ---------------------------------------------------------------------------

def test_gradient_tolerates_repeated_heights_and_top_down_order():
    z = np.array([5.0, 4.0, 3.0, 3.0, 2.0, 1.0])       # top-down, one repeat
    v = 2.0 * z
    g = analysis._gradient(z, v)
    assert np.all(np.isfinite(g))
    np.testing.assert_allclose(g, 2.0)


def test_log_interpolation_is_exact_for_an_exponential():
    z = np.arange(0.0, 21.0, 2.0)                       # 2 km levels
    p = 1000.0 * np.exp(-z / 7.0)
    grid = np.arange(0.0, 20.01, 0.5)
    exact = 1000.0 * np.exp(-grid / 7.0)
    lin = analysis.interp_to_grid(z, p, grid)
    log = analysis.interp_field(z, p, grid, "Pres")
    np.testing.assert_allclose(log, exact, rtol=1e-12)
    assert np.nanmax(np.abs(lin / exact - 1)) > 0.005   # linear is ~1 % high


def test_log_interpolation_falls_back_to_linear_on_nonpositive_values():
    z = np.array([0.0, 1.0, 2.0])
    ne = np.array([-5.0, 10.0, 100.0])
    out = analysis.interp_field(z, ne, np.array([0.5, 1.5]), "ELEC_dens")
    assert out[0] == pytest.approx(2.5)                 # linear across the negative
    assert out[1] == pytest.approx(np.sqrt(10.0 * 100.0))


def test_make_grid_rejects_nonpositive_step():
    with pytest.raises(ValueError):
        analysis.make_grid(60.0, 0.0)


# ---------------------------------------------------------------------------
# tropopause
# ---------------------------------------------------------------------------

def _two_layer(lapse_strat):
    z = np.arange(0.0, 30.01, 0.05)
    t = np.where(z <= 12.0, 300.0 - 6.5 * z, 300.0 - 6.5 * 12.0 - lapse_strat * (z - 12.0))
    return z, t


def test_wmo_tropopause_accepts_a_layer_at_exactly_two_k_per_km():
    z, t = _two_layer(2.0)
    tp = analysis.tropopause_wmo(z, t)
    assert tp["found"] and tp["height_km"] == pytest.approx(12.0, abs=0.15)


def test_wmo_tropopause_needs_the_full_layer_below_the_search_top():
    # Lapse rate drops below 2 K/km only 1 km under the search ceiling.
    z = np.arange(0.0, 45.0, 0.05)
    t = np.where(z <= 39.0, 300.0 - 6.5 * z, 300.0 - 6.5 * 39.0)
    tp = analysis.tropopause_wmo(z, t, z_max=40.0)
    assert not tp["found"]


# ---------------------------------------------------------------------------
# ionosphere
# ---------------------------------------------------------------------------

def _chapman(z, nm=1e6, hm=300.0, h=50.0):
    y = (z - hm) / h
    return nm * np.exp(0.5 * (1 - y - np.exp(-y)))


def test_vtec_below_peak_integrates_the_whole_column():
    z = np.arange(80.0, 600.0, 2.0)
    ne = _chapman(z)
    res = analysis.ionosphere_peak(z, ne)
    below = z <= res["hmF2_km"]
    expected = np.trapezoid(ne[below] * 1e6, z[below] * 1e3) / 1e16
    assert res["vtec_below_peak_TECU"] == pytest.approx(expected, rel=1e-9)


def test_peak_refinement_on_uneven_levels():
    z = np.sort(np.concatenate([np.arange(150.0, 600.0, 3.7), [301.3]]))
    ne = _chapman(z, hm=301.0)
    res = analysis.ionosphere_peak(z, ne)
    assert res["hmF2_km"] == pytest.approx(301.0, abs=0.3)
    assert res["NmF2_el_cm3"] == pytest.approx(1e6, rel=1e-3)


def test_monotonic_profile_has_no_f2_peak_or_e_layer():
    z = np.arange(90.0, 400.0, 2.0)
    ne = 1e3 * np.exp((z - 90.0) / 40.0)                # still rising at the top
    res = analysis.ionosphere_peak(z, ne)
    assert res["found"] is False and res["peak_at_profile_edge"] is True
    assert res["E_layer"] is None


def test_sample_ionprf_has_no_spurious_e_layer_at_150_km():
    g = readers.load(str(next(sampledata_dir().glob("ionPrf_*"))))
    res = analysis.ionosphere_peak(g.data["MSL_alt"], g.data["ELEC_dens"])
    assert res["found"]
    assert res["E_layer"] is None or res["E_layer"]["hmE_km"] < 149.0


# ---------------------------------------------------------------------------
# moisture
# ---------------------------------------------------------------------------

def _wet_granule():
    return readers.load(str(next(sampledata_dir().glob("wetPf2_*E23*"))), "wetPf2")


def test_iwv_pressure_stays_aligned_when_humidity_has_gaps():
    g = _wet_granule()
    ref = analysis.diagnostics(g)["column_water_vapour_mm"]
    # Blank the lowest levels of q only: the remaining q must be paired with
    # the pressures at the same heights, not with the first len(q) pressures.
    g.data["sph"] = g.data["sph"].copy()
    g.data["sph"][:40] = np.nan
    z, q, p = g.data["MSL_alt"], g.data["sph"], g.data["Pres"]
    ok = np.isfinite(q)
    expected = abs(np.trapezoid(q[ok] / 1000.0, p[ok] * 100.0)) / analysis.G0
    d = analysis.diagnostics(g)
    assert d["column_water_vapour_mm"] == pytest.approx(expected, rel=1e-9)
    assert d["column_water_vapour_mm"] < ref
    assert d["column_water_vapour_bottom_km"] == pytest.approx(float(z[ok].min()))


def test_density_counts_water_vapour():
    g = _wet_granule()
    rho = analysis.derived_fields(g)["density"]
    tk = g.data["Temp"] + 273.15
    p, e = g.data["Pres"] * 100.0, g.data["Vp"] * 100.0
    expected = (p - e) / (analysis.R_DRY * tk) + e / (analysis.R_VAPOUR * tk)
    np.testing.assert_allclose(rho, expected, rtol=1e-12)
    dry = p / (analysis.R_DRY * tk)
    assert np.nanmax(dry - rho) > 0                     # moist air is lighter


def test_composite_grouped_by_date_uses_the_index_date():
    paths = sorted(sampledata_dir().glob("wetPf2_*"))
    rows = [(str(p), {"product": "wetPf2", "good": True, "date": "2026-07-19"})
            for p in paths]
    comp = analysis.composite(rows, "Temp", group_by="date", min_count=1)
    assert list(comp.groups) == ["2026-07-19"]


def test_atmprf_temp_is_labelled_dry_and_never_averaged_with_wetpf2_temp():
    from cosmic2 import vocab
    assert vocab.info("Temp", "atmPrf")["label"] == "Dry temperature"
    assert vocab.info("Temp", "wetPf2")["label"] == "Temperature"
    assert vocab.info("Temp", "atmPrf")["name"] == "Temp"
    rows = [(str(p), {"product": p.name[:6], "good": True})
            for p in sorted(sampledata_dir().iterdir())
            if p.name.startswith(("atmPrf", "wetPf2"))]
    comp = analysis.composite(rows, "Temp", group_by="all", min_count=1)
    assert len(comp.groups) == 2
    assert all(g["n"] == 2 for g in comp.groups.values())
    only_atm = [r for r in rows if r[1]["product"] == "atmPrf"]
    c2 = analysis.composite(only_atm, "Temp", group_by="all", min_count=1)
    assert list(c2.groups) == ["all"]
    assert c2.to_json()["field_label"].startswith("Dry temperature")


def test_granule_variable_list_uses_product_meaning():
    g = readers.load(str(next(sampledata_dir().glob("atmPrf_*"))))
    labels = {v["name"]: v["label"] for v in g.variables()}
    assert labels["Temp"] == "Dry temperature" and labels["Pres"] == "Dry pressure"


def test_composite_spread_of_a_single_profile_is_undefined_not_zero():
    p = next(sampledata_dir().glob("wetPf2_*"))
    comp = analysis.composite([(str(p), {"product": "wetPf2", "good": True})],
                              "Temp", min_count=1)
    g = comp.groups["all"]
    assert np.isfinite(g["mean"]).any()
    assert not np.isfinite(g["std"]).any()
