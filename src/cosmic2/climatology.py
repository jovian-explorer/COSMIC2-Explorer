"""Statistics over many profiles: sampling and quality, and (below) gridded
climatologies.

Everything here works on index rows (``store.query_granules``) and, for the
gridded fields, on the granules they point to.  Nothing is fitted or
smoothed: counts, means and percentiles only, so every number can be
reproduced from the exported index table.
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

import numpy as np

# Products whose lowest level says how far the occultation reached down
# ("penetration depth").  atmPrf is the observation itself; wetPf2's lowest
# level is that of the 1D-Var retrieval, which follows the same profile.
NEUTRAL = ("atmPrf", "wetPf2")
PENETRATION_THRESHOLDS_KM = (0.1, 0.5, 1.0, 2.0, 3.0, 5.0)


def _hist(values: np.ndarray, edges: np.ndarray) -> list[int]:
    v = values[np.isfinite(values)]
    return [int(c) for c in np.histogram(v, bins=edges)[0]]


def _utc_hour(iso: str | None) -> float:
    try:
        return int(iso[11:13]) + int(iso[14:16]) / 60.0
    except (TypeError, ValueError, IndexError):
        return float("nan")


def terrain_by_atmprf(rows: Sequence[dict]) -> dict[str, float]:
    """``{atmPrf file name: terrain height km}`` from wetPf2 index rows.

    wetPf2 files name the atmPrf they were retrieved from and carry the
    terrain height at the occultation, which turns an atmPrf's lowest level
    into a height above the ground.
    """
    out = {}
    for w in rows:
        if w.get("product") != "wetPf2":
            continue
        ex = w.get("extras") or {}
        src, th = ex.get("source_atmPrf"), ex.get("terrain_height_km")
        if src and isinstance(th, (int, float)):
            out[src] = float(th)
    return out


def sampling_statistics(rows: Sequence[dict], lat_step: float = 10.0,
                        pen_step_km: float = 0.25, pen_top_km: float = 10.0,
                        terrain: dict[str, float] | None = None) -> dict:
    """Counts, quality flags and penetration depth for a set of index rows.

    Per product: how many profiles, how many CDAAC flagged bad (and with
    which code), and how they are spread over latitude, local solar time and
    UTC hour.  For the neutral products, the *penetration depth* is the
    height of the lowest retrieved level above mean sea level (the index's
    ``alt_min``), from good profiles only: its histogram, the fraction of
    profiles reaching below each of ``PENETRATION_THRESHOLDS_KM`` and its
    median by latitude band.  Heights are above sea level, not above the
    ground, so over high terrain a profile can stop well above the sea-level
    mark and still reach the surface.  For atmPrf the lowest level is
    compared with CDAAC's own ``profile_bottom_km`` attribute, and turned
    into a height above the ground where ``terrain`` (see
    :func:`terrain_by_atmprf`; built from ``rows`` when not given) knows the
    terrain under it.
    """
    lat_edges = np.arange(-90.0, 90.0 + lat_step / 2, lat_step)
    hour_edges = np.arange(0.0, 24.5, 1.0)
    pen_edges = np.arange(0.0, pen_top_km + pen_step_km / 2, pen_step_km)
    by_product: dict[str, list[dict]] = {}
    for r in rows:
        by_product.setdefault(r.get("product") or "unknown", []).append(r)

    products = {}
    for prod, rs in sorted(by_product.items()):
        lat = np.array([np.nan if r.get("lat") is None else r["lat"] for r in rs], float)
        lt = np.array([np.nan if r.get("local_time") is None else r["local_time"]
                       for r in rs], float)
        utc = np.array([_utc_hour(r.get("time_utc")) for r in rs], float)
        good = np.array([bool(r.get("good")) for r in rs])
        levels = np.array([r.get("n_levels") or np.nan for r in rs], float)
        codes = Counter(str(r.get("bad_code")) for r in rs if not r.get("good"))
        p = {
            "n": len(rs), "n_good": int(good.sum()), "n_bad": int((~good).sum()),
            "bad_fraction": float((~good).mean()) if rs else None,
            "bad_codes": dict(codes),
            "lat_counts": _hist(lat, lat_edges),
            "lat_counts_good": _hist(lat[good], lat_edges),
            "local_time_counts": _hist(lt, hour_edges),
            "utc_hour_counts": _hist(utc, hour_edges),
            "levels_median": float(np.nanmedian(levels)) if np.isfinite(levels).any() else None,
            "lat_range": [float(np.nanmin(lat)), float(np.nanmax(lat))]
            if np.isfinite(lat).any() else None,
        }
        if prod in NEUTRAL:
            zmin = np.array([np.nan if r.get("alt_min") is None else r["alt_min"]
                             for r in rs], float)[good]
            ok = np.isfinite(zmin)
            z = zmin[ok]
            pen = {
                "n": int(z.size),
                "counts": _hist(z, pen_edges),
                "above_top": int((z >= pen_top_km).sum()),
                "median_km": float(np.median(z)) if z.size else None,
                "fraction_below": {f"{t:g}": (float((z < t).mean()) if z.size else None)
                                   for t in PENETRATION_THRESHOLDS_KM},
            }
            glat = lat[good][ok]
            band_median, band_n = [], []
            for lo, hi in zip(lat_edges[:-1], lat_edges[1:]):
                sel = (glat >= lo) & (glat < hi)
                band_n.append(int(sel.sum()))
                band_median.append(float(np.median(z[sel])) if sel.any() else None)
            pen["lat_median_km"] = band_median
            pen["lat_n"] = band_n
            if prod == "atmPrf":
                # Height above the ground: wetPf2 files name the atmPrf they
                # were retrieved from and carry the terrain height there, so
                # an atmPrf with its wetPf2 also on disk gets a true
                # penetration depth (the quantity papers quote: Schreiner et
                # al. 2020 report over 80 % of COSMIC-2 profiles reaching
                # within 1 km of the surface).
                if terrain is None:
                    terrain = terrain_by_atmprf(rows)
                agl = np.array([r["alt_min"] - terrain[r.get("file_name")]
                                for r in rs if r.get("good") and r.get("alt_min") is not None
                                and r.get("file_name") in terrain], float)
                pen["above_ground"] = {
                    "n": int(agl.size),
                    "median_km": float(np.median(agl)) if agl.size else None,
                    "fraction_below": {f"{t:g}": (float((agl < t).mean()) if agl.size else None)
                                       for t in PENETRATION_THRESHOLDS_KM},
                }
                # Cross-check: the index's lowest level against CDAAC's own
                # profile_bottom_km for the same granules.
                pairs = [(r["alt_min"], r.get("extras", {}).get("profile_bottom_km"))
                         for r in rs if r.get("good") and r.get("alt_min") is not None]
                d = np.array([a - b for a, b in pairs if isinstance(b, (int, float))], float)
                pen["archive_check"] = {
                    "n": int(d.size),
                    "max_abs_diff_km": float(np.max(np.abs(d))) if d.size else None}
            p["penetration"] = pen
        products[prod] = p
    return {
        "n": len(rows),
        "lat_edges": lat_edges.tolist(),
        "hour_edges": hour_edges.tolist(),
        "penetration_edges_km": pen_edges.tolist(),
        "penetration_thresholds_km": list(PENETRATION_THRESHOLDS_KM),
        "products": products,
    }


# ---------------------------------------------------------------------------
# latitude-height cross sections
# ---------------------------------------------------------------------------

def _section_column(task: tuple):
    """One profile of a cross section: ``(lat, gridded column, units,
    quantity)``.  Module-level so it runs on the worker processes."""
    from .analysis import _composite_column
    meta = task[1]
    res = _composite_column(task)
    if res is None or meta.get("lat") is None:
        return None
    _key, col, units, qty, source = res
    return float(meta["lat"]), col, units, qty, source


def cross_section(granule_paths: Sequence[tuple[str, dict]], field: str,
                  vertical: str = "MSL_alt", lat_step: float = 5.0,
                  top_km: float = 40.0, step_km: float = 0.5,
                  bottom_km: float = 0.0, good_only: bool = True,
                  min_count: int = 3, convert_kelvin: bool = True,
                  workers: int | None = None, screen_k: float | None = None) -> dict:
    """Zonal-mean latitude-height section of one quantity.

    ``screen_k`` drops each latitude band's outlying profiles before
    averaging (:func:`analysis.robust_screen`).

    Every profile is put on the common height grid exactly as for the
    Compare tab's averages (log interpolation for the quantities in
    ``analysis.LOG_INTERP_FIELDS``, never across gaps wider than 2 km), then the columns
    are averaged in latitude bands ``lat_step`` degrees wide.  A cell with
    fewer than ``min_count`` profiles is blank.

    Besides the mean (and standard deviation and count) of each cell, the
    *departure* of each band from the mean of the whole selection at the
    same height is returned in percent,

        departure = 100 (mean_band(z) - mean_all(z)) / mean_all(z),

    which for refractivity is the ``N_anom_pct`` of the vocabulary: the
    latitude structure of N with its exponential fall-off removed.  It is a
    departure from this selection's own mean, not a bias against an
    independent reference (see the radiosonde comparison for that).

    A selection mixing dry (atmPrf) and moist (wetPf2) ``Temp``, or
    observations with weather-model profiles, is refused rather than
    averaged.
    """
    from . import vocab
    from .analysis import make_grid
    from .parallel import pmap
    if not (lat_step > 0):
        raise ValueError("lat_step must be > 0")
    grid = make_grid(top_km, step_km, bottom_km)
    tasks = [(path, meta, field, vertical, grid, "all", convert_kelvin)
             for path, meta in granule_paths
             if not (good_only and not meta.get("good", True))]
    results = [r for r in pmap(_section_column, tasks, workers=workers)
               if r is not None]
    quantities = {r[3] for r in results}
    kinds = {r[3:5] for r in results}
    if len(kinds) > 1:
        raise ValueError(
            f"the selection holds {field} as different quantities "
            f"({', '.join(sorted(vocab.info(q)['label'] + (f' ({s})' if s else '') for q, s in kinds))}); "
            f"choose one product")
    edges = np.arange(-90.0, 90.0 + lat_step / 2, lat_step)
    if not results:
        return {"field": field, "vertical": vertical, "n_profiles": 0,
                "grid": grid.tolist(), "lat_edges": [], "lat_centres": [],
                "mean": [], "std": [], "count": [], "sem": [], "departure_pct": [],
                "overall_mean": [], "units": "", "min_count": min_count}
    lats = np.array([r[0] for r in results])
    cols = np.vstack([r[1] for r in results])
    units = results[0][2]
    qty = next(iter(quantities))
    idx = np.clip(np.digitize(lats, edges) - 1, 0, edges.size - 2)
    screened = 0
    if screen_k:
        from .analysis import robust_screen
        keep = np.ones(len(lats), dtype=bool)
        for b in np.unique(idx):
            sel = np.flatnonzero(idx == b)
            keep[sel] = robust_screen(cols[sel], grid, k=screen_k)
        screened = int((~keep).sum())
        lats, cols, idx = lats[keep], cols[keep], idx[keep]
    used = np.arange(idx.min(), idx.max() + 1)
    with np.errstate(invalid="ignore", divide="ignore"), \
            warnings_off():
        overall_n = np.isfinite(cols).sum(axis=0)
        overall = np.nanmean(cols, axis=0)
        overall[overall_n < min_count] = np.nan
        mean = np.full((used.size, grid.size), np.nan)
        std = np.full((used.size, grid.size), np.nan)
        count = np.zeros((used.size, grid.size), dtype=int)
        for k, b in enumerate(used):
            m = cols[idx == b]
            if not m.shape[0]:
                continue
            n = np.isfinite(m).sum(axis=0)
            count[k] = n
            mu = np.nanmean(m, axis=0)
            sd = np.nanstd(m, axis=0, ddof=1) if m.shape[0] > 1 else np.full(grid.size, np.nan)
            thin = n < min_count
            mu[thin] = np.nan
            sd[thin] = np.nan
            mean[k], std[k] = mu, sd
        departure = 100.0 * (mean - overall) / overall
        # standard error of each cell's mean (profiles taken as independent)
        sem = std / np.sqrt(np.where(count > 0, count, np.nan))
    return {
        "field": field, "vertical": vertical, "quantity": qty, "units": units,
        "field_label": vocab.axis_title(qty, units),
        "vertical_label": vocab.axis_title(vertical),
        "n_profiles": int(len(lats)), "min_count": min_count,
        "screen_k": screen_k, "screened_out": screened,
        "grid": grid.tolist(),
        "lat_edges": edges[used[0]:used[-1] + 2].tolist(),
        "lat_centres": (0.5 * (edges[used] + edges[used + 1])).tolist(),
        "profiles_per_band": [int((idx == b).sum()) for b in used],
        "mean": mean, "std": std, "count": count, "sem": sem,
        "departure_pct": departure, "overall_mean": overall,
    }


class warnings_off:
    """Silence numpy's all-NaN-slice warnings (empty cells are expected)."""

    def __enter__(self):
        import warnings
        self._cm = warnings.catch_warnings()
        self._cm.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)


# ---------------------------------------------------------------------------
# gridded maps of per-profile diagnostics (gravity-wave energy and others)
# ---------------------------------------------------------------------------

EP_COLUMN = "gravity_waves.ep_J_per_kg"


def once_per_occultation(rows: Sequence[dict], values: Sequence) -> list:
    """``values`` (one per row, ``None`` for none), each occultation once.

    With both the atmPrf and the wetPf2 of an occultation selected, a
    per-occultation statistic would count it twice, and intervals that take
    the profiles as independent would come out too narrow by about sqrt(2).
    The wetPf2's value stands for the occultation (moist, real temperature),
    the atmPrf's where the wetPf2 has none (the boundary-layer top is
    atmPrf-only).  Rows of other products are all kept."""
    out, seen = [], set()
    for i in sorted(range(len(rows)), key=lambda i: rows[i].get("product") != "wetPf2"):
        r, v = rows[i], values[i]
        if v is None:
            continue
        stamp = r.get("stamp") if r.get("product") in ("atmPrf", "wetPf2") else None
        if stamp:
            if stamp in seen:
                continue
            seen.add(stamp)
        out.append(v)
    return out


def _map_value(task: tuple):
    """``(lat, lon, value)`` of one profile, or ``None``.  Module-level so
    it runs on the worker processes.

    The gravity-wave energy is recomputed with the requested layer and
    filter (``gw``); any other column comes from the standard diagnostics.
    """
    from . import analysis, readers
    row, column, gw = task
    if row.get("lat") is None or row.get("lon") is None:
        return None
    if column == EP_COLUMN and gw:
        try:
            g = readers.load(row["path"], row["product"])
        except Exception:  # noqa: BLE001
            return None
        d = g.data
        tname = "Temp" if "Temp" in d else "temp_dry"
        if "MSL_alt" not in d or tname not in d:
            return None
        tk = analysis.to_kelvin(d[tname], g.units.get(tname, "C"))
        v = analysis.gravity_wave_energy(d["MSL_alt"], tk, **gw)["ep_J_per_kg"]
    else:
        flat = analysis.diagnostics_row(row)
        v = None if flat is None else flat.get(column)
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not np.isfinite(v):
        return None
    return float(row["lat"]), float(row["lon"]), float(v)


def diagnostic_map(rows: Sequence[dict], column: str = EP_COLUMN,
                   lat_step: float = 10.0, lon_step: float = 20.0,
                   min_count: int = 1, gw: dict | None = None,
                   workers: int | None = None) -> dict:
    """Mean of a per-profile diagnostic in latitude-longitude cells, and its
    zonal mean (mean, median, standard deviation, count per latitude band).

    ``gw`` (keywords of :func:`analysis.gravity_wave_energy`: ``z_lo``,
    ``z_hi``, ``method``, ``poly_order``, ``cutoff_km``) recomputes the
    gravity-wave energy with that layer and background filter; without it
    the per-profile diagnostic (polynomial, 20-40 km) is used.  Cells with
    fewer than ``min_count`` profiles are blank.  With a day or two of data
    the cells are sparse: the zonal mean is the steadier number.
    """
    from .parallel import pmap
    if not (lat_step > 0 and lon_step > 0):
        raise ValueError("lat_step and lon_step must be > 0")
    if gw and gw.get("method", "polynomial") not in ("polynomial", "highpass"):
        raise ValueError("method must be polynomial or highpass")
    tasks = [(r, column, gw or None) for r in rows]
    vals = np.array(once_per_occultation(rows, pmap(_map_value, tasks, workers=workers)),
                    float).reshape(-1, 3)
    lat_edges = np.arange(-90.0, 90.0 + lat_step / 2, lat_step)
    lon_edges = np.arange(-180.0, 180.0 + lon_step / 2, lon_step)
    nlat, nlon = lat_edges.size - 1, lon_edges.size - 1
    out = {"column": column, "n": int(vals.shape[0]), "min_count": min_count,
           "gw": gw or None,
           "lat_edges": lat_edges.tolist(), "lon_edges": lon_edges.tolist(),
           "lat_centres": (0.5 * (lat_edges[:-1] + lat_edges[1:])).tolist(),
           "lon_centres": (0.5 * (lon_edges[:-1] + lon_edges[1:])).tolist()}
    mean = np.full((nlat, nlon), np.nan)
    count = np.zeros((nlat, nlon), dtype=int)
    zonal = {k: [None] * nlat for k in ("mean", "median", "std", "sem", "ci95_lo", "ci95_hi")}
    zonal["n"] = [0] * nlat
    if vals.size:
        li = np.clip(np.digitize(vals[:, 0], lat_edges) - 1, 0, nlat - 1)
        lj = np.clip(np.digitize(vals[:, 1], lon_edges) - 1, 0, nlon - 1)
        np.add.at(count, (li, lj), 1)
        sums = np.zeros((nlat, nlon))
        np.add.at(sums, (li, lj), vals[:, 2])
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = sums / count
        mean[count < max(min_count, 1)] = np.nan
        for i in range(nlat):
            v = vals[li == i, 2]
            zonal["n"][i] = int(v.size)
            if v.size:
                zonal["mean"][i] = float(v.mean())
                zonal["median"][i] = float(np.median(v))
                zonal["std"][i] = float(v.std(ddof=1)) if v.size > 1 else None
                if v.size > 1:
                    # 95 % confidence interval of the zonal mean (Student's t)
                    from .analysis import mean_uncertainty
                    se, lo, hi = mean_uncertainty(np.array([v.mean()]), np.array([v.std(ddof=1)]),
                                                  np.array([v.size]))
                    zonal["sem"][i], zonal["ci95_lo"][i], zonal["ci95_hi"][i] = \
                        float(se[0]), float(lo[0]), float(hi[0])
        out["overall"] = {"mean": float(vals[:, 2].mean()),
                          "median": float(np.median(vals[:, 2]))}
    out.update(mean=mean, count=count, zonal=zonal)
    return out


# ---------------------------------------------------------------------------
# atmPrf and wetPf2 of the same occultations
# ---------------------------------------------------------------------------

# What can be compared between an atmPrf and the wetPf2 retrieved from it:
# (variable in atmPrf or None, variable in wetPf2, relative?, label, units).
PAIR_QUANTITIES = {
    "refractivity": ("Ref", "ref", True,
                     "Refractivity, atmPrf (observed) minus wetPf2 (1D-Var analysis)", "%"),
    "dry_temperature": ("Temp", "temp_dry", False,
                        "Dry temperature, atmPrf minus wetPf2", "K"),
    "dry_pressure": ("Pres", "pres_dry", True,
                     "Dry pressure, atmPrf minus wetPf2", "%"),
    "moisture_effect": (None, "Temp", False,
                        "Temperature minus dry temperature (wetPf2)", "K"),
}


def pair_rows(selected: Sequence[dict], atm_rows: Sequence[dict],
              wet_rows: Sequence[dict], good_only: bool = True) -> list[tuple[dict, dict]]:
    """``(atmPrf row, wetPf2 row)`` for the occultations in ``selected``.

    Each wetPf2 file names the atmPrf it was retrieved from (``source_atmPrf``),
    so the pairing is exact, not a colocation.  A selected wetPf2 brings its
    atmPrf and a selected atmPrf its wetPf2, when the other file is in the
    index; each pair counts once."""
    atm_by_name = {r.get("file_name"): r for r in atm_rows}
    wet_by_src = {}
    for w in wet_rows:
        src = (w.get("extras") or {}).get("source_atmPrf")
        if src:
            wet_by_src[src] = w
    pairs, seen = [], set()
    for r in selected:
        if r.get("product") == "wetPf2":
            a, w = atm_by_name.get((r.get("extras") or {}).get("source_atmPrf")), r
        elif r.get("product") == "atmPrf":
            a, w = r, wet_by_src.get(r.get("file_name"))
        else:
            continue
        if a is None or w is None or a.get("file_name") in seen:
            continue
        if good_only and not (a.get("good", True) and w.get("good", True)):
            continue
        seen.add(a.get("file_name"))
        pairs.append((a, w))
    return pairs


def _pair_column(task: tuple):
    """The difference of one pair on the grid, or None.  Module-level so it
    runs on the worker processes."""
    from . import readers
    from .analysis import interp_field
    a_row, w_row, quantity, grid = task
    va, vw, relative, _, _ = PAIR_QUANTITIES[quantity]
    try:
        gw = readers.load(w_row["path"], "wetPf2")
        wcol = interp_field(gw.data["MSL_alt"], gw.data[vw], grid, vw, max_gap=2.0)
        if va is None:          # within the wetPf2: moist minus dry temperature
            other = interp_field(gw.data["MSL_alt"], gw.data["temp_dry"], grid, "temp_dry", max_gap=2.0)
            return w_row.get("lat"), wcol - other
        ga = readers.load(a_row["path"], "atmPrf")
        acol = interp_field(ga.data["MSL_alt"], ga.data[va], grid, va, max_gap=2.0)
    except Exception:  # noqa: BLE001 - an unreadable file drops the pair
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        diff = 100.0 * (acol - wcol) / wcol if relative else acol - wcol
    return a_row.get("lat"), diff


def product_differences(pairs: Sequence[tuple[dict, dict]], quantity: str = "refractivity",
                        top_km: float = 30.0, step_km: float = 0.5, bottom_km: float = 0.0,
                        min_count: int = 3, workers: int | None = None) -> dict:
    """Differences between the atmPrf and the wetPf2 of the same occultations,
    by height above mean sea level: mean, median, standard deviation, count,
    standard error and 95 % confidence interval of the mean at each level.

    atmPrf holds the observed (dry) retrieval and wetPf2 the 1D-Var moist
    retrieval made from it, so the refractivity difference is the 1D-Var
    analysis' departure from the observation, and the dry temperature and
    pressure differences check that both files carry the same dry retrieval.
    ``moisture_effect`` is wetPf2's temperature minus its dry temperature:
    how far water vapour makes the dry temperature wrong."""
    from .analysis import column_stats, make_grid
    from .parallel import pmap
    if quantity not in PAIR_QUANTITIES:
        raise ValueError(f"quantity must be one of {', '.join(PAIR_QUANTITIES)}")
    grid = make_grid(top_km, step_km, bottom_km)
    res = [r for r in pmap(_pair_column, [(a, w, quantity, grid) for a, w in pairs],
                           workers=workers) if r is not None]
    _, _, relative, label, units = PAIR_QUANTITIES[quantity]
    out = {"quantity": quantity, "label": label, "units": units, "relative": relative,
           "grid": grid.tolist(), "n_pairs": len(res), "min_count": min_count}
    if not res:
        return {**out, **{k: [] for k in ("mean", "median", "std", "n", "sem", "ci95_lo", "ci95_hi")}}
    out.update(column_stats(np.vstack([d for _, d in res]), min_count))
    return out


# ---------------------------------------------------------------------------
# tropopause and cold point by latitude
# ---------------------------------------------------------------------------

TROPOPAUSE_COLUMNS = {
    "wmo_height_km": "tropopause.height_km",
    "wmo_temp_K": "tropopause.temp_K",
    "cp_height_km": "cold_point.height_km",
    "cp_temp_K": "cold_point.temp_K",
}
# CDAAC's own values in atmPrf files (index extras), for comparison
ARCHIVE_TROPOPAUSE = {
    "wmo_height_km": ("tropopause_height_wmo_km", 0.0),
    "wmo_temp_K": ("tropopause_temp_wmo_C", 273.15),
    "cp_height_km": ("cold_point_height_km", 0.0),
    "cp_temp_K": ("cold_point_temp_C", 273.15),
}


def _band_stats(values: Sequence[float], min_count: int) -> dict:
    from .analysis import mean_uncertainty
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], float)
    out = {"n": int(v.size), "mean": None, "ci95_lo": None, "ci95_hi": None,
           "median": None, "std": None}
    if v.size >= max(min_count, 1):
        out["mean"], out["median"] = float(v.mean()), float(np.median(v))
        if v.size > 1:
            sd = float(v.std(ddof=1))
            _, lo, hi = mean_uncertainty(np.array([v.mean()]), np.array([sd]), np.array([v.size]))
            out.update(std=sd, ci95_lo=float(lo[0]), ci95_hi=float(hi[0]))
    return out


def tropopause_table(rows: Sequence[dict], lat_step: float = 10.0, min_count: int = 3,
                     workers: int | None = None) -> dict:
    """WMO (lapse-rate) tropopause and cold point by latitude band: mean,
    95 % confidence interval of the mean, median, standard deviation and count
    of the height and temperature, from the per-profile diagnostics of the
    good neutral profiles in ``rows``; for atmPrf, CDAAC's own values from the
    same files beside them.  The cold point is the coldest level between 10
    and 30 km, which is a tropopause in the tropics only."""
    from .analysis import diagnostics_row
    from .parallel import pmap
    if not lat_step > 0:
        raise ValueError("lat_step must be > 0")
    good = [r for r in rows if r.get("product") in ("atmPrf", "wetPf2") and r.get("good", True)
            and r.get("lat") is not None]
    # CDAAC's columns still come from every atmPrf file
    diag = once_per_occultation(good, pmap(diagnostics_row, good, workers=workers))
    edges = np.arange(-90.0, 90.0 + lat_step / 2, lat_step)
    bands = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = [d for d in diag if d.get("lat") is not None and lo <= d["lat"] < hi]
        if not sel:
            continue
        band = {"lat_lo": float(lo), "lat_hi": float(hi), "n_profiles": len(sel)}
        for key, col in TROPOPAUSE_COLUMNS.items():
            band[key] = _band_stats([d.get(col) for d in sel], min_count)
        arch = [r for r in good if r.get("product") == "atmPrf" and lo <= r["lat"] < hi]
        if arch:
            band["archive"] = {}
            for key, (name, off) in ARCHIVE_TROPOPAUSE.items():
                vals = [(r.get("extras") or {}).get(name) for r in arch]
                band["archive"][key] = _band_stats(
                    [v + off for v in vals if isinstance(v, (int, float)) and v > -900], min_count)
        bands.append(band)
    products = sorted({r["product"] for r in good})
    return {"lat_step": lat_step, "min_count": min_count, "n_profiles": len(diag),
            "products": products, "bands": bands}
