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
