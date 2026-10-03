"""Optional process-level parallelism for per-granule work.

Composites, the diagnostics table, regridded exports and indexing all do the
same thing to every granule independently: open the netCDF file, compute,
return a small result.  That is embarrassingly parallel and CPU/IO bound in
numpy and the netCDF readers, so it is spread over worker *processes* (the
GIL would serialise threads).

The worker count comes from ``Settings.analysis_workers``:

    0   automatic: one fewer than the number of CPUs (at least 1)
    1   serial, in the calling process (no pool at all)
    N   up to N worker processes (capped at the CPU count)

Starting a pool costs a second or two (each worker imports numpy, scipy and
netCDF4), so small jobs always run serially and the pool is kept alive for
reuse once started.  Any failure of the pool itself (a worker killed, a
result that cannot be pickled) falls back to running the job serially, so
parallelism can never make a request fail that would succeed without it.
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Iterable, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")

log = logging.getLogger(__name__)

# Below this many items the pool start-up and pickling overhead outweighs
# the gain for typical granules (~10-30 ms each).
MIN_PARALLEL_ITEMS = 24

_lock = threading.Lock()
_pool: ProcessPoolExecutor | None = None
_pool_size = 0


def cpu_count() -> int:
    try:
        return len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def resolve_workers(requested: int | None = None) -> int:
    """Effective worker count for a requested value (``None`` reads Settings)."""
    if requested is None:
        from .config import SETTINGS
        requested = getattr(SETTINGS, "analysis_workers", 0)
    try:
        n = int(requested)
    except (TypeError, ValueError):
        n = 0
    cpus = cpu_count()
    if n <= 0:
        n = max(1, cpus - 1)
    return max(1, min(n, cpus))


def _get_pool(workers: int) -> ProcessPoolExecutor:
    global _pool, _pool_size
    with _lock:
        if _pool is None or _pool_size != workers:
            if _pool is not None:
                _pool.shutdown(wait=False, cancel_futures=True)
            _pool = ProcessPoolExecutor(max_workers=workers)
            _pool_size = workers
        return _pool


def shutdown() -> None:
    """Stop the worker pool (also registered to run at interpreter exit)."""
    global _pool, _pool_size
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
        _pool, _pool_size = None, 0


atexit.register(shutdown)


def pmap(func: Callable[[T], R], items: Iterable[T], workers: int | None = None,
         min_items: int | None = None) -> list[R]:
    """``list(map(func, items))``, on worker processes when worthwhile.

    ``func`` must be a module-level function and its arguments and results
    picklable.  Order is preserved.  Exceptions raised *by func* propagate as
    they would serially; a broken pool falls back to serial execution.
    """
    seq: Sequence[T] = items if isinstance(items, (list, tuple)) else list(items)
    n = resolve_workers(workers)
    if min_items is None:
        min_items = MIN_PARALLEL_ITEMS
    if n <= 1 or len(seq) < max(min_items, 2):
        return [func(x) for x in seq]
    chunk = max(1, len(seq) // (n * 4))
    try:
        return list(_get_pool(n).map(func, seq, chunksize=chunk))
    except Exception as exc:  # noqa: BLE001
        from concurrent.futures.process import BrokenProcessPool
        import pickle
        if not isinstance(exc, (BrokenProcessPool, pickle.PicklingError,
                                AttributeError, TypeError, OSError)):
            raise
        log.warning("worker pool failed (%s); running serially", exc)
        shutdown()
        return [func(x) for x in seq]
