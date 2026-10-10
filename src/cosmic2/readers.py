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
#   ivmL2m_C2E1.2026.200.01_0001.0001_nc   (one file per satellite per day;
#                                            the "01" is a file sequence, not an hour)
_NAME_RE = re.compile(r"^(?P<product>[A-Za-z0-9]+)_(?P<stamp>.+?)_(?P<v1>\d{4})\.(?P<v2>\d{4})(?:_nc|\.nc)?$")
_RO_STAMP = re.compile(r"^(?P<sat>C2E\d|[A-Z0-9]{4})\.(?P<year>\d{4})\.(?P<doy>\d{3})\.(?P<hh>\d{2})\.(?P<mm>\d{2})\.(?P<prn>[A-Z]\d{2})$")
_IVM_STAMP = re.compile(r"^(?P<sat>C2E\d)\.(?P<year>\d{4})\.(?P<doy>\d{3})\.(?P<seq>\d{2})$")
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
        # scnLv2 names the satellite by number: LEO 001-006 are COSMIC-2
        # FM1-6, the C2E1-C2E6 of every other product (each matched to the
        # ionPrf of the same occultation, tangent points 8 km apart)
        out["sat"] = g.get("sat") or (f"C2E{int(g['leo'])}" if g.get("leo") else "")
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
        # Relative tolerance for the huge netCDF default fill: stored as
        # float32 it reads back as 9.969209968e36, which no absolute tolerance
        # would match.
        tol = 1e-3 if abs(fv) < 1e6 else abs(fv) * 1e-6
        bad |= np.abs(arr - fv) <= tol
    arr = arr.copy()
    arr[bad] = np.nan
    return arr


def _open(path: str):
    # CDAAC granules are netCDF-3 classic, mostly with an unlimited (record)
    # dimension.  scipy reads those in one pass; netCDF4 strides through every
    # record once per variable, which is ~20x slower on a day-long ivmL2m file
    # (1.2 s against 0.05 s).  netCDF4 is kept for netCDF-4/HDF5 files, which
    # scipy cannot open.
    try:
        return _NC3(path, "r", mmap=False), "nc3"
    except Exception:
        if _NC4 is None:
            raise
    return _NC4(path, "r"), "nc4"


def _numeric(raw: Any, attrs: dict) -> np.ndarray | None:
    """Float64 copy of a variable's values with CF packing undone and its own
    declared fill values set to NaN.  Character variables return ``None``.

    ``valid_range`` is deliberately *not* applied: CDAAC declares ranges that
    real data exceed (scnLv2 GNSS positions near 15 000 km against a declared
    +/-9999 km), and masking on them would delete good samples.
    """
    arr = np.ma.getdata(raw)
    if arr.dtype.kind not in "biuf":
        return None
    out = np.array(arr, dtype="float64")
    bad = np.zeros(out.shape, dtype=bool)
    for key in ("_FillValue", "missing_value"):
        fv = attrs.get(key)
        if fv is None:
            continue
        # Compared in the variable's own type, as the netCDF library does, so
        # a fill attribute written at a different precision still matches.
        try:
            fills = np.ravel(np.asarray(fv)).astype(arr.dtype)
        except (TypeError, ValueError, OverflowError):
            continue
        for f in fills:
            bad |= arr == f
    scale = attrs.get("scale_factor")
    offset = attrs.get("add_offset")
    if scale is not None:
        out *= float(np.ravel(scale)[0])
    if offset is not None:
        out += float(np.ravel(offset)[0])
    out[bad] = np.nan
    return out


def _read_raw(path: str) -> tuple[dict, dict, dict]:
    """Return ``(attrs, attr_desc, variables)`` for a granule."""
    ds, flavour = _open(path)
    try:
        variables = {}
        if flavour == "nc4":
            raw_attrs = {k: ds.getncattr(k) for k in ds.ncattrs()}
            for name, v in ds.variables.items():
                # Packing and fills are handled in _numeric, identically for
                # both backends.
                v.set_auto_maskandscale(False)
                vattrs = {k: v.getncattr(k) for k in v.ncattrs()}
                arr = _numeric(v[:], vattrs)
                if arr is not None:
                    variables[name] = (arr, _to_str(vattrs.get("units", "")))
        else:
            raw_attrs = dict(ds._attributes)
            for name, v in ds.variables.items():
                vattrs = dict(v._attributes)
                arr = _numeric(v[:], vattrs)
                if arr is not None:
                    variables[name] = (arr, _to_str(vattrs.get("units", b"")))
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


# GPS minus UTC (leap seconds) from each date on (IERS Bulletin C)
_GPS_UTC = ((dt.datetime(2006, 1, 1, tzinfo=dt.timezone.utc), 14),
            (dt.datetime(2009, 1, 1, tzinfo=dt.timezone.utc), 15),
            (dt.datetime(2012, 7, 1, tzinfo=dt.timezone.utc), 16),
            (dt.datetime(2015, 7, 1, tzinfo=dt.timezone.utc), 17),
            (dt.datetime(2017, 1, 1, tzinfo=dt.timezone.utc), 18))


def _iso(year, month, day, hour, minute, second) -> tuple[str | None, float | None]:
    """UTC of a CDAAC date and time, which is GPS time.

    The calendar attributes are the GPS seconds fields (atmPrf start_time,
    ionPrf edmaxtime) counted from 1980-01-06 with no leap seconds, and the
    scnLv2 ones put the Earth 18 s ahead of the rotation angle (gast1) the
    file itself gives: UTC is 18 s earlier (since 2017).
    """
    try:
        sec = float(second)
        whole = int(math.floor(sec))
        micro = int(round((sec - whole) * 1e6))
        t = dt.datetime(int(year), int(month), int(day), int(hour), int(minute),
                        min(whole, 59), min(micro, 999999), tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None, None
    t -= dt.timedelta(seconds=next((s for d, s in reversed(_GPS_UTC) if t >= d), 13))
    return t.isoformat().replace("+00:00", "Z"), t.timestamp()


def _local_time(lon: float | None, epoch: float | None) -> float | None:
    if lon is None or epoch is None:
        return None
    utc_h = (epoch % 86400.0) / 3600.0
    return (utc_h + lon / 15.0) % 24.0


def _direction(flag) -> str | None:
    """'setting', 'rising' or None (the file does not say), from atmPrf and
    wetPf2 ``irs`` or ionPrf ``setting``: 1 is setting in both, -1 (irs) or 0
    (setting) rising.

    CDAAC's atmPrf format says irs = +1 setting (the wetPf2 attribute text
    says the opposite).  The files agree with the format: on 2026-09-16 the
    2044 wetPf2 whose ionPrf of the same occultation was found have irs = 1
    exactly when that ionPrf says setting, and ionPrf's flag matches its
    bottom and top times (690 ionPrf of 2026-09-18).  PAZ, which records
    setting occultations only (Padulles et al. 2020,
    doi:10.5194/amt-13-1299-2020), has irs = 1 in every file that has it.
    """
    if flag is None:
        return None
    return "setting" if flag == 1 else "rising"


WGS84_A_KM = 6378.137
WGS84_F = 1.0 / 298.257223563
EARTH_ROTATION_RAD_S = 7.2921150e-5


def geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """WGS-84 latitude and longitude (degrees) and height (km) of an
    Earth-fixed position in km."""
    e2 = WGS84_F * (2.0 - WGS84_F)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - e2))
    h = 0.0
    for _ in range(6):
        s = math.sin(lat)
        n = WGS84_A_KM / math.sqrt(1.0 - e2 * s * s)
        h = p / math.cos(lat) - n if abs(lat) < math.pi / 4 else z / s - n * (1.0 - e2)
        lat = math.atan2(z, p * (1.0 - e2 * n / (n + h)))
    return math.degrees(lat), math.degrees(math.atan2(y, x)), h


def scn_earth_fixed(data: dict, i: int, xyz) -> tuple[float, float, float] | None:
    """Turn a position of a scnLv2 file at sample ``i`` Earth-fixed.

    The file's positions (``x/y/z_LEO``, ``x/y/z_GPS``, km) are inertial and
    ``gast1`` is the Greenwich sidereal angle (rad) at the first sample, so
    the Earth has turned gast1 + omega (time[i] - time[0]) by sample ``i``.
    On 602 COSMIC-2 files (2025-12-21, 2026-06-19) the satellite positions
    turned this way match the file's own ``lat``/``lon`` within 0.0002 and
    0.006 degrees at every sample.
    """
    try:
        t = np.asarray(data["time"], dtype="float64")
        theta = float(np.ravel(data["gast1"])[0]) + EARTH_ROTATION_RAD_S * (t[i] - t[0])
        x, y, z = (float(v) for v in xyz)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (theta, x, y, z)):
        return None
    c, s = math.cos(theta), math.sin(theta)
    return c * x + s * y, -s * x + c * y, z


def scn_tangent_point(data: dict, i: int) -> tuple[float, float, float] | None:
    """Latitude, longitude (degrees) and height (km) of the tangent point of
    sample ``i`` of a scnLv2 file: the point of the straight line from the
    satellite to the GNSS transmitter that is closest to the Earth.

    Its height is the file's ``occheight`` (within 1 m on the 602 files
    above).  CDAAC's ``lat_s4max_L1``/``lon_s4max_L1``/``alt_s4max_L1`` are
    the satellite's own position at the S4 maximum (about 570 km up), one to
    two and a half thousand kilometres from the tangent point.
    """
    try:
        leo = np.array([data[k][i] for k in ("x_LEO", "y_LEO", "z_LEO")], dtype="float64")
        gnss = np.array([data[k][i] for k in ("x_GPS", "y_GPS", "z_GPS")], dtype="float64")
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    d = gnss - leo
    dd = float(d @ d)
    if not (np.isfinite(leo).all() and np.isfinite(gnss).all() and dd > 0):
        return None
    k = -float(leo @ d) / dd
    if not 0.0 < k < 1.0:            # the line does not dip below the satellite
        return None
    fixed = scn_earth_fixed(data, i, leo + k * d)
    return None if fixed is None else geodetic(*fixed)


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
            vi = vocab.info(name, self.product)
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
        # Computed like every other product.  CDAAC's timloc is the local
        # time of hh:mm:00 GPS time, the occultation's start cut to the
        # minute (exactly, on 22 atmPrf of COSMIC-2 and PAZ): 0-60 s early,
        # and 18 s more against UTC.
        local_time=_local_time(attrs.get("lon"), epoch),
        setting=_direction(attrs.get("irs")),
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
        # atmPrf gives rgeoid in km (wetPf2 in m: 0.05091 and 50.91 for
        # the same occultation)
        "geoid_undulation_m": None if scrub(attrs.get("rgeoid")) is None
        else 1000.0 * attrs["rgeoid"],
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
        setting=_direction(attrs.get("irs")),
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
        # edmaxlct is the local time of edmaxtime taken as UTC, 18 s late
        local_time=_local_time(attrs.get("edmaxlon"), epoch),
        setting=_direction(attrs.get("setting")),
        ref_sat=attrs.get("reference_sat_id"),
        mission=_to_str(attrs.get("mission", "")),
    )
    # The profile is placed at its density peak (edmax).  CDAAC's edmax is
    # sometimes an E-region or bottomside maximum (5 of 690 ionPrf of
    # 2026-09-18, at 40-93 km), whose tangent point is up to 1600 km from
    # the F2 peak's: place those at the largest density above 150 km.
    z, ne = data.get("MSL_alt"), data.get("ELEC_dens")
    hm = scrub(attrs.get("edmaxalt"))
    if (hm is not None and hm < 150.0 and z is not None and ne is not None
            and {"GEO_lat", "GEO_lon"} <= data.keys()):
        f2 = np.flatnonzero((z > 150.0) & np.isfinite(ne))
        if f2.size:
            i = f2[np.argmax(ne[f2])]
            meta.update(lat=float(data["GEO_lat"][i]), lon=float(data["GEO_lon"][i]))
            meta["local_time"] = _local_time(meta["lon"], epoch)
    nmf2 = attrs.get("edmax")
    meta["good"] = bool(nmf2 and nmf2 > 0)
    meta["bad_code"] = "0" if meta["good"] else "1"
    meta["extras"] = {
        "NmF2_el_cm3": nmf2,
        "hmF2_km": attrs.get("edmaxalt"),
        "foF2_MHz": attrs.get("critfreq"),
        "scale_height_km": attrs.get("hscale"),
        # CDAAC ionPrf format: tec0 is the TEC integrated between the bottom
        # and the top of the profile (not below the peak), tec1 the
        # extrapolated TEC above the top.
        "tec_profile_TECU": attrs.get("tec0"),
        "tec_above_top_TECU": attrs.get("tec1"),
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
    # The record is placed where the scintillation was seen: the tangent
    # point of the ray at the S4 maximum (the first sample if S4 is all
    # missing), as RO scintillation studies do.  Files without the ray
    # geometry fall back to CDAAC's position attributes below.
    s4_l1 = np.asarray(data.get("s4_L1", np.array([])), dtype="float64")
    i_max = int(np.nanargmax(s4_l1)) if np.isfinite(s4_l1).any() else 0
    tangent = scn_tangent_point(data, i_max)
    tangent_height = None
    if tangent is not None:
        lat, lon, _h = tangent
        t = np.asarray(data["time"], dtype="float64")
        local_time = _local_time(lon, None if epoch is None else epoch + float(t[i_max]))
        occ = data.get("occheight")
        if occ is not None and i_max < np.size(occ) and np.isfinite(occ[i_max]):
            tangent_height = float(occ[i_max])
    else:
        lat = scrub(attrs.get("lat_s4max_L1"))
        lon = scrub(attrs.get("lon_s4max_L1"))
        local_time = scrub(attrs.get("lct_s4max_L1"))
    if lat is None or lon is None:
        # No S4 maximum (the attributes hold the -999 sentinel): place the
        # record at the start of the ray, with the local time of that point
        # rather than the sentinel of the missing maximum.
        lat = scrub(attrs.get("lat_start"))
        lon = scrub(attrs.get("lon_start"))
        local_time = _local_time(lon, epoch)
    meta.update(
        time_utc=iso, epoch=epoch, lat=lat, lon=lon,
        local_time=local_time,
        mission=_to_str(attrs.get("missionId", "")),
        ref_sat=_to_str(attrs.get("refsatId", "")),
    )
    if not meta["sat"]:
        try:
            meta["sat"] = f"C2E{int(float(scrub(attrs.get('leoId'))))}"
        except (TypeError, ValueError):
            meta["sat"] = ""
    s4 = attrs.get("s4max_L1")
    meta["good"] = bool(s4 is not None and np.isfinite(s4) and s4 >= 0)
    meta["bad_code"] = "0" if meta["good"] else "1"
    meta["extras"] = {
        "s4max_L1": s4,
        "s4max_L2": attrs.get("s4max_L2"),
        "tangent_height_s4max_L1_km": tangent_height,
        # CDAAC's lat/lon/alt_s4max_L1: where the satellite was at the maximum
        "satellite_lat_s4max_L1": attrs.get("lat_s4max_L1"),
        "satellite_lon_s4max_L1": attrs.get("lon_s4max_L1"),
        "satellite_alt_s4max_L1_km": attrs.get("alt_s4max_L1"),
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
    # Local *solar* time of the first sample, the same instant as time_utc.
    # (The file's "mlt" variable is magnetic local time, a different
    # coordinate; using it here mislabelled day/night grouping and the
    # local-time filter.  Its median is kept in extras.)
    meta["local_time"] = None
    if uts is not None and lon is not None:
        ok = np.isfinite(uts) & np.isfinite(lon[:uts.size])
        if ok.any():
            i = int(np.flatnonzero(ok)[np.argmin(uts[ok])])
            meta["local_time"] = _local_time(float(lon[i]), float(uts[i]))
    # ion_dens is orig_ion_density rescaled against TGRS TEC (Space Weather
    # Data Release 4, UCAR 2021), which also takes about 7900 /cc off: where
    # the raw density was below that it goes negative (604 of 84520 samples
    # of the bundled day).  A density cannot be negative, so those samples
    # are missing.  The release validates densities above 8e3 /cc.
    dens = data.get("ion_dens")
    n_neg = 0
    if dens is not None:
        n_neg = int((dens <= 0).sum())
        dens[dens <= 0] = np.nan
    meta["good"] = bool(dens is not None and np.isfinite(dens).sum() > 100)
    meta["bad_code"] = "0" if meta["good"] else "1"
    meta["extras"] = {
        "n_samples": int(dens.size) if dens is not None else 0,
        "n_nonpositive_ion_dens": n_neg,
        "median_ion_dens_Ncc": float(np.nanmedian(dens)) if dens is not None
        and np.isfinite(dens).any() else None,
        "median_alt_km": float(np.nanmedian(data["alt"])) if "alt" in data
        and np.isfinite(data["alt"]).any() else None,
        "lat_range": [float(np.nanmin(lat)), float(np.nanmax(lat))]
        if lat is not None and np.isfinite(lat).any() else None,
        "median_mlt_h": float(np.nanmedian(data["mlt"]))
        if "mlt" in data and np.isfinite(data["mlt"]).any() else None,
    }
    g = Granule("ivmL2m", path, meta, attrs, desc, data, units,
                vertical="alt", independent="uts")
    _finish_altitude(meta, data, "alt")
    return g


def _read_model(path: str, product: str) -> Granule:
    """echPrf / avnPrf: weather-model fields (ECMWF / NCEP) that CDAAC
    interpolates along the path of one occultation, named like the atmPrf of
    that occultation (same file stamp).  The levels carry their own Lat/Lon
    (the tangent point drifts with height); the time and the reference
    position are the occultation's."""
    attrs, desc, raw = _read_raw(path)
    data = {k: _mask_fill(v[0]) for k, v in raw.items()}
    units = {k: v[1] for k, v in raw.items()}
    meta = _base_meta(path, product)
    iso, epoch = _iso(attrs.get("year"), attrs.get("month"), attrs.get("day"),
                      attrs.get("hour"), attrs.get("minute"), attrs.get("second"))
    meta.update(time_utc=iso, epoch=epoch, lat=attrs.get("lat"), lon=attrs.get("lon"),
                local_time=_local_time(attrs.get("lon"), epoch),
                ref_sat=attrs.get("reference_sat_id"),
                mission=_to_str(attrs.get("center", "")))
    meta["extras"] = {
        "model_file_1": _to_str(attrs.get("Model_File_1", "")),
        "model_file_2": _to_str(attrs.get("Model_File_2", "")),
        "history": _to_str(attrs.get("history", "")),
    }
    g = Granule(product, path, meta, attrs, desc, data, units,
                vertical="MSL_alt", independent="MSL_alt")
    _finish_altitude(meta, data, "MSL_alt")
    return g


def _read_echprf(path: str) -> Granule:
    return _read_model(path, "echPrf")


def _read_avnprf(path: str) -> Granule:
    return _read_model(path, "avnPrf")


# Raised whenever a reader change alters what is indexed (position, local
# time, quality, extras); an index written by an older version is then
# re-read once at start-up (see store.index_outdated).
INDEX_VERSION = 4

READERS = {
    "atmPrf": _read_atmprf,
    "echPrf": _read_echprf,
    "avnPrf": _read_avnprf,
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
    # One longitude convention, [-180, 180), for the index: the map, the
    # longitude-box search and the antimeridian logic all assume it, and some
    # products declare 0-360 (wetPf2 valid_range is -180..360).
    if g.meta["lon"] is not None:
        g.meta["lon"] = ((float(g.meta["lon"]) + 180.0) % 360.0) - 180.0
    return g


def quick_meta(path: str, product: str | None = None) -> dict:
    """Metadata only - used when indexing thousands of files."""
    g = load(path, product)
    m = dict(g.meta)
    m["size_bytes"] = os.path.getsize(path)
    return m


def quick_meta_safe(task: tuple) -> tuple[dict | None, str]:
    """``(metadata, "")`` or ``(None, error text)`` for ``(path, product)``.

    Never raises, so a batch of files can be indexed on worker processes
    (see :mod:`.parallel`) without one bad file aborting the rest.
    """
    path, product = task
    try:
        return quick_meta(path, product), ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)

