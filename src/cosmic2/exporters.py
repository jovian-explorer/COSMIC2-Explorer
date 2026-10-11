"""Export selected profiles as data files or figures.

Every export carries provenance: which CDAAC product and processing stream it
came from, the granule filenames, the software version that wrote it, and the
suggested data citation.  A file that leaves this application should be
publishable without the user having to reconstruct where it came from.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from . import analysis, plotting, readers, vocab
from .parallel import pmap
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
    # Profiles of different products have different variables, so the
    # columns are every variable met, each in its own column, empty where a
    # profile has none.  (The first profile's columns used to head the file,
    # and a wetPf2 after an atmPrf put its values under the atmPrf names.)
    # Rows go to a scratch file until all columns are known.
    columns: list[str] = []
    units: dict[str, set[str]] = {}
    body = path.with_name(path.name + ".part")
    with body.open("w", newline="", encoding="utf-8") as fb:
        writer = csv.writer(fb)
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
            columns += [c for c in cols if c not in columns]
            idx = [columns.index(c) for c in cols]
            for c in cols:
                u = vocab.normalise_units(g.units.get(c) or vocab.info(c, g.product)["units"])
                if u and u != "-":
                    units.setdefault(c, set()).add(u)
            base = [g.meta["file_name"], g.meta["product"], g.meta["time_utc"],
                    g.meta["lat"], g.meta["lon"], g.meta["local_time"]]
            arrs = [src[c] for c in cols]
            n = min(a.size for a in arrs)
            for i in range(n):
                vals = [""] * len(columns)
                for k, a in zip(idx, arrs):
                    vals[k] = _fmt(a[i])
                writer.writerow(base + [i] + vals)
                n_rows += 1
    width = 7 + len(columns)
    with path.open("w", newline="", encoding="utf-8") as fh, \
            body.open(newline="", encoding="utf-8") as fb:
        if comment_header:
            for line in _header_lines(prov):
                fh.write(f"# {line}\n")
            if units:
                fh.write("# Units: " + "; ".join(
                    f"{c} {' or '.join(sorted(units[c]))}" for c in columns if c in units) + "\n")
        if columns:
            writer = csv.writer(fh)
            writer.writerow(["granule", "product", "time_utc", "lat", "lon",
                             "local_time_h", "level_index"] + columns)
            for row in csv.reader(fb):
                writer.writerow(row + [""] * (width - len(row)))
    body.unlink()
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "text/csv", "rows": n_rows, "provenance": prov}


def _fmt(v) -> str:
    f = float(v)
    # Shortest text that reads back as the same double.  Rounding to a fixed
    # number of decimals (as before) left small quantities such as N^2
    # (~1e-5 s-2) or upper-stratosphere density with one or two digits.
    return "" if not np.isfinite(f) else repr(f)


def _licence_text(lic) -> str:
    """One readable line for the software licence (it is a dict in
    DATA_LICENSES, which was printed into CSV headers as a Python repr)."""
    if isinstance(lic, dict):
        bits = [lic.get("name") or "MIT License", lic.get("copyright"), lic.get("url")]
        return "; ".join(b for b in bits if b)
    return str(lic or "MIT License")


def _header_lines(prov: dict) -> list[str]:
    lines = [
        f"{prov['generated_by']} - exported {prov['generated_at_utc']}",
        f"Source: {prov['source']} ({prov['source_root']})",
        f"Products: {', '.join(prov['products']) or 'n/a'}; streams: {', '.join(prov['processing_streams']) or 'n/a'}",
        f"Granules: {prov['n_granules']}; time range {prov['time_first_utc']} .. {prov['time_last_utc']}",
        f"Cite as: {prov['data_citation']}",
        f"Data Availability: {prov.get('data_availability', '')}",
        f"Software License: {_licence_text(prov.get('licenses', {}).get('software'))}",
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


# Display units (vocab) -> UDUNITS strings for the CF-1.8 netCDF export.
# "C" in particular is the coulomb to UDUNITS (and to xarray/cf-units/pint),
# so a temperature written with units="C" decodes as an electric charge.
CF_UNITS = {
    "C": "degree_Celsius", "K/km": "K km-1", "N-units": "1",
    "N-units/km": "km-1", "N/cc": "cm-3", "el/cm3": "cm-3", "g/kg": "g kg-1",
    "kg/m^3": "kg m-3", "s^-2": "s-2", "%": "percent", "-": "1",
    "count": "1", "deg": "degree", "deg E": "degrees_east",
    "deg N": "degrees_north", "TECU": "1e16 m-2", "0.1 V/V": "1",
    "s since 1970-01-01": "seconds since 1970-01-01T00:00:00Z",
}


def cf_units(units: str) -> str:
    """UDUNITS-parsable form of a display unit string."""
    return CF_UNITS.get(units, units)


def _regrid_granule(task: tuple) -> tuple[dict, dict[str, np.ndarray]] | None:
    """Read one granule and interpolate its profile variables onto ``grid``.

    ``task`` is ``(index_row, vertical, grid, names)``; ``names=None`` means
    every variable sampled on the vertical coordinate.  Returns
    ``(granule metadata, {name: gridded column})``, or ``None`` if the
    granule is unreadable or lacks the vertical coordinate.  Module-level so
    it can run in a worker process (see :mod:`.parallel`).
    """
    gmeta, vertical, grid, names = task
    try:
        g = readers.load(gmeta["path"], gmeta.get("product"))
    except Exception:
        return None
    src = dict(g.data)
    src.update(analysis.derived_fields(g))
    if vertical not in src:
        return None
    z = src[vertical]
    wanted = names if names is not None else [
        k for k, v in src.items() if v.size == z.size and k != vertical
        and not readers.BULK_VAR_RE.match(k)]
    out = {k: analysis.interp_field(z, src[k], grid, k, max_gap=2.0)
           for k in wanted if k in src and src[k].size == z.size}
    return g.meta, out


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
    tasks = [(gmeta, vertical, grid, [field]) for gmeta in granules]
    cols: list[tuple[str, np.ndarray, str]] = [
        (meta["file_name"], gridded[field], meta.get("product") or "")
        for res in pmap(_regrid_granule, tasks) if res is not None
        for meta, gridded in [res] if field in gridded]
    # Named as stored in each product: atmPrf "Temp" is the dry temperature
    labels = sorted({(vocab.axis_title(field, None, p), p) for _, _, p in cols})
    label = (labels[0][0] if len({lab for lab, _ in labels}) == 1 else "; ".join(
        f"{lab} in {p}" for lab, p in labels)) if labels else vocab.axis_title(field)
    with path.open("w", newline="", encoding="utf-8") as fh:
        for line in _header_lines(prov):
            fh.write(f"# {line}\n")
        fh.write(f"# Field: {label}; "
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
    # Each worker returns the granule already interpolated onto the grid, so
    # only small arrays travel back from the worker processes.
    tasks = [(gmeta, vertical, grid, list(fields) if fields else None)
             for gmeta in granules]
    loaded: list[tuple[dict, dict]] = [r for r in pmap(_regrid_granule, tasks)
                                       if r is not None]
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

        zv = ds.createVariable(vertical, "f8", ("level",))
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
        pv = ds.createVariable("product", str, ("profile",))
        pv.long_name = "CDAAC product of the source granule"
        for i, (m, _) in enumerate(loaded):
            pv[i] = m.get("product") or ""
        qv = ds.createVariable("quality_good", "i1", ("profile",))
        qv.long_name = "1 if the granule passed the CDAAC quality flag"
        qv[:] = [1 if m.get("good", True) else 0 for m, _ in loaded]

        products = sorted({m.get("product") or "" for m, _ in loaded})
        for name in names:
            # Describe the variable as stored in these products (atmPrf
            # "Temp" is the dry temperature); if the rows mix products where
            # the name means different quantities, say which rows are which.
            qtys = {vocab.quantity(name, p) for p in products}
            vi = vocab.info(name, products[0] if len(qtys) == 1 else None)
            var = ds.createVariable(name, "f4", ("profile", "level"),
                                    fill_value=np.float32(-999.0), zlib=True,
                                    complevel=4)
            var.units = cf_units(vi["units"])
            var.long_name = vi["label"]
            if len(qtys) > 1:
                var.comment = "; ".join(
                    f"rows with product={p}: {vocab.info(name, p)['label']}"
                    for p in products) + ". See the 'product' variable."
            elif vi["plain"]:
                var.comment = vi["plain"]
            block = np.full((len(loaded), grid.size), np.nan)
            for i, (meta, data) in enumerate(loaded):
                if name in data:
                    block[i] = data[name]
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


def export_radiosonde_csv(result: dict, granules: Sequence[dict],
                          basename: str = "cosmic2_radiosonde") -> dict:
    """The radiosonde comparison as CSV: the statistics by height, then one
    row per colocated pair, under the usual provenance header."""
    path = export_path(basename, "csv")
    prov = provenance(granules, {
        "comparison": "COSMIC-2 minus NOAA IGRA v2 radiosonde",
        "colocation": f"within {result.get('max_km')} km and {result.get('max_hours')} h",
        "radiosonde_source": "https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/"})
    with open(path, "w", newline="", encoding="utf-8") as f:
        for line in _header_lines(prov):
            f.write(f"# {line}\n")
        f.write(f"# Radiosondes: NOAA IGRA v2; {result['n_pairs']} pairs; "
                f"differences are occultation minus sonde\n")
        w = csv.writer(f)
        stats = result.get("stats", {})
        cols = ["bin_centre_km"]
        for q, st in stats.items():
            u = st["units"]
            cols += [f"{q}_mean_diff_{u}", f"{q}_std_{u}", f"{q}_median_diff_{u}", f"{q}_n"]
        w.writerow(cols)
        for i, c in enumerate(result.get("bin_centres_km", [])):
            row = [repr(float(c))]
            for st in stats.values():
                row += ["" if st[k][i] is None else repr(float(st[k][i]))
                        for k in ("mean", "std", "median")] + [st["n"][i]]
            w.writerow(row)
        f.write("\n")
        keys = ["file_name", "product", "time_utc", "lat", "lon", "station",
                "station_name", "launch_utc", "sonde_lat", "sonde_lon",
                "distance_km", "dt_hours", "sonde_top_km", "ro_pbl_km", "sonde_pbl_km"]
        w.writerow(keys)
        for pr in result.get("pairs", []):
            w.writerow([pr.get(k, "") for k in keys])
    return {"path": str(path), "filename": path.name, "bytes": path.stat().st_size,
            "mime": "text/csv", "provenance": prov}


def export_figure(fig, fmt: str = "png", basename: str = "cosmic2_figure",
                  dpi: int | None = None) -> dict:
    data = plotting.render(fig, fmt, dpi)
    path = export_path(basename, fmt)
    path.write_bytes(data)
    return {"path": str(path), "filename": path.name, "bytes": len(data),
            "mime": plotting.MIME[fmt.lower()]}


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
