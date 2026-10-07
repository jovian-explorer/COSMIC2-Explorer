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

from typing import Sequence

import numpy as np

MODELS = {"echPrf": "ECMWF", "avnPrf": "NCEP"}

# quantity -> (RO product, RO variable, model variable, relative?, label, units)
QUANTITIES = {
    "refractivity": ("atmPrf", "Ref", "Ref", True, "Refractivity, RO (atmPrf) minus model", "%"),
    "temperature": ("wetPf2", "Temp", "Temp", False, "Temperature, RO (wetPf2) minus model", "K"),
}


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
    from .analysis import make_grid, mean_uncertainty
    from .climatology import warnings_off
    if quantity not in QUANTITIES:
        raise ValueError(f"quantity must be one of {', '.join(QUANTITIES)}")
    ro_prod, ro_var, m_var, relative, label, units = QUANTITIES[quantity]
    grid = make_grid(top_km, step_km, bottom_km)
    wanted = {ro_prod: ro_var, **{m: m_var for m in MODELS}}
    cols = _gridded(groups, wanted, grid, 3.0, workers)
    out = {"quantity": quantity, "label": label, "units": units, "relative": relative,
           "grid": grid.tolist(), "min_count": min_count, "models": {}}
    for model, name in MODELS.items():
        diffs = []
        for c in cols:
            if ro_prod in c and model in c:
                with np.errstate(invalid="ignore", divide="ignore"):
                    d = c[ro_prod] - c[model]
                    diffs.append(100.0 * d / c[model] if relative else d)
        st = {"name": name, "n_profiles": len(diffs)}
        if diffs:
            m = np.vstack(diffs)
            with np.errstate(invalid="ignore", divide="ignore"), warnings_off():
                n = np.isfinite(m).sum(axis=0)
                mean, median = np.nanmean(m, axis=0), np.nanmedian(m, axis=0)
                std = np.nanstd(m, axis=0, ddof=1)
            sem, lo, hi = mean_uncertainty(mean, std, n)
            for a in (mean, median, std, sem, lo, hi):
                a[n < min_count] = np.nan
            st.update(mean=mean, median=median, std=std, n=n, sem=sem, ci95_lo=lo, ci95_hi=hi)
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
