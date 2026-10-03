"""Exported numbers must read back at full precision."""
import csv

import numpy as np

from cosmic2 import analysis, exporters, readers
from cosmic2.config import sampledata_dir


def _wet_meta():
    p = next(sampledata_dir().glob("wetPf2_*E23*"))
    return readers.quick_meta(str(p), "wetPf2")


def test_fmt_round_trips_small_values():
    for v in (1.234567891e-5, 3.2743671931e-4, 287.0578, -0.000012345678):
        assert float(exporters._fmt(v)) == v
    assert exporters._fmt(float("nan")) == ""


def test_profiles_csv_keeps_full_precision_of_derived_fields():
    meta = _wet_meta()
    res = exporters.export_profiles_csv([meta], ["buoyancy_freq_sq"],
                                        basename="precision_test")
    try:
        with open(res["path"], encoding="utf-8") as fh:
            rows = list(csv.reader(line for line in fh if not line.startswith("#")))
        col = rows[0].index("buoyancy_freq_sq")
        got = np.array([float(r[col]) if r[col] else np.nan for r in rows[1:]])
        g = readers.load(meta["path"], "wetPf2")
        want = analysis.derived_fields(g)["buoyancy_freq_sq"][:got.size]
        np.testing.assert_array_equal(got, want)
    finally:
        import os
        os.remove(res["path"])


def test_composite_json_is_not_rounded():
    grid = np.array([0.0, 1.0])
    vals = np.array([1.23456789e-5, 2.5e-7])
    comp = analysis.Composite(
        "buoyancy_freq_sq", "MSL_alt", grid,
        {"all": {"n": 3, "count": np.array([3, 3]), "mean": vals, "median": vals,
                 "std": vals, "p10": vals, "p90": vals}}, 3)
    out = comp.to_json()
    assert out["groups"]["all"]["mean"] == [1.23456789e-5, 2.5e-7]


def test_netcdf_export_uses_udunits_strings():
    import os
    from netCDF4 import Dataset
    meta = _wet_meta()
    res = exporters.export_netcdf([meta], ["Temp", "density", "buoyancy_freq_sq", "sph"],
                                  top_km=20.0, step_km=1.0, basename="cf_test")
    try:
        with Dataset(res["path"]) as ds:
            assert ds["Temp"].units == "degree_Celsius"     # "C" is the coulomb
            assert ds["density"].units == "kg m-3"
            assert ds["buoyancy_freq_sq"].units == "s-2"
            assert ds["sph"].units == "g kg-1"
            assert ds["MSL_alt"].units == "km"
    finally:
        os.remove(res["path"])


def test_netcdf_states_the_meaning_of_temp_per_product():
    import os
    from netCDF4 import Dataset
    metas = [readers.quick_meta(str(p)) for p in sorted(sampledata_dir().iterdir())
             if p.name.startswith(("atmPrf", "wetPf2"))]
    atm = [m for m in metas if m["product"] == "atmPrf"]
    res = exporters.export_netcdf(atm, ["Temp"], top_km=20.0, step_km=1.0, basename="q1")
    res2 = exporters.export_netcdf(metas, ["Temp"], top_km=20.0, step_km=1.0, basename="q2")
    try:
        with Dataset(res["path"]) as ds:
            assert ds["Temp"].long_name == "Dry temperature"
            assert list(ds["product"][:]) == ["atmPrf", "atmPrf"]
        with Dataset(res2["path"]) as ds:
            assert "product=atmPrf: Dry temperature" in ds["Temp"].comment
            assert "product=wetPf2: Temperature" in ds["Temp"].comment
    finally:
        os.remove(res["path"])
        os.remove(res2["path"])


def test_csv_header_licence_is_readable_text():
    from cosmic2 import exporters
    from cosmic2.config import DATA_LICENSES
    line = next(l for l in exporters._header_lines(exporters.provenance([]))
                if l.startswith("Software License"))
    assert "{" not in line and "'" not in line
    if isinstance(DATA_LICENSES.get("software"), dict):
        assert DATA_LICENSES["software"]["name"] in line
