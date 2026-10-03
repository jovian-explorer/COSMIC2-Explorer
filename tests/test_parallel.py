"""Worker-process parallelism gives the same answers as serial runs."""
import math

import numpy as np
import pytest

from cosmic2 import analysis, exporters, fetch, parallel, readers
from cosmic2.config import sampledata_dir


@pytest.fixture
def force_parallel(monkeypatch):
    """Use a 2-process pool even for the handful of sample granules."""
    monkeypatch.setattr(parallel, "MIN_PARALLEL_ITEMS", 1)
    monkeypatch.setattr(parallel, "cpu_count", lambda: max(2, parallel.os.cpu_count() or 2))
    return 2


@pytest.fixture(scope="module", autouse=True)
def _stop_pool():
    # One pool serves the whole module (starting one costs ~2 s on Windows).
    yield
    parallel.shutdown()


def _rows():
    rows = []
    for p in sorted(sampledata_dir().iterdir()):
        m = readers.quick_meta(str(p))
        m.update(id=m["file_name"], date="2026-07-19")
        rows.append(m)
    return rows


def test_resolve_workers(monkeypatch):
    monkeypatch.setattr(parallel, "cpu_count", lambda: 8)
    assert parallel.resolve_workers(0) == 7
    assert parallel.resolve_workers(1) == 1
    assert parallel.resolve_workers(3) == 3
    assert parallel.resolve_workers(64) == 8
    monkeypatch.setattr(parallel, "cpu_count", lambda: 1)
    assert parallel.resolve_workers(0) == 1


def test_pmap_matches_serial_and_keeps_order(force_parallel):
    xs = list(range(50))
    assert parallel.pmap(math.sqrt, xs, workers=force_parallel) == [math.sqrt(x) for x in xs]


def test_small_jobs_stay_serial(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("pool must not start for a small job")
    monkeypatch.setattr(parallel, "_get_pool", boom)
    assert parallel.pmap(math.sqrt, [1.0, 4.0], workers=4) == [1.0, 2.0]


def test_composite_parallel_equals_serial(force_parallel):
    rows = [(r["path"], r) for r in _rows() if r["product"] in ("wetPf2", "atmPrf")]
    a = analysis.composite(rows, "Temp", group_by="product", min_count=1, workers=1)
    b = analysis.composite(rows, "Temp", group_by="product", min_count=1,
                           workers=force_parallel)
    assert a.groups.keys() == b.groups.keys()
    for k in a.groups:
        np.testing.assert_array_equal(a.groups[k]["mean"], b.groups[k]["mean"])


def test_diagnostics_rows_parallel_equal_serial(force_parallel):
    rows = _rows()
    serial = [analysis.diagnostics_row(r) for r in rows]
    par = parallel.pmap(analysis.diagnostics_row, rows, workers=force_parallel)
    assert par == serial


def test_regrid_parallel_equals_serial(force_parallel):
    grid = analysis.make_grid(40.0, 1.0)
    tasks = [(r, "MSL_alt", grid, None) for r in _rows()]
    serial = [exporters._regrid_granule(t) for t in tasks]
    par = parallel.pmap(exporters._regrid_granule, tasks, workers=force_parallel)
    for s, p in zip(serial, par):
        assert (s is None) == (p is None)
        if s is not None:
            assert s[1].keys() == p[1].keys()
            for k in s[1]:
                np.testing.assert_array_equal(s[1][k], p[1][k])


def test_quick_meta_safe_reports_errors(tmp_path):
    bad = tmp_path / "atmPrf_C2E1.2026.200.00.00.G01_0001.0001_nc"
    bad.write_bytes(b"not netcdf")
    m, err = readers.quick_meta_safe((str(bad), None))
    assert m is None and err


def test_profile_series_parallel_matches_serial(force_parallel):
    from cosmic2.pipeline import profile_series
    req = dict(field="Temp", vertical="MSL_alt", max_points=300, convert_kelvin=True,
               outlier_method="mad", outlier_kwargs={}, smooth_method="gaussian",
               smooth_kwargs={}, uncert_method="standard_deviation", uncert_kwargs={})
    tasks = [(r, req) for r in _rows()]
    serial = parallel.pmap(profile_series, tasks, workers=1)
    par = parallel.pmap(profile_series, tasks, workers=force_parallel)
    assert [("skip" in s) for s in serial] == [("skip" in p) for p in par]
    drawn = [(s, p) for s, p in zip(serial, par) if "skip" not in s]
    assert len(drawn) == 4                       # 2 atmPrf + 2 wetPf2 samples
    for s, p in drawn:
        assert s["units"] == p["units"] == "K"
        np.testing.assert_array_equal(s["series"]["x"], p["series"]["x"])
        np.testing.assert_array_equal(s["series"]["uncertainty"], p["series"]["uncertainty"])
