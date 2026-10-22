"""Archive listing cache and download bookkeeping, with the network faked."""
import types

import pytest

from cosmic2 import catalog


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text
        self.ok = status < 400
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _archive():
    settings = types.SimpleNamespace(listing_cache_hours=6, request_timeout_s=5,
                                     user_agent="test")
    return catalog.Archive(settings)


def test_missing_directory_is_retried_after_a_few_minutes(monkeypatch):
    arc = _archive()
    answers = [FakeResponse(404),
               FakeResponse(200, '<a href="wetPf2_nrt_2026_200.tar.gz">x</a>')]
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return answers[min(len(calls) - 1, 1)]

    monkeypatch.setattr(arc._session, "get", fake_get)
    clock = [1000.0]
    monkeypatch.setattr(catalog.time, "time", lambda: clock[0])
    assert arc.list_dir("https://x/2026/200") == []
    clock[0] += 60
    assert arc.list_dir("https://x/2026/200") == []          # still cached
    clock[0] += 600                                            # 11 min later
    assert arc.list_dir("https://x/2026/200") == ["wetPf2_nrt_2026_200.tar.gz"]
    clock[0] += 3600                                           # found: long TTL
    arc.list_dir("https://x/2026/200")
    assert len(calls) == 2


def test_day_manifest_requests_run_concurrently_and_keep_order(monkeypatch):
    import datetime as dt
    import time as _time
    arc = _archive()
    names = [f"prod{i}_nrt_2026_200.tar.gz" for i in range(12)]
    listing = "".join(f'<a href="{n}">x</a>' for n in names)

    def fake_get(url, timeout=None):
        _time.sleep(0.05)
        if url.rstrip("/").endswith("nrt/level2/2026/200"):
            return FakeResponse(200, listing)
        return FakeResponse(404)

    def fake_head(url, timeout=None, allow_redirects=True):
        _time.sleep(0.2)
        r = FakeResponse(200)
        r.headers = {"Content-Length": str(len(url))}
        return r

    monkeypatch.setattr(arc._session, "get", fake_get)
    monkeypatch.setattr(arc._session, "head", fake_head)
    t0 = _time.perf_counter()
    rows = arc.day_manifest(dt.date(2026, 7, 19))
    elapsed = _time.perf_counter() - t0
    assert [r["name"] for r in rows] == sorted(names, key=lambda n: n.split("_")[0])
    assert all(r["size_bytes"] == len(r["url"]) for r in rows)
    assert elapsed < 1.5        # 12 HEADs x 0.2 s + 7 listings x 0.05 s serially


# ---------------------------------------------------------------------------
# interrupted downloads
# ---------------------------------------------------------------------------

def _tar_gz_of_samples():
    import io
    import tarfile
    from cosmic2.config import sampledata_dir
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for p in sorted(sampledata_dir().glob("wetPf2_*")):
            tf.add(str(p), arcname=f"wetPf2/{p.name}")
    return buf.getvalue()


class _BreakingRaw:
    """Serves ``data`` and then fails (or cancels the job) at ``frac``."""

    def __init__(self, data, frac, on_break):
        self.data, self.pos = data, 0
        self.limit = int(len(data) * frac)
        self.on_break = on_break

    def read(self, n=-1):
        if self.pos >= self.limit:
            self.on_break()
        n = 4096 if n is None or n < 0 else min(n, 4096)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk


def _run_interrupted(monkeypatch, mode):
    import requests
    from cosmic2 import fetch, store
    data = _tar_gz_of_samples()
    remote = catalog.RemoteFile("wetPf2", "nrt", 2026, 200, "wetPf2_nrt_2026_200.tar.gz",
                                "https://x/wetPf2_nrt_2026_200.tar.gz")
    job_box = {}

    def on_break():
        if mode == "network":
            raise requests.ConnectionError("connection reset")
        job_box["job"].cancel()

    class Resp:
        status_code, headers = 200, {}
        raw = _BreakingRaw(data, 0.85, on_break)

        def raise_for_status(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    arc = types.SimpleNamespace(
        files=lambda *a: [remote], head_size=lambda url: len(data),
        session=lambda: types.SimpleNamespace(get=lambda *a, **k: Resp()))
    settings = types.SimpleNamespace(concurrent_downloads=1, max_profiles_per_download=0,
                                     cache_quota_gb=0, request_timeout_s=5)
    mgr = fetch.DownloadManager(archive=arc, settings=settings)
    job = fetch.Job(id="t", kind="download", title="t",
                    params=dict(stream="nrt-test", level="level2", product="wetPf2",
                                date="2026-07-19", year=2026, doy=200,
                                max_profiles=None, sampling="first", good_only=False))
    job_box["job"] = job
    mgr._run_download(job)
    rows = store.query_granules(streams=["nrt-test"])["granules"]
    return job, rows


@pytest.mark.parametrize("mode", ["network", "cancel"])
def test_granules_received_before_an_interruption_are_indexed(monkeypatch, mode):
    from cosmic2 import store
    job, rows = _run_interrupted(monkeypatch, mode)
    try:
        assert job.state == ("failed" if mode == "network" else "cancelled")
        assert job.extracted >= 1
        assert len(rows) == job.extracted == job.indexed
        ds = [d for d in store.datasets() if d["stream"] == "nrt-test"]
        assert ds and ds[0]["complete"] == 0
    finally:
        for d in store.datasets():
            if d["stream"] == "nrt-test":
                store.delete_dataset(d["key"])


def test_concurrent_downloads_setting_takes_effect_without_restart():
    from cosmic2 import fetch
    settings = types.SimpleNamespace(concurrent_downloads=1)
    arc = types.SimpleNamespace()
    mgr = fetch.DownloadManager(archive=arc, settings=settings)
    assert mgr._executor()._max_workers == 1
    settings.concurrent_downloads = 3
    assert mgr._executor()._max_workers == 3


# whole-day products and the per-hour "spread" quota
# ---------------------------------------------------------------------------

def test_ivm_filename_sequence_is_not_an_hour():
    from cosmic2 import readers
    meta = readers.parse_filename("ivmL2m_C2E1.2026.273.01_0001.0001_nc")
    assert meta["sat"] == "C2E1" and meta["nominal_doy"] == 273
    assert "nominal_hour" not in meta


def test_spread_sampling_keeps_every_whole_day_ivm_file():
    import io
    import tarfile
    from cosmic2 import fetch, store
    from cosmic2.config import sampledata_dir
    src = next(sampledata_dir().glob("ivmL2m_*"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=1) as tf:
        for sat in ("C2E1", "C2E2", "C2E4"):
            tf.add(str(src), arcname=f"ivmL2m/ivmL2m_{sat}.2026.200.01_0001.0001_nc")
    data = buf.getvalue()

    class Resp:
        status_code, headers = 200, {}
        raw = io.BytesIO(data)

        def raise_for_status(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    remote = catalog.RemoteFile("ivmL2m", "rapid", 2026, 200,
                                "ivmL2m_rapid_2026_200.tar.gz", "https://x/ivm.tar.gz")
    arc = types.SimpleNamespace(
        files=lambda *a: [remote], head_size=lambda url: len(data),
        session=lambda: types.SimpleNamespace(get=lambda *a, **k: Resp()))
    settings = types.SimpleNamespace(concurrent_downloads=1, max_profiles_per_download=0,
                                     cache_quota_gb=0, request_timeout_s=5)
    mgr = fetch.DownloadManager(archive=arc, settings=settings)
    # 24 profiles spread over 24 h is a quota of one per hour; before the fix
    # the three satellites' day files all counted against "hour 01".
    job = fetch.Job(id="t", kind="download", title="t",
                    params=dict(stream="rapid-test", level="level2", product="ivmL2m",
                                date="2026-07-19", year=2026, doy=200,
                                max_profiles=24, sampling="spread", good_only=False))
    try:
        mgr._run_download(job)
        assert job.state == "completed", job.error
        assert job.extracted == 3 and job.skipped == 0
    finally:
        for d in store.datasets():
            if d["stream"] == "rapid-test":
                store.delete_dataset(d["key"])


def test_other_missions_have_their_own_archive_paths_and_streams():
    assert catalog.collection_url("nrt", "level2").endswith("/gnss-ro/cosmic2/nrt/level2")
    assert catalog.day_url("paz-nrt", "level2", 2026, 171).endswith("/gnss-ro/paz/nrt/level2/2026/171")
    assert catalog.day_url("kompsat5-nrt", "level2", 2026, 5).endswith("/gnss-ro/kompsat5/nrt/level2/2026/005")
    assert catalog.mission_of("rapid") == "cosmic2" and catalog.mission_of("paz-nrt") == "paz"
    assert catalog.day_url("metopc-postProc", "level2", 2026, 151).endswith(
        "/gnss-ro/metopc/postProc/level2/2026/151")
    assert catalog.day_url("paz-postProc", "level2", 2021, 278).endswith(
        "/gnss-ro/paz/postProc/level2/2021/278")
    assert catalog.collection_url("cosmic1-repro2021", "level2").endswith(
        "/gnss-ro/cosmic1/repro2021/level2")
    # the stream code is also the cache folder: it must be a valid folder name everywhere
    for s in catalog.STREAMS:
        assert all(c.isalnum() or c in "-_" for c in s), s


def test_latest_day_comes_from_the_listing_not_from_today(monkeypatch):
    """Post-processed streams end months back; empty newest days are skipped."""
    arc = _archive()
    tree = {"": ["2019/", "2020/", "README"], "/2020": ["001/", "002/"], "/2019": ["365/"]}
    base = catalog.collection_url("metopc-postProc", "level2")
    monkeypatch.setattr(arc, "list_dir", lambda url: tree.get(url[len(base):], []))
    from types import SimpleNamespace
    files = {(2020, 2): [], (2020, 1): [SimpleNamespace(product="wetPf2")]}
    monkeypatch.setattr(arc, "files", lambda s, l, y, d: files.get((y, d), []))
    assert arc.latest_available("metopc-postProc")["date"] == "2020-01-01"
    assert arc.latest_available("metopc-postProc", search_days=1) is None


def test_day_scan_lists_other_missions_only_when_asked(monkeypatch):
    import datetime as dt
    arc = _archive()
    asked = []
    monkeypatch.setattr(arc, "files", lambda stream, level, y, d: asked.append(stream) or [])
    arc.day_manifest(dt.date(2026, 6, 20), with_sizes=False)
    assert asked and all(catalog.mission_of(s) == "cosmic2" for s in asked)
    asked.clear()
    arc.day_manifest(dt.date(2026, 6, 20), ["paz-nrt"], with_sizes=False)
    assert asked == ["paz-nrt"]


# ---------------------------------------------------------------------------
# what a download keeps: hour quota, quality filter, whole-day flag
# ---------------------------------------------------------------------------

def _atm_tar(tmp_path, hours, bad=()):
    """A day tarball of copies of a sample atmPrf, one per entry of ``hours``
    (its nominal hour in the name); entries listed in ``bad`` flagged bad."""
    import io
    import shutil
    import tarfile
    from netCDF4 import Dataset
    from cosmic2.config import sampledata_dir
    src = next(sampledata_dir().glob("atmPrf_*E23*"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=1) as tf:
        for k, h in enumerate(hours):
            name = f"atmPrf_C2E1.2026.200.{h:02d}.{k:02d}.G{k + 1:02d}_0001.0001_nc"
            p = tmp_path / name
            shutil.copy(src, p)
            if k in bad:
                with Dataset(p, "a") as ds:
                    ds.bad = "1"
            tf.add(str(p), arcname=f"atmPrf/{name}")
    return buf.getvalue()


def _download(data, stream, product="atmPrf", quota_gb=0, **params):
    import io
    from cosmic2 import fetch

    class Resp:
        status_code, headers = 200, {}
        raw = io.BytesIO(data)

        def raise_for_status(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    remote = catalog.RemoteFile("atmPrf", "nrt", 2026, 200, "atmPrf_nrt_2026_200.tar.gz",
                                "https://x/atmPrf_nrt_2026_200.tar.gz")
    arc = types.SimpleNamespace(
        files=lambda *a: [remote], head_size=lambda url: len(data),
        session=lambda: types.SimpleNamespace(get=lambda *a, **k: Resp()))
    settings = types.SimpleNamespace(concurrent_downloads=1, max_profiles_per_download=0,
                                     cache_quota_gb=quota_gb, request_timeout_s=5)
    mgr = fetch.DownloadManager(archive=arc, settings=settings)
    p = dict(stream=stream, level="level2", product=product, date="2026-07-19",
             year=2026, doy=200, max_profiles=None, sampling="first", good_only=False)
    p.update(params)
    job = fetch.Job(id="t", kind="download", title="t", params=p)
    mgr._run_download(job)
    return job


@pytest.fixture
def cleanup_streams():
    from cosmic2 import store
    yield
    for d in store.datasets():
        if d["stream"].endswith("-test"):
            store.delete_dataset(d["key"])


def test_spread_keeps_a_quota_per_hour_and_the_day_is_not_complete(tmp_path, cleanup_streams):
    from cosmic2 import store
    # 48 over 24 h is two an hour: three 00 UTC profiles lose one, 05 UTC keeps its one
    job = _download(_atm_tar(tmp_path, [0, 0, 0, 5]), "spread-test",
                    max_profiles=48, sampling="spread")
    assert job.state == "completed", job.error
    assert (job.extracted, job.skipped, job.per_hour_quota, job.hours_covered) == (3, 1, 2, 2)
    ds = [d for d in store.datasets() if d["stream"] == "spread-test"][0]
    assert ds["complete"] == 0          # a sample is not the whole day


def test_whole_day_is_complete_and_a_cap_is_not(tmp_path, cleanup_streams):
    from cosmic2 import store
    data = _atm_tar(tmp_path, [0, 1, 2])
    whole = _download(data, "whole-test")
    capped = _download(data, "capped-test", max_profiles=2)
    assert (whole.extracted, capped.extracted) == (3, 2)
    flags = {d["stream"]: d["complete"] for d in store.datasets()}
    assert flags["whole-test"] == 1 and flags["capped-test"] == 0


def test_good_only_leaves_flagged_profiles_out(tmp_path, cleanup_streams):
    from cosmic2 import store
    job = _download(_atm_tar(tmp_path, [0, 1, 2], bad={1}), "good-test", good_only=True)
    assert (job.extracted, job.skipped) == (2, 1)
    rows = store.query_granules(streams=["good-test"])["granules"]
    assert len(rows) == 2 and all(r["good"] for r in rows)
    assert not any(p.name.endswith(".G02_0001.0001_nc")
                   for p in __import__("pathlib").Path(job.result["directory"]).iterdir())


def test_a_product_the_day_lacks_and_a_full_cache_fail_with_a_reason(tmp_path, monkeypatch,
                                                                    cleanup_streams):
    from cosmic2 import store
    data = _atm_tar(tmp_path, [0])
    job = _download(data, "missing-test", product="wetPf2")
    assert job.state == "failed" and "not published" in job.error
    monkeypatch.setattr(store, "cache_bytes", lambda *a, **k: 2 * 1024 ** 3)
    job = _download(data, "quota-test", quota_gb=1)
    assert job.state == "failed" and "1 GB quota" in job.error and job.extracted == 0


def test_job_progress_follows_the_profile_cap_then_the_bytes():
    from cosmic2.fetch import Job
    job = Job(id="j", kind="download", title="t", params={"max_profiles": 40},
              state="running", bytes_done=50, bytes_total=200, extracted=10)
    job.started_at = job.created_at - 10
    s = job.snapshot()
    # capped: a quarter of the profiles, not of the day's bytes
    assert s["percent"] == 25.0 and "_cancel" not in s
    assert s["speed_bps"] is not None and s["eta_s"] > 0
    job.params["max_profiles"] = None
    assert job.snapshot()["percent"] == 25.0          # 50 of 200 bytes
    job.extracted = job.bytes_done = 200
    assert job.snapshot()["percent"] == 99.0           # 100 only once finished
    job.cancel()
    job.state = "cancelled"
    s = job.snapshot()
    assert s["percent"] == 100.0 and s["cancel_requested"]
