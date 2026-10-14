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
    # 06:00 GPS time (05:59:42 UTC) at 30 E is 08:00 local solar time less 18 s
    assert g.meta["local_time"] == pytest.approx(8.0 - 18 / 3600)


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


def test_ivm_day_has_no_single_position_or_local_time():
    """A file is a whole day of the orbit: no median point stands for it."""
    g = readers.load(str(next(sampledata_dir().glob("ivmL2m_*"))))
    assert np.nanmax(g.data["uts"]) - np.nanmin(g.data["uts"]) > 23 * 3600
    assert g.meta["lat"] is None and g.meta["lon"] is None and g.meta["local_time"] is None
    assert g.meta["extras"]["lat_range"][0] < -20 < 20 < g.meta["extras"]["lat_range"][1]
    assert g.meta["extras"]["median_mlt_h"] == pytest.approx(float(np.nanmedian(g.data["mlt"])))


def test_ivm_map_uses_the_samples_where_they_were_taken():
    from cosmic2 import climatology
    p = next(sampledata_dir().glob("ivmL2m_*"))
    row = {"path": str(p), "product": "ivmL2m", "lat": None, "lon": None}
    res = climatology.diagnostic_map([row], "insitu.ion_dens_median_Ncc", workers=1)
    assert res["insitu_samples"] and 1300 < res["n"] <= 1441    # a sample a minute
    filled = np.isfinite(np.asarray(res["mean"], float))
    assert filled.sum() >= 30                                   # the orbit's cells, not one


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
    # 1 is setting in both irs (atmPrf, wetPf2) and setting (ionPrf), as
    # CDAAC's atmPrf format says and same-occultation ionPrf confirm
    ion = readers.load(str(next(sampledata_dir().glob("ionPrf_*"))))
    assert ion.attrs["setting"] == 1 and ion.meta["setting"] == "setting"
    assert readers._direction(0) == "rising"
    assert readers._direction(-1) == "rising"
    assert readers._direction(None) is None
    v = {"MSL_alt": (np.array([1.0, 2.0]), {})}
    for sat, irs, want in (("C2E1", 1, "setting"), ("C2E1", -1, "rising"),
                           ("PAZ1", 1, "setting")):
        p = tmp_path / f"atmPrf_{sat}.2026.200.01.02.G01_0001.0001_nc"
        assert readers.load(_write(p, dict(_atm_attrs(), irs=irs), v)).meta["setting"] == want


def test_atmprf_geoid_undulation_is_in_metres():
    # atmPrf's rgeoid is in km, wetPf2's in m (same occultation)
    atm, wet = (readers.load(str(sorted(sampledata_dir().glob(f"{p}_*E23*"))[0]))
                for p in ("atmPrf", "wetPf2"))
    assert atm.meta["extras"]["geoid_undulation_m"] == pytest.approx(wet.attrs["rgeoid"])


def test_second_frequency_text_covers_galileo_e5a():
    # COSMIC-2 tracks Galileo on E1/E5a (freq2 L5Q), not only GPS L1/L2
    from cosmic2 import vocab
    g = readers.load(str(next(sampledata_dir().glob("atmPrf_*E23*"))))
    assert g.attrs["freq2"] == "L5Q"
    assert "1176.45 MHz for Galileo E5a" in vocab.VAR_INFO["Bend_ang2"]["plain"]


def test_ionprf_whose_edmax_is_not_the_f2_peak_is_placed_at_the_f2_peak(tmp_path):
    """CDAAC's edmax can be an E-region maximum (5 of 690 COSMIC-2 ionPrf of
    2026-09-18) or a spike near the orbit (COSMIC-1, 2019-12-10, 778 km)."""
    z = np.arange(80.0, 800.0, 10.0)
    y = (z - 300.0) / 50.0
    ne = 1.5e5 * np.exp(0.5 * (1 - y - np.exp(-y)))
    lat, lon = 10.0 - z / 100.0, -101.0 + z / 25.0          # the tangent point drifts
    i300 = int(np.argmin(abs(z - 300.0)))
    attrs = dict(year=2026, month=9, day=18, hour=9, minute=3, second=0.0, setting=1,
                 edmaxlct=2.0, edmax=2e5)
    p = tmp_path / "ionPrf_C2E4.2026.261.09.03.G06_0001.0001_nc"

    def place(hm, dens):
        k = int(np.argmin(abs(z - hm)))
        v = {"MSL_alt": (z, {}), "ELEC_dens": (dens, {}), "GEO_lat": (lat, {}),
             "GEO_lon": (lon, {})}
        return readers.load(_write(p, dict(attrs, edmaxalt=hm, edmaxlat=lat[k],
                                           edmaxlon=lon[k]), v)).meta

    e_region = ne.copy()
    e_region[0] = 2e5
    m = place(80.0, e_region)
    assert (m["lat"], m["lon"]) == pytest.approx((lat[i300], lon[i300]))
    assert m["local_time"] == pytest.approx((9.05 - 18 / 3600 + lon[i300] / 15.0) % 24.0)
    spike = ne.copy()
    k = int(np.argmin(abs(z - 780.0)))
    spike[k - 1:k + 2] = [-2.8e5, 4.75e5, 1.2e4]
    m = place(780.0, spike)
    assert (m["lat"], m["lon"]) == pytest.approx((lat[i300], lon[i300]))
    # an edmax at the F2 peak stays where CDAAC put it; edmaxlct is not used
    m = place(300.0, ne)
    assert (m["lat"], m["lon"]) == pytest.approx((lat[i300], lon[i300]))
    assert m["local_time"] == pytest.approx((9.05 - 18 / 3600 + lon[i300] / 15.0) % 24.0)


def test_cdaac_times_are_gps_time_and_read_as_utc():
    import datetime as dt
    import math
    gps0 = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc).timestamp()
    a = readers.load(str(next(sampledata_dir().glob("atmPrf_*E23*"))))
    # the calendar attributes are start_time (GPS seconds) with no leap seconds
    assert a.meta["epoch"] == pytest.approx(gps0 + a.attrs["start_time"] + 0.112 - 18, abs=0.01)
    assert a.meta["time_utc"].startswith("2026-07-18T23:57:16")
    # scnLv2: the Earth rotation angle at the file's first sample (gast1)
    # matches its time as UTC = header - 18 s, not the header itself
    s = readers.load(str(next(sampledata_dir().glob("scnLv2_*G01*"))))
    t = s.meta["epoch"] / 86400.0 + 2440587.5 - 2451545.0
    gmst = math.radians((67310.54841 + (876600 * 3600 + 8640184.812866) * t / 36525)
                        % 86400 / 240)
    diff = (gmst - s.data["gast1"][0] + math.pi) % (2 * math.pi) - math.pi
    assert abs(diff) / 7.2921159e-5 < 1.5          # seconds of time


def test_ivm_nonpositive_ion_density_is_missing():
    g = readers.load(str(next(sampledata_dir().glob("ivmL2m_*"))))
    n = g.data["ion_dens"]
    assert not (n <= 0).any()
    assert g.meta["extras"]["n_nonpositive_ion_dens"] == 604
    assert np.isfinite(g.data["orig_ion_density"][np.isnan(n)]).sum() >= 604


def test_atmprf_local_time_is_computed_not_cdaacs_minute_value():
    # timloc is the local time of the start cut to the minute in GPS time
    g = readers.load(str(next(sampledata_dir().glob("atmPrf_*E23*"))))
    lt = readers._local_time(g.attrs["lon"], g.meta["epoch"])
    assert g.meta["local_time"] == pytest.approx(lt)
    gps0 = 315964800.0
    t = gps0 + g.attrs["start_time"]
    assert g.attrs["timloc"] == pytest.approx(readers._local_time(g.attrs["lon"], t - t % 60), abs=1e-6)


def test_imp_height_corr_is_described_as_a_correction_not_a_height():
    from cosmic2 import vocab
    g = readers.load(str(next(sampledata_dir().glob("atmPrf_*E23*"))))
    assert np.nanmax(np.abs(g.data["Imp_height_corr"])) < 0.01      # km
    v = vocab.VAR_INFO["Imp_height_corr"]
    assert v["role"] != vocab.VERTICAL and "correction" in v["label"]


def test_ivm_drift_texts_follow_the_file_sign_conventions():
    from scipy.io import netcdf_file
    from cosmic2 import vocab
    f = netcdf_file(str(next(sampledata_dir().glob("ivmL2m_*"))), "r", mmap=False)
    assert b"+up" in f.variables["iv_mer"].long_name
    assert b"+north" in f.variables["iv_par"].long_name
    f.close()
    assert "positive upward" in vocab.VAR_INFO["iv_mer"]["plain"]
    assert "positive northward" in vocab.VAR_INFO["iv_par"]["plain"]


def test_scnlv2_without_ray_geometry_gets_a_computed_local_time(tmp_path):
    attrs = dict(year=2026, month=7, day=19, hour=15, minute=16, second=19.0,
                 lat_s4max_L1=16.28, lon_s4max_L1=163.97, lct_s4max_L1=15.38, s4max_L1=0.9)
    p = _write(tmp_path / "scnLv2_2026.200.002.01.01.G01.SC001_0001.0001_nc", attrs, {
        "occheight": (np.array([100.0, 200.0]), {"units": "km"}),
        "s4_L1": (np.array([0.1, 0.9]), {}),
    })
    m = readers.load(p).meta
    assert m["local_time"] == pytest.approx(readers._local_time(163.97, m["epoch"]), abs=1e-4)
    assert abs(m["local_time"] - 15.38) > 10.0


def test_ionprf_hscale_is_kept_as_the_scale_height_at_orbit():
    g = readers.load(str(next(sampledata_dir().glob("ionPrf_*"))))
    ex = g.meta["extras"]
    assert "scale_height_km" not in ex
    # CDAAC fills hscale only when icalib = 0; this file has icalib = 1
    assert g.attrs["icalib"] == 1 and ex["scale_height_at_orbit_km"] is None


def test_truncated_file_is_refused_not_read_as_zeros(tmp_path):
    src = next(sampledata_dir().glob("ivmL2m_*"))
    p = tmp_path / src.name
    p.write_bytes(src.read_bytes()[: 10_000_000])
    with pytest.raises(ValueError, match="truncated"):
        readers.load(str(p))


def test_ap_pot_is_named_as_the_file_names_it():
    from scipy.io import netcdf_file
    from cosmic2 import vocab
    f = netcdf_file(str(next(sampledata_dir().glob("ivmL2m_*"))), "r", mmap=False)
    assert f.variables["ap_pot"].long_name == b"Aperture plane potential"
    f.close()
    assert vocab.VAR_INFO["ap_pot"]["label"] == "Aperture-plane potential"


def test_podtc2_and_scn1c2_get_satellite_and_position_from_their_attributes(tmp_path):
    attrs = dict(year=2026, month=9, day=27, hour=0, minute=2, second=36.0, leo_id=2,
                 prn_id=10, conid="G", lat_start=-11.663, lon_start=23.304)
    v = {"occheight": (np.array([100.0, 200.0]), {"units": "km"})}
    m = readers.load(_write(tmp_path / "podTc2_C2E2.2026.270.00.02.0027.G10.01_0001.0001_nc",
                            attrs, v)).meta
    assert (m["sat"], m["occ_prn"]) == ("C2E2", "G10")
    assert (m["lat"], m["lon"]) == pytest.approx((-11.663, 23.304))
    assert m["local_time"] == pytest.approx(readers._local_time(23.304, m["epoch"]))
    assert readers.parse_filename("scn1c2_2026.270.002.01.02.G06.OS006_0001.0001_nc")["sat"] == "C2E2"
