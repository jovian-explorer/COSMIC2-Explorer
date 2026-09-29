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
            "ON CONFLICT(id) DO UPDATE SET "
            "product=excluded.product, stream=excluded.stream, level=excluded.level, "
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
    """Filtered, paged granule search. ``start``/``end`` are ISO timestamps."""
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
    }


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
        f"SELECT CAST(FLOOR(lat/{b}) AS INT) iy, CAST(FLOOR(lon/{b}) AS INT) ix, "
        f"COUNT(*) n FROM granules{w} GROUP BY iy, ix", args).fetchall()
    lat_hist = conn.execute(
        f"SELECT CAST(FLOOR(lat/5.0) AS INT) iy, COUNT(*) n FROM granules{w} "
        f"GROUP BY iy ORDER BY iy", args).fetchall()
    lt_hist = conn.execute(
        f"SELECT CAST(FLOOR(local_time) AS INT) h, COUNT(*) n FROM granules{w} "
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

    rng = conn.execute("SELECT MIN(date) a, MAX(date) b FROM granules").fetchone()
    return {"products": col("product"), "streams": col("stream"),
            "sats": col("sat"), "prns": col("occ_prn"),
            "date_min": rng["a"], "date_max": rng["b"]}


def cache_bytes() -> int:
    total = 0
    for root, _dirs, files in os.walk(CACHE_DIR):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


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
    added, failed = 0, 0
    for root, _dirs, files in os.walk(CACHE_DIR):
        rel = Path(root).relative_to(CACHE_DIR).parts
        stream = rel[0] if len(rel) > 0 else None
        level = "/".join(rel[1:-3]) if len(rel) > 4 else (rel[1] if len(rel) > 1 else None)
        batch = []
        for f in files:
            if not (f.endswith("_nc") or f.endswith(".nc")):
                continue
            p = os.path.join(root, f)
            try:
                m = readers.quick_meta(p, product_hint)
            except Exception:
                failed += 1
                continue
            m.update(stream=stream, level=level)
            if m.get("epoch"):
                d = dt.datetime.fromtimestamp(m["epoch"], dt.timezone.utc).date()
                m.update(year=d.year, doy=d.timetuple().tm_yday, date=d.isoformat())
            batch.append(m)
        if batch:
            added += upsert_granules(batch)
    return {"indexed": added, "failed": failed}
