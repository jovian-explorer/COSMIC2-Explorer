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
