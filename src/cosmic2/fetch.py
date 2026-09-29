"""Streaming, cancellable downloads from the CDAAC archive.

CDAAC publishes one gzipped tar per product per day.  Those tars range from
~15 MB (ionPrf) to >2 GB (atmPrf), and a full day is rarely what somebody
actually wants to look at.  So instead of downloading the archive and then
unpacking it, this module pipes the HTTP response straight through gzip and
tar, writes out granules as they appear, and **closes the connection as soon
as the requested number of profiles has been collected**.  Asking for 200
atmPrf profiles therefore costs tens of megabytes, not two gigabytes.

Two sampling strategies:

``first``
    Take granules in archive order (chronological) and stop.  Cheapest;
    covers only the first part of the UTC day.
``spread``
    Estimate the total member count live from the compression ratio observed
    so far, then keep every *n*-th granule so the sample spans the whole day.
    Costs more bandwidth than ``first`` but still aborts once the quota is met.
"""
from __future__ import annotations

import datetime as dt
import io
import os
import tarfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Any, Callable

import requests

from . import readers, store
from .catalog import Archive, date_to_doy, describe_product
from .config import CACHE_DIR, SETTINGS, ensure_dirs

# Nominal granules per day, used only as the initial guess for ``spread``
# before enough of the stream has been read to estimate it properly.
NOMINAL_PER_DAY = {
    "atmPrf": 5500, "wetPf2": 5500, "avnPrf": 5500, "echPrf": 5500,
    "bfrPrf": 5500, "ionPrf": 4500, "scnLv2": 9000, "ivmL2m": 6,
    "conPhs": 5500, "podTc2": 6, "leoOrb": 6,
}


class Cancelled(Exception):
    pass


class _CountingReader(io.RawIOBase):
    """Wrap a socket-backed stream and count *compressed* bytes consumed."""

    def __init__(self, fp, on_read: Callable[[int], None],
                 should_stop: Callable[[], bool]):
        self._fp = fp
        self._on_read = on_read
        self._should_stop = should_stop
        self.count = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        if self._should_stop():
            raise Cancelled()
        chunk = self._fp.read(size if size and size > 0 else 65536)
        if chunk:
            self.count += len(chunk)
            self._on_read(len(chunk))
        return chunk

    def readinto(self, b) -> int:  # type: ignore[override]
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n


@dataclass
class Job:
    id: str
    kind: str
    title: str
    params: dict
    state: str = "queued"          # queued|running|completed|failed|cancelled
    phase: str = "waiting"
    message: str = ""
    error: str = ""
    bytes_done: int = 0
    bytes_total: int | None = None
    members_seen: int = 0
    extracted: int = 0
    skipped: int = 0
    indexed: int = 0
    per_hour_quota: int | None = None
    hours_covered: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict = field(default_factory=dict)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    # -- progress reporting ---------------------------------------------
    def snapshot(self) -> dict:
        # Built field-by-field rather than with dataclasses.asdict(), which
        # deep-copies and so chokes on the threading.Event.
        d: dict[str, Any] = {}
        for f in dataclass_fields(self):
            if f.name.startswith("_"):
                continue
            v = getattr(self, f.name)
            d[f.name] = dict(v) if isinstance(v, dict) else v
        elapsed = (self.finished_at or time.time()) - (self.started_at or time.time())
        d["elapsed_s"] = round(max(elapsed, 0.0), 1)
        d["speed_bps"] = (self.bytes_done / elapsed) if elapsed > 0.5 else None
        # Progress is driven by whichever target is meaningful for the job.
        target = self.params.get("max_profiles")
        if target and self.extracted and self.state == "running":
            d["percent"] = min(99.0, 100.0 * self.extracted / target)
        elif self.bytes_total:
            d["percent"] = min(99.0, 100.0 * self.bytes_done / self.bytes_total)
        else:
            d["percent"] = 0.0
        if self.state in ("completed", "cancelled", "failed"):
            d["percent"] = 100.0
        if d["speed_bps"] and self.bytes_total:
            remaining = max(self.bytes_total - self.bytes_done, 0)
            d["eta_s"] = round(remaining / d["speed_bps"], 1)
        else:
            d["eta_s"] = None
        d["cancel_requested"] = self._cancel.is_set()
        return d

    def cancel(self) -> None:
        self._cancel.set()

    def stopped(self) -> bool:
        return self._cancel.is_set()


class DownloadManager:
    """Owns the worker pool and the job table."""

    def __init__(self, archive: Archive | None = None, settings=SETTINGS):
        self.settings = settings
        self.archive = archive or Archive(settings)
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, int(settings.concurrent_downloads)),
            thread_name_prefix="c2dl")

    # -- job table -------------------------------------------------------
    def _add(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            # keep the table from growing without bound
            if len(self._order) > 200:
                for old in self._order[:-200]:
                    j = self._jobs.get(old)
                    if j and j.state in ("completed", "failed", "cancelled"):
                        self._jobs.pop(old, None)
                self._order = self._order[-200:]
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, active_only: bool = False) -> list[dict]:
        with self._lock:
            jobs = [self._jobs[i] for i in self._order if i in self._jobs]
        snaps = [j.snapshot() for j in reversed(jobs)]
        if active_only:
            snaps = [s for s in snaps if s["state"] in ("queued", "running")]
        return snaps

    def cancel(self, job_id: str) -> bool:
        j = self._jobs.get(job_id)
        if j and j.state in ("queued", "running"):
            j.cancel()
            j.message = "Cancelling..."
            return True
        return False

    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.state in ("queued", "running"))

    # -- public API ------------------------------------------------------
    def submit_download(self, *, stream: str, level: str, product: str,
                        date: str, max_profiles: int | None = None,
                        sampling: str = "first",
                        good_only: bool = False) -> Job:
        d = dt.date.fromisoformat(date)
        year, doy = date_to_doy(d)
        cap = self.settings.max_profiles_per_download
        if max_profiles is None:
            max_profiles = cap
        max_profiles = None if max_profiles <= 0 else int(max_profiles)
        params = dict(stream=stream, level=level, product=product, date=date,
                      year=year, doy=doy, max_profiles=max_profiles,
                      sampling=sampling if sampling in ("first", "spread") else "first",
                      good_only=bool(good_only))
        p = describe_product(product)
        title = (f"{p.label} - {d.isoformat()} ({stream})"
                 if p.label != product else f"{product} - {d.isoformat()}")
        job = self._add(Job(id=uuid.uuid4().hex[:12], kind="download",
                            title=title, params=params))
        self._pool.submit(self._run_download, job)
        return job

    def submit_reindex(self) -> Job:
        job = self._add(Job(id=uuid.uuid4().hex[:12], kind="reindex",
                            title="Rebuild local index", params={}))
        self._pool.submit(self._run_reindex, job)
        return job

    # -- workers ---------------------------------------------------------
    def _run_reindex(self, job: Job) -> None:
        job.state, job.started_at, job.phase = "running", time.time(), "scanning"
        try:
            res = store.reindex_cache()
            job.result = res
            job.indexed = res["indexed"]
            job.state, job.phase = "completed", "done"
            job.message = f"Indexed {res['indexed']} granules ({res['failed']} unreadable)"
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            job.state, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = time.time()

    def _dest_dir(self, p: dict) -> Path:
        return (CACHE_DIR / p["stream"] / p["level"].replace("/", "_") /
                p["product"] / str(p["year"]) / f"{p['doy']:03d}")

    def _run_download(self, job: Job) -> None:
        p = job.params
        job.state, job.started_at = "running", time.time()
        job.phase, job.message = "locating", "Looking up the file on the archive..."
        try:
            ensure_dirs()
            files = self.archive.files(p["stream"], p["level"], p["year"], p["doy"])
            match = next((f for f in files if f.product == p["product"]), None)
            if match is None:
                raise FileNotFoundError(
                    f"{p['product']} is not published for {p['date']} in "
                    f"{p['stream']}/{p['level']}")
            job.bytes_total = self.archive.head_size(match.url)
            job.result["source_url"] = match.url

            used = store.cache_bytes()
            quota = self.settings.cache_quota_gb * 1024 ** 3
            if quota and used >= quota:
                raise RuntimeError(
                    f"Local cache is at its {self.settings.cache_quota_gb:g} GB quota "
                    f"({used / 1024 ** 3:.1f} GB used). Delete a dataset or raise the "
                    f"quota in Settings.")

            dest = self._dest_dir(p)
            dest.mkdir(parents=True, exist_ok=True)
            job.phase, job.message = "downloading", "Streaming from CDAAC..."
            n_bytes, metas = self._stream_extract(job, match.url, dest)

            job.phase, job.message = "indexing", "Reading metadata..."
            for m in metas:
                m.update(stream=p["stream"], level=p["level"],
                         year=p["year"], doy=p["doy"], date=p["date"])
            if metas:
                job.indexed = store.upsert_granules(metas)
            # "complete" means the whole day is on disk: we never hit the cap,
            # never decimated, and were not interrupted.
            cap = p["max_profiles"]
            reached_cap = cap is not None and job.extracted >= cap
            complete = (not reached_cap) and job.skipped == 0 and not job.stopped()
            key = store.record_dataset(
                p["stream"], p["level"], p["product"], p["year"], p["doy"],
                match.url, job.extracted, n_bytes, complete, p["max_profiles"],
                note=f"sampling={p['sampling']}")
            job.result.update(dataset_key=key, granules=job.extracted,
                              bytes=n_bytes, complete=complete,
                              directory=str(dest))
            job.state = "cancelled" if job.stopped() else "completed"
            job.phase = "done"
            job.message = (f"{job.extracted} granules ready "
                           f"({n_bytes / 1024 ** 2:.1f} MB on disk"
                           + (f", {job.bytes_done / 1024 ** 2:.1f} MB transferred)"
                              if job.bytes_done else ")"))
        except Cancelled:
            job.state, job.phase = "cancelled", "done"
            job.message = f"Cancelled after {job.extracted} granules"
        except requests.RequestException as exc:
            job.state, job.phase = "failed", "done"
            job.error = f"Network error: {exc}"
        except Exception as exc:  # noqa: BLE001
            job.state, job.phase = "failed", "done"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = time.time()

    def _stream_extract(self, job: Job, url: str, dest: Path) -> tuple[int, list[dict]]:
        p = job.params
        target = p["max_profiles"]
        sampling = p["sampling"]

        # "spread" fills a per-UTC-hour quota so the sample covers the whole
        # day rather than only its first minutes.  The nominal hour is encoded
        # in every CDAAC filename, so for most products the decision is made
        # before a single byte of the member is written to disk.
        per_hour = max(1, -(-target // 24)) if (sampling == "spread" and target) else None
        job.per_hour_quota = per_hour
        hour_counts: dict[int, int] = {}

        def hour_full(h: int | None) -> bool:
            if per_hour is None or h is None:
                return False
            return hour_counts.get(h, 0) >= per_hour

        metas: list[dict] = []
        on_disk = 0
        session = self.archive.session()

        def bump(n: int) -> None:
            job.bytes_done += n

        with session.get(url, stream=True,
                         timeout=self.settings.request_timeout_s) as resp:
            resp.raise_for_status()
            if job.bytes_total is None and "Content-Length" in resp.headers:
                job.bytes_total = int(resp.headers["Content-Length"])
            counter = _CountingReader(resp.raw, bump, job.stopped)
            reader = io.BufferedReader(counter, buffer_size=1 << 20)
            with tarfile.open(mode="r|gz", fileobj=reader) as tf:
                for member in tf:
                    if job.stopped():
                        raise Cancelled()
                    if not member.isfile():
                        continue
                    job.members_seen += 1
                    name = os.path.basename(member.name)

                    # Cheap path: reject from the filename, before any I/O.
                    nominal_hour = readers.parse_filename(name).get("nominal_hour")
                    if hour_full(nominal_hour):
                        job.skipped += 1
                        continue

                    fh = tf.extractfile(member)
                    if fh is None:
                        continue
                    data = fh.read()
                    out = dest / name
                    tmp = out.with_suffix(out.suffix + ".part")
                    tmp.write_bytes(data)
                    os.replace(tmp, out)

                    try:
                        m = readers.quick_meta(str(out), p["product"])
                    except Exception as exc:  # unreadable granule: keep going
                        out.unlink(missing_ok=True)
                        job.skipped += 1
                        job.message = f"Skipped {name}: {exc}"
                        continue
                    if p["good_only"] and not m.get("good", True):
                        out.unlink(missing_ok=True)
                        job.skipped += 1
                        continue

                    # Products whose filename carries no hour (e.g. scnLv2) are
                    # bucketed on the timestamp read from the granule itself.
                    obs_hour = nominal_hour
                    if obs_hour is None and m.get("epoch") is not None:
                        obs_hour = int((m["epoch"] % 86400) // 3600)
                    if hour_full(obs_hour):
                        out.unlink(missing_ok=True)
                        job.skipped += 1
                        continue
                    if per_hour is not None and obs_hour is not None:
                        hour_counts[obs_hour] = hour_counts.get(obs_hour, 0) + 1

                    metas.append(m)
                    on_disk += len(data)
                    job.extracted += 1
                    if job.extracted % 10 == 0 or job.extracted <= 3:
                        job.message = (
                            f"{job.extracted} granules"
                            + (f" of {target}" if target else "")
                            + f" - {job.bytes_done / 1024 ** 2:.0f} MB transferred")
                    if target and job.extracted >= target:
                        break  # connection closes on context exit
        job.hours_covered = len(hour_counts) if per_hour else 0
        return on_disk, metas


MANAGER: DownloadManager | None = None


def manager() -> DownloadManager:
    global MANAGER
    if MANAGER is None:
        MANAGER = DownloadManager()
    return MANAGER


def import_local_files(paths: list[str], product: str | None = None) -> dict:
    """Index granules the user already has (e.g. from a manual CDAAC pull)."""
    metas, failed = [], []
    for p in paths:
        try:
            m = readers.quick_meta(p, product)
        except Exception as exc:  # noqa: BLE001
            failed.append({"path": p, "error": str(exc)})
            continue
        if m.get("epoch"):
            d = dt.datetime.fromtimestamp(m["epoch"], dt.timezone.utc).date()
            m.update(year=d.year, doy=d.timetuple().tm_yday, date=d.isoformat())
        m.setdefault("stream", "local")
        m.setdefault("level", "imported")
        metas.append(m)
    n = store.upsert_granules(metas) if metas else 0
    return {"indexed": n, "failed": failed}
