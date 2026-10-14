"""COSMIC-2 against another radio occultation mission (PAZ, KOMPSAT-5).

CDAAC processes PAZ and KOMPSAT-5 into the same atmPrf, wetPf2 and echPrf
files as COSMIC-2 (the ``paz-nrt`` and ``kompsat5-nrt`` streams).  Two
independent estimates of how the missions differ:

``collocated``
    Each profile of the other mission is paired with the COSMIC-2 profile
    nearest in the normalised distance

        D = w_t |dt| / max_hours + (1 - w_t) d / max_km,   w_t = 0.75,

    among those within ``max_km`` and ``max_hours`` (Rieckh et al. 2021,
    J. Atmos. Oceanic Technol., doi:10.1175/JTECH-D-20-0209.1, appendix A,
    weights time 0.75 and distance 0.25 for 3 h and 300 km); each COSMIC-2
    profile is used at most once.  The differences COSMIC-2 minus the other
    mission are summarised by height.  Their spread includes the atmosphere's
    own variability over the collocation window; ``corrected`` subtracts
    from each pair ECMWF's difference between its two occultations (their
    echPrf), which removes the part of that mismatch the model resolves
    (Gilpin et al. 2018, Atmos. Meas. Tech., doi:10.5194/amt-11-2567-2018).

``via_ecmwf``
    The double difference mean(COSMIC-2 - ECMWF) - mean(other - ECMWF) over
    the profiles of each mission within the latitudes both cover, with the
    ECMWF profile CDAAC colocates with every occultation (echPrf).  It needs
    no collocation, so it uses many more profiles, but the two missions
    still sample different places and times within those latitudes.

Missions are told apart by the satellite code in the file names (C2E1-C2E6,
PAZ1, KOM5), so files imported by hand count too.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .catalog import MISSION_SATS

MISSION_NAMES = {"cosmic2": "COSMIC-2", "paz": "PAZ", "kompsat5": "KOMPSAT-5",
                 "metopb": "Metop-B", "metopc": "Metop-C", "cosmic1": "COSMIC-1"}

# quantity -> (product, variable, relative?, vertical, label, units, nwp quantity)
QUANTITIES = {
    "temperature": ("wetPf2", "Temp", False, "MSL_alt", "Temperature (wetPf2)", "K", "temperature"),
    "refractivity_1dvar": ("wetPf2", "ref", True, "MSL_alt", "Refractivity (wetPf2, 1D-Var)", "%",
                           "refractivity_1dvar"),
    "refractivity": ("atmPrf", "Ref", True, "MSL_alt", "Refractivity (atmPrf, observed)", "%",
                     "refractivity"),
}


def mission_of_sat(sat: str | None) -> str | None:
    s = (sat or "").upper()
    # LEO001-LEO006: COSMIC-2 scintillation files indexed before they were
    # named C2E1-C2E6
    if s.startswith("C2E") or s.startswith("LEO"):
        return "cosmic2"
    for mission, sats in MISSION_SATS.items():
        if s in sats:
            return mission
    return None


def collocate(ref_rows: Sequence[dict], other_rows: Sequence[dict], max_km: float = 300.0,
              max_hours: float = 3.0, w_time: float = 0.75) -> list[tuple[dict, dict, float, float]]:
    """``(COSMIC-2 row, other row, distance km, |dt| h)`` pairs, one to one,
    best normalised distance first."""
    from .radiosonde import great_circle_km
    ref = [r for r in ref_rows if r.get("lat") is not None and r.get("lon") is not None
           and r.get("epoch") is not None]
    if not ref:
        return []
    lat = np.array([r["lat"] for r in ref], float)
    lon = np.array([r["lon"] for r in ref], float)
    ep = np.array([r["epoch"] for r in ref], float)
    cand = []
    for j, o in enumerate(other_rows):
        if o.get("lat") is None or o.get("lon") is None or o.get("epoch") is None:
            continue
        # cheap prefilter on time and latitude before the great circle
        near = np.flatnonzero((np.abs(ep - o["epoch"]) <= max_hours * 3600.0)
                              & (np.abs(lat - o["lat"]) <= max_km / 111.0 + 0.1))
        if not near.size:
            continue
        d = great_circle_km(o["lat"], o["lon"], lat[near], lon[near])
        dt = np.abs(ep[near] - o["epoch"]) / 3600.0
        for k in np.flatnonzero(d <= max_km):
            score = w_time * dt[k] / max_hours + (1 - w_time) * d[k] / max_km
            cand.append((float(score), j, int(near[k]), float(d[k]), float(dt[k])))
    cand.sort()
    used_ref, used_other, pairs = set(), set(), []
    for _, j, i, d, dt in cand:
        if i in used_ref or j in used_other:
            continue
        used_ref.add(i)
        used_other.add(j)
        pairs.append((ref[i], other_rows[j], d, dt))
    return pairs


def _pair_diff(task: tuple):
    """One pair's gridded difference (COSMIC-2 minus other), and the same
    minus ECMWF's difference between the two occultations when both echPrf
    rows are given (else None).  Module-level so it runs on the worker
    processes."""
    from . import nwp, readers
    from .analysis import interp_field
    a_row, o_row, quantity, grid, ech_rows = task
    prod, var, relative, vert, _, _, nwp_q = QUANTITIES[quantity]
    try:
        cols = []
        for row in (a_row, o_row):
            g = readers.load(row["path"], prod)
            cols.append(interp_field(g.data[vert], g.data[var], grid, var, max_gap=3.0))
    except Exception:  # noqa: BLE001 - an unreadable file drops the pair
        return None
    a, o = cols
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = 100.0 * (a - o) / o if relative else a - o
    corrected = None
    if all(ech_rows):
        m_var = nwp.QUANTITIES[nwp_q][2]
        try:
            ma, mo = (interp_field(h.data["MSL_alt"], h.data[m_var], grid, m_var, max_gap=3.0)
                      for h in (readers.load(r["path"], "echPrf") for r in ech_rows))
            with np.errstate(invalid="ignore", divide="ignore"):
                # (COSMIC-2 - its ECMWF) - (other - its ECMWF), like the
                # double difference through ECMWF
                corrected = (100.0 * ((a - ma) / ma - (o - mo) / mo) if relative
                             else (a - ma) - (o - mo))
        except Exception:  # noqa: BLE001 - the raw difference still counts
            corrected = None
    return raw, corrected


def compare(rows: Sequence[dict], index_rows: Sequence[dict], other: str = "paz",
            quantity: str = "temperature", max_km: float = 300.0, max_hours: float = 3.0,
            top_km: float = 30.0, step_km: float = 0.5, bottom_km: float = 0.0,
            min_count: int = 3, workers: int | None = None) -> dict:
    """COSMIC-2 minus ``other`` by height: collocated pairs, and the double
    difference through ECMWF.  ``rows`` are the profiles to use (both missions,
    the quantity's product); ``index_rows`` the index rows used to find each
    profile's echPrf."""
    from . import nwp
    from .analysis import column_stats, make_grid
    from .parallel import pmap
    if quantity not in QUANTITIES:
        raise ValueError(f"quantity must be one of {', '.join(QUANTITIES)}")
    if other not in MISSION_SATS:
        raise ValueError(f"other must be one of {', '.join(MISSION_SATS)}")
    prod, var, relative, vert, label, units, nwp_q = QUANTITIES[quantity]
    grid = make_grid(top_km, step_km, bottom_km)
    use = [r for r in rows if r.get("product") == prod and r.get("good", True)]
    ref_rows = [r for r in use if mission_of_sat(r.get("sat")) == "cosmic2"]
    oth_rows = [r for r in use if mission_of_sat(r.get("sat")) == other]
    out = {"quantity": quantity, "label": label, "units": units, "relative": relative,
           "other": other, "other_name": MISSION_NAMES[other], "grid": grid.tolist(),
           "min_count": min_count, "max_km": max_km, "max_hours": max_hours,
           "n_cosmic2": len(ref_rows), "n_other": len(oth_rows)}
    pairs = collocate(ref_rows, oth_rows, max_km, max_hours)
    ech = {r["stamp"]: r for r in index_rows
           if r.get("product") == "echPrf" and r.get("good", True) and r.get("stamp")}
    tasks = [(a, o, quantity, grid, (ech.get(a.get("stamp")), ech.get(o.get("stamp"))))
             for a, o, _, _ in pairs]
    done = [d for d in pmap(_pair_diff, tasks, workers=workers) if d is not None]
    diffs = [raw for raw, _ in done]
    corrected = [c for _, c in done if c is not None]
    col = {"n_pairs": len(diffs)}
    if pairs:
        col.update(median_km=float(np.median([p[2] for p in pairs])),
                   median_hours=float(np.median([p[3] for p in pairs])))
    if diffs:
        col.update(column_stats(np.vstack(diffs), min_count))
    # The pair difference minus ECMWF's difference between the two
    # occultations: removes the part of the collocation mismatch the model
    # resolves (the sampling correction of Gilpin et al. 2018,
    # doi:10.5194/amt-11-2567-2018).  On 14 days of 2026 (817 PAZ pairs) it
    # took the 28-31 km temperature difference from +0.19..+0.28 K to
    # +0.02..+0.21 K, and the spread of the pair differences from 1.56 to
    # 1.30 K at 29.5 km and from 1.16 to 0.74 K at 10 km.
    col["corrected"] = {"n_pairs": len(corrected)}
    if corrected:
        col["corrected"].update(column_stats(np.vstack(corrected), min_count))
    out["collocated"] = col
    # double difference through ECMWF (no collocation), over the latitudes
    # both missions cover: COSMIC-2 reaches about 45 degrees, PAZ and
    # KOMPSAT-5 the poles, and RO minus ECMWF changes with latitude (on 14
    # whole days of 2026, COSMIC-2 minus PAZ was +0.09 K at 10 km with every
    # PAZ profile and +0.05 K over the common latitudes, as with 10-degree
    # strata)
    via = {"available": False}
    common = [[r for r in sel if r.get("lat") is not None] for sel in (ref_rows, oth_rows)]
    if all(common):
        lo = max(min(r["lat"] for r in sel) for sel in common)
        hi = min(max(r["lat"] for r in sel) for sel in common)
        via["lat_range"] = [lo, hi]
        common = [[r for r in sel if lo <= r["lat"] <= hi] for sel in common]
    sides = []
    for sel in common:
        groups = nwp.stamp_groups(sel, index_rows)
        sides.append(nwp.model_differences(groups, nwp_q, top_km=top_km, step_km=step_km,
                                           bottom_km=bottom_km, min_count=min_count,
                                           workers=workers)["models"].get("echPrf", {}))
    if all(s.get("n_profiles") for s in sides):
        a, b = sides
        with np.errstate(invalid="ignore"):
            dd = np.asarray(a["mean"], float) - np.asarray(b["mean"], float)
            se = np.sqrt(np.asarray(a["sem"], float) ** 2 + np.asarray(b["sem"], float) ** 2)
        via.update(available=True, n_cosmic2=a["n_profiles"], n_other=b["n_profiles"],
                   mean=dd, ci95_lo=dd - 1.96 * se, ci95_hi=dd + 1.96 * se)
    out["via_ecmwf"] = via
    return out
