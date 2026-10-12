"""Local index behaviour."""
from cosmic2 import store


def test_reindex_refreshes_quality_code_and_identifiers(tmp_path):
    path = str(tmp_path / "atmPrf_C2E1.2026.200.00.00.G01_0001.0001_nc")
    base = dict(path=path, product="atmPrf", stream="t-store", level="level2",
                good=True, bad_code="0", sat="C2E1", occ_prn="G01", stamp="a",
                antenna="")
    store.upsert_granules([base])
    store.upsert_granules([dict(base, good=False, bad_code="3", sat="C2E2",
                                occ_prn="G02", stamp="b")])
    row = store.get_granule(store.granule_id(path))
    try:
        assert row["good"] is False
        assert (row["bad_code"], row["sat"], row["occ_prn"], row["stamp"]) == \
            ("3", "C2E2", "G02", "b")
    finally:
        conn = store.connect()
        with conn:
            conn.execute("DELETE FROM granules WHERE stream='t-store'")


def test_coverage_bins_negative_coordinates_without_sql_floor(tmp_path):
    import inspect
    assert "FLOOR(" not in inspect.getsource(store.coverage)
    pts = [(-2.5, -177.5, 23.9), (-5.0, 0.0, 0.0), (7.4, 179.9, 12.5)]
    rows = [dict(path=str(tmp_path / f"tcov_{i}"), product="tcov", stream="t-cov",
                 level="level2", lat=lat, lon=lon, local_time=lt, good=True)
            for i, (lat, lon, lt) in enumerate(pts)]
    store.upsert_granules(rows)
    try:
        cov = store.coverage(products=["tcov"], bin_deg=5.0)
        cells = sorted((c["lat"], c["lon"]) for c in cov["cells"])
        assert cells == [(-2.5, -177.5), (-2.5, 2.5), (7.5, 177.5)]
        assert sorted(h["hour"] for h in cov["local_time_hist"]) == [0.5, 12.5, 23.5]
    finally:
        conn = store.connect()
        with conn:
            conn.execute("DELETE FROM granules WHERE stream='t-cov'")


def test_date_range_covers_observations_before_the_archive_day(tmp_path):
    # A 2026-07-19 day file whose first granule was observed at 23:59:50
    # the day before: the default From date must include it.
    store.upsert_granules([dict(path=str(tmp_path / "tdate_0"), product="tdate",
                                stream="t-date", level="level2", date="2026-07-19",
                                time_utc="2026-07-18T23:59:50Z", epoch=1784419190.0,
                                good=True)])
    try:
        f = store.facets()
        assert f["date_min"] <= "2026-07-18"
        hits = store.query_granules(products=["tdate"], start=f["date_min"],
                                    end=f"{f['date_max']}T23:59:59Z")
        assert hits["total"] == 1
    finally:
        conn = store.connect()
        with conn:
            conn.execute("DELETE FROM granules WHERE stream='t-date'")


def test_reindex_keeps_the_archive_day_of_the_cache_folder(tmp_path, monkeypatch):
    import shutil
    from cosmic2.config import sampledata_dir
    src = next(sampledata_dir().glob("wetPf2_*"))          # observed on day 200
    day_dir = tmp_path / "t-reidx" / "level2" / "wetPf2" / "2026" / "201"
    day_dir.mkdir(parents=True)
    shutil.copy(src, day_dir / src.name)
    monkeypatch.setattr(store, "CACHE_DIR", tmp_path)
    try:
        assert store.reindex_cache()["indexed"] == 1
        row = store.connect().execute(
            "SELECT date, year, doy FROM granules WHERE stream='t-reidx'").fetchone()
        assert (row["date"], row["year"], row["doy"]) == ("2026-07-20", 2026, 201)
    finally:
        conn = store.connect()
        with conn:
            conn.execute("DELETE FROM granules WHERE stream='t-reidx'")


def test_index_from_older_readers_is_reread_once(tmp_path, monkeypatch):
    import shutil
    from cosmic2 import readers
    from cosmic2.config import sampledata_dir
    src = next(sampledata_dir().glob("atmPrf_*E23*"))
    path = str(tmp_path / src.name)
    shutil.copy(src, path)
    # an index row as an older version wrote it, outside the cache folder
    store.upsert_granules([dict(path=path, product="atmPrf", stream="t-ver", level="imported",
                                year=2026, doy=199, date="2026-07-18", lat=0.0, lon=0.0,
                                extras={"geoid_undulation_m": 0.05091})])
    conn = store.connect()
    try:
        with conn:
            conn.execute("DELETE FROM kv WHERE k='index_version'")
        assert store.index_outdated(readers.INDEX_VERSION)
        store.refresh_metadata()
        assert not store.index_outdated(readers.INDEX_VERSION)
        row = store.get_granule(store.granule_id(path))
        assert (row["stream"], row["level"], row["date"]) == ("t-ver", "imported", "2026-07-18")
        assert row["lat"] == readers.load(path).meta["lat"]
        assert row["extras"]["geoid_undulation_m"] == 50.91
    finally:
        with conn:
            conn.execute("DELETE FROM granules WHERE stream='t-ver'")


def test_cache_bytes_counts_every_file_below_the_folder(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "x.nc").write_bytes(b"1234")
    (tmp_path / "a" / "b" / "y.nc").write_bytes(b"123456")
    assert store.cache_bytes(tmp_path) == 10
    assert store.cache_bytes(tmp_path / "missing") == 0


def test_summary_counts_cache_bytes_from_the_index():
    from cosmic2.config import CACHE_DIR
    before = store.summary()["cache_bytes_indexed"]
    store.upsert_granules([dict(path=str(CACHE_DIR / "t-sum" / "x_nc"), product="tsum",
                                stream="t-sum", level="level2", size_bytes=1234, good=True)])
    try:
        assert store.summary()["cache_bytes_indexed"] - before == 1234
    finally:
        with store.connect() as conn:
            conn.execute("DELETE FROM granules WHERE stream='t-sum'")
