"""Validation of COSMIC-2 profiles against radiosondes from NOAA IGRA v2.

The Integrated Global Radiosonde Archive (IGRA) version 2 is public and
needs no login:

    https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/

Station files are fetched on demand, only for stations that have an
occultation nearby, and cached under ``cache/igra``.  The current year sits
in ``access/data-y2d/<ID>-data-beg<YEAR>.txt.zip``; earlier years only in the
whole period of record, ``access/data-por/<ID>-data.txt.zip`` (often tens of
MB per station).

Method
------
* **Colocation**: an occultation and a sounding are a pair when the launch
  point (from the sounding header) is within ``max_km`` great-circle
  distance of the occultation and the launch time within ``max_hours``.
  Each occultation keeps its nearest sounding.
* **Common height**: both profiles are compared on a geopotential-height
  grid.  The sonde's geopotential height is the reported one, filled in
  between reported levels by interpolation in ln p (the hypsometric
  relation for a layer of constant temperature).  wetPf2 carries its own
  geopotential height (``gph``); atmPrf's geometric height is converted
  with the normal-gravity formula of Mahoney (2001), checked against
  wetPf2's ``gph`` to within a few metres.
* **Sonde humidity**: vapour pressure from the dew point (temperature minus
  the reported dew-point depression) or, failing that, from relative
  humidity, both with Bolton's (1980) saturation vapour pressure over water.
  Where a cold level (below -40 C) reports no humidity it is taken as dry
  (e = 0) for refractivity, as is usual above the upper troposphere;
  specific humidity is compared only where the sonde is warmer than -40 C.
* **Sonde refractivity**: N = 77.6 p/T + 3.73e5 e/T^2, the form CDAAC uses.
* **Differences** (occultation minus sonde) at each grid level: temperature
  in K, refractivity in percent of the sonde value, specific humidity in
  g/kg; then their mean, standard deviation and count in height bins.

atmPrf temperature is the *dry* temperature, which equals the real one only
where water vapour is negligible (above about 8-10 km in the tropics); below
that its difference from the sonde measures the moisture, not an error.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import os
import threading
import zipfile
from pathlib import Path
from typing import Sequence

import numpy as np

log = logging.getLogger(__name__)

IGRA_ROOT = "https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive"
STATION_LIST_URL = f"{IGRA_ROOT}/doc/igra2-station-list.txt"
EARTH_RADIUS_KM = 6371.0
_lock = threading.Lock()


def cache_dir() -> Path:
    from .config import CACHE_DIR
    d = CACHE_DIR / "igra"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str, dest: Path, timeout: float = 120.0) -> Path:
    import requests
    from .config import SETTINGS
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=timeout,
                      headers={"User-Agent": SETTINGS.user_agent}) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    os.replace(tmp, dest)
    return dest


# ---------------------------------------------------------------------------
# station list and sounding files
# ---------------------------------------------------------------------------

def parse_station_list(text: str) -> list[dict]:
    """IGRA2 station list (fixed columns: ID 1-11, LAT 13-20, LON 22-30,
    ELEV 32-37, NAME 42-71, FSTYEAR 73-76, LSTYEAR 78-81)."""
    out = []
    for line in text.splitlines():
        if len(line) < 81:
            continue
        try:
            out.append({"id": line[0:11].strip(), "lat": float(line[12:20]),
                        "lon": float(line[21:30]), "elev_m": float(line[31:37]),
                        "name": line[41:71].strip(),
                        "first_year": int(line[72:76]), "last_year": int(line[77:81])})
        except ValueError:
            continue
    return out


def station_list(download: bool = True, max_age_days: float = 30.0) -> list[dict]:
    path = cache_dir() / "igra2-station-list.txt"
    with _lock:
        stale = (not path.exists() or
                 (dt.datetime.now().timestamp() - path.stat().st_mtime) > max_age_days * 86400)
        if stale and download:
            try:
                _download(STATION_LIST_URL, path)
            except Exception as exc:  # noqa: BLE001
                if not path.exists():
                    raise RuntimeError(f"Could not fetch the IGRA station list: {exc}") from exc
                log.warning("IGRA station list refresh failed (%s); using the cached one", exc)
        if not path.exists():
            raise RuntimeError("The IGRA station list is not cached; allow downloads")
        return parse_station_list(path.read_text(encoding="utf-8", errors="replace"))


def _val(s: str, scale: float = 1.0) -> float:
    try:
        v = int(s)
    except ValueError:
        return math.nan
    return math.nan if v in (-9999, -8888) else v * scale


def parse_soundings(text: str, keep=None) -> list[dict]:
    """Soundings of an IGRA2 data file.

    Header lines start with ``#`` (ID 2-12, YEAR 14-17, MONTH 19-20, DAY
    22-23, HOUR 25-26, RELTIME 28-31, NUMLEV 33-36, LAT 56-62 and LON 64-71
    in 1e-4 degrees).  Data lines: PRESS 10-15 (Pa), GPH 17-21 (m), TEMP
    23-27 (0.1 C), RH 29-33 (0.1 %), DPDP 35-39 (0.1 C); -9999 is missing,
    -8888 removed by IGRA's quality control.  ``keep(header)`` may skip a
    sounding before its levels are parsed.
    """
    out: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        h = lines[i]
        if not h.startswith("#"):
            i += 1
            continue
        try:
            nlev = int(h[32:36])
            year, month, day = int(h[13:17]), int(h[18:20]), int(h[21:23])
            hour = int(h[24:26])
            rel = h[27:31]
            if rel.strip() and rel[:2] != "99" and rel[2:] != "99":
                launch = dt.datetime(year, month, day, int(rel[:2]), int(rel[2:]),
                                     tzinfo=dt.timezone.utc)
            else:
                launch = dt.datetime(year, month, day, hour if hour != 99 else 0,
                                     tzinfo=dt.timezone.utc)
            # RELTIME is the actual launch, a little before the nominal hour
            # (2305 for 00 UTC): it belongs to the previous day.
            if hour != 99 and launch.hour > hour + 3:
                launch -= dt.timedelta(days=1)
            head = {"station": h[1:12].strip(), "time": launch,
                    "lat": int(h[55:62]) / 1e4, "lon": int(h[63:71]) / 1e4}
        except ValueError:
            i += 1
            continue
        block = lines[i + 1:i + 1 + nlev]
        i += 1 + nlev
        if keep is not None and not keep(head):
            continue
        p, z, t, rh, dpd = [], [], [], [], []
        for ln in block:
            if len(ln) < 39:
                ln = ln.ljust(39)
            pv = _val(ln[9:15], 0.01)          # Pa -> hPa
            if not math.isfinite(pv):
                continue                         # wind-only (height) levels
            p.append(pv)
            z.append(_val(ln[16:21]))
            t.append(_val(ln[22:27], 0.1))
            rh.append(_val(ln[28:33], 0.1))
            dpd.append(_val(ln[34:39], 0.1))
        if len(p) < 5:
            continue
        head.update(p_hpa=np.array(p), gph_m=np.array(z), temp_c=np.array(t),
                    rh_pct=np.array(rh), dpd_c=np.array(dpd))
        out.append(head)
    return out


_LEVEL_KEYS = ("p_hpa", "gph_m", "temp_c", "rh_pct", "dpd_c")


def _station_arrays(path: Path) -> dict:
    """All soundings of a station file as flat arrays, cached beside it.

    Decompressing and parsing a year-to-date text file costs ~0.1 s; a
    comparison touches a hundred or more stations, so the parsed soundings
    are kept in ``<file>.npz`` and rebuilt only when the file changes.
    """
    cache = path.with_name(path.name + ".npz")
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        with np.load(cache) as z:
            return {k: z[k] for k in z.files}
    with zipfile.ZipFile(path) as zf:
        text = zf.read(zf.namelist()[0]).decode("ascii", errors="replace")
    snds = parse_soundings(text)
    counts = np.array([s_["p_hpa"].size for s_ in snds], dtype=np.int64)
    out = {"time": np.array([s_["time"].timestamp() for s_ in snds], dtype="float64"),
           "lat": np.array([s_["lat"] for s_ in snds], dtype="float64"),
           "lon": np.array([s_["lon"] for s_ in snds], dtype="float64"),
           "start": np.concatenate(([0], np.cumsum(counts)[:-1])).astype(np.int64)
           if counts.size else np.zeros(0, np.int64),
           "count": counts}
    for k in _LEVEL_KEYS:
        out[k] = (np.concatenate([s_[k] for s_ in snds]).astype("float32")
                  if snds else np.zeros(0, "float32"))
    tmp = cache.with_name(cache.name + ".tmp.npz")
    np.savez_compressed(tmp, **out)
    os.replace(tmp, cache)
    return out


MISSING_RETRY_HOURS = 24.0


def station_file(station: str, year: int, download: bool = True,
                 need_until: dt.datetime | None = None) -> Path | None:
    """Local copy of the IGRA2 file holding ``year`` for ``station``.

    The current year is only in the year-to-date file; earlier years only in
    the period-of-record file.  A file the archive does not have is
    remembered for ``MISSING_RETRY_HOURS`` so a repeated comparison does not
    ask again for every silent station.
    """
    d = cache_dir()
    this_year = dt.datetime.now(dt.timezone.utc).year
    if year >= this_year:
        name = f"{station}-data-beg{year}.txt.zip"
        url = f"{IGRA_ROOT}/access/data-y2d/{name}"
    else:
        name = f"{station}-data.txt.zip"
        url = f"{IGRA_ROOT}/access/data-por/{name}"
    path = d / name
    if path.exists():
        # A year-to-date file grows every day: fetch it again (at most every
        # 6 h) when an occultation is later than the copy we have.
        age_s = dt.datetime.now().timestamp() - path.stat().st_mtime
        stale = (year >= this_year and need_until is not None and download
                 and path.stat().st_mtime < need_until.timestamp() + 2 * 86400
                 and age_s > 6 * 3600)
        if stale:
            try:
                _download(url, path)
            except Exception as exc:  # noqa: BLE001
                log.info("IGRA refresh of %s failed: %s", name, exc)
        return path
    marker = d / (name + ".missing")
    if not download or (marker.exists() and
                        dt.datetime.now().timestamp() - marker.stat().st_mtime
                        < MISSING_RETRY_HOURS * 3600):
        return None
    try:
        return _download(url, path)
    except Exception as exc:  # noqa: BLE001
        log.info("IGRA %s: %s", url, exc)
        marker.write_text(str(exc)[:200], encoding="utf-8")
        return None


def soundings_near(station: str, times: Sequence[dt.datetime], max_hours: float,
                   download: bool = True) -> list[dict]:
    """Soundings of ``station`` launched within ``max_hours`` of any of
    ``times``."""
    out = []
    ts = np.array([t.timestamp() for t in times], dtype="float64")
    for year in sorted({t.year for t in times}):
        path = station_file(station, year, download,
                            need_until=max(t for t in times if t.year == year))
        if path is None:
            continue
        a = _station_arrays(path)
        if not a["time"].size:
            continue
        near = np.abs(a["time"][:, None] - ts[None, :]).min(axis=1) <= max_hours * 3600
        for i in np.flatnonzero(near):
            sl = slice(int(a["start"][i]), int(a["start"][i] + a["count"][i]))
            snd = {"station": station, "lat": float(a["lat"][i]), "lon": float(a["lon"][i]),
                   "time": dt.datetime.fromtimestamp(float(a["time"][i]), dt.timezone.utc)}
            snd.update({k: a[k][sl].astype("float64") for k in _LEVEL_KEYS})
            out.append(snd)
    return out


# ---------------------------------------------------------------------------
# physics
# ---------------------------------------------------------------------------

def sat_vapour_pressure_hpa(temp_c: np.ndarray) -> np.ndarray:
    """Bolton (1980) saturation vapour pressure over water, hPa."""
    t = np.asarray(temp_c, dtype="float64")
    return 6.112 * np.exp(17.67 * t / (t + 243.5))


def sonde_profile(s: dict) -> dict:
    """Geopotential height (km), temperature (K), vapour pressure (hPa),
    specific humidity (g/kg) and refractivity (N-units) of one sounding,
    sorted by pressure (surface first)."""
    order = np.argsort(-s["p_hpa"])
    p = s["p_hpa"][order]
    z = s["gph_m"][order]
    tc = s["temp_c"][order]
    td = tc - s["dpd_c"][order]
    e = sat_vapour_pressure_hpa(td)
    from_rh = s["rh_pct"][order] / 100.0 * sat_vapour_pressure_hpa(tc)
    e = np.where(np.isfinite(e), e, from_rh)
    e = np.where(~np.isfinite(e) & (tc < -40.0), 0.0, e)
    tk = tc + 273.15
    # Geopotential height between reported levels: linear in ln p.
    ok = np.isfinite(z) & (p > 0)
    lnp = np.log(p)
    if ok.sum() >= 2:
        zf = np.interp(-lnp, -lnp[ok], z[ok], left=np.nan, right=np.nan)
        z = np.where(ok, z, zf)
    with np.errstate(invalid="ignore", divide="ignore"):
        q = 622.0 * e / (p - 0.378 * e)
        n = 77.6 * p / tk + 3.73e5 * e / tk ** 2
    # Sonde humidity sensors are not trusted below -40 C (and the dry
    # assumption above is for refractivity only): no humidity comparison there.
    q = np.where(tc >= -40.0, q, np.nan)
    return {"gph_km": z / 1000.0, "temp_K": tk, "e_hpa": e, "sph_gkg": q,
            "ref_N": n, "p_hpa": p}


def geopotential_height_km(z_km: np.ndarray, lat_deg: float) -> np.ndarray:
    """Geopotential height from geometric height above sea level.

    Mahoney (2001): normal gravity at the surface (Somigliana) and an
    effective Earth radius chosen so that g(z) = g(lat) (R / (R + z))^2
    matches the WGS-84 free-air gradient; Z = (g(lat)/g0) R z / (R + z).
    """
    phi = math.radians(lat_deg)
    s2 = math.sin(phi) ** 2
    g_lat = 9.7803253359 * (1 + 0.00193185265241 * s2) / math.sqrt(1 - 0.00669437999013 * s2)
    r_eff = 6378.137 / (1.006803 - 0.006706 * s2)       # km
    z = np.asarray(z_km, dtype="float64")
    return (g_lat / 9.80665) * r_eff * z / (r_eff + z)


def great_circle_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------

def _ro_profile(row: dict) -> dict | None:
    """Geopotential height and the compared quantities of one occultation."""
    from . import analysis, readers
    try:
        g = readers.load(row["path"], row["product"])
    except Exception:  # noqa: BLE001
        return None
    d = g.data
    if "MSL_alt" not in d or "Temp" not in d:
        return None
    lat = g.meta.get("lat") if g.meta.get("lat") is not None else row.get("lat")
    if g.product == "wetPf2" and "gph" in d:
        z = d["gph"]
    else:
        z = geopotential_height_km(d["MSL_alt"], lat or 0.0)
    out = {"gph_km": z, "temp_K": analysis.to_kelvin(d["Temp"], g.units.get("Temp", "C")),
           "ref_N": d.get("Ref", d.get("ref")), "product": g.product}
    if "sph" in d:
        out["sph_gkg"] = d["sph"]
    return out


QUANTITIES = {
    "temp_K": {"label": "Temperature", "units": "K", "relative": False},
    "ref_N": {"label": "Refractivity", "units": "%", "relative": True},
    "sph_gkg": {"label": "Specific humidity", "units": "g/kg", "relative": False},
}


def _differences(ro: dict, sonde: dict, grid: np.ndarray) -> dict:
    from .analysis import interp_to_grid
    out = {}
    for key, info in QUANTITIES.items():
        if ro.get(key) is None or key not in sonde:
            continue
        log_ = key in ("ref_N", "sph_gkg")
        a = interp_to_grid(ro["gph_km"], ro[key], grid, max_gap=1.0, log=log_)
        b = interp_to_grid(sonde["gph_km"], sonde[key], grid, max_gap=1.0, log=log_)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[key] = 100.0 * (a - b) / b if info["relative"] else a - b
    return out


def compare(rows: Sequence[dict], max_km: float = 300.0, max_hours: float = 3.0,
            top_km: float = 30.0, step_km: float = 0.2, bin_km: float = 1.0,
            download: bool = True, max_stations: int = 200) -> dict:
    """Colocate occultations with IGRA soundings and summarise the
    differences (occultation minus sonde) by height.  See the module
    docstring for the method."""
    from .analysis import make_grid
    rows = [r for r in rows if r.get("lat") is not None and r.get("lon") is not None
            and r.get("time_utc")]
    stations = station_list(download)
    if not rows:
        return {"n_pairs": 0, "pairs": [], "stats": {}, "n_occultations": 0}
    t_occ = [dt.datetime.fromisoformat(r["time_utc"].replace("Z", "+00:00")) for r in rows]
    years = {t.year for t in t_occ}
    st = [s for s in stations if s["last_year"] >= min(years) and s["first_year"] <= max(years)]
    slat = np.array([s["lat"] for s in st])
    slon = np.array([s["lon"] for s in st])
    # Candidate stations per occultation, by the station-list position (a
    # margin of 50 km covers sondes launched away from the listed point).
    need: dict[str, list[int]] = {}
    for k, r in enumerate(rows):
        dist = great_circle_km(r["lat"], r["lon"], slat, slon)
        for j in np.flatnonzero(dist <= max_km + 50.0):
            need.setdefault(st[j]["id"], []).append(k)
    names = {s["id"]: s["name"] for s in st}
    ordered = sorted(need, key=lambda sid: -len(need[sid]))[:max_stations]
    best: dict[int, tuple] = {}
    fetched = missing = 0
    # Downloads and decompression both release the GIL: a few threads cut
    # a 160-station comparison from ~25 s to a few seconds once cached.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        found = list(ex.map(lambda sid: soundings_near(
            sid, [t_occ[k] for k in need[sid]], max_hours, download), ordered))
    for sid, snds in zip(ordered, found):
        ks = need[sid]
        if snds:
            fetched += 1
        else:
            missing += 1
        for s in snds:
            for k in ks:
                dt_h = abs((s["time"] - t_occ[k]).total_seconds()) / 3600.0
                if dt_h > max_hours:
                    continue
                d_km = float(great_circle_km(rows[k]["lat"], rows[k]["lon"], s["lat"], s["lon"]))
                if d_km > max_km:
                    continue
                if k not in best or (d_km, dt_h) < best[k][:2]:
                    best[k] = (d_km, dt_h, s)
    grid = make_grid(top_km, step_km)
    diffs: dict[str, list[np.ndarray]] = {q: [] for q in QUANTITIES}
    pairs = []
    for k, (d_km, dt_h, s) in sorted(best.items()):
        ro = _ro_profile(rows[k])
        if ro is None:
            continue
        sonde = sonde_profile(s)
        dd = _differences(ro, sonde, grid)
        if not any(np.isfinite(v).any() for v in dd.values()):
            continue
        for q, v in dd.items():
            diffs[q].append(v)
        pairs.append({"granule_id": rows[k].get("id"), "file_name": rows[k].get("file_name"),
                      "product": rows[k].get("product"), "time_utc": rows[k]["time_utc"],
                      "lat": rows[k]["lat"], "lon": rows[k]["lon"],
                      "station": s["station"], "station_name": names.get(s["station"], ""),
                      "launch_utc": s["time"].isoformat().replace("+00:00", "Z"),
                      "sonde_lat": s["lat"], "sonde_lon": s["lon"],
                      "distance_km": round(d_km, 1), "dt_hours": round(dt_h, 2),
                      "sonde_top_km": float(np.nanmax(sonde["gph_km"]))
                      if np.isfinite(sonde["gph_km"]).any() else None})
    edges = np.arange(0.0, top_km + bin_km / 2, bin_km)
    centres = 0.5 * (edges[:-1] + edges[1:])
    stats = {}
    for q, cols in diffs.items():
        if not cols:
            continue
        m = np.vstack(cols)                       # pairs x levels
        mean, std, n, med = [], [], [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = (grid >= lo) & (grid < hi)
            # one value per pair and bin (its mean over the bin's levels),
            # so a pair counts once however fine the grid
            with np.errstate(invalid="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    per_pair = np.nanmean(m[:, sel], axis=1)
            v = per_pair[np.isfinite(per_pair)]
            n.append(int(v.size))
            mean.append(float(v.mean()) if v.size else None)
            med.append(float(np.median(v)) if v.size else None)
            std.append(float(v.std(ddof=1)) if v.size > 1 else None)
        stats[q] = dict(QUANTITIES[q], mean=mean, median=med, std=std, n=n)
    return {"n_occultations": len(rows), "n_pairs": len(pairs), "pairs": pairs,
            "stations_with_data": fetched, "stations_without_data": missing,
            "stations_considered": len(ordered),
            "max_km": max_km, "max_hours": max_hours,
            "bin_edges_km": edges.tolist(), "bin_centres_km": centres.tolist(),
            "stats": stats}
