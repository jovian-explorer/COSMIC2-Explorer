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
