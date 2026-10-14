"""Local SQLite index over downloaded granules.

The netCDF files stay on disk exactly as CDAAC shipped them; this index holds
only the metadata needed to *find* profiles fast (time, position, quality,
product).  Re-opening the app therefore costs one SQL query rather than a
re-scan of tens of thousands of files.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from .config import CACHE_DIR, DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS granules (
    id          TEXT PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    product     TEXT NOT NULL,
    stream      TEXT,
    level       TEXT,
    year        INTEGER,
    doy         INTEGER,
    date        TEXT,
    stamp       TEXT,
    sat         TEXT,
    occ_prn     TEXT,
    antenna     TEXT,
    time_utc    TEXT,
    epoch       REAL,
    lat         REAL,
    lon         REAL,
    local_time  REAL,
    good        INTEGER,
    bad_code    TEXT,
    n_levels    INTEGER,
    alt_min     REAL,
    alt_max     REAL,
    size_bytes  INTEGER,
    extras      TEXT,
    added_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_gran_epoch   ON granules(epoch);
CREATE INDEX IF NOT EXISTS ix_gran_product ON granules(product, epoch);
CREATE INDEX IF NOT EXISTS ix_gran_pos     ON granules(lat, lon);
CREATE INDEX IF NOT EXISTS ix_gran_day     ON granules(stream, product, year, doy);

CREATE TABLE IF NOT EXISTS datasets (
    key          TEXT PRIMARY KEY,
    stream       TEXT, level TEXT, product TEXT,
    year         INTEGER, doy INTEGER, date TEXT,
    source_url   TEXT,
    n_granules   INTEGER DEFAULT 0,
    bytes        INTEGER DEFAULT 0,
    complete     INTEGER DEFAULT 0,
    max_profiles INTEGER,
    downloaded_at TEXT,
    note         TEXT
);

CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""

_local = threading.local()


def granule_id(path: str) -> str:
    return hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:16]


def dataset_key(stream: str, level: str, product: str, year: int, doy: int) -> str:
    return f"{stream}/{level}/{product}/{year}/{doy:03d}"


def connect() -> sqlite3.Connection:
    """One connection per thread (FastAPI runs handlers on a thread pool)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        ensure_dirs()
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
        _local.conn = conn
    return conn


def init_db() -> None:
    connect()


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------

def upsert_granules(rows: Iterable[dict]) -> int:
    conn = connect()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    payload = []
    for m in rows:
        path = os.path.abspath(m["path"])
        payload.append((
            granule_id(path), path, m.get("product"), m.get("stream"), m.get("level"),
            m.get("year"), m.get("doy"), m.get("date"), m.get("stamp"), m.get("sat"),
            m.get("occ_prn"), m.get("antenna"), m.get("time_utc"), m.get("epoch"),
            m.get("lat"), m.get("lon"), m.get("local_time"),
            1 if m.get("good", True) else 0, str(m.get("bad_code", "")),
            m.get("n_levels"), m.get("alt_min"), m.get("alt_max"),
            m.get("size_bytes"), json.dumps(m.get("extras") or {}), now,
        ))
    with conn:
        conn.executemany(
            "INSERT INTO granules (id,path,product,stream,level,year,doy,date,stamp,"
            "sat,occ_prn,antenna,time_utc,epoch,lat,lon,local_time,good,bad_code,"
            "n_levels,alt_min,alt_max,size_bytes,extras,added_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            # Every derived column is refreshed on re-index, so a reader fix
            # (or a re-download) is reflected without deleting the index.
            "ON CONFLICT(id) DO UPDATE SET "
            "product=excluded.product, stream=excluded.stream, level=excluded.level, "
            "stamp=excluded.stamp, sat=excluded.sat, occ_prn=excluded.occ_prn, "
            "antenna=excluded.antenna, bad_code=excluded.bad_code, "
            "year=excluded.year, doy=excluded.doy, date=excluded.date, "
            "time_utc=excluded.time_utc, epoch=excluded.epoch, lat=excluded.lat, "
            "lon=excluded.lon, local_time=excluded.local_time, good=excluded.good, "
            "n_levels=excluded.n_levels, alt_min=excluded.alt_min, "
            "alt_max=excluded.alt_max, size_bytes=excluded.size_bytes, "
            "extras=excluded.extras",
            payload,
        )
    return len(payload)


def record_dataset(stream: str, level: str, product: str, year: int, doy: int,
                   source_url: str, n_granules: int, nbytes: int,
                   complete: bool, max_profiles: int | None,
                   note: str = "") -> str:
    key = dataset_key(stream, level, product, year, doy)
    date = (dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)).isoformat()
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO datasets (key,stream,level,product,year,doy,date,source_url,"
            "n_granules,bytes,complete,max_profiles,downloaded_at,note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET n_granules=excluded.n_granules, "
            "bytes=excluded.bytes, complete=excluded.complete, "
            "max_profiles=excluded.max_profiles, downloaded_at=excluded.downloaded_at, "
            "note=excluded.note",
            (key, stream, level, product, year, doy, date, source_url, n_granules,
             nbytes, 1 if complete else 0, max_profiles,
             dt.datetime.now(dt.timezone.utc).isoformat(), note),
        )
    return key


def delete_dataset(key: str, remove_files: bool = True) -> dict:
    conn = connect()
    row = conn.execute("SELECT * FROM datasets WHERE key=?", (key,)).fetchone()
    if row is None:
        return {"deleted": 0, "freed_bytes": 0}
    grans = conn.execute(
        "SELECT id, path, size_bytes FROM granules WHERE stream=? AND product=? "
        "AND year=? AND doy=?",
        (row["stream"], row["product"], row["year"], row["doy"]),
    ).fetchall()
    freed = 0
    if remove_files:
        for g in grans:
            try:
                os.remove(g["path"])
                freed += g["size_bytes"] or 0
            except OSError:
                pass
        # prune the now-empty day directory
        if grans:
            d = Path(grans[0]["path"]).parent
            try:
                if d.is_dir() and not any(d.iterdir()) and CACHE_DIR in d.parents:
                    d.rmdir()
            except OSError:
                pass
    with conn:
        conn.execute(
            "DELETE FROM granules WHERE stream=? AND product=? AND year=? AND doy=?",
            (row["stream"], row["product"], row["year"], row["doy"]))
        conn.execute("DELETE FROM datasets WHERE key=?", (key,))
    return {"deleted": len(grans), "freed_bytes": freed}


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------

_SORTS = {
    "time": "epoch", "lat": "lat", "lon": "lon", "levels": "n_levels",
    "local_time": "local_time", "product": "product",
}


def query_granules(*, products: list[str] | None = None,
                   streams: list[str] | None = None,
                   start: str | None = None, end: str | None = None,
                   lat_min: float | None = None, lat_max: float | None = None,
                   lon_min: float | None = None, lon_max: float | None = None,
                   local_time_min: float | None = None,
                   local_time_max: float | None = None,
                   sats: list[str] | None = None,
                   prns: list[str] | None = None,
                   good_only: bool = False,
                   min_levels: int | None = None,
                   max_alt_below: float | None = None,
                   sort: str = "time", desc: bool = False,
                   limit: int = 200, offset: int = 0) -> dict:
    """Filtered, paged granule search. ``start``/``end`` are ISO timestamps; an
    ``end`` that is a bare date (2026-05-31) takes in the whole of that day."""
    if end and len(end) == 10:
        end += "T23:59:59.999Z"
    conn = connect()
    where: list[str] = []
    args: list[Any] = []

    def _in(col: str, values: list[str] | None):
        if values:
            where.append(f"{col} IN ({','.join('?' * len(values))})")
            args.extend(values)

    _in("product", products)
    _in("stream", streams)
    _in("sat", sats)
    _in("occ_prn", prns)
    for col, val, op in (("epoch", _epoch(start), ">="), ("epoch", _epoch(end), "<="),
                         ("lat", lat_min, ">="), ("lat", lat_max, "<="),
                         ("n_levels", min_levels, ">="), ("alt_max", max_alt_below, "<=")):
        if val is not None:
            where.append(f"{col} {op} ?")
            args.append(val)
    if lon_min is not None and lon_max is not None:
        if lon_min <= lon_max:
            where.append("lon BETWEEN ? AND ?")
            args.extend([lon_min, lon_max])
        else:  # box crosses the antimeridian
            where.append("(lon >= ? OR lon <= ?)")
            args.extend([lon_min, lon_max])
    if local_time_min is not None and local_time_max is not None:
        if local_time_min <= local_time_max:
            where.append("local_time BETWEEN ? AND ?")
            args.extend([local_time_min, local_time_max])
        else:
            where.append("(local_time >= ? OR local_time <= ?)")
            args.extend([local_time_min, local_time_max])
    if good_only:
        where.append("good = 1")

    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM granules{sql_where}", args).fetchone()[0]
    order = _SORTS.get(sort, "epoch") + (" DESC" if desc else " ASC")
    rows = conn.execute(
        f"SELECT * FROM granules{sql_where} ORDER BY {order} LIMIT ? OFFSET ?",
        args + [int(limit), int(offset)],
    ).fetchall()
    return {"total": total, "count": len(rows), "offset": offset,
            "granules": [_row_to_dict(r) for r in rows]}


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    s = iso.replace("Z", "+00:00")
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        try:
            t = dt.datetime.fromisoformat(s + "T00:00:00+00:00")
        except ValueError:
            return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def _row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["good"] = bool(d.get("good"))
    # Not stored: the granule filename is always the basename of its path, and
    # every consumer (exports, tables, plot labels) wants it by that name.
    d["file_name"] = os.path.basename(d.get("path") or "")
    try:
        d["extras"] = json.loads(d.get("extras") or "{}")
    except ValueError:
        d["extras"] = {}
    return d


def get_granule(gid: str) -> dict | None:
    r = connect().execute("SELECT * FROM granules WHERE id=?", (gid,)).fetchone()
    return _row_to_dict(r) if r else None


def get_granules(gids: list[str]) -> list[dict]:
    if not gids:
        return []
    q = ",".join("?" * len(gids))
    rows = connect().execute(
        f"SELECT * FROM granules WHERE id IN ({q}) ORDER BY epoch", gids).fetchall()
    return [_row_to_dict(r) for r in rows]


def datasets() -> list[dict]:
    rows = connect().execute(
        "SELECT * FROM datasets ORDER BY date DESC, product").fetchall()
    return [dict(r) for r in rows]


def summary() -> dict:
    conn = connect()
    g = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(size_bytes),0) b, MIN(time_utc) t0, "
        "MAX(time_utc) t1 FROM granules").fetchone()
    per = conn.execute(
        "SELECT product, COUNT(*) n, COALESCE(SUM(size_bytes),0) b, "
        "SUM(good) ngood FROM granules GROUP BY product ORDER BY n DESC").fetchall()
    return {
        "n_granules": g["n"], "bytes": g["b"],
        "time_min": g["t0"], "time_max": g["t1"],
        "by_product": [dict(r) for r in per],
        "n_datasets": conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0],
        "cache_dir": str(CACHE_DIR),
        # the files in the cache folder, by their indexed sizes: walking the
        # folder took 0.2-0.9 s for a month of files on every refresh
        "cache_bytes_indexed": conn.execute(
            "SELECT COALESCE(SUM(size_bytes),0) FROM granules WHERE path LIKE ?",
            (str(CACHE_DIR) + "%",)).fetchone()[0],
    }


def _floor_int(expr: str) -> str:
    """SQL for ``floor(expr)`` as an integer.  SQLite has ``FLOOR`` only when
    built with its math functions (3.35+, enabled by the build), so it is
    missing from, for example, the system SQLite of RHEL/Rocky 9 (3.34)."""
    return f"(CAST({expr} AS INT) - ({expr} < CAST({expr} AS INT)))"


def coverage(products: list[str] | None = None, good_only: bool = False,
             bin_deg: float = 5.0) -> dict:
    """Aggregates for the overview panel: map bins, latitude and local-time
    histograms, computed in SQL so the browser never sees raw rows."""
    conn = connect()
    where, args = [], []
    if products:
        where.append(f"product IN ({','.join('?' * len(products))})")
        args += products
    if good_only:
        where.append("good = 1")
    where.append("lat IS NOT NULL AND lon IS NOT NULL")
    w = " WHERE " + " AND ".join(where)
    b = float(bin_deg)
    cells = conn.execute(
        f"SELECT {_floor_int(f'lat/{b}')} iy, {_floor_int(f'lon/{b}')} ix, "
        f"COUNT(*) n FROM granules{w} GROUP BY iy, ix", args).fetchall()
    lat_hist = conn.execute(
        f"SELECT {_floor_int('lat/5.0')} iy, COUNT(*) n FROM granules{w} "
        f"GROUP BY iy ORDER BY iy", args).fetchall()
    lt_hist = conn.execute(
        f"SELECT {_floor_int('local_time')} h, COUNT(*) n FROM granules{w} "
        f"AND local_time IS NOT NULL GROUP BY h ORDER BY h", args).fetchall()
    day_hist = conn.execute(
        f"SELECT date, COUNT(*) n FROM granules{w} GROUP BY date ORDER BY date", args
    ).fetchall()
    return {
        "bin_deg": b,
        "cells": [{"lat": (r["iy"] + 0.5) * b, "lon": (r["ix"] + 0.5) * b,
                   "n": r["n"]} for r in cells],
        "lat_hist": [{"lat": (r["iy"] + 0.5) * 5.0, "n": r["n"]} for r in lat_hist],
        "local_time_hist": [{"hour": r["h"] + 0.5, "n": r["n"]} for r in lt_hist],
        "day_hist": [{"date": r["date"], "n": r["n"]} for r in day_hist],
    }


def facets() -> dict:
    """Distinct values available for the filter widgets."""
    conn = connect()

    def col(name):
        return [r[0] for r in conn.execute(
            f"SELECT DISTINCT {name} FROM granules WHERE {name} IS NOT NULL "
            f"AND {name} != '' ORDER BY {name}").fetchall()]

    # The date filter applies to the observation time, and a CDAAC day file
    # starts with occultations from the last minute of the previous UTC day
    # (every ivmL2m day file does).  The range therefore spans observation
    # dates as well as archive days, or the default search hid those
    # granules (all of a single day's ivmL2m files).
    rng = conn.execute(
        "SELECT MIN(date) a, MAX(date) b, MIN(substr(time_utc, 1, 10)) c, "
        "MAX(substr(time_utc, 1, 10)) d FROM granules").fetchone()
    lows = [v for v in (rng["a"], rng["c"]) if v]
    highs = [v for v in (rng["b"], rng["d"]) if v]
    return {"products": col("product"), "streams": col("stream"),
            "sats": col("sat"), "prns": col("occ_prn"),
            "date_min": min(lows) if lows else None,
            "date_max": max(highs) if highs else None}


def cache_bytes(path: Path | str = CACHE_DIR) -> int:
    """Bytes of every file under the cache folder.  os.scandir's entries
    carry their size on Windows, where os.walk plus getsize asked the disk
    again for every file (0.21 s against 0.38 s for a month of 10 800 files,
    on every summary refresh and download)."""
    total = 0
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    total += cache_bytes(e.path) if e.is_dir(follow_symlinks=False) else e.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def index_outdated(version: int) -> bool:
    """True when the index was written by readers older than ``version``.
    An empty index is simply marked current."""
    conn = connect()
    row = conn.execute("SELECT v FROM kv WHERE k='index_version'").fetchone()
    if row and row[0] == str(version):
        return False
    if conn.execute("SELECT 1 FROM granules LIMIT 1").fetchone():
        return True
    with conn:
        conn.execute("INSERT OR REPLACE INTO kv VALUES ('index_version', ?)", (str(version),))
    return False


def refresh_metadata() -> dict:
    """Re-read every indexed granule with the current readers, keeping where
    it came from (stream, level, archive day), so a reader fix reaches
    downloaded and imported files alike."""
    from . import readers
    from .parallel import pmap
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT path, product, stream, level, year, doy, date FROM granules")]
    results = pmap(readers.quick_meta_safe, [(r["path"], r["product"]) for r in rows])
    batch = []
    for r, (m, _err) in zip(rows, results):
        if m is not None:
            batch.append(dict(m, **{k: r[k] for k in ("stream", "level", "year", "doy", "date")}))
    n = upsert_granules(batch) if batch else 0
    with conn:
        conn.execute("INSERT OR REPLACE INTO kv VALUES ('index_version', ?)",
                     (str(readers.INDEX_VERSION),))
    return {"indexed": n, "failed": len(rows) - n}


def prune_missing() -> dict:
    """Drop index rows whose granule file is gone from disk.

    The index and the cache can drift apart if files are deleted outside the
    app, so this is called on startup and offered in the UI.
    """
    conn = connect()
    rows = conn.execute("SELECT id, path FROM granules").fetchall()
    gone = [r["id"] for r in rows if not os.path.exists(r["path"])]
    for i in range(0, len(gone), 500):
        chunk = gone[i:i + 500]
        with conn:
            conn.execute(
                f"DELETE FROM granules WHERE id IN ({','.join('?' * len(chunk))})",
                chunk)
    with conn:  # forget datasets that no longer have any granules
        conn.execute(
            "DELETE FROM datasets WHERE NOT EXISTS (SELECT 1 FROM granules g "
            "WHERE g.stream=datasets.stream AND g.product=datasets.product "
            "AND g.year=datasets.year AND g.doy=datasets.doy)")
    return {"pruned": len(gone), "remaining": len(rows) - len(gone)}


def reindex_cache(product_hint: str | None = None) -> dict:
    """Rebuild the index from whatever is on disk (recovery path)."""
    from . import readers  # local import keeps module import cheap
    from .parallel import pmap
    jobs: list[tuple[str, str | None, str | None, dt.date | None]] = []
    for root, _dirs, files in os.walk(CACHE_DIR):
        rel = Path(root).relative_to(CACHE_DIR).parts
        stream = rel[0] if len(rel) > 0 else None
        level = "/".join(rel[1:-3]) if len(rel) > 4 else (rel[1] if len(rel) > 1 else None)
        # Downloads live in <stream>/<level>/<product>/<YYYY>/<DDD>: that is
        # the archive day the granule belongs to (and the dataset it is
        # deleted with), even for the occultations from 23:59 of the day
        # before that open every CDAAC day file.
        day = None
        if len(rel) >= 2 and rel[-2].isdigit() and rel[-1].isdigit():
            try:
                day = dt.date(int(rel[-2]), 1, 1) + dt.timedelta(days=int(rel[-1]) - 1)
            except ValueError:
                day = None
        for f in files:
            if f.endswith("_nc") or f.endswith(".nc"):
                jobs.append((os.path.join(root, f), stream, level, day))
    # Reading metadata is the slow part (thousands of files), so it runs on
    # the worker pool; the SQLite writes stay in this process.
    results = pmap(readers.quick_meta_safe, [(p, product_hint) for p, _, _, _ in jobs])
    added, failed = 0, 0
    batch = []
    for (p, stream, level, day), (m, _err) in zip(jobs, results):
        if m is None:
            failed += 1
            continue
        m.update(stream=stream, level=level)
        d = day
        if d is None and m.get("epoch"):
            d = dt.datetime.fromtimestamp(m["epoch"], dt.timezone.utc).date()
        if d is not None:
            m.update(year=d.year, doy=d.timetuple().tm_yday, date=d.isoformat())
        batch.append(m)
        if len(batch) >= 500:
            added += upsert_granules(batch)
            batch = []
    if batch:
        added += upsert_granules(batch)
    return {"indexed": added, "failed": failed}
