"""Readers that turn a CDAAC netCDF granule into one normalised object.

CDAAC granules are netCDF-3 classic with the science payload in 1-D arrays and
the interesting metadata in *global attributes*.  The attribute conventions are
not uniform: ``atmPrf`` stores numbers, ``wetPf2`` stores
``"36.798, Nominal latitude (degrees North)"`` strings, ``scnLv2`` stores
16-bit ints.  Everything is normalised here so the rest of the application
sees one shape::

    Granule.meta   -> flat, JSON-safe metadata with stable key names
    Granule.data   -> {variable: numpy array} with fill values masked to NaN
    Granule.vertical / .independent -> the natural x/y coordinate names
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:  # netCDF4 reads both classic and HDF5-backed files
    from netCDF4 import Dataset as _NC4
except Exception:  # pragma: no cover - fallback for minimal installs
    _NC4 = None
from scipy.io import netcdf_file as _NC3

from . import vocab

FILL_VALUES = (-999.0, -9999.0, -99999.0, 9.96921e36)
BULK_VAR_RE = re.compile(r"^(OL_vec\d*|OL_par|OL_ipar|ies|hes|wes)$")

# Filename stamps seen in the archive:
#   atmPrf_C2E1.2026.200.00.00.E23_0001.0001_nc
#   scnLv2_2026.200.006.01.01.R16.SC001_0001.0001_nc
#   ivmL2m_C2E1.2026.200.01_0001.0001_nc
_NAME_RE = re.compile(r"^(?P<product>[A-Za-z0-9]+)_(?P<stamp>.+?)_(?P<v1>\d{4})\.(?P<v2>\d{4})(?:_nc|\.nc)?$")
_RO_STAMP = re.compile(r"^(?P<sat>C2E\d|[A-Z0-9]{4})\.(?P<year>\d{4})\.(?P<doy>\d{3})\.(?P<hh>\d{2})\.(?P<mm>\d{2})\.(?P<prn>[A-Z]\d{2})$")
_IVM_STAMP = re.compile(r"^(?P<sat>C2E\d)\.(?P<year>\d{4})\.(?P<doy>\d{3})\.(?P<hh>\d{2})$")
_SCN_STAMP = re.compile(r"^(?P<year>\d{4})\.(?P<doy>\d{3})\.(?P<leo>\d{3})\.(?P<a>\d{2})\.(?P<b>\d{2})\.(?P<prn>[A-Z]\d{2})\.(?P<ant>SC\d+)$")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _to_str(v: Any) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip()
    if isinstance(v, np.ndarray):
        return " ".join(str(x) for x in v.tolist())
    return str(v).strip()


_NUM_PREFIX = re.compile(r"^\s*([-+]?\d+(?:\.\d*)?(?:[eEdD][-+]?\d+)?)\s*(?:,\s*(.*))?$")


def _parse_attr(value: Any) -> tuple[Any, str]:
    """Return ``(python_value, description)`` for one global attribute."""
    if isinstance(value, (bytes, str)):
        s = _to_str(value)
        m = _NUM_PREFIX.match(s)
        if m:
            num = float(m.group(1).replace("D", "E").replace("d", "e"))
            desc = (m.group(2) or "").strip()
            if desc:
                return num, desc
            return num, ""
        return s, ""
    if isinstance(value, np.ndarray):
        return [float(x) for x in np.ravel(value).tolist()], ""
    if isinstance(value, (np.integer,)):
        return int(value), ""
    if isinstance(value, (np.floating,)):
        return float(value), ""
    return value, ""


def parse_filename(path: str) -> dict:
    """Split a CDAAC granule filename into its parts."""
    base = os.path.basename(path)
    out: dict[str, Any] = {"file_name": base, "product": "", "stamp": "",
                           "version": "", "sat": "", "prn": "", "antenna": ""}
    m = _NAME_RE.match(base)
    if not m:
        return out
    out["product"] = m.group("product")
    out["stamp"] = m.group("stamp")
    out["version"] = f"{m.group('v1')}.{m.group('v2')}"
    st = m.group("stamp")
    for rx in (_RO_STAMP, _IVM_STAMP, _SCN_STAMP):
        mm = rx.match(st)
        if not mm:
            continue
        g = mm.groupdict()
        out["sat"] = g.get("sat") or (f"LEO{g['leo']}" if g.get("leo") else "")
        out["prn"] = g.get("prn", "")
        out["antenna"] = g.get("ant", "")
        out["nominal_year"] = int(g["year"])
        out["nominal_doy"] = int(g["doy"])
        if g.get("hh"):
            out["nominal_hour"] = int(g["hh"])
        break
    return out


def scrub(value):
    """Turn CDAAC sentinel values into ``None`` (recursively) for metadata."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        f = float(value)
        if not math.isfinite(f) or any(abs(f - fv) < 1e-3 for fv in FILL_VALUES):
            return None
        return f if isinstance(value, (float, np.floating)) else int(value)
    return value


def _mask_fill(a: np.ndarray) -> np.ndarray:
    arr = np.asarray(a, dtype="float64")
    bad = ~np.isfinite(arr)
    for fv in FILL_VALUES:
        bad |= np.isclose(arr, fv, rtol=0, atol=1e-3)
    arr = arr.copy()
    arr[bad] = np.nan
    return arr


def _open(path: str):
    if _NC4 is not None:
        try:
            return _NC4(path, "r"), "nc4"
        except Exception:
            pass
    return _NC3(path, "r", mmap=False), "nc3"


def _read_raw(path: str) -> tuple[dict, dict, dict]:
    """Return ``(attrs, attr_desc, variables)`` for a granule."""
    ds, flavour = _open(path)
    try:
        if flavour == "nc4":
            raw_attrs = {k: ds.getncattr(k) for k in ds.ncattrs()}
            variables = {}
            for name, v in ds.variables.items():
                units = ""
                if "units" in v.ncattrs():
                    units = _to_str(v.getncattr("units"))
                variables[name] = (np.asarray(v[:]).astype("float64", copy=False), units)
        else:
            raw_attrs = dict(ds._attributes)
            variables = {}
            for name, v in ds.variables.items():
                units = _to_str(v._attributes.get("units", b""))
                variables[name] = (np.asarray(v[:]).astype("float64"), units)
    finally:
        try:
            ds.close()
        except Exception:
            pass
    attrs, desc = {}, {}
    for k, v in raw_attrs.items():
        val, d = _parse_attr(v)
        attrs[k] = val
        if d:
            desc[k] = d
    return attrs, desc, variables


def _iso(year, month, day, hour, minute, second) -> tuple[str | None, float | None]:
    try:
        sec = float(second)
        whole = int(math.floor(sec))
        micro = int(round((sec - whole) * 1e6))
        t = dt.datetime(int(year), int(month), int(day), int(hour), int(minute),
                        min(whole, 59), min(micro, 999999), tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None, None
    return t.isoformat().replace("+00:00", "Z"), t.timestamp()


def _local_time(lon: float | None, epoch: float | None) -> float | None:
    if lon is None or epoch is None:
        return None
    utc_h = (epoch % 86400.0) / 3600.0
    return (utc_h + lon / 15.0) % 24.0


# ---------------------------------------------------------------------------
# Granule
# ---------------------------------------------------------------------------


@dataclass
class Granule:
    product: str
    path: str
    meta: dict
    attrs: dict
    attr_desc: dict
    data: dict[str, np.ndarray]
    units: dict[str, str]
    vertical: str = ""
    independent: str = ""
    warnings: list[str] = field(default_factory=list)

    # -- introspection ---------------------------------------------------
    def variables(self, include_bulk: bool = False) -> list[dict]:
        out = []
        for name, arr in self.data.items():
            if not include_bulk and BULK_VAR_RE.match(name):
                continue
            vi = vocab.info(name)
            finite = np.isfinite(arr)
            out.append({
                "name": name,
                "label": vi["label"],
                "plain": vi["plain"],
                "units": self.units.get(name) or vi["units"],
                "role": vi["role"],
                "n": int(arr.size),
                "n_valid": int(finite.sum()),
                "min": float(np.nanmin(arr)) if finite.any() else None,
                "max": float(np.nanmax(arr)) if finite.any() else None,
            })
        return out

    def series(self, name: str) -> np.ndarray:
        if name not in self.data:
            raise KeyError(f"{name!r} not present in {self.product} granule")
        return self.data[name]

    def to_columns(self, names: list[str] | None = None) -> tuple[list[str], np.ndarray]:
        """Stack same-length variables into a 2-D column block."""
        if names is None:
            n0 = self.data[self.vertical or self.independent].size
            names = [k for k, v in self.data.items()
                     if v.size == n0 and not BULK_VAR_RE.match(k)]
        if not names:
            return [], np.empty((0, 0))
        n = max(self.data[k].size for k in names)
        cols = []
        for k in names:
            a = self.data[k]
            if a.size != n:
                a = np.full(n, np.nan)
            cols.append(a)
        return names, np.column_stack(cols)


# ---------------------------------------------------------------------------
# product-specific metadata normalisation
# ---------------------------------------------------------------------------

def _base_meta(path: str, product: str) -> dict:
    fn = parse_filename(path)
    return {
        "product": product,
        "path": os.path.abspath(path),
        "file_name": fn["file_name"],
        "stamp": fn["stamp"],
        "version": fn["version"],
        "sat": fn["sat"],
        "occ_prn": fn["prn"],
        "antenna": fn["antenna"],
        "time_utc": None, "epoch": None,
        "lat": None, "lon": None, "local_time": None,
        "setting": None, "good": True, "bad_code": "0", "error_text": "",
        "time_is_nominal": False,
        "n_levels": 0, "alt_min": None, "alt_max": None,
        "ref_sat": None, "mission": None, "extras": {},
        "nominal_year": fn.get("nominal_year"),
        "nominal_doy": fn.get("nominal_doy"),
        "nominal_hour": fn.get("nominal_hour"),
    }


def _nominal_time(meta: dict) -> None:
    """CDAAC ships placeholder granules for failed retrievals; they carry no
    date attribute.  Fall back to the slot time encoded in the filename so the
    granule still sorts and filters like its neighbours."""
    if meta.get("time_utc") or not meta.get("nominal_year"):
        return
    try:
        d = dt.date(int(meta["nominal_year"]), 1, 1) + dt.timedelta(
            days=int(meta["nominal_doy"]) - 1)
        t = dt.datetime(d.year, d.month, d.day, int(meta.get("nominal_hour") or 0),
                        tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return
    meta["time_utc"] = t.isoformat().replace("+00:00", "Z")
    meta["epoch"] = t.timestamp()
    meta["time_is_nominal"] = True


def _finish_altitude(meta: dict, data: dict, vertical: str) -> None:
    if vertical and vertical in data:
        z = data[vertical]
        ok = np.isfinite(z)
        meta["n_levels"] = int(ok.sum())
        if ok.any():
            meta["alt_min"] = float(np.nanmin(z))
            meta["alt_max"] = float(np.nanmax(z))


def _read_atmprf(path: str) -> Granule:
    attrs, desc, raw = _read_raw(path)
    data = {k: _mask_fill(v[0]) for k, v in raw.items()}
    units = {k: v[1] for k, v in raw.items()}
    meta = _base_meta(path, "atmPrf")
    iso, epoch = _iso(attrs.get("year"), attrs.get("month"), attrs.get("day"),
                      attrs.get("hour"), attrs.get("minute"), attrs.get("second"))
    meta.update(
        time_utc=iso, epoch=epoch,
        lat=attrs.get("lat"), lon=attrs.get("lon"),
        local_time=attrs.get("timloc") if attrs.get("timloc") is not None
        else _local_time(attrs.get("lon"), epoch),
        setting="setting" if attrs.get("irs", 0) == -1 else "rising",
        bad_code=str(attrs.get("bad", "0")),
        ref_sat=attrs.get("reference_sat_id"),
        mission=_to_str(attrs.get("center", "")),
    )
    meta["good"] = str(meta["bad_code"]).strip() in ("0", "0.0")
    meta["extras"] = {
        "tropopause_height_wmo_km": attrs.get("trhwmo"),
        "tropopause_temp_wmo_C": attrs.get("trtwmo"),
        "cold_point_height_km": attrs.get("trhcp"),
        "cold_point_temp_C": attrs.get("trtcp"),
        "profile_top_km": attrs.get("ztop"),
        "profile_bottom_km": attrs.get("zbot"),
        "radius_curvature_km": attrs.get("rfict"),
        "geoid_undulation_m": attrs.get("rgeoid"),
        "l1_snr_mean_Vv": attrs.get("snr1avg"),
        "l2_snr_mean_Vv": attrs.get("snr2avg"),
        "occ_point_offset_km": attrs.get("occpt_offset"),
        "inverter": _to_str(attrs.get("inverter", "")),
        "freq1": _to_str(attrs.get("freq1", "")),
        "freq2": _to_str(attrs.get("freq2", "")),
    }
    g = Granule("atmPrf", path, meta, attrs, desc, data, units,
                vertical="MSL_alt", independent="MSL_alt")
    _finish_altitude(meta, data, "MSL_alt")
    return g


def _read_wetpf2(path: str) -> Granule:
    attrs, desc, raw = _read_raw(path)
    data = {k: _mask_fill(v[0]) for k, v in raw.items()}
    units = {k: v[1] for k, v in raw.items()}
    meta = _base_meta(path, "wetPf2")
    iso, epoch = None, None
    date_s = attrs.get("date")
    if isinstance(date_s, str):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})[_ ](\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", date_s)
        if m:
            iso, epoch = _iso(*m.groups())
    meta.update(
        time_utc=iso, epoch=epoch,
        lat=attrs.get("lat"), lon=attrs.get("lon"),
        local_time=_local_time(attrs.get("lon"), epoch),
        setting="setting" if attrs.get("irs", 0) == -1 else "rising",
        bad_code=str(attrs.get("bad", "0")),
        mission=_to_str(attrs.get("inverter", "")),
    )
    meta["good"] = str(meta["bad_code"]).strip() in ("0", "0.0")
    meta["extras"] = {
        "landmask": attrs.get("landmask"),
        "terrain_height_km": attrs.get("terrain_height"),
        "model_levels": attrs.get("number_mdl_levels"),
        "iterations": attrs.get("number_iterations"),
        "obs_used": attrs.get("number_thinned_ob"),
        "obs_total": attrs.get("number_original_ob"),
        "cost_final": attrs.get("final_jt"),
        "cost_initial": attrs.get("init_jt"),
        "ducting_flagged": attrs.get("fgs_shows_ducting"),
        "ducting_layer_top_km": attrs.get("ducting_layer_top"),
        "source_atmPrf": _to_str(attrs.get("atmPrf", "")),
        "code_version": _to_str(attrs.get("source_code_version", "")),
    }
    g = Granule("wetPf2", path, meta, attrs, desc, data, units,
                vertical="MSL_alt", independent="MSL_alt")
    _finish_altitude(meta, data, "MSL_alt")
    return g


def _read_ionprf(path: str) -> Granule:
    attrs, desc, raw = _read_raw(path)
    data = {k: _mask_fill(v[0]) for k, v in raw.items()}
    units = {k: v[1] for k, v in raw.items()}
    meta = _base_meta(path, "ionPrf")
    iso, epoch = _iso(attrs.get("year"), attrs.get("month"), attrs.get("day"),
                      attrs.get("hour"), attrs.get("minute"), attrs.get("second"))
    meta.update(
        time_utc=iso, epoch=epoch,
        lat=attrs.get("edmaxlat"), lon=attrs.get("edmaxlon"),
        local_time=attrs.get("edmaxlct"),
        setting="setting" if attrs.get("setting", 0) == -1 else "rising",
        ref_sat=attrs.get("reference_sat_id"),
        mission=_to_str(attrs.get("mission", "")),
    )
    nmf2 = attrs.get("edmax")
    meta["good"] = bool(nmf2 and nmf2 > 0)
    meta["bad_code"] = "0" if meta["good"] else "1"
    meta["extras"] = {
        "NmF2_el_cm3": nmf2,
        "hmF2_km": attrs.get("edmaxalt"),
        "foF2_MHz": attrs.get("critfreq"),
        "scale_height_km": attrs.get("hscale"),
        "tec_below_edmax_TECU": attrs.get("tec0"),
        "tec_residual_TECU": attrs.get("tec1"),
        "profile_top_km": attrs.get("topalt"),
        "profile_bottom_km": attrs.get("botalt"),
        "calibration_flag": attrs.get("icalib"),
    }
    g = Granule("ionPrf", path, meta, attrs, desc, data, units,
                vertical="MSL_alt", independent="MSL_alt")
    _finish_altitude(meta, data, "MSL_alt")
    return g


def _read_scnlv2(path: str) -> Granule:
    attrs, desc, raw = _read_raw(path)
    data = {k: _mask_fill(v[0]) for k, v in raw.items()}
    units = {k: v[1] for k, v in raw.items()}
    meta = _base_meta(path, "scnLv2")
    iso, epoch = _iso(attrs.get("year"), attrs.get("month"), attrs.get("day"),
                      attrs.get("hour"), attrs.get("minute"), attrs.get("second"))
    lat = attrs.get("lat_s4max_L1")
    lon = attrs.get("lon_s4max_L1")
    if lat is None or not np.isfinite(lat):
        lat = attrs.get("lat_start")
        lon = attrs.get("lon_start")
    meta.update(
        time_utc=iso, epoch=epoch, lat=lat, lon=lon,
        local_time=attrs.get("lct_s4max_L1"),
        mission=_to_str(attrs.get("missionId", "")),
        ref_sat=_to_str(attrs.get("refsatId", "")),
    )
    if not meta["sat"]:
        meta["sat"] = f"LEO{_to_str(attrs.get('leoId',''))}"
    s4 = attrs.get("s4max_L1")
    meta["good"] = bool(s4 is not None and np.isfinite(s4) and s4 >= 0)
    meta["bad_code"] = "0" if meta["good"] else "1"
    meta["extras"] = {
        "s4max_L1": s4,
        "s4max_L2": attrs.get("s4max_L2"),
        "alt_s4max_L1_km": attrs.get("alt_s4max_L1"),
        "sigmaphimax_L1_m": attrs.get("sigmaphimax_L1"),
        "duration_s": attrs.get("duration"),
        "elev_min_deg": attrs.get("elevmin"),
        "elev_max_deg": attrs.get("elevmax"),
        "constellation": _to_str(attrs.get("conId", "")),
        "antenna_id": _to_str(attrs.get("antenna_id", "")),
    }
    g = Granule("scnLv2", path, meta, attrs, desc, data, units,
                vertical="occheight", independent="time")
    _finish_altitude(meta, data, "occheight")
    return g


def _read_ivml2m(path: str) -> Granule:
    attrs, desc, raw = _read_raw(path)
    data = {k: _mask_fill(v[0]) for k, v in raw.items()}
    units = {k: v[1] for k, v in raw.items()}
    meta = _base_meta(path, "ivmL2m")
    epoch = None
    iso = None
    uts = data.get("uts")
    if uts is not None and np.isfinite(uts).any():
        epoch = float(np.nanmin(uts))
        iso = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")
    lat = data.get("lat")
    lon = data.get("lon")
    meta.update(
        time_utc=iso, epoch=epoch,
        lat=float(np.nanmedian(lat)) if lat is not None and np.isfinite(lat).any() else None,
        lon=float(np.nanmedian(lon)) if lon is not None and np.isfinite(lon).any() else None,
        mission="COSMIC-2 IVM",
    )
    meta["local_time"] = (float(np.nanmedian(data["mlt"]))
                          if "mlt" in data and np.isfinite(data["mlt"]).any() else None)
    dens = data.get("ion_dens")
    meta["good"] = bool(dens is not None and np.isfinite(dens).sum() > 100)
    meta["bad_code"] = "0" if meta["good"] else "1"
    meta["extras"] = {
        "n_samples": int(dens.size) if dens is not None else 0,
        "median_ion_dens_Ncc": float(np.nanmedian(dens)) if dens is not None
        and np.isfinite(dens).any() else None,
        "median_alt_km": float(np.nanmedian(data["alt"])) if "alt" in data
        and np.isfinite(data["alt"]).any() else None,
        "lat_range": [float(np.nanmin(lat)), float(np.nanmax(lat))]
        if lat is not None and np.isfinite(lat).any() else None,
    }
    g = Granule("ivmL2m", path, meta, attrs, desc, data, units,
                vertical="alt", independent="uts")
    _finish_altitude(meta, data, "alt")
    return g


READERS = {
    "atmPrf": _read_atmprf,
    "wetPf2": _read_wetpf2,
    "ionPrf": _read_ionprf,
    "scnLv2": _read_scnlv2,
    "ivmL2m": _read_ivml2m,
}


def _read_generic(path: str, product: str) -> Granule:
    attrs, desc, raw = _read_raw(path)
    data = {k: _mask_fill(v[0]) for k, v in raw.items()}
    units = {k: v[1] for k, v in raw.items()}
    meta = _base_meta(path, product)
    iso, epoch = _iso(attrs.get("year"), attrs.get("month"), attrs.get("day"),
                      attrs.get("hour", 0), attrs.get("minute", 0), attrs.get("second", 0))
    meta.update(time_utc=iso, epoch=epoch, lat=attrs.get("lat"), lon=attrs.get("lon"))
    vertical = next((c for c in ("MSL_alt", "alt", "gph", "occheight") if c in data), "")
    g = Granule(product, path, meta, attrs, desc, data, units,
                vertical=vertical, independent=vertical or next(iter(data), ""))
    g.warnings.append(f"No dedicated reader for {product}; metadata may be incomplete.")
    _finish_altitude(meta, data, vertical)
    return g


def load(path: str, product: str | None = None) -> Granule:
    """Read a granule, dispatching on product code."""
    prod = product or parse_filename(path)["product"]
    fn = READERS.get(prod)
    g = _read_generic(path, prod or "unknown") if fn is None else fn(path)
    err = _to_str(g.attrs.get("errstr", ""))
    if err:
        g.meta["error_text"] = err
        g.meta["good"] = False
    _nominal_time(g.meta)
    # Sentinels (-999 etc.) are meaningless to a reader of the UI or an export.
    g.meta["extras"] = scrub(g.meta["extras"])
    for k in ("lat", "lon", "local_time", "alt_min", "alt_max"):
        g.meta[k] = scrub(g.meta[k])
    return g


def quick_meta(path: str, product: str | None = None) -> dict:
    """Metadata only - used when indexing thousands of files."""
    g = load(path, product)
    m = dict(g.meta)
    m["size_bytes"] = os.path.getsize(path)
    return m
