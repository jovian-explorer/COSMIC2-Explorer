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
