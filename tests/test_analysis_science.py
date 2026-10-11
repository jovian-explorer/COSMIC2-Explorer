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


def test_negative_bottomside_densities_do_not_subtract_tec():
    # Abel-inversion artefact: a long negative bottomside (seen on real ionPrf
    # profiles) must count as zero, as in CDAAC's own tec0.
    z = np.arange(50.0, 600.0, 2.0)
    ne = _chapman(z)
    noisy = np.where(z < 150.0, -4e4, ne)
    res = analysis.ionosphere_peak(z, noisy)
    clean = np.where(z < 150.0, 0.0, ne)
    expected = np.trapezoid(clean * 1e6, z * 1e3) / 1e16
    assert res["vtec_profile_TECU"] == pytest.approx(expected, rel=1e-9)
    assert res["vtec_below_peak_TECU"] > 0


def test_profile_tec_matches_cdaac_tec0_on_bundled_sample():
    g = readers.load(str(next(sampledata_dir().glob("ionPrf_*"))))
    res = analysis.ionosphere_peak(g.data["MSL_alt"], g.data["ELEC_dens"])
    assert res["vtec_profile_TECU"] == pytest.approx(
        g.meta["extras"]["tec_profile_TECU"], rel=0.03)


def _moist_artefact_profile():
    """Dry-temperature-like profile: a spurious near-isothermal layer at
    6-8.5 km (~250 K, the signature of water vapour in atmPrf "Temp") below
    a real tropical tropopause at 16 km."""
    z = np.arange(0.0, 30.0, 0.05)
    t = np.interp(z, [0.0, 6.0, 8.5, 16.0, 30.0],
                  [285.0, 252.0, 249.0, 195.0, 215.0])
    p = 1013.25 * np.exp(-z / 7.5)
    return z, t, p


def test_dry_temperature_guard_skips_the_moist_layer_artefact():
    z, t, p = _moist_artefact_profile()
    bare = analysis.tropopause_wmo(z, t, p)
    assert bare["height_km"] == pytest.approx(6.0, abs=0.2)
    guarded = analysis.tropopause_wmo(z, t, p, t_max_k=analysis.DRY_TROPOPAUSE_T_MAX_K)
    assert guarded["height_km"] == pytest.approx(16.0, abs=0.2)
    assert "235 K" in guarded["method"]


@pytest.mark.parametrize("product, expected_km", [("atmPrf", 16.0), ("wetPf2", 6.0)])
def test_diagnostics_guard_only_dry_temperature(product, expected_km):
    z, t, p = _moist_artefact_profile()
    g = readers.Granule(product, "x", {"extras": {}}, {}, {},
                        {"MSL_alt": z, "Temp": t - 273.15, "Pres": p},
                        {"Temp": "C"})
    tp = analysis.diagnostics(g)["tropopause"]
    assert tp["height_km"] == pytest.approx(expected_km, abs=0.2)


def test_fields_with_derives_only_when_asked():
    g = readers.load(str(next(sampledata_dir().glob("wetPf2_*"))))
    native = analysis.fields_with(g, "Temp", "MSL_alt")
    assert "theta" not in native and "Temp" in native
    derived = analysis.fields_with(g, "theta", "MSL_alt")
    np.testing.assert_array_equal(derived["theta"], analysis.derived_fields(g)["theta"])


def test_mean_uncertainty_textbook_value_and_coverage():
    """sem = s/sqrt(n) and the 95 % interval uses Student's t (t(0.975, 9) =
    2.262 in every t table); on Gaussian samples the interval covers the true
    mean in 95 % of draws."""
    import numpy as np
    from cosmic2.analysis import mean_uncertainty
    x = np.array([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    m, s, n = x.mean(), x.std(ddof=1), np.array([10])
    sem, lo, hi = mean_uncertainty(np.array([m]), np.array([s]), n)
    assert sem[0] == pytest.approx(s / np.sqrt(10))
    assert (hi[0] - m) / sem[0] == pytest.approx(2.262, abs=5e-4)
    assert np.isnan(mean_uncertainty(np.array([1.0]), np.array([np.nan]), np.array([1]))[0][0])
    rng = np.random.default_rng(42)
    draws = rng.normal(5.0, 2.0, size=(20000, 6))
    mu, sd = draws.mean(axis=1), draws.std(axis=1, ddof=1)
    _, lo, hi = mean_uncertainty(mu, sd, np.full(mu.size, 6))
    cover = np.mean((lo <= 5.0) & (5.0 <= hi))
    assert cover == pytest.approx(0.95, abs=0.006)


def test_composite_reports_the_confidence_interval_of_the_mean(tmp_path):
    import numpy as np
    from cosmic2 import analysis
    paths = sorted(str(p) for p in sampledata_dir().glob("wetPf2_*"))
    comp = analysis.composite([(p, {"good": True, "lat": 0.0}) for p in paths], "Temp",
                              group_by="all", top_km=20, step_km=1.0, min_count=2).to_json()
    g = next(iter(comp["groups"].values()))
    for k in range(len(comp["grid"])):
        if g["mean"][k] is None:
            continue
        n = g["n_per_level"][k]
        assert g["sem"][k] == pytest.approx(g["std"][k] / np.sqrt(n))
        assert g["ci95_lo"][k] < g["mean"][k] < g["ci95_hi"][k]


def test_robust_screen_drops_layer_outliers_not_spikes_or_small_groups():
    from cosmic2.analysis import robust_screen, make_grid
    grid = make_grid(20.0, 0.5)
    rng = np.random.default_rng(0)
    m = 250.0 + rng.normal(0.0, 1.0, size=(60, grid.size))
    layer = m[0].copy(); layer[(grid >= 5) & (grid <= 8)] += 10.0     # 10 sigma over 3 km
    thin = m[1].copy(); thin[(grid >= 5) & (grid < 5.6)] += 10.0      # only 0.5 km deep
    spike = m[2].copy(); spike[grid == 10.0] += 50.0
    keep = robust_screen(np.vstack([m, layer, thin, spike]), grid, k=5)
    assert keep[:60].mean() > 0.98
    assert not keep[60] and keep[61] and keep[62]
    # Gaussian noise alone: nothing dropped
    assert robust_screen(m, grid, k=5).all()
    # too few profiles to judge: nothing dropped
    assert robust_screen(np.vstack([m[:5], layer]), grid, k=5).all()


def test_composite_reports_screened_profiles(monkeypatch):
    from cosmic2 import analysis
    grid = analysis.make_grid(10.0, 0.5)
    rng = np.random.default_rng(1)
    cols = {f"p{i}": 250 + rng.normal(0, 1, grid.size) for i in range(20)}
    cols["bad"] = 250 + rng.normal(0, 1, grid.size) + np.where(grid > 3, 15.0, 0.0)
    monkeypatch.setattr(analysis, "_composite_column",
                        lambda t: ("all", cols[t[0]], "K", "Temp", ""))
    rows = [(k, {"good": True}) for k in cols]
    plain = analysis.composite(rows, "Temp", top_km=10, step_km=0.5, workers=1)
    comp = analysis.composite(rows, "Temp", top_km=10, step_km=0.5, workers=1, screen_k=5)
    assert plain.n_profiles == 21 and comp.n_profiles == 20
    assert comp.to_json()["screened_out"] == {"all": 1}
    assert abs(np.nanmean(comp.groups["all"]["mean"][grid > 3]) - 250) < 0.5


def test_refractivity_is_interpolated_in_log_space():
    """Model refractivity comes on levels 2-3 km apart above 17 km (NCEP);
    straight-line interpolation of N = N0 exp(-z/H) was 2 % too large there."""
    from cosmic2.analysis import interp_field
    z = np.arange(15.0, 41.0, 2.7)
    n = 300.0 * np.exp(-z / 6.5)
    grid = np.arange(16.0, 40.0, 0.1)
    truth = 300.0 * np.exp(-grid / 6.5)
    for name in ("Ref", "ref"):
        got = interp_field(z, n, grid, name)
        assert np.nanmax(np.abs(got / truth - 1)) < 1e-9


def _pbl_profile(knots_z, knots_n, step=0.01):
    z = np.arange(knots_z[0], knots_z[-1] + step / 2, step)
    return z, np.interp(z, knots_z, knots_n)


def test_boundary_layer_top_is_the_steepest_fall_of_refractivity():
    """Ao et al. (2012): where N falls fastest, from 300 m straight-line fits
    (Guo et al. 2011); accepted only for a profile reaching 0.5 km, a top
    below 3.5 km and a fall steeper than 50 N-units/km."""
    # mixed layer -20 N/km, capping layer 1.2-1.5 km at -100, free
    # troposphere -35 above
    knots_z, knots_n = [0.0, 1.2, 1.5, 6.0], [320.0, 296.0, 266.0, 108.5]
    r = analysis.boundary_layer_height(*_pbl_profile(knots_z, knots_n))
    assert r["found"] and r["height_km"] == pytest.approx(1.35, abs=0.006)
    assert r["gradient"] == pytest.approx(-100.0, abs=0.5)
    assert r["sharpness"] == pytest.approx(100.0 / 157.0, abs=0.01)
    # a radiosonde reporting only five levels gives the same top
    sparse = analysis.boundary_layer_height(np.array([0.0, 1.2, 1.5, 3.0, 6.0]),
                                            np.array([320.0, 296.0, 266.0, 213.5, 108.5]))
    assert sparse["found"] and sparse["height_km"] == pytest.approx(1.35, abs=0.006)
    # a profile that stops above 0.5 km is not used
    z, n = _pbl_profile(knots_z, knots_n)
    r = analysis.boundary_layer_height(z[z >= 0.8], n[z >= 0.8])
    assert not r["found"] and "0.5 km" in r["reason"]
    # a weak top (-45 N/km) is not a boundary-layer top
    r = analysis.boundary_layer_height(*_pbl_profile(knots_z, [320.0, 296.0, 282.5, 125.0]))
    assert not r["found"] and r["height_km"] is None and "sharp" in r["reason"]
    # nor is a sharp layer above 3.5 km
    r = analysis.boundary_layer_height(*_pbl_profile([0.0, 3.7, 4.0, 6.0],
                                                     [320.0, 190.5, 160.5, 90.5]))
    assert not r["found"]


def test_boundary_layer_top_only_from_observed_refractivity():
    """wetPf2's refractivity is the 1D-Var analysis: no boundary-layer top."""
    seen = set()
    for p in sorted(sampledata_dir().glob("*_nc")):
        if p.name.startswith(("atmPrf_", "wetPf2_")):
            g = readers.load(str(p))
            seen.add(g.product)
            assert ("boundary_layer" in analysis.diagnostics(g)) == (g.product == "atmPrf")
    assert seen == {"atmPrf", "wetPf2"}


def test_plasma_frequency_coefficient_from_the_constants():
    from scipy.constants import e, epsilon_0, m_e, pi
    exact = (e * e / (epsilon_0 * m_e)) ** 0.5 / (2 * pi) * 1e-3   # MHz per sqrt(cm-3)
    assert analysis.PLASMA_FREQ_COEFF == pytest.approx(exact, rel=1e-6)


def test_tec_columns_start_at_80_km_like_cdaac_tec0():
    # Abel residue below 80 km (1e4-1e5 el/cm3 at 30-60 km on real ionPrf)
    # is left out, as in CDAAC's tec0
    z = np.arange(30.0, 600.0, 2.0)
    ne = np.where(z < 80.0, 5e4, _chapman(z))
    res = analysis.ionosphere_peak(z, ne)
    top = z >= 80.0
    expected = np.trapezoid(ne[top] * 1e6, z[top] * 1e3) / 1e16
    assert res["vtec_profile_TECU"] == pytest.approx(expected, rel=1e-9)


def test_bending_angle_is_interpolated_in_log_space():
    z = np.array([30.0, 32.0])
    b = 1e-3 * np.exp(-z / 6.0)
    mid = analysis.interp_field(z, b, np.array([31.0]), "Bend_ang")[0]
    assert mid == pytest.approx(1e-3 * np.exp(-31.0 / 6.0), rel=1e-9)


def test_composite_keeps_observations_and_ecmwf_apart():
    paths = [(str(next(sampledata_dir().glob(f"{p}_*E23*"))), {"product": p, "good": True})
             for p in ("wetPf2", "echPrf")]
    comp = analysis.composite(paths, "Temp", top_km=10.0, step_km=1.0, min_count=1, workers=1)
    assert sorted(comp.groups) == ["all - Temperature", "all - Temperature (ECMWF)"]


def test_composite_keeps_dry_and_moist_derived_fields_apart():
    paths = [(str(next(sampledata_dir().glob(f"{p}_*E23*"))), {"product": p, "good": True})
             for p in ("wetPf2", "atmPrf")]
    comp = analysis.composite(paths, "theta", top_km=10.0, step_km=1.0, min_count=1, workers=1)
    assert sorted(comp.groups) == ["all - Potential temperature",
                                   "all - Potential temperature (from dry temperature)"]
    one = analysis.composite(paths[1:], "theta", top_km=10.0, step_km=1.0, min_count=1, workers=1)
    assert list(one.groups) == ["all"]
    assert one.to_json()["field_label"] == "Potential temperature (from dry temperature) [K]"


def test_composite_groups_keep_a_fixed_order(monkeypatch):
    # latitude bands south to north whatever their sizes
    cols = {f"p{i}": (lat, np.ones(3)) for i, lat in enumerate([50, 50, 50, -45, 0])}
    monkeypatch.setattr(analysis, "_composite_column", lambda t: (
        analysis.band_of(cols[t[0]][0]), cols[t[0]][1], "K", "Temp", "Temperature"))
    comp = analysis.composite([(k, {"good": True}) for k in cols], "Temp",
                              top_km=2.0, step_km=1.0, min_count=1, workers=1)
    assert list(comp.groups) == ["S mid-latitude", "Equatorial", "N mid-latitude"]


def test_diagnostics_row_carries_the_occultation_stamp():
    # the scatter uses it to say which occultations are drawn twice
    m = readers.quick_meta(str(next(sampledata_dir().glob("atmPrf_*E23*"))))
    m["id"] = "x"
    assert analysis.diagnostics_row(m)["stamp"] == "C2E1.2026.200.00.00.E23"
