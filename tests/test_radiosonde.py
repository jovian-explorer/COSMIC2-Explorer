"""Radiosonde comparison (NOAA IGRA v2): file parsing, sonde physics,
height conversion and the colocation/difference pipeline, all offline."""
import datetime as dt
import json
import os
import urllib.error
import urllib.request

import numpy as np
import pytest

from cosmic2 import radiosonde, readers
from cosmic2.config import sampledata_dir

BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")

# Real lines from igra2-station-list.txt and USM00072201-data-beg2026.txt
STATIONS = (
    "AEM00041217  24.4333   54.6500   16.0    ABU DHABI INTERNATIONAL AIRPOR 1983 2026  41271\n"
    "USM00072201  24.5531  -81.7886   13.4 FL KEY WEST/INT.; FL              1919 2026  69391\n")
SOUNDING = """#USM00072201 2026 06 20 00 2305    7 ncdc-nws ncdc-gts  245531  -817886
21     0 101507B   13   307B  710    58   135    31
10    26 100000   147B  290B  772    44   132    33
10   243  92500   836B  227B  910    15    66    25
30 -9999  -9999 26700 -9999 -9999 -9999    90   159
10   520  85000  1571B  197B  615    76    85    32
10  1053  70000  3219B  115B  412   127    76    33
20  1236  65875  3723B   75B  433   117    47    50
#USM00072201 2026 06 20 12 1110    5 ncdc-nws ncdc-gts  245531  -817886
21     0 101500B   13   280B  800    40   135    31
10    26 100000   147B  270B  772    44   132    33
10   243  92500   836B  217B  910    15    66    25
10   520  85000  1571B  187B  615    76    85    32
10  1053  70000  3219B  105B  412   127    76    33
"""


def test_station_list_and_sounding_parsing():
    st = radiosonde.parse_station_list(STATIONS)
    assert [s["id"] for s in st] == ["AEM00041217", "USM00072201"]
    assert st[1]["lat"] == pytest.approx(24.5531) and st[1]["lon"] == pytest.approx(-81.7886)
    assert st[1]["last_year"] == 2026 and st[1]["name"].startswith("KEY WEST")
    snd = radiosonde.parse_soundings(SOUNDING)
    assert len(snd) == 2
    a = snd[0]
    # nominal 00 UTC on the 20th, launched 23:05 on the 19th
    assert a["time"] == dt.datetime(2026, 6, 19, 23, 5, tzinfo=dt.timezone.utc)
    assert snd[1]["time"] == dt.datetime(2026, 6, 20, 11, 10, tzinfo=dt.timezone.utc)
    assert a["lat"] == pytest.approx(24.5531) and a["lon"] == pytest.approx(-81.7886)
    # the wind-only level (no pressure) is dropped
    assert a["p_hpa"].tolist() == [1015.07, 1000.0, 925.0, 850.0, 700.0, 658.75]
    assert a["temp_c"][0] == pytest.approx(30.7) and a["rh_pct"][0] == pytest.approx(71.0)
    assert a["dpd_c"][0] == pytest.approx(5.8) and a["gph_m"][3] == 1571


def test_sonde_physics_by_hand():
    s = radiosonde.parse_soundings(SOUNDING)[0]
    pr = radiosonde.sonde_profile(s)
    t, td, p = 30.7, 30.7 - 5.8, 1015.07
    e = 6.112 * np.exp(17.67 * td / (td + 243.5))
    tk = t + 273.15
    assert pr["e_hpa"][0] == pytest.approx(e)
    assert pr["ref_N"][0] == pytest.approx(77.6 * p / tk + 3.73e5 * e / tk ** 2)
    assert pr["sph_gkg"][0] == pytest.approx(622 * e / (p - 0.378 * e))
    # relative humidity from the dew point agrees with the reported 71 %
    assert 100 * e / (6.112 * np.exp(17.67 * t / (t + 243.5))) == pytest.approx(71, abs=1.5)
    assert pr["gph_km"][0] == pytest.approx(0.013)


def test_geopotential_conversion_matches_wetpf2_gph():
    """atmPrf heights are converted with Mahoney's normal gravity; wetPf2
    carries CDAAC's own geopotential height to check it against."""
    wet = [p for p in sampledata_dir().iterdir() if p.name.startswith("wetPf2")]
    assert wet
    for p in wet:
        g = readers.load(str(p))
        z, gph = g.data["MSL_alt"], g.data["gph"]
        ok = np.isfinite(gph) & (z <= 30)
        conv = radiosonde.geopotential_height_km(z[ok], g.meta["lat"])
        assert np.max(np.abs(conv - gph[ok])) < 0.005     # 5 m


def test_compare_with_a_sonde_that_is_the_occultation(monkeypatch):
    """A synthetic sonde built from a wetPf2 profile's own T, p and vapour
    pressure must come out with ~zero differences; one 1 K warmer, +1 K."""
    p = next(q for q in sampledata_dir().iterdir() if q.name.startswith("wetPf2"))
    g = readers.load(str(p))
    d = g.data
    ok = np.isfinite(d["Temp"]) & np.isfinite(d["Vp"]) & np.isfinite(d["Pres"])
    tc, e = d["Temp"][ok], d["Vp"][ok]
    # dew point from e, inverting Bolton
    ln = np.log(e / 6.112)
    td = 243.5 * ln / (17.67 - ln)
    t0 = dt.datetime.fromisoformat(g.meta["time_utc"].replace("Z", "+00:00"))
    row = {"id": "x", "path": str(p), "product": "wetPf2", "file_name": p.name,
           "time_utc": g.meta["time_utc"], "lat": g.meta["lat"], "lon": g.meta["lon"],
           "good": True}

    def sonde(warm):
        return {"station": "TEST0000001", "time": t0 + dt.timedelta(hours=1),
                "lat": g.meta["lat"] + 0.5, "lon": g.meta["lon"],
                "p_hpa": d["Pres"][ok], "gph_m": d["gph"][ok] * 1000.0,
                "temp_c": tc + warm, "rh_pct": np.full(tc.size, np.nan),
                "dpd_c": tc + warm - td}
    lst = [{"id": "TEST0000001", "lat": g.meta["lat"] + 0.5, "lon": g.meta["lon"],
            "elev_m": 0, "name": "SYNTHETIC", "first_year": 2000, "last_year": 2100}]
    monkeypatch.setattr(radiosonde, "station_list", lambda download=True: lst)
    for warm, expect in ((0.0, 0.0), (1.0, -1.0)):
        monkeypatch.setattr(radiosonde, "soundings_near",
                            lambda sid, times, h, download=True, w=warm: [sonde(w)])
        res = radiosonde.compare([row], max_km=300, max_hours=3, top_km=20)
        assert res["n_pairs"] == 1
        pr = res["pairs"][0]
        assert pr["distance_km"] == pytest.approx(55.6, abs=0.5) and pr["dt_hours"] == 1.0
        t = [v for v in res["stats"]["temp_K"]["mean"] if v is not None]
        assert t and np.allclose(t, expect, atol=0.02)
        if warm == 0.0:
            q = [v for v in res["stats"]["sph_gkg"]["mean"] if v is not None]
            assert np.allclose(q, 0.0, atol=0.02)
            n = [v for v in res["stats"]["ref_N"]["mean"] if v is not None]
            # CDAAC's ref is the same Smith-Weintraub expression of the same fields
            assert np.allclose(n, 0.0, atol=0.1)
    # outside the window: no pair
    res = radiosonde.compare([row], max_km=300, max_hours=0.5, top_km=20)
    assert res["n_pairs"] == 0



def test_boundary_layer_tops_of_an_atmprf_and_its_own_sonde_agree(monkeypatch):
    """A sonde carrying an atmPrf's own dry pressure and temperature (and no
    vapour) has the occultation's refractivity, so both boundary-layer tops
    coincide; the profile that stops above 0.5 km has none on either side."""
    rows, sondes = [], {}
    for p in sorted(sampledata_dir().glob("atmPrf_*")):
        g = readers.load(str(p))
        d = g.data
        ok = np.isfinite(d["Pres"]) & np.isfinite(d["Temp"]) & np.isfinite(d["MSL_alt"])
        sid = "TEST%07d" % len(rows)
        sondes[sid] = {"station": sid, "lat": g.meta["lat"], "lon": g.meta["lon"],
                       "time": dt.datetime.fromisoformat(g.meta["time_utc"].replace("Z", "+00:00")),
                       "p_hpa": d["Pres"][ok], "temp_c": d["Temp"][ok],
                       "gph_m": 1000.0 * radiosonde.geopotential_height_km(d["MSL_alt"][ok],
                                                                         g.meta["lat"]),
                       "rh_pct": np.zeros(ok.sum()), "dpd_c": np.full(ok.sum(), np.nan)}
        rows.append({"id": sid, "path": str(p), "product": "atmPrf", "file_name": p.name,
                     "time_utc": g.meta["time_utc"], "lat": g.meta["lat"],
                     "lon": g.meta["lon"], "good": True})
    lst = [{"id": sid, "lat": s["lat"], "lon": s["lon"], "elev_m": 0, "name": "SYNTHETIC",
            "first_year": 2000, "last_year": 2100} for sid, s in sondes.items()]
    monkeypatch.setattr(radiosonde, "station_list", lambda download=True: lst)
    monkeypatch.setattr(radiosonde, "soundings_near",
                        lambda sid, times, h, download=True: [sondes[sid]])
    res = radiosonde.compare(rows, max_km=300, max_hours=3, top_km=20)
    by_file = {p["file_name"]: p for p in res["pairs"]}
    top = by_file["atmPrf_C2E1.2026.200.00.00.E23_0001.0001_nc"]
    assert top["ro_pbl_km"] == pytest.approx(2.306, abs=0.005)
    assert top["sonde_pbl_km"] == pytest.approx(top["ro_pbl_km"], abs=1e-6)
    low = by_file["atmPrf_C2E1.2026.200.00.00.E34_0001.0001_nc"]
    assert low["ro_pbl_km"] is None and low["sonde_pbl_km"] is None
    pbl = res["pbl"]
    assert (pbl["n_pairs"], pbl["n_both"], pbl["n_ro"], pbl["n_sonde"]) == (2, 1, 1, 1)
    assert pbl["mean_diff_km"] == pytest.approx(0.0, abs=1e-6)
    assert pbl["within_0p5_km_pct"] == 100.0 and pbl["r"] is None


def test_station_limit_is_reported(monkeypatch):
    """Only the max_stations stations with the most occultations nearby are
    read; the result says how many were within reach, so a capped comparison
    is not mistaken for all there was (5000 atmPrf of May-June 2026: 487
    stations within reach, 200 read, 297 pairs instead of 391)."""
    row = {"id": "x", "path": "unused", "product": "atmPrf", "file_name": "x",
           "time_utc": "2026-06-05T12:00:00Z", "lat": 10.0, "lon": 20.0, "good": True}
    lst = [{"id": f"TEST000000{k}", "lat": 10.0 + 0.5 * k, "lon": 20.0, "elev_m": 0,
            "name": "SYNTHETIC", "first_year": 2000, "last_year": 2100} for k in range(3)]
    asked = []
    monkeypatch.setattr(radiosonde, "station_list", lambda download=True: lst)
    monkeypatch.setattr(radiosonde, "soundings_near",
                        lambda sid, times, h, download=True: asked.append(sid) or [])
    res = radiosonde.compare([row], max_km=300, max_hours=3, max_stations=2)
    assert (res["stations_available"], res["stations_considered"], len(asked)) == (3, 2, 2)
    asked.clear()
    res = radiosonde.compare([row], max_km=300, max_hours=3, max_stations=5)
    assert (res["stations_available"], res["stations_considered"], len(asked)) == (3, 3, 3)
    for bad in (0, 2001):
        body = json.dumps({"search": {}, "download": False, "max_stations": bad}).encode()
        req = urllib.request.Request(BASE + "/api/validation/radiosonde", data=body,
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=60)
        assert err.value.code == 422

def test_endpoint_without_downloads_reports_the_missing_station_list():
    urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/local/load-samples", data=b"{}",
        headers={"Content-Type": "application/json"}), timeout=60)
    # the samples hold atmPrf and wetPf2: never pooled against the sondes
    body = json.dumps({"search": {}, "download": False}).encode()
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/validation/radiosonde", data=body,
            headers={"Content-Type": "application/json"}), timeout=60)
    assert err.value.code == 400 and b"choose one product" in err.value.read()
    body = json.dumps({"search": {}, "download": False, "product": "wetPf2"}).encode()
    req = urllib.request.Request(BASE + "/api/validation/radiosonde", data=body,
                                 headers={"Content-Type": "application/json"})
    cached = (radiosonde.cache_dir() / "igra2-station-list.txt").exists()
    if cached:
        res = json.loads(urllib.request.urlopen(req, timeout=120).read())
        assert "n_pairs" in res
    else:
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=120)
        assert err.value.code == 502


def test_comparison_csv_export(tmp_path):
    from cosmic2 import exporters
    res = {"n_pairs": 1, "max_km": 300, "max_hours": 3, "bin_centres_km": [0.5, 1.5],
           "stats": {"temp_K": {"units": "K", "mean": [0.1, None], "std": [1.0, None],
                                "median": [0.0, None], "n": [3, 0]}},
           "pairs": [{"file_name": "wetPf2_x", "product": "wetPf2", "station": "S",
                      "distance_km": 12.5, "dt_hours": 0.5, "ro_pbl_km": 1.25,
                      "sonde_pbl_km": 1.1}]}
    out = exporters.export_radiosonde_csv(res, [{"file_name": "wetPf2_x",
                                                 "product": "wetPf2"}], basename="rs_test")
    text = open(out["path"], encoding="utf-8").read()
    assert "temp_K_mean_diff_K" in text and "0.1" in text and "wetPf2_x" in text
    assert "IGRA" in text and "geopotential_height_km," in text
    assert "ro_pbl_km,sonde_pbl_km" in text and ",1.25,1.1" in text
    os.remove(out["path"])


def test_soundings_near_reads_the_next_year_at_new_year(monkeypatch):
    import datetime as dt
    asked = []
    monkeypatch.setattr(radiosonde, "station_file",
                        lambda st, year, download, need_until=None: asked.append(year))
    t = dt.datetime(2025, 12, 31, 23, 30, tzinfo=dt.timezone.utc)
    radiosonde.soundings_near("USM00072201", [t], 3.0, download=False)
    assert asked == [2025, 2026]


def test_atmprf_without_a_latitude_is_not_given_one(monkeypatch):
    """Geopotential needs normal gravity at the latitude: no equator is assumed."""
    from cosmic2 import readers
    from cosmic2.config import sampledata_dir
    p = str(next(sampledata_dir().glob("atmPrf_*")))
    g = readers.load(p)
    g.meta["lat"] = None
    monkeypatch.setattr(readers, "load", lambda *a, **k: g)
    assert radiosonde._ro_profile({"path": p, "product": "atmPrf", "lat": None}) is None
    assert radiosonde._ro_profile({"path": p, "product": "atmPrf", "lat": 30.0}) is not None


def test_levels_whose_tangent_point_is_far_from_the_launch_are_left_out():
    z = np.linspace(0.0, 30.0, 61)
    ro = {"gph_km": z, "temp_K": 250.0 + 0 * z, "ref_N": None, "product": "wetPf2",
          "lat": 0.1 * z, "lon": 0 * z}                     # drifts 11 km per km up
    sonde = {"gph_km": z, "temp_K": 249.0 + 0 * z}
    grid = np.arange(0.0, 30.01, 0.5)
    d = radiosonde._differences(ro, sonde, grid, 200.0, (0.0, 0.0))["temp_K"]
    far = 0.1 * grid * 111.195 > 200.0
    assert np.isnan(d[far]).all() and d[~far] == pytest.approx(1.0)
    assert np.isfinite(radiosonde._differences(ro, sonde, grid)["temp_K"]).all()


# --- IGRA files: parsing details, the parsed-file cache, which file a year is in


def _zip_sounding(path, text=SOUNDING):
    import zipfile
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("USM00072201-data.txt", text)
    return path


def test_sounding_header_details():
    # RELTIME 9999 (launch time unknown) falls back to the nominal hour; a
    # value IGRA's quality control removed (-8888) is missing, not -888.8 C
    text = SOUNDING.replace(" 00 2305 ", " 00 9999 ").replace("  147B  290B", "  147B-8888B")
    a = radiosonde.parse_soundings(text)[0]
    assert a["time"] == dt.datetime(2026, 6, 20, 0, 0, tzinfo=dt.timezone.utc)
    assert np.isnan(a["temp_c"][1]) and a["temp_c"][2] == pytest.approx(22.7)
    # a sounding with fewer than five pressure levels is dropped
    short = SOUNDING.split("#")[2].splitlines()
    short = "#" + "\n".join(short[:1] + short[1:5]).replace("    5 ncdc", "    4 ncdc")
    assert radiosonde.parse_soundings(short) == []
    # keep() skips a sounding before its levels are read
    kept = radiosonde.parse_soundings(SOUNDING, keep=lambda h: h["time"].hour == 11)
    assert [s["time"].hour for s in kept] == [11]


def test_station_arrays_are_cached_and_rebuilt_when_the_file_changes(tmp_path):
    z = _zip_sounding(tmp_path / "USM00072201-data.txt.zip")
    a = radiosonde._station_arrays(z)
    assert a["count"].tolist() == [6, 5] and a["start"].tolist() == [0, 6]
    assert a["p_hpa"][6] == pytest.approx(1015.0)
    assert (tmp_path / "USM00072201-data.txt.zip.npz").exists()
    # a newer file (the year-to-date file grows) is parsed again
    one = "#" + SOUNDING.split("#")[2]
    _zip_sounding(z, one)
    later = (tmp_path / "USM00072201-data.txt.zip.npz").stat().st_mtime + 10
    os.utime(z, (later, later))
    b = radiosonde._station_arrays(z)
    assert b["count"].tolist() == [5]


def test_station_file_names_and_missing_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(radiosonde, "cache_dir", lambda: tmp_path)
    asked = []

    def fake(url, dest, timeout=120.0):
        asked.append(url)
        raise OSError("404")
    monkeypatch.setattr(radiosonde, "_download", fake)
    year = dt.datetime.now(dt.timezone.utc).year
    assert radiosonde.station_file("USM00072201", year) is None
    assert asked[-1].endswith(f"/data-y2d/USM00072201-data-beg{year}.txt.zip")
    assert radiosonde.station_file("USM00072201", 2020) is None
    assert asked[-1].endswith("/data-por/USM00072201-data.txt.zip")
    # a file the archive did not have is not asked for again within a day
    assert radiosonde.station_file("USM00072201", 2020) is None
    assert len(asked) == 2
    # nor without downloads; a file on disk is used as it is
    _zip_sounding(tmp_path / "USM00072202-data.txt.zip")
    assert radiosonde.station_file("USM00072202", 2020, download=False).exists()
    assert radiosonde.station_file("USM00072203", 2020, download=False) is None
    assert len(asked) == 2


def test_soundings_near_keeps_only_launches_within_the_window(tmp_path, monkeypatch):
    z = _zip_sounding(tmp_path / "USM00072201-data.txt.zip")
    monkeypatch.setattr(radiosonde, "station_file", lambda *a, **k: z)
    t = dt.datetime(2026, 6, 20, 12, 0, tzinfo=dt.timezone.utc)
    near = radiosonde.soundings_near("USM00072201", [t], 3.0, download=False)
    assert [s["time"] for s in near] == [dt.datetime(2026, 6, 20, 11, 10, tzinfo=dt.timezone.utc)]
    assert near[0]["p_hpa"].tolist()[:2] == [1015.0, 1000.0]
    assert radiosonde.soundings_near("USM00072201", [t], 0.5, download=False) == []


def test_station_list_uses_the_cached_copy_when_a_refresh_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(radiosonde, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(radiosonde, "_download",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(RuntimeError, match="Could not fetch"):
        radiosonde.station_list()
    with pytest.raises(RuntimeError, match="not cached"):
        radiosonde.station_list(download=False)
    path = tmp_path / "igra2-station-list.txt"
    path.write_text(STATIONS, encoding="utf-8")
    os.utime(path, (1, 1))                      # older than 30 days
    assert [s["id"] for s in radiosonde.station_list()] == ["AEM00041217", "USM00072201"]
