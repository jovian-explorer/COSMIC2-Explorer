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
