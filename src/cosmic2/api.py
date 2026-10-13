"""HTTP API and static-file host for COSMIC-2 Explorer.

The desktop shell (pywebview) and any browser both talk to this one FastAPI
app: ``/`` serves the frontend, ``/api/*`` serves JSON.  The API is local-only
by default, so there is no authentication layer; binding is to 127.0.0.1 in
``server.py``.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from contextlib import asynccontextmanager

from . import (analysis, climatology, exporters, fetch, parallel, plotting,
               radiosonde, readers, store, vocab)
from .catalog import (COLLECTIONS, PRODUCTS, STREAMS, Archive,
                      describe_product, doy_to_date)
from .config import (APP_TITLE, APP_VERSION, CACHE_DIR, EXPORT_DIR, SETTINGS,
                     CITATION_SOURCE, LEAD_RESEARCHER, DATA_AVAILABILITY_STATEMENT,
                     DATA_LICENSES, DATA_PORTALS, citation, ensure_dirs, frontend_dir,
                     sampledata_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    store.init_db()
    store.prune_missing()
    if store.index_outdated(readers.INDEX_VERSION):
        fetch.manager().submit_reindex(refresh=True)
    # Spawn the analysis workers now, in the background, so the first large
    # composite or plot does not wait for them (see parallel.warm_up).
    if os.environ.get("COSMIC2_NO_WARM_UP") != "1":
        parallel.warm_up()
    yield


app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
# The API has no authentication, so a wildcard CORS policy would let any web
# page open in the user's browser read the index or delete datasets and
# exports through it.  The frontend is served from this same origin and
# needs no CORS at all; other loopback origins (a dev server on another port)
# stay allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

ARCHIVE = Archive(SETTINGS)


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    """An error nobody anticipated: say what failed in words the page can
    show (it showed "500 Internal Server Error") and keep the traceback in
    the log folder."""
    import logging
    import traceback
    from .config import LOG_DIR
    logging.getLogger(__name__).exception("%s failed", request.url.path)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "errors.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now().isoformat()} {request.method} {request.url.path}\n"
                     + "".join(traceback.format_exception(exc)) + "\n")
    except OSError:
        pass
    return JSONResponse(status_code=500, content={"detail": (
        f"Something went wrong while doing that ({type(exc).__name__}: {exc}). "
        f"The details are in {LOG_DIR / 'errors.log'}; please include them if you report it.")})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clean(v: Any) -> Any:
    """JSON-safe: NaN/Inf become null (strict JSON has no NaN literal)."""
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if not math.isfinite(f) else f
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.ndarray):
        if v.dtype.kind == "f" and v.ndim == 1:
            # Whole-array path: element-by-element recursion cost ~0.4 s for
            # a 200-profile overlay, this ~0.02 s.
            out = v.tolist()
            for i in np.flatnonzero(~np.isfinite(v)):
                out[i] = None
            return out
        return _clean(v.tolist())
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _decimate(a: np.ndarray, max_points: int) -> np.ndarray:
    from .pipeline import decimate
    return decimate(a, max_points)


def _granule_or_404(gid: str) -> dict:
    row = store.get_granule(gid)
    if row is None:
        raise HTTPException(404, f"No profile with id {gid!r}")
    if not os.path.exists(row["path"]):
        raise HTTPException(410, f"{row['file_name']} is indexed but missing from "
                                 f"the cache. Run 'Rebuild index' to clean up.")
    return row


def _load(row: dict) -> readers.Granule:
    try:
        return readers.load(row["path"], row["product"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Could not read {row['file_name']}: {exc}") from exc


# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": APP_TITLE, "version": APP_VERSION,
            "time_utc": dt.datetime.now(dt.timezone.utc).isoformat()}


@app.get("/api/meta")
def meta() -> dict:
    """Everything the frontend needs to build its widgets."""
    return _clean({
        "app": {"title": APP_TITLE, "version": APP_VERSION,
                "cache_dir": str(CACHE_DIR), "export_dir": str(EXPORT_DIR)},
        "lead_researcher": LEAD_RESEARCHER,
        "data_availability": DATA_AVAILABILITY_STATEMENT,
        "licenses": DATA_LICENSES,
        "data_portals": DATA_PORTALS,
        "citation": citation(),
        "citation_source": CITATION_SOURCE,
        "streams": {k: {"label": v["label"], "blurb": v["blurb"],
                        "levels": v["levels"], "mission": v.get("mission")}
                    for k, v in STREAMS.items()},
        "collections": [{"stream": s, "level": l} for s, l in COLLECTIONS],
        "products": {c: {"code": p.code, "label": p.label, "kind": p.kind,
                         "blurb": p.blurb, "plain": p.plain,
                         "readable": bool(p.reader), "size_class": p.size_class,
                         "key_vars": list(p.key_vars),
                         "reference": p.reference,
                         "doi": p.doi,
                         "archive_url": p.archive_url,
                         "processing_chain": p.processing_chain,
                         "license": p.license}
                     for c, p in PRODUCTS.items()},
        "vocabulary": {k: vocab.info(k) for k in vocab.VAR_INFO},
        "diag_columns": {c: vocab.column_title(c) for c in vocab.DIAG_COLUMNS},
        "defaults": {"field": vocab.DEFAULT_FIELD, "vertical": vocab.DEFAULT_VERTICAL},
        "lat_bands": [{"min": lo, "max": hi, "name": n}
                      for lo, hi, n in analysis.LAT_BANDS],
        "group_by_options": ["all", "lat_band", "hemisphere", "day_night", "date",
                             "product", "satellite"],
        "settings": SETTINGS.to_dict(),
        "cpu_count": parallel.cpu_count(),
        "effective_workers": parallel.resolve_workers(),
        "sample_data_available": sampledata_dir().is_dir(),
    })


@app.get("/api/data-availability")
def data_availability_endpoint() -> dict:
    """Data availability statements, authoritative archives, and access endpoints."""
    return {
        "lead_researcher": LEAD_RESEARCHER,
        "statement": DATA_AVAILABILITY_STATEMENT,
        "portals": DATA_PORTALS,
        "licenses": DATA_LICENSES,
        "citation": citation(),
    }


@app.get("/api/licenses")
def licenses_endpoint() -> dict:
    """Open source software and data license declarations."""
    return {
        "lead_researcher": LEAD_RESEARCHER,
        "licenses": DATA_LICENSES,
    }


@app.get("/api/variables")
def variables_endpoint() -> dict:
    """Detailed scientific dictionary of all variables, formulas, DOIs, and archive links."""
    return {k: vocab.info(k) for k in vocab.VAR_INFO}


class SettingsPatch(BaseModel):
    # Bounds keep a typo from being persisted and then breaking every later
    # composite or export (a zero grid step used to be accepted and saved).
    max_profiles_per_download: int | None = Field(default=None, ge=0)
    concurrent_downloads: int | None = Field(default=None, ge=1, le=16)
    cache_quota_gb: float | None = Field(default=None, ge=0)
    warn_download_mb: int | None = Field(default=None, ge=0)
    listing_cache_hours: int | None = Field(default=None, ge=0)
    qc_require_good: bool | None = None
    grid_top_km: float | None = Field(default=None, gt=0)
    grid_step_km: float | None = Field(default=None, gt=0)
    plot_dpi: int | None = Field(default=None, ge=50, le=1200)
    analysis_workers: int | None = Field(default=None, ge=0, le=512)
    plot_theme: str | None = None
    ui_theme: str | None = None
    ui_font_size: int | None = None
    ui_mode: str | None = None
    units_temperature: str | None = None
    explain_mode: bool | None = None
    # Sent by the Settings drawer but missing from this model before, so the
    # choice was silently dropped.
    default_stream: str | None = None
    default_product: str | None = None
    auto_update: bool | None = None


@app.post("/api/settings")
def update_settings(patch: SettingsPatch) -> dict:
    if patch.default_stream is not None and patch.default_stream not in STREAMS:
        raise HTTPException(422, f"default_stream must be one of {sorted(STREAMS)}")
    if patch.default_product is not None and patch.default_product not in PRODUCTS:
        raise HTTPException(422, f"default_product must be one of {sorted(PRODUCTS)}")
    before = parallel.resolve_workers()
    try:
        SETTINGS.update(**{k: v for k, v in patch.model_dump().items() if v is not None})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if parallel.resolve_workers() != before:
        parallel.warm_up()   # a new pool size starts a new pool
    return _clean(SETTINGS.to_dict())


@app.get("/api/settings/changes")
def settings_changes() -> dict:
    """Settings added, removed or changed since the version the user last saw
    and, after an automatic update, the new build's release notes (shown once)."""
    from . import settings_migration
    return _clean(settings_migration.pending())


@app.post("/api/settings/changes/ack")
async def settings_changes_ack(request: Request) -> dict:
    """The user has seen the changes; ``{"settings": {...}}`` holds their choices."""
    from . import settings_migration
    try:
        body = await request.json()
    except ValueError:
        body = {}
    patch = (body or {}).get("settings") if isinstance(body, dict) else None
    if patch is not None and not isinstance(patch, dict):
        raise HTTPException(400, "settings must be a JSON object")
    try:
        return _clean(settings_migration.acknowledge(patch))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"The settings could not be saved: {exc}") from exc


@app.get("/api/update/status")
def update_status() -> dict:
    """The weekly automatic update: this build's tag, the last check, a build
    waiting to be installed, a download in progress, or why this copy does not
    update itself."""
    from . import autoupdate
    return _clean(autoupdate.status())


@app.post("/api/update/check")
def update_check() -> dict:
    """Check now: look for a newer published build and download it in the
    background; it is installed when the app next starts."""
    from . import autoupdate
    problem = autoupdate.install_problem()
    if problem:
        raise HTTPException(409, f"This copy cannot update itself: {problem}")
    return _clean(autoupdate.start_check(force=True))


# ---------------------------------------------------------------------------
# remote archive browsing
# ---------------------------------------------------------------------------

@app.get("/api/archive/years")
def archive_years(stream: str = "nrt", level: str = "level2") -> dict:
    try:
        return {"stream": stream, "level": level,
                "years": ARCHIVE.years(stream, level)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"CDAAC listing failed: {exc}") from exc


@app.get("/api/archive/days")
def archive_days(stream: str = "nrt", level: str = "level2",
                 year: int = Query(...)) -> dict:
    try:
        doys = ARCHIVE.doys(stream, level, year)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"CDAAC listing failed: {exc}") from exc
    return {"stream": stream, "level": level, "year": year, "doys": doys,
            "dates": [doy_to_date(year, d).isoformat() for d in doys]}


@app.get("/api/archive/day")
def archive_day(date: str, streams: str | None = None,
                sizes: bool = True) -> dict:
    """What CDAAC published for one calendar day, across collections."""
    try:
        d = dt.date.fromisoformat(date)
    except ValueError as exc:
        raise HTTPException(400, "date must be YYYY-MM-DD") from exc
    sl = [s.strip() for s in streams.split(",")] if streams else None
    try:
        rows = ARCHIVE.day_manifest(d, sl, with_sizes=sizes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"CDAAC listing failed: {exc}") from exc
    return _clean({"date": date, "files": rows,
                   "total_bytes": sum(r["size_bytes"] or 0 for r in rows)})


@app.get("/api/archive/latest")
def archive_latest(stream: str = "nrt", level: str = "level2",
                   product: str | None = None, search_days: int = 14) -> dict:
    res = ARCHIVE.latest_available(stream, level, product, search_days)
    if res is None:
        raise HTTPException(404, f"Nothing published in {stream}/{level} in the "
                                 f"last {search_days} days")
    return res


@app.post("/api/archive/clear-cache")
def archive_clear_cache() -> dict:
    ARCHIVE.clear_cache()
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# downloads / jobs
# ---------------------------------------------------------------------------

MAX_DOWNLOAD_DAYS = 31


class DownloadRequest(BaseModel):
    stream: str = "nrt"
    level: str = "level2"
    product: str = "wetPf2"
    date: str
    # last day (inclusive): the same product is fetched for every day from
    # date to date_end, one download each
    date_end: str | None = None
    max_profiles: int | None = Field(default=None,
                                     description="0 or null means the whole day")
    sampling: Literal["first", "spread"] = "spread"
    good_only: bool = False


@app.post("/api/download")
def start_download(req: DownloadRequest) -> dict:
    """One day (the job), or with ``date_end`` one download per day (the
    jobs, at most MAX_DOWNLOAD_DAYS)."""
    try:
        first = dt.date.fromisoformat(req.date)
        last = dt.date.fromisoformat(req.date_end) if req.date_end else first
    except ValueError as exc:
        raise HTTPException(400, "date must be YYYY-MM-DD") from exc
    if last < first:
        raise HTTPException(400, "date_end is before date")
    n_days = (last - first).days + 1
    if n_days > MAX_DOWNLOAD_DAYS:
        raise HTTPException(400, f"at most {MAX_DOWNLOAD_DAYS} days in one request")
    jobs = [fetch.manager().submit_download(
        stream=req.stream, level=req.level, product=req.product,
        date=(first + dt.timedelta(days=i)).isoformat(),
        max_profiles=req.max_profiles, sampling=req.sampling,
        good_only=req.good_only) for i in range(n_days)]
    if not req.date_end:
        return _clean(jobs[0].snapshot())
    return _clean({"n_days": n_days, "date": first.isoformat(), "date_end": last.isoformat(),
                   "jobs": [j.snapshot() for j in jobs]})


@app.get("/api/jobs")
def list_jobs(active_only: bool = False) -> dict:
    return _clean({"jobs": fetch.manager().list(active_only)})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = fetch.manager().get(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown job {job_id!r}")
    return _clean(job.snapshot())


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    ok = fetch.manager().cancel(job_id)
    if not ok:
        raise HTTPException(409, "Job is not running")
    return {"status": "cancelling", "job_id": job_id}


@app.post("/api/jobs/reindex")
def reindex() -> dict:
    return _clean(fetch.manager().submit_reindex().snapshot())


@app.post("/api/local/prune")
def prune() -> dict:
    return store.prune_missing()


class ImportRequest(BaseModel):
    paths: list[str]
    product: str | None = None


@app.post("/api/local/import")
def import_files(req: ImportRequest) -> dict:
    """Index granules the user already has on disk."""
    found: list[str] = []
    for raw in req.paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            found += [str(q) for q in p.rglob("*")
                      if q.is_file() and (q.name.endswith("_nc") or q.suffix == ".nc")]
        elif p.is_file():
            found.append(str(p))
    if not found:
        raise HTTPException(400, "No netCDF files (.nc or _nc) found at the given paths")
    return _clean(fetch.import_local_files(found, req.product))


@app.post("/api/local/upload-file")
async def upload_file(request: Request, filename: str = Query(...)) -> dict:
    """Accept a raw NetCDF file stream via drag-and-drop and index it locally."""
    clean_name = os.path.basename(filename)
    if not (clean_name.endswith("_nc") or clean_name.endswith(".nc")):
        raise HTTPException(400, "File must be a netCDF file (*.nc or *_nc)")

    target_dir = CACHE_DIR / "imported"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / clean_name

    content = await request.body()
    if not content:
        raise HTTPException(400, "File content is empty")

    with open(target_path, "wb") as f:
        f.write(content)

    res = fetch.import_local_files([str(target_path)])
    return _clean({"saved_path": str(target_path), **res})


@app.post("/api/local/load-samples")
def load_samples() -> dict:
    """Index the granules bundled with the application.

    Gives a first-run user something to look at without a download, and makes
    the app usable with no network at all.
    """
    d = sampledata_dir()
    if not d.is_dir():
        raise HTTPException(404, "No sample data bundled with this build")
    files = [str(p) for p in d.iterdir()
             if p.is_file() and (p.name.endswith("_nc") or p.suffix == ".nc")]
    if not files:
        raise HTTPException(404, "Sample data directory is empty")
    return _clean(fetch.import_local_files(files))


# ---------------------------------------------------------------------------
# local index
# ---------------------------------------------------------------------------

@app.get("/api/local/summary")
def local_summary() -> dict:
    s = store.summary()
    s["cache_bytes_on_disk"] = s.pop("cache_bytes_indexed")
    s["cache_quota_bytes"] = int(SETTINGS.cache_quota_gb * 1024 ** 3)
    return _clean(s)


@app.get("/api/local/datasets")
def local_datasets() -> dict:
    return _clean({"datasets": store.datasets()})


@app.delete("/api/local/datasets/{key:path}")
def delete_dataset(key: str, remove_files: bool = True) -> dict:
    return _clean(store.delete_dataset(key, remove_files))


@app.get("/api/local/facets")
def local_facets() -> dict:
    return _clean(store.facets())


@app.get("/api/local/coverage")
def local_coverage(products: str | None = None, good_only: bool = False,
                   bin_deg: float = 5.0) -> dict:
    pl = [p.strip() for p in products.split(",")] if products else None
    return _clean(store.coverage(pl, good_only, bin_deg))


# ---------------------------------------------------------------------------
# profile search and retrieval
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    products: list[str] | None = None
    streams: list[str] | None = None
    start: str | None = None
    end: str | None = None
    lat_min: float | None = None
    lat_max: float | None = None
    lon_min: float | None = None
    lon_max: float | None = None
    local_time_min: float | None = None
    local_time_max: float | None = None
    sats: list[str] | None = None
    prns: list[str] | None = None
    good_only: bool = False
    min_levels: int | None = None
    sort: str = "time"
    desc: bool = False
    limit: int = 200
    offset: int = 0


@app.post("/api/profiles/search")
def search_profiles(req: SearchRequest) -> dict:
    return _clean(store.query_granules(**req.model_dump()))


@app.get("/api/profiles/{gid}")
def profile_detail(gid: str, diagnostics: bool = True) -> dict:
    row = _granule_or_404(gid)
    g = _load(row)
    out: dict[str, Any] = {
        "granule": row,
        "meta": g.meta,
        "warnings": g.warnings,
        "vertical": g.vertical,
        "independent": g.independent,
        "variables": g.variables(),
        "derived_variables": [
            dict(vocab.info(k), name=k, derived=True,
                 n_valid=int(np.isfinite(v).sum()))
            for k, v in analysis.derived_fields(g).items()],
        "attribute_notes": g.attr_desc,
        "product_info": vars(describe_product(g.product)),
    }
    if diagnostics:
        out["diagnostics"] = analysis.diagnostics(g)
    return _clean(out)


@app.get("/api/profiles/{gid}/data")
def profile_data(gid: str, vars: str | None = None, max_points: int = 1200,
                 include_derived: bool = True) -> dict:
    """Arrays for one granule, decimated for display."""
    row = _granule_or_404(gid)
    g = _load(row)
    src = dict(g.data)
    if include_derived:
        src.update(analysis.derived_fields(g))
    wanted = [v.strip() for v in vars.split(",")] if vars else [
        k for k in src if not readers.BULK_VAR_RE.match(k)]
    missing = [w for w in wanted if w not in src]
    series = {}
    for name in wanted:
        if name not in src:
            continue
        arr = _decimate(src[name], max_points)
        series[name] = {
            "values": _clean(arr),
            "units": g.units.get(name) or vocab.info(name)["units"],
            "label": vocab.info(name, g.product)["label"],
            "plain": vocab.info(name, g.product)["plain"],
            "decimated": src[name].size > arr.size,
            "n_original": int(src[name].size),
        }
    return _clean({"granule_id": gid, "product": g.product, "meta": g.meta,
                   "vertical": g.vertical, "series": series,
                   "unavailable": missing})


class PlotRequest(BaseModel):
    granule_ids: list[str]
    field: str
    vertical: str = "MSL_alt"
    max_points: int = 900
    convert_kelvin: bool = False
    outlier_method: str = "none"
    outlier_kwargs: dict = Field(default_factory=dict)
    smooth_method: str = "none"
    smooth_kwargs: dict = Field(default_factory=dict)
    uncert_method: str = "none"
    uncert_kwargs: dict = Field(default_factory=dict)


@app.post("/api/plot/profiles")
def plot_profiles(req: PlotRequest) -> dict:
    """Series ready for an overlay plot in the browser."""
    if not req.granule_ids:
        raise HTTPException(400, "Select at least one profile")
    rows = store.get_granules(req.granule_ids)
    out, skipped = [], []
    units = ""
    products: set[str] = set()
    # Reading and filtering each granule is independent work: a page of 100+
    # atmPrf profiles is drawn on the worker processes (see .parallel).
    from .parallel import pmap
    from .pipeline import profile_series
    params = req.model_dump(exclude={"granule_ids"})
    for row, res in zip(rows, pmap(profile_series, [(r, params) for r in rows])):
        if "skip" in res:
            skipped.append({"file": row["file_name"], "product": row["product"],
                            "why": res["skip"]})
            continue
        # Kelvin conversion labels every series "K"; otherwise the first
        # profile's units stand for the overlay.
        units = res["units"] if res["units"] == "K" else (units or res["units"])
        products.add(res["product"])
        out.append(res["series"])
    return _clean({
        "field": req.field, "vertical": req.vertical, "units": units,
        "field_label": _overlay_title(req.field, products, units),
        "vertical_label": vocab.axis_title(req.vertical),
        "series": out, "skipped": skipped,
    })


def _overlay_title(field: str, products: set[str], units: str) -> str:
    """The x title of an overlay: the quantity as its products hold it, each
    named when they differ (atmPrf "Temp" is the dry temperature)."""
    labels = {p: analysis.quantity_label(field, p) for p in sorted(products)}
    if not labels:
        return vocab.axis_title(field, units)
    if len(set(labels.values())) == 1:
        return analysis.quantity_title(next(iter(labels.values())), units)
    return analysis.quantity_title("; ".join(f"{lab} ({p})" for p, lab in labels.items()), units)


class CompositeRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    field: str = "Temp"
    vertical: str = "MSL_alt"
    group_by: str = "lat_band"
    top_km: float = Field(default=60.0, gt=0)
    step_km: float = Field(default=0.5, gt=0)
    good_only: bool = True
    min_count: int = Field(default=3, ge=1)
    convert_kelvin: bool = True
    max_profiles: int = 2000
    # drop each group's outlying profiles first (analysis.robust_screen)
    screen_k: float | None = Field(default=None, ge=2, le=20)


def _resolve_selection(granule_ids: list[str] | None,
                       search: SearchRequest | None,
                       cap: int) -> list[dict]:
    if granule_ids:
        rows = store.get_granules(granule_ids)
    elif search is not None:
        payload = search.model_dump()
        payload["limit"] = min(cap, max(payload.get("limit") or cap, 1))
        payload["offset"] = 0
        rows = store.query_granules(**payload)["granules"]
    else:
        rows = store.query_granules(limit=cap)["granules"]
    return [r for r in rows if os.path.exists(r["path"])]


@app.post("/api/composite")
def make_composite(req: CompositeRequest) -> dict:
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    comp = analysis.composite(
        [(r["path"], r) for r in rows], req.field, req.vertical,
        group_by=req.group_by, top_km=req.top_km, step_km=req.step_km,
        good_only=req.good_only, min_count=req.min_count,
        convert_kelvin=req.convert_kelvin, screen_k=req.screen_k)
    out = comp.to_json()
    out["selected"] = len(rows)
    # what the selection holds, so an empty result can say why (an ivmL2m
    # selection has no height profiles to average)
    products: dict[str, int] = {}
    for r in rows:
        products[r["product"]] = products.get(r["product"], 0) + 1
    out["products"] = products
    out["missions"] = _missions_of(rows)
    return _clean(out)


class DiagnosticsTableRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    max_profiles: int = 1000


@app.post("/api/diagnostics/table")
def diagnostics_table(req: DiagnosticsTableRequest) -> dict:
    """Flat table of scalar diagnostics, one row per profile.

    This is the shape needed to plot tropopause height against latitude, or
    peak electron density against local time, across a whole day.
    """
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    results = analysis.diagnostics_rows(rows)
    table = [r for r in results if r is not None]
    failed = len(results) - len(table)
    columns = sorted({k for row in table for k in row})
    return _clean({"rows": table, "columns": columns, "n": len(table),
                   "unreadable": failed})


# ---------------------------------------------------------------------------
# statistics and climatologies
# ---------------------------------------------------------------------------

class StatsRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    lat_step: float = Field(default=10.0, gt=0, le=90)
    max_profiles: int = Field(default=200000, ge=1)


@app.post("/api/stats/sampling")
def stats_sampling(req: StatsRequest) -> dict:
    """Counts, quality flags and penetration depth of a selection.

    Read from the index only (no granule is opened), so it is instant even
    for a whole downloaded month.
    """
    if req.granule_ids:
        rows = store.get_granules(req.granule_ids)
    else:
        payload = (req.search.model_dump() if req.search is not None else {})
        payload.update(limit=req.max_profiles, offset=0)
        rows = store.query_granules(**payload)["granules"]
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    # Terrain heights come from every wetPf2 on disk, so an atmPrf-only
    # selection still gets heights above the ground.
    wet = store.query_granules(products=["wetPf2"], limit=10 ** 7)["granules"]
    return _clean(climatology.sampling_statistics(
        rows, lat_step=req.lat_step, terrain=climatology.terrain_by_atmprf(wet)))


class SectionRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    field: str = "Temp"
    vertical: str = "MSL_alt"
    lat_step: float = Field(default=5.0, gt=0, le=90)
    bottom_km: float = Field(default=0.0, ge=0)
    top_km: float = Field(default=40.0, gt=0)
    step_km: float = Field(default=0.5, gt=0)
    good_only: bool = True
    min_count: int = Field(default=3, ge=1)
    convert_kelvin: bool = True
    max_profiles: int = Field(default=5000, ge=1)
    screen_k: float | None = Field(default=None, ge=2, le=20)


class ProductPairRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    quantity: Literal["refractivity", "dry_temperature", "dry_pressure",
                      "moisture_effect"] = "refractivity"
    bottom_km: float = Field(default=0.0, ge=0)
    top_km: float = Field(default=30.0, gt=0, le=100)
    step_km: float = Field(default=0.5, gt=0)
    min_count: int = Field(default=3, ge=1)
    good_only: bool = True
    max_profiles: int = Field(default=5000, ge=1)


@app.post("/api/compare/products")
def compare_products(req: ProductPairRequest) -> dict:
    """atmPrf against the wetPf2 retrieved from it, for the occultations of
    the selection (either product): the statistics of their difference by
    height."""
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    if req.top_km <= req.bottom_km:
        raise HTTPException(422, "top_km must be above bottom_km")
    atm = store.query_granules(products=["atmPrf"], limit=10 ** 7)["granules"]
    wet = store.query_granules(products=["wetPf2"], limit=10 ** 7)["granules"]
    pairs = climatology.pair_rows(rows, atm, wet, good_only=req.good_only)
    out = climatology.product_differences(
        pairs, req.quantity, top_km=req.top_km, step_km=req.step_km,
        bottom_km=req.bottom_km, min_count=req.min_count)
    out["selected"] = len(rows)
    return _clean(out)


class ModelCompareRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    kind: Literal["differences", "tch", "ducting", "ducting_rel"] = "differences"
    quantity: Literal["refractivity", "temperature", "bending_angle"] = "refractivity"
    bottom_km: float = Field(default=0.0, ge=0)
    top_km: float = Field(default=30.0, gt=0, le=60)
    step_km: float = Field(default=0.5, ge=0.1, le=5)
    # levels with fewer profiles are blank (default 3, or 30 triplets for the
    # three-cornered hat)
    min_count: int | None = Field(default=None, ge=1)
    n_boot: int = Field(default=200, ge=20, le=2000)
    good_only: bool = True
    max_profiles: int = Field(default=20000, ge=1)


@app.post("/api/compare/models")
def compare_models(req: ModelCompareRequest) -> dict:
    """Radio occultation against the ECMWF (echPrf) and NCEP (avnPrf)
    profiles CDAAC colocates with each occultation of the selection: RO minus
    model by height, or the three-cornered-hat error estimates of all three."""
    from . import nwp
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    if req.top_km <= req.bottom_km:
        raise HTTPException(422, "top_km must be above bottom_km")
    index = store.query_granules(products=["atmPrf", "wetPf2", "echPrf", "avnPrf"],
                                 limit=10 ** 7)["granules"]
    groups = nwp.stamp_groups(rows, index, good_only=req.good_only)
    if req.kind == "tch":
        out = nwp.three_cornered_hat(groups, top_km=req.top_km, step_km=req.step_km,
                                     bottom_km=req.bottom_km, min_count=req.min_count or 30,
                                     n_boot=req.n_boot)
    elif req.kind in ("ducting", "ducting_rel"):
        out = nwp.ducting_differences(groups, top_km=req.top_km, step_km=req.step_km,
                                      bottom_km=req.bottom_km,
                                      around_duct=req.kind == "ducting_rel",
                                      min_count=req.min_count or 3)
    else:
        out = nwp.model_differences(groups, req.quantity, top_km=req.top_km,
                                    step_km=req.step_km, bottom_km=req.bottom_km,
                                    min_count=req.min_count or 3)
    have = {p: sum(1 for g in groups if p in g) for p in ("atmPrf", "wetPf2", "echPrf", "avnPrf")}
    out.update(kind=req.kind, selected=len(rows), occultations=len(groups), products_found=have,
               missions=_missions_of(rows))
    return _clean(out)


def _missions_of(rows) -> dict[str, int]:
    """Profiles per mission ("COSMIC-2", "PAZ", "KOMPSAT-5"), so a caption can
    say when a statistic mixes missions."""
    from .missions import MISSION_NAMES, mission_of_sat
    out: dict[str, int] = {}
    for r in rows:
        name = MISSION_NAMES.get(mission_of_sat(r.get("sat")) or "")
        if name:
            out[name] = out.get(name, 0) + 1
    return out


class TropopauseRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    lat_step: float = Field(default=10.0, gt=0, le=90)
    min_count: int = Field(default=3, ge=1)
    max_profiles: int = Field(default=20000, ge=1)


@app.post("/api/climatology/tropopause")
def climatology_tropopause(req: TropopauseRequest) -> dict:
    """WMO tropopause and cold point by latitude band, with 95 % intervals,
    and CDAAC's own values for atmPrf."""
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    out = climatology.tropopause_table(rows, lat_step=req.lat_step, min_count=req.min_count)
    out["missions"] = _missions_of([r for r in rows if r.get("good", True)
                                    and r.get("product") in ("atmPrf", "wetPf2")])
    return _clean(out)


class MissionCompareRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    other: Literal["paz", "kompsat5"] = "paz"
    quantity: Literal["temperature", "refractivity_1dvar", "refractivity"] = "temperature"
    max_km: float = Field(default=300.0, gt=0, le=2000)
    max_hours: float = Field(default=3.0, gt=0, le=24)
    bottom_km: float = Field(default=0.0, ge=0)
    top_km: float = Field(default=30.0, gt=0, le=60)
    step_km: float = Field(default=0.5, ge=0.1, le=5)
    min_count: int = Field(default=3, ge=1)
    max_profiles: int = Field(default=50000, ge=1)


@app.post("/api/compare/missions")
def compare_missions(req: MissionCompareRequest) -> dict:
    """COSMIC-2 against PAZ or KOMPSAT-5: collocated pairs and the double
    difference through ECMWF, by height.  The selection's dates (and other
    filters) apply; the quantity decides the product."""
    from . import missions
    prod = missions.QUANTITIES[req.quantity][0]
    if req.search is not None:
        req.search.products = [prod]
        req.search.sats = None
    # an empty selection is an answer here (the card says which profiles are missing)
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles) or []
    index = store.query_granules(products=[prod, "echPrf"], limit=10 ** 7)["granules"]
    if req.top_km <= req.bottom_km:
        raise HTTPException(422, "top_km must be above bottom_km")
    out = missions.compare(rows, index, other=req.other, quantity=req.quantity,
                           max_km=req.max_km, max_hours=req.max_hours, top_km=req.top_km,
                           step_km=req.step_km, bottom_km=req.bottom_km,
                           min_count=req.min_count)
    out["selected"] = len(rows)
    return _clean(out)


@app.post("/api/climatology/section")
def climatology_section(req: SectionRequest) -> dict:
    """Zonal-mean latitude-height section (mean, spread, count, and the
    departure of each latitude band from the selection's mean)."""
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    if req.top_km <= req.bottom_km:
        raise HTTPException(422, "top_km must be above bottom_km")
    try:
        sec = climatology.cross_section(
            [(r["path"], r) for r in rows], req.field, req.vertical,
            lat_step=req.lat_step, top_km=req.top_km, step_km=req.step_km,
            bottom_km=req.bottom_km, good_only=req.good_only,
            min_count=req.min_count, convert_kelvin=req.convert_kelvin,
            screen_k=req.screen_k)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    sec["selected"] = len(rows)
    sec["missions"] = _missions_of([r for r in rows if r.get("good", True) or not req.good_only])
    return _clean(sec)


class MapRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    column: str = climatology.EP_COLUMN
    lat_step: float = Field(default=10.0, gt=0, le=90)
    lon_step: float = Field(default=20.0, gt=0, le=180)
    min_count: int = Field(default=1, ge=1)
    # Gravity-wave energy only: layer and background filter.
    gw_z_lo: float = Field(default=20.0, ge=0)
    gw_z_hi: float = Field(default=40.0, gt=0)
    gw_method: Literal["polynomial", "highpass"] = "polynomial"
    gw_poly_order: int = Field(default=4, ge=1, le=8)
    gw_cutoff_km: float = Field(default=10.0, gt=0.5)
    max_profiles: int = Field(default=5000, ge=1)
    good_only: bool = True


@app.post("/api/climatology/map")
def climatology_map(req: MapRequest) -> dict:
    """Latitude-longitude map and zonal mean of a per-profile diagnostic."""
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    # like the section and the tables: profiles CDAAC flagged bad stay out
    # (a selection could hold them; the search path already left them out)
    rows = [r for r in rows if r.get("good", True) or not req.good_only]
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    gw = None
    if req.column == climatology.EP_COLUMN:
        if req.gw_z_hi <= req.gw_z_lo:
            raise HTTPException(422, "gw_z_hi must be above gw_z_lo")
        gw = {"z_lo": req.gw_z_lo, "z_hi": req.gw_z_hi, "method": req.gw_method}
        gw.update({"poly_order": req.gw_poly_order} if req.gw_method == "polynomial"
                  else {"cutoff_km": req.gw_cutoff_km})
    try:
        res = climatology.diagnostic_map(rows, req.column, req.lat_step, req.lon_step,
                                         req.min_count, gw=gw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    res["selected"] = len(rows)
    res["title"] = vocab.column_title(req.column)
    res["missions"] = _missions_of(rows)
    return _clean(res)


class RadiosondeRequest(BaseModel):
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    max_km: float = Field(default=300.0, gt=0, le=1000)
    max_hours: float = Field(default=3.0, gt=0, le=24)
    top_km: float = Field(default=30.0, gt=1, le=40)
    bin_km: float = Field(default=1.0, gt=0.1, le=10)
    # station files are read (and fetched once) for at most this many
    # stations, those with the most occultations nearby
    max_stations: int = Field(default=200, ge=1, le=2000)
    download: bool = True
    export_csv: bool = False
    max_profiles: int = Field(default=5000, ge=1)
    # atmPrf "Temp" is the dry temperature, wetPf2's the real one: the two
    # are never pooled against the same sondes
    product: Literal["wetPf2", "atmPrf"] | None = None


@app.post("/api/validation/radiosonde")
def validation_radiosonde(req: RadiosondeRequest) -> dict:
    """Occultation minus radiosonde (NOAA IGRA v2) by height.

    Fetches the station files it needs from NCEI on first use (cached
    afterwards), so the first comparison of a period takes a minute or two.
    """
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    rows = [r for r in rows if r["product"] in ((req.product,) if req.product
                                                else ("atmPrf", "wetPf2")) and r.get("good")]
    if not rows:
        raise HTTPException(400, f"No good {req.product or 'atmPrf or wetPf2'} profiles in that selection")
    if len({r["product"] for r in rows}) > 1:
        raise HTTPException(400, "The selection holds both atmPrf (dry temperature) and wetPf2: "
                                 "choose one product")
    try:
        res = radiosonde.compare(rows, req.max_km, req.max_hours, req.top_km,
                                 bin_km=req.bin_km, download=req.download,
                                 max_stations=req.max_stations)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    res["products"] = sorted({r["product"] for r in rows})
    if req.export_csv and res["n_pairs"]:
        used = {p["granule_id"] for p in res["pairs"]}
        res["export"] = exporters.export_radiosonde_csv(
            res, [r for r in rows if r["id"] in used])
    return _clean(res)


@app.get("/api/coastlines")
def coastlines_endpoint(resolution: Literal["110m", "50m"] = "110m") -> dict:
    """Bundled coastlines as one polyline (null between segments), for maps
    drawn as plain x-y plots."""
    lon: list = []
    lat: list = []
    for line in plotting.coastlines(resolution):
        lon += line[:, 0].round(3).tolist() + [None]
        lat += line[:, 1].round(3).tolist() + [None]
    return {"lon": lon, "lat": lat}


# ---------------------------------------------------------------------------
# exports
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    kind: Literal["profiles_csv", "metadata_csv", "grid_csv", "netcdf", "json"]
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    variables: list[str] | None = None
    field: str = "Temp"
    vertical: str = "MSL_alt"
    top_km: float = Field(default=60.0, gt=0)
    step_km: float = Field(default=0.2, gt=0)
    basename: str = "cosmic2"
    max_profiles: int = 2000
    outlier_method: str = "none"
    smooth_method: str = "none"
    uncert_method: str = "none"


def _display_processing(req) -> dict:
    """Provenance entry for the Profiles-tab processing settings.

    Exports are written from the archive values (plus derived fields); the
    outlier, smoothing and uncertainty settings shape only the on-screen
    plot.  Recording the settings without saying so would suggest the file
    holds filtered data, so the entry states it explicitly.
    """
    return {
        "processing_parameters": {
            "outlier_method": req.outlier_method,
            "smooth_method": req.smooth_method,
            "uncert_method": req.uncert_method,
            "applied_to_exported_values": False,
            "note": ("These are the interactive plot settings at export time. "
                     "Exported values are unfiltered archive values and "
                     "derived fields."),
        }
    }


@app.post("/api/export/data")
def export_data(req: ExportRequest) -> dict:
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    if not rows:
        raise HTTPException(400, "No local profiles match that selection")
    extra_prov = _display_processing(req)
    try:
        if req.kind == "profiles_csv":
            res = exporters.export_profiles_csv(rows, req.variables,
                                                basename=req.basename, extra_prov=extra_prov)
        elif req.kind == "metadata_csv":
            res = exporters.export_metadata_csv(rows, basename=req.basename, extra_prov=extra_prov)
        elif req.kind == "grid_csv":
            res = exporters.export_grid_csv(rows, req.field, req.vertical,
                                            req.top_km, req.step_km,
                                            basename=req.basename, extra_prov=extra_prov)
        elif req.kind == "netcdf":
            res = exporters.export_netcdf(rows, req.variables, req.vertical,
                                          req.top_km, req.step_km,
                                          basename=req.basename, extra_prov=extra_prov)
        else:
            res = exporters.export_json(
                {"granules": rows, "provenance": exporters.provenance(rows, extra_prov)},
                basename=req.basename)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return _clean(res)


class FigureRequest(BaseModel):
    kind: Literal["profiles", "composite", "map", "coverage", "panels", "scatter"]
    granule_ids: list[str] | None = None
    search: SearchRequest | None = None
    field: str = "Temp"
    vertical: str = "MSL_alt"
    group_by: str = "lat_band"
    x_field: str | None = None
    y_field: str | None = None
    color_field: str | None = None
    panels: list[str] | None = None
    title: str = ""
    caption: str = ""
    fmt: Literal["png", "pdf", "svg", "eps", "jpg"] = "png"
    dpi: int | None = Field(default=None, ge=50, le=1200)
    logx: bool = False
    spread: Literal["std", "p10p90", "ci95"] = "std"
    convert_kelvin: bool = False
    screen_k: float | None = Field(default=None, ge=2, le=20)
    top_km: float = Field(default=60.0, gt=0)     # composite grid
    step_km: float = Field(default=0.5, gt=0)
    max_profiles: int = 2000
    outlier_method: str = "none"
    smooth_method: str = "none"
    uncert_method: str = "none"


@app.post("/api/export/figure")
def export_figure(req: FigureRequest) -> dict:
    """Render a publication-quality figure server-side and save it."""
    rows = _resolve_selection(req.granule_ids, req.search, req.max_profiles)
    if not rows and req.kind not in ("coverage",):
        raise HTTPException(400, "No local profiles match that selection")
    try:
        fig = _build_figure(req, rows)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, f"Cannot build that figure: {exc}") from exc
    res = exporters.export_figure(fig, req.fmt, req.title or f"cosmic2_{req.kind}",
                                  req.dpi)
    extra_prov = _display_processing(req)
    res["provenance"] = exporters.provenance(rows, extra_prov)
    return _clean(res)


def _latlon(meta: dict) -> str:
    """'12.3N 45.6E', or '' when the granule has no position."""
    lat, lon = meta.get("lat"), meta.get("lon")
    if lat is None or lon is None:
        return ""
    return f"{lat:.1f}N {lon:.1f}E"


def _build_figure(req: FigureRequest, rows: list[dict]):
    if req.kind == "coverage":
        # the selection's products (it showed every file indexed, so one
        # occultation counted four times with its atmPrf, wetPf2 and models)
        return plotting.coverage_figure(
            store.coverage(products=sorted({r["product"] for r in rows})), title=req.title)
    if req.kind == "map":
        return plotting.map_figure(rows, req.color_field, title=req.title,
                                   caption=req.caption)
    if req.kind == "composite":
        comp = analysis.composite([(r["path"], r) for r in rows], req.field,
                                  req.vertical, group_by=req.group_by,
                                  top_km=req.top_km, step_km=req.step_km,
                                  convert_kelvin=req.convert_kelvin,
                                  screen_k=req.screen_k).to_json()
        return plotting.composite_figure(comp, spread=req.spread, title=req.title,
                                         caption=req.caption, logx=req.logx)
    if req.kind == "panels":
        g = readers.load(rows[0]["path"], rows[0]["product"])
        src = dict(g.data)
        src.update(analysis.derived_fields(g))
        names = [n for n in (req.panels or [req.field]) if n in src]
        if not names:
            raise ValueError(f"none of {req.panels} exist in {g.product}")
        panels = [{"x": src[n], "y": src[req.vertical], "x_var": n,
                   "units": g.units.get(n, ""), "y_var": req.vertical,
                   "product": g.product,
                   "logx": n in ("ref", "Ref", "ELEC_dens")} for n in names]
        return plotting.panels_figure(
            panels, suptitle=req.title or
            f"{g.meta['product']} {g.meta['time_utc'] or ''} {_latlon(g.meta)}",
            caption=req.caption)
    if req.kind == "scatter":
        tbl = diagnostics_table(DiagnosticsTableRequest(
            granule_ids=[r["id"] for r in rows]))["rows"]
        xf = req.x_field or "lat"
        yf = req.y_field or "tropopause.height_km"
        xs = [r.get(xf) for r in tbl]
        ys = [r.get(yf) for r in tbl]
        cs = [r.get(req.color_field) for r in tbl] if req.color_field else None
        return plotting.scatter_figure(
            [np.nan if v is None else v for v in xs],
            [np.nan if v is None else v for v in ys],
            xf, yf, color=None if cs is None else
            [np.nan if v is None else v for v in cs],
            color_var=req.color_field or "", title=req.title,
            caption=req.caption or f"n = {len(tbl)} profiles.")
    # default: overlay of profiles
    # max_points=0: a publication figure is drawn from every level, not from
    # the ~900-point subsample sent to the browser (atmPrf has ~3800 levels).
    series = plot_profiles(PlotRequest(granule_ids=[r["id"] for r in rows],
                                       field=req.field, vertical=req.vertical,
                                       convert_kelvin=req.convert_kelvin,
                                       max_points=0))
    items = [{"x": s["x"], "y": s["y"], "label": s["label"], "value": s["lat"]}
             for s in series["series"]]
    if not items:
        raise ValueError("no profile carried the requested field")
    return plotting.profile_figure(
        items, req.field, req.vertical, title=req.title,
        x_units=series["units"], x_label=series["field_label"],
        color_by="Lat", logx=req.logx,
        caption=req.caption or f"{len(items)} COSMIC-2 profiles.")


@app.get("/api/exports")
def list_exports() -> dict:
    return _clean({"exports": exporters.list_exports()})


@app.get("/api/exports/{filename}")
def fetch_export(filename: str):
    """Serve a generated file for download."""
    safe = Path(filename).name
    path = EXPORT_DIR / safe
    if not path.is_file():
        raise HTTPException(404, f"No export named {safe!r}")
    return FileResponse(path, filename=safe, media_type="application/octet-stream")


@app.delete("/api/exports/{filename}")
def delete_export(filename: str) -> dict:
    path = EXPORT_DIR / Path(filename).name
    if not path.is_file():
        raise HTTPException(404, "No such export")
    path.unlink()
    return {"deleted": path.name}


@app.get("/api/reveal-folder")
def reveal_folder(which: Literal["exports", "cache"] = "exports") -> dict:
    """Open the exports or cache folder in the OS file manager."""
    target = EXPORT_DIR if which == "exports" else CACHE_DIR
    ensure_dirs()
    try:
        if os.name == "nt":
            os.startfile(target)  # noqa: S606 - local desktop app, fixed paths
        else:
            import subprocess
            opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
            subprocess.Popen([opener, str(target)])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not open {target}: {exc}") from exc
    return {"opened": str(target)}


# ---------------------------------------------------------------------------
# static frontend (mounted last so /api/* wins)
# ---------------------------------------------------------------------------

_FRONTEND = frontend_dir()
if _FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
else:  # pragma: no cover
    @app.get("/")
    def _no_frontend() -> JSONResponse:
        return JSONResponse(
            {"error": "frontend assets not found", "looked_in": str(_FRONTEND)},
            status_code=500)
