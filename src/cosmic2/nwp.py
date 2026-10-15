"""Radio occultation against the weather models CDAAC colocates with it, and
error estimates by the three-cornered hat.

For every occultation CDAAC publishes the ECMWF fields colocated along its
path (echPrf) and the NCEP fields interpolated the same way (avnPrf), named
with the occultation's file stamp, so an atmPrf, its wetPf2 and the two
model profiles pair exactly.

``model_differences``
    RO minus each model by height: refractivity (atmPrf, in percent of the
    model value) or temperature (wetPf2's 1D-Var temperature, in K).

``three_cornered_hat``
    With three estimates X, Y, Z of the same quantity whose errors are
    independent, the variance of each pairwise difference is the sum of the
    two error variances, so

        sigma_X^2 = (var(X - Y) + var(X - Z) - var(Y - Z)) / 2

    and likewise for Y and Z (Anthes and Rieckh 2018; Rieckh et al. 2021,
    J. Atmos. Oceanic Technol., 38, doi:10.1175/JTECH-D-20-0209.1).
    Here X = RO refractivity (atmPrf), Y = ECMWF, Z = NCEP, in percent of the
    mean of the three.  The 95 % intervals come from resampling the
    occultations (bootstrap).  Correlated errors bias the estimates: with
    covariances c, the RO estimate is sigma_RO^2 - c(RO,ECMWF) - c(RO,NCEP)
    + c(ECMWF,NCEP).  Both models assimilate COSMIC-2 and largely the same other
    observations, so neither term is zero; the estimates are "apparent" errors,
    which also include representativeness differences (the models' coarser
    footprint).
"""
from __future__ import annotations

import re
from typing import Sequence

import numpy as np

MODELS = {"echPrf": "ECMWF", "avnPrf": "NCEP"}

# quantity -> (RO product, RO variable, model variable, relative?, label, units)
QUANTITIES = {
    "refractivity": ("atmPrf", "Ref", "Ref", True, "Refractivity, RO (atmPrf) minus model", "%"),
    "temperature": ("wetPf2", "Temp", "Temp", False, "Temperature, RO (wetPf2) minus model", "K"),
    "refractivity_1dvar": ("wetPf2", "ref", "Ref", True,
                           "Refractivity, RO (wetPf2 1D-Var) minus model", "%"),
    "bending_angle": ("atmPrf", "Bend_ang", "Bend_ang", True,
                      "Bending angle, RO (atmPrf) minus ECMWF", "%"),
}


def model_impact_height(z_km: np.ndarray, ref: np.ndarray, rc_km: float) -> np.ndarray:
    """Impact height above mean sea level of a ray whose tangent point is at
    ``z_km`` where the refractivity is ``ref``: n (Rc + z) - Rc, with Rc the
    occultation's local radius of curvature (atmPrf attribute ``rfict``).

    atmPrf's own Impact_height follows exactly this relation (checked on 300
    real profiles: median difference 0.0000 km), and echPrf's simulated
    bending angles belong to their levels' tangent points: compared on these
    impact heights, RO minus ECMWF bending angle is within 0.15 % from 10 to
    35 km on the 2026 sample, while taking MSL_alt as the impact height gives
    offsets of +0.3 % to +23 %."""
    return (1.0 + 1e-6 * np.asarray(ref, float)) * (rc_km + np.asarray(z_km, float)) - rc_km


def _bending_columns(task: tuple):
    """RO (atmPrf) and ECMWF (echPrf) bending angles of one occultation on a
    grid of impact heights.  Module-level so it runs on the worker processes."""
    from . import readers
    from .analysis import interp_to_grid
    group, grid = task
    if "atmPrf" not in group or "echPrf" not in group:
        return None
    try:
        a = readers.load(group["atmPrf"]["path"], "atmPrf")
        e = readers.load(group["echPrf"]["path"], "echPrf")
        rc = float(a.attrs["rfict"])
        ro = interp_to_grid(a.data["Impact_height"], a.data["Bend_ang"], grid, max_gap=3.0, log=True)
        x = model_impact_height(e.data["MSL_alt"], e.data["Ref"], rc)
        ec = interp_to_grid(x, e.data["Bend_ang"], grid, max_gap=3.0, log=True)
    except Exception:  # noqa: BLE001 - an unreadable or incomplete file drops the pair
        return None
    return {"atmPrf": ro, "echPrf": ec}


def stamp_groups(selected: Sequence[dict], index_rows: Sequence[dict],
                 good_only: bool = True) -> list[dict[str, dict]]:
    """``{product: index row}`` for each occultation of ``selected`` (any of
    atmPrf, wetPf2, echPrf, avnPrf), gathered from ``index_rows`` by the file
    stamp the four share.  Each occultation counts once."""
    by_stamp: dict[str, dict[str, dict]] = {}
    for r in index_rows:
        st = r.get("stamp")
        if not st or r.get("product") not in ("atmPrf", "wetPf2", "echPrf", "avnPrf"):
            continue
        if good_only and not r.get("good", True):
            continue
        by_stamp.setdefault(st, {})[r["product"]] = r
    out, seen = [], set()
    for r in selected:
        st = r.get("stamp")
        # the selected profile itself must have passed the quality filter
        if not st or st in seen or r.get("product") not in by_stamp.get(st, {}):
            continue
        seen.add(st)
        out.append(by_stamp[st])
    return out


# CDAAC's post-processed echPrf of October 2021 were interpolated from ECMWF
# analysis files (ecmAnc) whose refractivity is about 0.35 % above the
# occultations', ERA5's and GFS's.  Metop-A/B/C minus echPrf, 10-30 km:
# -0.30 to -0.38 % on 2021-10-01 to 10-31, within 0.06 % on 09-15 to 09-29
# and 11-01 to 11-10; minus ERA5 (er5Prf) and GFS (gfsPrf) of the same
# occultations within 0.1 % throughout.  PAZ and KOMPSAT-5 post-processed
# files show the same (PAZ on 2021-10-05 and 10-27, KOMPSAT-5 on 10-05,
# 10-15 and 10-27): -0.28 to -0.42 % against echPrf, -0.07 to +0.03 %
# against ERA5.  The near-real-time echPrf use
# forecast files (ecmFcc) and are not affected.
_ECM_OCT_2021 = re.compile(r"ecmAnc_2021\.(27[4-9]|28\d|29\d|30[0-4])\.")


def october_2021_echprf(groups: Sequence[dict[str, dict]]) -> int:
    """How many occultations of ``groups`` have one of those echPrf."""
    return sum(1 for g in groups if "echPrf" in g and _ECM_OCT_2021.match(
        str((g["echPrf"].get("extras") or {}).get("model_file_1") or "")))


def _columns(task: tuple):
    """The gridded columns of one occultation, ``{product: column}``.
    Module-level so it runs on the worker processes."""
    from . import readers
    from .analysis import interp_field
    group, wanted, grid, max_gap = task
    cols = {}
    for prod, var in wanted.items():
        row = group.get(prod)
        if row is None:
            continue
        try:
            g = readers.load(row["path"], prod)
            if var not in g.data or "MSL_alt" not in g.data:
                continue
            cols[prod] = interp_field(g.data["MSL_alt"], g.data[var], grid, var, max_gap=max_gap)
        except Exception:  # noqa: BLE001 - an unreadable file drops that product
            continue
    return cols or None


def _gridded(groups, wanted, grid, max_gap, workers):
    from .parallel import pmap
    return [c for c in pmap(_columns, [(g, wanted, grid, max_gap) for g in groups],
                            workers=workers) if c]


def model_differences(groups: Sequence[dict[str, dict]], quantity: str = "refractivity",
                      top_km: float = 30.0, step_km: float = 0.5, bottom_km: float = 0.0,
                      min_count: int = 3, workers: int | None = None) -> dict:
    """RO minus ECMWF and RO minus NCEP by height: mean, median, standard
    deviation, count, standard error and 95 % confidence interval of the mean."""
    from .analysis import column_stats, make_grid
    if quantity not in QUANTITIES:
        raise ValueError(f"quantity must be one of {', '.join(QUANTITIES)}")
    from .parallel import pmap
    ro_prod, ro_var, m_var, relative, label, units = QUANTITIES[quantity]
    grid = make_grid(top_km, step_km, bottom_km)
    if quantity == "bending_angle":
        # ECMWF only (avnPrf carries no bending angle), on impact heights
        models = {"echPrf": MODELS["echPrf"]}
        cols = [c for c in pmap(_bending_columns, [(g, grid) for g in groups], workers=workers) if c]
        vertical_label = "Impact height above mean sea level [km]"
    else:
        models = MODELS
        wanted = {ro_prod: ro_var, **{m: m_var for m in MODELS}}
        cols = _gridded(groups, wanted, grid, 3.0, workers)
        vertical_label = "Altitude above mean sea level [km]"
    out = {"quantity": quantity, "label": label, "units": units, "relative": relative,
           "grid": grid.tolist(), "min_count": min_count, "models": {},
           "vertical_label": vertical_label}
    for model, name in models.items():
        diffs = []
        for c in cols:
            if ro_prod in c and model in c:
                with np.errstate(invalid="ignore", divide="ignore"):
                    d = c[ro_prod] - c[model]
                    diffs.append(100.0 * d / c[model] if relative else d)
        st = {"name": name, "n_profiles": len(diffs)}
        if diffs:
            st.update(column_stats(np.vstack(diffs), min_count))
        out["models"][model] = st
    out["n_profiles"] = max((v["n_profiles"] for v in out["models"].values()), default=0)
    return out


def tch_variances(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Three-cornered-hat error variances ``[3, levels]`` of three datasets
    ``[profiles, levels]`` (NaN where a value is missing: each level uses the
    profiles that have all three)."""
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)

    def v(a, b):
        d = np.where(ok, a - b, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            n = ok.sum(axis=0)
            mu = np.nansum(d, axis=0) / np.where(n > 0, n, np.nan)
            return np.nansum((d - mu) ** 2, axis=0) / np.where(n > 1, n - 1, np.nan)
    vxy, vxz, vyz = v(x, y), v(x, z), v(y, z)
    return np.vstack([(vxy + vxz - vyz) / 2, (vxy + vyz - vxz) / 2, (vxz + vyz - vxy) / 2])


def three_cornered_hat(groups: Sequence[dict[str, dict]], top_km: float = 30.0,
                       step_km: float = 0.5, bottom_km: float = 0.0, min_count: int = 30,
                       n_boot: int = 200, seed: int = 0, workers: int | None = None) -> dict:
    """Refractivity error variances (in %^2 of the mean of the three) of RO,
    ECMWF and NCEP by height, with bootstrap 95 % intervals; levels with fewer
    than ``min_count`` complete triplets are blank.  See the module docstring
    for the method and its assumptions."""
    from .analysis import make_grid
    grid = make_grid(top_km, step_km, bottom_km)
    names = ["atmPrf", "echPrf", "avnPrf"]
    cols = [c for c in _gridded(groups, {p: "Ref" for p in names}, grid, 3.0, workers)
            if all(p in c for p in names)]
    out = {"grid": grid.tolist(), "n_triplets": len(cols), "min_count": min_count,
           "datasets": ["RO (atmPrf)", "ECMWF (echPrf)", "NCEP (avnPrf)"], "units": "%^2",
           "n_boot": n_boot}
    if not cols:
        return {**out, "n": [], "variance": [], "lo": [], "hi": [], "std_pct": []}
    x, y, z = (np.vstack([c[p] for c in cols]) for p in names)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean3 = (x + y + z) / 3.0
        x, y, z = (100.0 * a / mean3 for a in (x, y, z))
    n = (np.isfinite(x) & np.isfinite(y) & np.isfinite(z)).sum(axis=0)
    var = tch_variances(x, y, z)
    rng = np.random.default_rng(seed)
    boots = np.empty((n_boot,) + var.shape)
    for b in range(n_boot):
        i = rng.integers(0, x.shape[0], x.shape[0])
        boots[b] = tch_variances(x[i], y[i], z[i])
    from .climatology import warnings_off
    with np.errstate(invalid="ignore"), warnings_off():      # empty levels: all-NaN slices
        lo = np.nanpercentile(boots, 2.5, axis=0)
        hi = np.nanpercentile(boots, 97.5, axis=0)
    thin = n < min_count
    for a in (var, lo, hi):
        a[:, thin] = np.nan
    with np.errstate(invalid="ignore"):
        std = np.where(var >= 0, np.sqrt(np.abs(var)), np.nan)
    out.update(n=n, variance=var, lo=lo, hi=hi, std_pct=std)
    return out


# echPrf's ducting diagnosis of the ECMWF profile (variable ductid)
DUCT_CLASSES = {0: "no duct", 1: "elevated duct", 2: "surface duct (two break points)",
                3: "surface duct (one break point)"}


def _duct_columns(task: tuple):
    """``(ductid, RO minus ECMWF refractivity in % on the grid, the same on
    heights relative to the duct or None)`` of one occultation.  Module-level
    so it runs on the worker processes."""
    from . import readers
    from .analysis import interp_field
    group, grid, rel = task
    if "atmPrf" not in group or "echPrf" not in group:
        return None
    try:
        a = readers.load(group["atmPrf"]["path"], "atmPrf").data
        e = readers.load(group["echPrf"]["path"], "echPrf").data
        duct = int(np.asarray(e["ductid"], float).ravel()[0])
        zsr = float(np.asarray(e["zsr"], float).ravel()[0])
    except Exception:  # noqa: BLE001 - an unreadable pair drops the occultation
        return None
    if duct not in DUCT_CLASSES:
        return None

    def diff(z):
        ro = interp_field(a["MSL_alt"], a["Ref"], z, "Ref", max_gap=3.0)
        m = interp_field(e["MSL_alt"], e["Ref"], z, "Ref", max_gap=3.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            return 100.0 * (ro - m) / m
    around = diff(zsr + rel) if duct > 0 and np.isfinite(zsr) and zsr > 0 else None
    return duct, diff(grid), around


def ducting_differences(groups: Sequence[dict[str, dict]], top_km: float = 6.0,
                        step_km: float = 0.1, bottom_km: float = 0.0,
                        around_duct: bool = False, half_width_km: float = 2.0,
                        min_count: int = 3, workers: int | None = None) -> dict:
    """RO (atmPrf) minus ECMWF refractivity, in percent of ECMWF, for the
    occultations where ECMWF diagnoses a duct (echPrf ``ductid`` 1-3) and
    where it does not; with ``around_duct`` by height relative to the centre
    of ECMWF's super-refraction layer (echPrf ``zsr``), duct cases only.

    In a duct the refractivity gradient is below about -157 N-units/km, rays
    are trapped and the Abel inversion has no unique solution: the retrieved
    refractivity is too low below the duct and its gradient never reaches
    the critical value (Sokolovskiy 2003; Xie et al. 2012,
    doi:10.5194/acp-12-903-2012; Feng et al. 2020, J. Atmos. Oceanic
    Technol., 37, 1013-1025, doi:10.1175/JTECH-D-19-0206.1).  On 952 COSMIC-2
    and PAZ occultations of 2026-06-20 and 09-30 ECMWF diagnosed a duct at
    183: there RO minus ECMWF was -4.2 % at 1 km (-1.4 % without a duct) and
    -8.4 % 0.2 km below the duct centre, back to +0.3 % 0.2 km above it."""
    from .analysis import column_stats, make_grid
    from .parallel import pmap
    grid = make_grid(top_km, step_km, bottom_km)
    rel = make_grid(half_width_km, step_km, -half_width_km)
    cols = [c for c in pmap(_duct_columns, [(g, grid, rel) for g in groups], workers=workers) if c]
    classes = {str(k): sum(1 for c in cols if c[0] == k) for k in DUCT_CLASSES}
    n_duct = sum(1 for c in cols if c[0] > 0)
    out = {"quantity": "refractivity", "units": "%", "relative": True, "min_count": min_count,
           "n_profiles": len(cols), "n_duct": n_duct, "duct_classes": classes,
           "around_duct": around_duct, "models": {}}
    if around_duct:
        sets = {"duct": ("ECMWF, around its duct", [c[2] for c in cols if c[2] is not None])}
        out.update(grid=rel.tolist(), label="Refractivity, RO (atmPrf) minus ECMWF",
                   vertical_label="Height above the centre of ECMWF's duct [km]")
    else:
        sets = {"no_duct": ("ECMWF, no duct", [c[1] for c in cols if c[0] == 0]),
                "duct": ("ECMWF, duct", [c[1] for c in cols if c[0] > 0])}
        out.update(grid=grid.tolist(), label="Refractivity, RO (atmPrf) minus ECMWF",
                   vertical_label="Altitude above mean sea level [km]")
    for key, (name, diffs) in sets.items():
        st = {"name": name, "n_profiles": len(diffs)}
        if diffs:
            st.update(column_stats(np.vstack(diffs), min_count))
        out["models"][key] = st
    return out
