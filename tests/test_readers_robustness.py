"""Reader edge cases: fill values, packing, character variables, and the
metadata fallbacks for scnLv2 and ivmL2m."""
import numpy as np
import pytest
from scipy.io import netcdf_file

from cosmic2 import readers
from cosmic2.config import sampledata_dir


def _write(path, attrs: dict, variables: dict):
    """variables: name -> (array, {attr: value})"""
    f = netcdf_file(str(path), "w")
    for k, v in attrs.items():
        setattr(f, k, v)
    for name, (arr, vattrs) in variables.items():
        arr = np.asarray(arr)
        dim = f"n_{name}"
        f.createDimension(dim, arr.shape[0])
        var = f.createVariable(name, arr.dtype, (dim,))
        var[:] = arr
        for k, v in vattrs.items():
            setattr(var, k, v)
    f.close()
    return str(path)


def _atm_attrs():
    return dict(year=2026, month=7, day=19, hour=1, minute=2, second=3.5,
                lat=10.0, lon=20.0, irs=-1, bad="0")


def test_declared_fill_value_outside_the_sentinel_list_is_masked(tmp_path):
    p = _write(tmp_path / "atmPrf_C2E1.2026.200.01.02.G01_0001.0001_nc", _atm_attrs(), {
        "MSL_alt": (np.array([1.0, 2.0, 3.0]), {"units": "km"}),
        "Temp": (np.array([10.0, -1.0e30, 5.0], dtype="float32"),
                 {"units": "C", "_FillValue": -1.0e30}),
    })
    g = readers.load(p)
    assert np.isnan(g.data["Temp"][1])
    assert g.data["Temp"][0] == 10.0


def test_missing_value_attribute_is_masked(tmp_path):
    p = _write(tmp_path / "atmPrf_C2E1.2026.200.01.02.G01_0001.0001_nc", _atm_attrs(), {
        "MSL_alt": (np.array([1.0, 2.0, 3.0]), {"units": "km"}),
        "Pres": (np.array([900.0, -8888.0, 700.0]), {"units": "hPa", "missing_value": -8888.0}),
    })
    g = readers.load(p)
    assert np.isnan(g.data["Pres"][1])


def test_packed_variable_is_unpacked(tmp_path):
    p = _write(tmp_path / "atmPrf_C2E1.2026.200.01.02.G01_0001.0001_nc", _atm_attrs(), {
        "MSL_alt": (np.array([1.0, 2.0]), {"units": "km"}),
        "Ref": (np.array([30000, 25000], dtype="int16"),
                {"units": "N", "scale_factor": 0.01, "add_offset": 1.0}),
    })
    g = readers.load(p)
    np.testing.assert_allclose(g.data["Ref"], [301.0, 251.0])


def test_character_variable_does_not_break_loading(tmp_path):
    p = _write(tmp_path / "atmPrf_C2E1.2026.200.01.02.G01_0001.0001_nc", _atm_attrs(), {
        "MSL_alt": (np.array([1.0, 2.0]), {"units": "km"}),
        "station": (np.array([b"A", b"B"], dtype="S1"), {}),
    })
    g = readers.load(p)
    assert "station" not in g.data
    assert g.meta["n_levels"] == 2


def test_float32_default_netcdf_fill_is_masked():
    a = np.array([1.0, 9.96921e36], dtype="float32")
    out = readers._mask_fill(a)
    assert out[0] == 1.0 and np.isnan(out[1])


def test_scnlv2_without_s4_maximum_falls_back_to_ray_start(tmp_path):
    attrs = dict(year=2026, month=7, day=19, hour=6, minute=0, second=0.0,
                 lat_s4max_L1=-999.0, lon_s4max_L1=-999.0, lct_s4max_L1=-999.0,
                 lat_start=10.0, lon_start=30.0, s4max_L1=-999.0)
    p = _write(tmp_path / "scnLv2_2026.200.002.01.01.G01.SC001_0001.0001_nc", attrs, {
        "occheight": (np.array([100.0, 200.0]), {"units": "km"}),
        "s4_L1": (np.array([0.1, 0.2]), {}),
    })
    g = readers.load(p)
    assert g.meta["lat"] == 10.0 and g.meta["lon"] == 30.0
    # 06:00 UTC at 30 E is 08:00 local solar time
    assert g.meta["local_time"] == pytest.approx(8.0)


def test_scnlv2_is_placed_at_the_tangent_point_of_the_s4_maximum():
    """CDAAC's lat/lon/alt_s4max_L1 are where the satellite was; the record is
    placed at the ray's tangent point at the S4 maximum instead."""
    from cosmic2.radiosonde import great_circle_km
    for p in sorted(sampledata_dir().glob("scnLv2_*")):
        g = readers.load(str(p))
        d = g.data
        for i in range(d["time"].size):
            # the inertial positions turned Earth-fixed land on the file's
            # own satellite latitude and longitude ...
            x = readers.scn_earth_fixed(d, i, (d["x_LEO"][i], d["y_LEO"][i], d["z_LEO"][i]))
            lat, lon, _ = readers.geodetic(*x)
            assert lat == pytest.approx(d["lat"][i], abs=1e-3)
            assert (lon - d["lon"][i] + 180.0) % 360.0 - 180.0 == pytest.approx(0.0, abs=0.01)
            # ... and the closest point of the ray is at the file's tangent height
            assert readers.scn_tangent_point(d, i)[2] == pytest.approx(d["occheight"][i], abs=0.01)
        i = int(np.nanargmax(d["s4_L1"]))
        lat, lon, _ = readers.scn_tangent_point(d, i)
        m, ex = g.meta, g.meta["extras"]
        assert (m["lat"], m["lon"]) == (pytest.approx(lat), pytest.approx(lon))
        assert m["local_time"] == pytest.approx(
            ((m["epoch"] + d["time"][i]) % 86400 / 3600 + lon / 15) % 24)
        assert ex["tangent_height_s4max_L1_km"] == pytest.approx(d["occheight"][i])
        # the archive's position is the satellite's: about 570 km up and
        # nearly 2000 km from where its ray grazed the F region
        assert ex["satellite_alt_s4max_L1_km"] > 500
        assert great_circle_km(lat, lon, ex["satellite_lat_s4max_L1"],
                               ex["satellite_lon_s4max_L1"]) > 1500


def test_ivm_local_time_is_solar_not_magnetic():
    p = next(sampledata_dir().glob("ivmL2m_*"))
    g = readers.load(str(p))
    uts, lon = g.data["uts"], g.data["lon"]
    i = int(np.nanargmin(uts))
    expected = ((uts[i] % 86400) / 3600 + lon[i] / 15) % 24
    assert g.meta["local_time"] == pytest.approx(expected)
    assert g.meta["extras"]["median_mlt_h"] == pytest.approx(float(np.nanmedian(g.data["mlt"])))


def test_ivm_derived_solar_local_time():
    from cosmic2 import analysis
    g = readers.load(str(next(sampledata_dir().glob("ivmL2m_*"))))
    slt = analysis.derived_fields(g)["slt"]
    assert slt.shape == g.data["uts"].shape
    assert np.nanmin(slt) >= 0 and np.nanmax(slt) < 24
    assert slt[0] == pytest.approx(((g.data["uts"][0] % 86400) / 3600 + g.data["lon"][0] / 15) % 24)


def test_longitude_is_normalised_to_plus_minus_180(tmp_path):
    attrs = dict(_atm_attrs(), lon=350.0)
    p = _write(tmp_path / "atmPrf_C2E1.2026.200.01.02.G01_0001.0001_nc", attrs, {
        "MSL_alt": (np.array([1.0, 2.0]), {"units": "km"}),
    })
    assert readers.load(p).meta["lon"] == pytest.approx(-10.0)


def test_model_profiles_pair_with_their_atmprf():
    """echPrf (ECMWF) and avnPrf (NCEP) carry the occultation's own time and
    position and the same file stamp as its atmPrf."""
    import numpy as np
    from cosmic2 import readers
    from cosmic2.config import sampledata_dir
    for stamp in ("E23", "E34"):
        atm = readers.load(str(next(sampledata_dir().glob(f"atmPrf_*{stamp}_*"))))
        for prod in ("echPrf", "avnPrf"):
            g = readers.load(str(next(sampledata_dir().glob(f"{prod}_*{stamp}_*"))))
            assert g.product == prod and not g.warnings
            assert g.meta["stamp"] == atm.meta["stamp"]
            assert g.meta["time_utc"][:19] == atm.meta["time_utc"][:19]
            assert abs(g.meta["lat"] - atm.meta["lat"]) < 1e-6
            assert g.vertical == "MSL_alt" and g.meta["n_levels"] > 40
            ref = g.data["Ref"][np.isfinite(g.data["Ref"])]
            assert 200 < ref.max() < 450 and ref.min() > 0            # N-units
            # Smith-Weintraub holds in the model's own fields
            T = g.data["Temp"] + 273.15
            n = 77.6 * g.data["Pres"] / T + 3.73e5 * g.data["Vp"] / T ** 2
            ok = np.isfinite(n) & np.isfinite(g.data["Ref"]) & (g.data["MSL_alt"] < 30)
            assert np.median(np.abs(n[ok] / g.data["Ref"][ok] - 1)) < 0.01


def test_s4_descriptions_match_the_files_and_the_classes():
    """The S4 texts said 1-second windows and called 0.3 or 0.4 'strong
    turbulence'; the files say 10 s windows given every second, and the
    scintillation class calls 0.4-0.7 strong."""
    from pathlib import Path
    from cosmic2 import analysis, catalog, vocab
    for p in sorted(sampledata_dir().glob("scnLv2_*")):
        g = readers.load(str(p))
        assert float(g.attrs["calculation_time_interval"]) == 10.0
        assert np.allclose(np.diff(g.data["time"]), 1.0)
    assert "10 s sliding windows" in vocab.VAR_INFO["s4_L1"]["algorithm"]
    assert "10 s sliding windows" in catalog.PRODUCTS["scnLv2"].processing_chain
    assert "1-second" not in catalog.PRODUCTS["scnLv2"].processing_chain
    sev = [analysis.scintillation_summary(np.array([100.0]), np.array([s]))["severity"]
           for s in (0.19, 0.2, 0.39, 0.4, 0.69, 0.7)]
    assert sev == ["quiet", "moderate", "moderate", "strong", "strong", "severe"]
    js = (Path(readers.__file__).parent / "frontend" / "js" / "tabs_science.js").read_text(
        encoding="utf-8")
    assert "below 0.2 quiet, ' +\n   '0.2-0.4 moderate, 0.4-0.7 strong and 0.7 or more severe" in js
    assert "0.4-0.7 strong and 0.7 or more severe" in vocab.VAR_INFO["s4_L1"]["plain"]


def test_scintillation_files_name_their_satellite_like_the_others():
    """scnLv2 named its satellite LEO002 where atmPrf, wetPf2 and ionPrf say
    C2E2: LEO 001-006 are COSMIC-2 FM1-6 (on 2025-12-21 and 2026-06-19 every
    scnLv2 of LEO n matched an ionPrf of C2E n, tangent points 8 km apart)."""
    from cosmic2 import missions
    got = {}
    for p in sorted(sampledata_dir().glob("scnLv2_*")):
        g = readers.load(str(p))
        got[p.name[:22]] = (g.meta["sat"], readers.parse_filename(str(p))["sat"])
        assert missions.mission_of_sat(g.meta["sat"]) == "cosmic2"
    assert got == {"scnLv2_2026.200.002.01": ("C2E2", "C2E2"),
                   "scnLv2_2026.200.006.01": ("C2E6", "C2E6")}


def test_occultation_direction_from_irs_and_setting(tmp_path):
    # ionPrf says it in "setting" (1 setting, 0 rising), atmPrf/wetPf2 in irs
    ion = readers.load(str(next(sampledata_dir().glob("ionPrf_*"))))
    assert ion.attrs["setting"] == 1 and ion.meta["setting"] == "setting"
    assert readers._direction("C2E2", 0, 1) == "rising"
    assert readers._direction("C2E1", 1, -1) == "rising"
    assert readers._direction("C2E1", None, -1) is None
    # PAZ files say irs = 1, but PAZ records setting occultations only
    rising = dict(_atm_attrs(), irs=1)
    v = {"MSL_alt": (np.array([1.0, 2.0]), {})}
    assert readers.load(_write(tmp_path / "atmPrf_C2E1.2026.200.01.02.G01_0001.0001_nc",
                               rising, v)).meta["setting"] == "rising"
    assert readers.load(_write(tmp_path / "atmPrf_PAZ1.2026.200.01.02.G01_0001.0001_nc",
                               rising, v)).meta["setting"] == "setting"


def test_atmprf_geoid_undulation_is_in_metres():
    # atmPrf's rgeoid is in km, wetPf2's in m (same occultation)
    atm, wet = (readers.load(str(sorted(sampledata_dir().glob(f"{p}_*E23*"))[0]))
                for p in ("atmPrf", "wetPf2"))
    assert atm.meta["extras"]["geoid_undulation_m"] == pytest.approx(wet.attrs["rgeoid"])
