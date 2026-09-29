"""Export selected profiles as data files or figures.

Every export carries provenance: which CDAAC product and processing stream it
came from, the granule filenames, the software version that wrote it, and the
suggested data citation.  A file that leaves this application should be
publishable without the user having to reconstruct where it came from.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from . import analysis, plotting, readers, vocab
from .config import (
    APP_TITLE,
    APP_VERSION,
    CDAAC_BASE,
    EXPORT_DIR,
    citation,
    ensure_dirs,
    DATA_AVAILABILITY_STATEMENT,
    DATA_LICENSES,
    LEAD_RESEARCHER,
)

SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(s: str, limit: int = 60) -> str:
    return SAFE.sub("-", s).strip("-")[:limit] or "export"


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def export_path(basename: str, ext: str) -> Path:
    ensure_dirs()
    return EXPORT_DIR / f"{_slug(basename)}_{_stamp()}.{ext.lstrip('.')}"


def provenance(granules: Sequence[dict], extra: dict | None = None) -> dict:
    products = sorted({g.get("product") for g in granules if g.get("product")})
    streams = sorted({g.get("stream") for g in granules if g.get("stream")})
    times = sorted(g["time_utc"] for g in granules if g.get("time_utc"))
    out = {
        "generated_by": f"{APP_TITLE} {APP_VERSION}",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "UCAR COSMIC Data Analysis and Archive Center (CDAAC)",
        "source_root": CDAAC_BASE,
        "data_citation": citation(),
        "data_availability": DATA_AVAILABILITY_STATEMENT,
        "licenses": DATA_LICENSES,
        "lead_researcher": LEAD_RESEARCHER,
        "products": products,
        "processing_streams": streams,
        "n_granules": len(granules),
        "time_first_utc": times[0] if times else None,
        "time_last_utc": times[-1] if times else None,
        "granule_files": [g.get("file_name") for g in granules][:5000],
    }
    if extra:
        out.update(extra)
    return out


# ---------------------------------------------------------------------------
# tabular
# ---------------------------------------------------------------------------

def export_profiles_csv(granules: Sequence[dict], variables: Sequence[str] | None = None,
                        include_derived: bool = True, basename: str = "cosmic2_profiles",
                        comment_header: bool = True, extra_prov: dict | None = None) -> dict:
    """Long-format CSV: one row per (profile, level).

    Long format is used rather than one column per profile because profiles do
    not share a vertical grid unless explicitly regridded; see
    :func:`export_grid_csv` for the regridded wide form.
    """
    path = export_path(basename, "csv")
    prov = provenance(granules, extra_prov)
    n_rows = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        if comment_header:
            for line in _header_lines(prov):
                fh.write(f"# {line}\n")
        writer = None
        for gmeta in granules:
            try:
                g = readers.load(gmeta["path"], gmeta.get("product"))
            except Exception:
                continue
            src = dict(g.data)
            if include_derived:
                src.update(analysis.derived_fields(g))
            zname = g.vertical or g.independent
            if zname not in src:
                continue
            names = [v for v in (variables or src.keys())
                     if v in src and src[v].size == src[zname].size
                     and not readers.BULK_VAR_RE.match(v)]
            if zname in names:
                names.remove(zname)
            cols = [zname] + names
            if writer is None:
                writer = csv.writer(fh)
                writer.writerow(["granule", "product", "time_utc", "lat", "lon",
                                 "local_time_h", "level_index"] + cols)
            base = [g.meta["file_name"], g.meta["product"], g.meta["time_utc"],
                    g.meta["lat"], g.meta["lon"], g.meta["local_time"]]
            arrs = [src[c] for c in cols]
            n = min(a.size for a in arrs)
            for i in range(n):
                row = base + [i] + [_fmt(a[i]) for a in arrs]
                writer.writerow(row)
                n_rows += 1
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "text/csv", "rows": n_rows, "provenance": prov}


def _fmt(v) -> str:
    f = float(v)
    return "" if not np.isfinite(f) else repr(round(f, 6))


def _header_lines(prov: dict) -> list[str]:
    lines = [
        f"{prov['generated_by']} - exported {prov['generated_at_utc']}",
        f"Source: {prov['source']} ({prov['source_root']})",
        f"Products: {', '.join(prov['products']) or 'n/a'}; streams: {', '.join(prov['processing_streams']) or 'n/a'}",
        f"Granules: {prov['n_granules']}; time range {prov['time_first_utc']} .. {prov['time_last_utc']}",
        f"Cite as: {prov['data_citation']}",
        f"Data Availability: {prov.get('data_availability', '')}",
        f"Software License: {prov.get('licenses', {}).get('software', 'MIT License')}",
        "Blank cells are missing or quality-rejected values.",
    ]
    return [l for l in lines if l]


def export_metadata_csv(granules: Sequence[dict],
                        basename: str = "cosmic2_index", extra_prov: dict | None = None) -> dict:
    """One row per profile: the searchable metadata plus derived scalars."""
    path = export_path(basename, "csv")
    prov = provenance(granules, extra_prov)
    fields = ["file_name", "product", "stream", "level", "time_utc", "lat", "lon",
              "local_time", "sat", "occ_prn", "good", "bad_code", "n_levels",
              "alt_min", "alt_max", "size_bytes", "path"]
    extra_keys: list[str] = []
    for g in granules:
        for k in (g.get("extras") or {}):
            if k not in extra_keys:
                extra_keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        for line in _header_lines(prov):
            fh.write(f"# {line}\n")
        w = csv.writer(fh)
        w.writerow(fields + extra_keys)
        for g in granules:
            ex = g.get("extras") or {}
            w.writerow([g.get(k) for k in fields] +
                       [ex.get(k) for k in extra_keys])
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "text/csv", "rows": len(granules), "provenance": prov}


def export_grid_csv(granules: Sequence[dict], field: str, vertical: str = "MSL_alt",
                    top_km: float = 60.0, step_km: float = 0.2,
                    basename: str = "cosmic2_grid", extra_prov: dict | None = None) -> dict:
    """Wide CSV: rows are altitude levels, columns are profiles, all regridded.

    This is the convenient shape for spreadsheet work and for feeding a
    profile ensemble into another tool, at the cost of interpolation.
    """
    grid = analysis.make_grid(top_km, step_km)
    path = export_path(basename, "csv")
    prov_extras = {"regridded_to": f"{step_km} km steps to {top_km} km",
                   "field": field, "vertical": vertical}
    if extra_prov: prov_extras.update(extra_prov)
    prov = provenance(granules, prov_extras)
    cols: list[tuple[str, np.ndarray]] = []
    for gmeta in granules:
        try:
            g = readers.load(gmeta["path"], gmeta.get("product"))
        except Exception:
            continue
        src = dict(g.data)
        src.update(analysis.derived_fields(g))
        if field not in src or vertical not in src:
            continue
        cols.append((g.meta["file_name"],
                     analysis.interp_to_grid(src[vertical], src[field], grid,
                                             max_gap=2.0)))
    with path.open("w", newline="", encoding="utf-8") as fh:
        for line in _header_lines(prov):
            fh.write(f"# {line}\n")
        fh.write(f"# Field: {vocab.axis_title(field)}; "
                 f"interpolated onto a uniform {step_km} km grid.\n")
        w = csv.writer(fh)
        w.writerow([f"{vertical}_km"] + [c[0] for c in cols])
        for i, z in enumerate(grid):
            w.writerow([round(float(z), 4)] + [_fmt(c[1][i]) for c in cols])
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "text/csv", "rows": len(grid), "columns": len(cols),
            "provenance": prov}


# ---------------------------------------------------------------------------
# netCDF
# ---------------------------------------------------------------------------

def export_netcdf(granules: Sequence[dict], fields: Sequence[str] | None = None,
                  vertical: str = "MSL_alt", top_km: float = 60.0,
                  step_km: float = 0.2, basename: str = "cosmic2_bundle", extra_prov: dict | None = None) -> dict:
    """Regridded netCDF-4 with dimensions ``(profile, level)``.

    Written with CF-style variable attributes and the full provenance block as
    global attributes.  Profiles are interpolated onto a shared vertical grid,
    which is what makes a rectangular array meaningful.
    """
    try:
        from netCDF4 import Dataset
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("netCDF export needs the netCDF4 package") from exc

    grid = analysis.make_grid(top_km, step_km)
    loaded: list[tuple[dict, dict]] = []
    for gmeta in granules:
        try:
            g = readers.load(gmeta["path"], gmeta.get("product"))
        except Exception:
            continue
        src = dict(g.data)
        src.update(analysis.derived_fields(g))
        if vertical not in src:
            continue
        loaded.append((g.meta, {k: v for k, v in src.items()
                                if v.size == src[vertical].size}))
    if not loaded:
        raise ValueError("No readable granules with the requested vertical coordinate")

    if fields:
        names = [f for f in fields if any(f in d for _, d in loaded)]
    else:
        common: set[str] = set(loaded[0][1])
        for _, d in loaded[1:]:
            common &= set(d)
        names = sorted(c for c in common
                       if c != vertical and not readers.BULK_VAR_RE.match(c))

    path = export_path(basename, "nc")
    prov_extras = {"regridded_to": f"{step_km} km steps to {top_km} km"}
    if extra_prov: prov_extras.update(extra_prov)
    prov = provenance(granules, prov_extras)
    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("profile", len(loaded))
        ds.createDimension("level", grid.size)

        zv = ds.createVariable(vertical, "f4", ("level",))
        zv.units = "km"
        zv.long_name = vocab.info(vertical)["label"]
        zv.axis = "Z"
        zv[:] = grid

        # Profile-level coordinates are prefixed: several products carry
        # per-level arrays literally named "lat", "lon" and "time", and a
        # netCDF group cannot hold two variables with the same name.
        for key, src_key, unit, label, std in [
            ("profile_time", "epoch", "seconds since 1970-01-01T00:00:00Z",
             "Observation time", "time"),
            ("profile_lat", "lat", "degrees_north", "Occultation latitude",
             "latitude"),
            ("profile_lon", "lon", "degrees_east", "Occultation longitude",
             "longitude"),
            ("profile_local_time", "local_time", "hours", "Local solar time", ""),
        ]:
            v = ds.createVariable(key, "f8", ("profile",), fill_value=-999.0)
            v.units = unit
            v.long_name = label
            if std:
                v.standard_name = std
            v[:] = [m.get(src_key) if m.get(src_key) is not None else -999.0
                    for m, _ in loaded]

        # Variable-length strings keep the full CDAAC filename intact; a
        # fixed-width char array would truncate the longer scintillation names.
        gv = ds.createVariable("granule", str, ("profile",))
        gv.long_name = "Source CDAAC granule filename"
        for i, (m, _) in enumerate(loaded):
            gv[i] = m["file_name"]
        qv = ds.createVariable("quality_good", "i1", ("profile",))
        qv.long_name = "1 if the granule passed the CDAAC quality flag"
        qv[:] = [1 if m.get("good", True) else 0 for m, _ in loaded]

        for name in names:
            vi = vocab.info(name)
            var = ds.createVariable(name, "f4", ("profile", "level"),
                                    fill_value=np.float32(-999.0), zlib=True,
                                    complevel=4)
            var.units = vi["units"]
            var.long_name = vi["label"]
            if vi["plain"]:
                var.comment = vi["plain"]
            block = np.full((len(loaded), grid.size), np.nan)
            for i, (meta, data) in enumerate(loaded):
                if name in data:
                    block[i] = analysis.interp_to_grid(data[vertical], data[name],
                                                       grid, max_gap=2.0)
            var[:] = np.where(np.isfinite(block), block, -999.0).astype(np.float32)

        for k, v in prov.items():
            if k == "granule_files":
                continue
            ds.setncattr(k, json.dumps(v) if isinstance(v, (list, dict)) else v)
        ds.Conventions = "CF-1.8"
        ds.title = "COSMIC-2 profiles regridded to a common vertical grid"
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "application/x-netcdf", "profiles": len(loaded),
            "variables": names, "provenance": prov}


# ---------------------------------------------------------------------------
# json / figures / bundle
# ---------------------------------------------------------------------------

def export_json(payload: dict, basename: str = "cosmic2_data") -> dict:
    path = export_path(basename, "json")
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "application/json"}


def export_figure(fig, fmt: str = "png", basename: str = "cosmic2_figure",
                  dpi: int | None = None) -> dict:
    data = plotting.render(fig, fmt, dpi)
    path = export_path(basename, fmt)
    path.write_bytes(data)
    return {"path": str(path), "filename": path.name, "bytes": len(data),
            "mime": plotting.MIME[fmt.lower()]}


def export_bundle(items: Sequence[dict], prov: dict,
                  basename: str = "cosmic2_bundle") -> dict:
    """Zip several exports together with a README explaining each file."""
    path = export_path(basename, "zip")
    readme = io.StringIO()
    readme.write(f"{prov['generated_by']}\n{'=' * len(prov['generated_by'])}\n\n")
    readme.write(f"Exported {prov['generated_at_utc']}\n\n")
    readme.write("Contents\n--------\n")
    for it in items:
        readme.write(f"  {it['filename']}  ({it['bytes'] / 1024:.0f} kB)"
                     f"  {it.get('description', '')}\n")
    readme.write("\nProvenance\n----------\n")
    for line in _header_lines(prov):
        readme.write(f"  {line}\n")
    readme.write("\nGranules included\n-----------------\n")
    for f in prov.get("granule_files", [])[:2000]:
        readme.write(f"  {f}\n")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", readme.getvalue())
        z.writestr("provenance.json", json.dumps(prov, indent=2, default=str))
        for it in items:
            src = Path(it["path"])
            if src.exists():
                z.write(src, arcname=src.name)
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "application/zip", "items": [i["filename"] for i in items]}


def list_exports(limit: int = 100) -> list[dict]:
    ensure_dirs()
    rows = []
    for p in sorted(EXPORT_DIR.glob("*"), key=lambda q: q.stat().st_mtime,
                    reverse=True)[:limit]:
        if p.is_file():
            rows.append({"filename": p.name, "bytes": p.stat().st_size,
                         "modified": dt.datetime.fromtimestamp(
                             p.stat().st_mtime, dt.timezone.utc).isoformat(),
                         "path": str(p)})
    return rows
