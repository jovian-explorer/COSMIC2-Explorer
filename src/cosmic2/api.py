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

from . import analysis, exporters, fetch, plotting, readers, store, vocab
from .catalog import (COLLECTIONS, PRODUCTS, STREAMS, Archive, date_to_doy,
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
        return _clean(v.tolist())
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _decimate(a: np.ndarray, max_points: int) -> np.ndarray:
    """Even subsample for display. Plot fidelity beyond ~1000 points on a
    1000-px axis is invisible, and the JSON cost is real."""
    if max_points <= 0 or a.size <= max_points:
        return a
    idx = np.linspace(0, a.size - 1, max_points).round().astype(int)
    return a[idx]


def _granule_or_404(gid: str) -> dict:
    row = store.get_granule(gid)
    if row is None:
        raise HTTPException(404, f"Unknown granule id {gid!r}")
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
                        "levels": v["levels"]} for k, v in STREAMS.items()},
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
        "defaults": {"field": vocab.DEFAULT_FIELD, "vertical": vocab.DEFAULT_VERTICAL},
        "lat_bands": [{"min": lo, "max": hi, "name": n}
                      for lo, hi, n in analysis.LAT_BANDS],
        "group_by_options": ["all", "lat_band", "hemisphere", "day_night", "date",
                             "product", "satellite"],
        "settings": vars(SETTINGS),
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
    plot_theme: str | None = None
    ui_theme: str | None = None
    ui_font_size: int | None = None
    ui_mode: str | None = None
    units_temperature: str | None = None
    explain_mode: bool | None = None


@app.post("/api/settings")
def update_settings(patch: SettingsPatch) -> dict:
    SETTINGS.update(**{k: v for k, v in patch.model_dump().items() if v is not None})
    return _clean(vars(SETTINGS))


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

class DownloadRequest(BaseModel):
    stream: str = "nrt"
    level: str = "level2"
    product: str = "wetPf2"
    date: str
    max_profiles: int | None = Field(default=None,
                                     description="0 or null means the whole day")
    sampling: Literal["first", "spread"] = "spread"
    good_only: bool = False


@app.post("/api/download")
def start_download(req: DownloadRequest) -> dict:
    try:
        dt.date.fromisoformat(req.date)
    except ValueError as exc:
        raise HTTPException(400, "date must be YYYY-MM-DD") from exc
    job = fetch.manager().submit_download(
        stream=req.stream, level=req.level, product=req.product, date=req.date,
        max_profiles=req.max_profiles, sampling=req.sampling,
        good_only=req.good_only)
    return _clean(job.snapshot())


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
        raise HTTPException(400, "No netCDF granules found at the given paths")
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
    s["cache_bytes_on_disk"] = store.cache_bytes()
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
            "label": vocab.info(name)["label"],
            "plain": vocab.info(name)["plain"],
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
    for row in rows:
        if not os.path.exists(row["path"]):
            skipped.append({"file": row["file_name"], "why": "file missing from cache"})
            continue
        try:
            g = readers.load(row["path"], row["product"])
        except Exception as exc:  # noqa: BLE001
            skipped.append({"file": row["file_name"], "why": str(exc)})
            continue
        src = dict(g.data)
        src.update(analysis.derived_fields(g))
        if req.field not in src or req.vertical not in src:
            skipped.append({"file": row["file_name"],
                            "why": f"no {req.field} on {req.vertical}"})
            continue
        y = src[req.vertical]
        x = src[req.field]
        if req.convert_kelvin and req.field in ("Temp", "temp_dry"):
            x = analysis.to_kelvin(x, g.units.get(req.field, "C"))
            units = "K"
        else:
            units = units or g.units.get(req.field, "") or vocab.info(req.field)["units"]
        n = min(x.size, y.size)
        
        # Apply pipeline
        from .pipeline import apply_pipeline
        prof = apply_pipeline(y[:n], x[:n], 
                              outlier_method=req.outlier_method, outlier_kwargs=req.outlier_kwargs,
                              smooth_method=req.smooth_method, smooth_kwargs=req.smooth_kwargs,
                              uncert_method=req.uncert_method, uncert_kwargs=req.uncert_kwargs)
        
        out.append({
            "granule_id": row["id"],
            "label": f"{g.meta['sat'] or '?'} {g.meta['occ_prn'] or ''} "
                     f"{(g.meta['time_utc'] or '')[11:16]}Z",
            "file_name": g.meta["file_name"],
            "x": _clean(_decimate(prof.v, req.max_points)),
            "original_x": _clean(_decimate(prof.original_v, req.max_points)),
            "y": _clean(_decimate(prof.z, req.max_points)),
            "uncertainty": _clean(_decimate(prof.uncertainty, req.max_points)) if prof.uncertainty is not None else None,
            "provenance": [p.__dict__ for p in prof.provenance],
            "lat": g.meta["lat"], "lon": g.meta["lon"],
            "local_time": g.meta["local_time"],
            "good": g.meta["good"],
        })
    return _clean({
        "field": req.field, "vertical": req.vertical, "units": units,
        "field_label": vocab.axis_title(req.field, units),
        "vertical_label": vocab.axis_title(req.vertical),
        "series": out, "skipped": skipped,
    })


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
        convert_kelvin=req.convert_kelvin)
    out = comp.to_json()
    out["selected"] = len(rows)
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
    table, failed = [], 0
    for r in rows:
        try:
            g = readers.load(r["path"], r["product"])
            d = analysis.diagnostics(g)
        except Exception:
            failed += 1
            continue
        flat = {"granule_id": r["id"], "file_name": r["file_name"],
                "product": r["product"], "time_utc": r["time_utc"],
                "lat": r["lat"], "lon": r["lon"], "local_time": r["local_time"],
                "sat": r["sat"], "good": r["good"]}
        for key, val in d.items():
            if key in ("product", "archive_values"):
                continue
            if isinstance(val, dict):
                for k2, v2 in val.items():
                    if isinstance(v2, (int, float, str, bool)) or v2 is None:
                        flat[f"{key}.{k2}"] = v2
            else:
                flat[key] = val
        table.append(flat)
    columns = sorted({k for row in table for k in row})
    return _clean({"rows": table, "columns": columns, "n": len(table),
                   "unreadable": failed})


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
        print(f"ValueError in export_data: {exc}")
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
    spread: Literal["std", "p10p90"] = "std"
    convert_kelvin: bool = False
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
        return plotting.coverage_figure(store.coverage(), title=req.title)
    if req.kind == "map":
        return plotting.map_figure(rows, req.color_field, title=req.title,
                                   caption=req.caption)
    if req.kind == "composite":
        comp = analysis.composite([(r["path"], r) for r in rows], req.field,
                                  req.vertical, group_by=req.group_by,
                                  convert_kelvin=req.convert_kelvin).to_json()
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
    series = plot_profiles(PlotRequest(granule_ids=[r["id"] for r in rows],
                                       field=req.field, vertical=req.vertical,
                                       convert_kelvin=req.convert_kelvin))
    items = [{"x": s["x"], "y": s["y"], "label": s["label"], "value": s["lat"]}
             for s in series["series"]]
    if not items:
        raise ValueError("no profile carried the requested field")
    return plotting.profile_figure(
        items, req.field, req.vertical, title=req.title,
        x_units=series["units"], color_by="Lat", logx=req.logx,
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
