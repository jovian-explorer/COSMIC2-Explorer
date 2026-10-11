"""Scientific processing pipeline for COSMIC-2 data.

Handles configurable outlier removal, smoothing/filtering, uncertainty
estimation, and tracks data provenance at every step.
"""
import datetime
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from .config import APP_VERSION

@dataclass
class ProvenanceRecord:
    timestamp: str
    operation: str
    parameters: dict
    software_version: str = APP_VERSION

@dataclass
class ProcessedProfile:
    z: np.ndarray
    original_v: np.ndarray
    v: np.ndarray
    uncertainty: Optional[np.ndarray] = None
    mask: np.ndarray = None # True for valid data
    provenance: List[ProvenanceRecord] = field(default_factory=list)

    def __post_init__(self):
        if self.mask is None:
            self.mask = np.ones_like(self.v, dtype=bool)

# Levels in the running median that outliers are measured from
OUTLIER_WINDOW = 21


def remove_outliers(profile: ProcessedProfile, method: str, threshold: float = 3.0, **kwargs) -> dict:
    """Configurable outlier removal.
    Methods: sigma, mad, iqr, percentile, none

    Each level is tested against the ``OUTLIER_WINDOW - 1`` levels around it
    (the logarithm when every value is positive, so relative): sigma against
    their mean and standard deviation, mad against their median and median
    absolute deviation (a Hampel filter), iqr against their quartiles;
    percentile drops the extreme departures from that local median.  A
    profile's values change with height by orders of magnitude: tested
    against the whole profile, as before, a clean refractivity profile lost
    its lowest 20 km to the MAD test and its lowest 2.5 km to the 3-sigma
    test.
    """
    valid = profile.mask & np.isfinite(profile.v)

    if valid.sum() < 3 or method == "none":
        return {"method": "none", "removed": 0, "percent": 0.0}
    x = profile.v[valid]
    if (x > 0).all():
        x = np.log(x)
    # Point-reflected at both ends so a steady trend carries on there
    h = min(OUTLIER_WINDOW // 2, x.size - 1)
    padded = np.concatenate([2 * x[0] - x[h:0:-1], x, 2 * x[-1] - x[-2:-h - 2:-1]])
    # each level's neighbours, the level itself left out so it cannot mask itself
    nb = np.delete(np.lib.stride_tricks.sliding_window_view(padded, 2 * h + 1), h, axis=1)
    bad = np.zeros(x.size, dtype=bool)
    outlier_mask = np.zeros_like(profile.v, dtype=bool)

    if method == "sigma":
        bad = np.abs(x - nb.mean(axis=1)) > threshold * nb.std(axis=1)
    elif method == "mad":
        med = np.median(nb, axis=1)
        mad = np.median(np.abs(nb - med[:, None]), axis=1)
        bad = np.abs(x - med) > threshold * 1.4826 * mad
    elif method == "iqr":
        q25, q75 = np.percentile(nb, [25, 75], axis=1)
        bad = (x < q25 - threshold * (q75 - q25)) | (x > q75 + threshold * (q75 - q25))
    elif method == "percentile":
        dep = x - np.median(nb, axis=1)
        low_val, high_val = np.percentile(dep, [kwargs.get("lower", 5.0), kwargs.get("upper", 95.0)])
        bad = (dep < low_val) | (dep > high_val)
    else:
        raise ValueError(f"Unknown outlier method: {method}")
    outlier_mask[valid] = bad

    removed_count = int(outlier_mask.sum())
    total_valid = int(valid.sum())
    
    profile.mask = profile.mask & (~outlier_mask)
    profile.v = np.where(profile.mask, profile.v, np.nan)
    
    prof_rec = ProvenanceRecord(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        operation="outlier_removal",
        parameters={"method": method, "threshold": threshold, "removed_count": removed_count, "percent": (removed_count / total_valid * 100.0) if total_valid > 0 else 0.0, **kwargs}
    )
    profile.provenance.append(prof_rec)

    return {
        "method": method,
        "threshold": threshold,
        "removed": removed_count,
        "percent": (removed_count / total_valid * 100.0) if total_valid > 0 else 0.0
    }

def smooth_data(profile: ProcessedProfile, method: str, window: int = 5, **kwargs) -> dict:
    """Robust smoothing and filtering.
    Methods: moving_average, gaussian, median, savgol, none
    """
    valid = profile.mask & np.isfinite(profile.v)
    if valid.sum() < window or method == "none":
        return {"method": "none"}
        
    v_clean = profile.v.copy()
    
    if method == "moving_average":
        from .analysis import _smooth
        v_clean = _smooth(profile.v, window)
    elif method == "median":
        from scipy.signal import medfilt
        v_interp = np.copy(profile.v)
        v_interp[~valid] = np.interp(np.flatnonzero(~valid), np.flatnonzero(valid), profile.v[valid])
        kernel = window if window % 2 == 1 else window + 1
        v_clean = medfilt(v_interp, kernel_size=kernel)
        v_clean[~valid] = np.nan
    elif method == "gaussian":
        from scipy.ndimage import gaussian_filter1d
        v_interp = np.copy(profile.v)
        v_interp[~valid] = np.interp(np.flatnonzero(~valid), np.flatnonzero(valid), profile.v[valid])
        sigma = kwargs.get("sigma", window / 3.0)
        v_clean = gaussian_filter1d(v_interp, sigma=sigma)
        v_clean[~valid] = np.nan
    elif method == "savgol":
        from scipy.signal import savgol_filter
        polyorder = kwargs.get("polyorder", 2)
        win = window if window % 2 == 1 else window + 1
        v_interp = np.copy(profile.v)
        if not (valid.sum() > win and polyorder < win):
            # Not applicable: leave the data alone and do not record a
            # smoothing step that never happened.
            return {"method": "none", "skipped": "savgol",
                    "reason": f"needs more than {win} valid levels and "
                              f"polyorder < window"}
        v_interp[~valid] = np.interp(np.flatnonzero(~valid), np.flatnonzero(valid), profile.v[valid])
        v_clean = savgol_filter(v_interp, window_length=win, polyorder=polyorder)
        v_clean[~valid] = np.nan
    else:
        raise ValueError(f"Unknown smoothing method: {method}")

    profile.v = v_clean
    prof_rec = ProvenanceRecord(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        operation="smoothing",
        parameters={"method": method, "window": window, **kwargs}
    )
    profile.provenance.append(prof_rec)
    return {"method": method, "window": window}

def compute_uncertainty(profile: ProcessedProfile, method: str = "standard_error", window: int = 5) -> dict:
    """Uncertainty support/error bar estimation.
    Methods: standard_deviation, standard_error, none

    The spread is the local scatter *about the running mean*, not the raw
    rolling standard deviation of the values.  A raw rolling std measures the
    profile's own vertical gradient (a noise-free temperature or pressure
    profile got error bars of several K or hPa simply because it changes with
    height); removing the running mean leaves only the level-to-level noise.
    For white noise of std sigma the estimate is unbiased:
    sigma_hat^2 = <r^2> / (1 - 1/w), with r = v - running_mean_w(v).
    ``standard_error`` divides that by sqrt(levels in the window).
    """
    valid = profile.mask & np.isfinite(profile.v)
    uncertainty = np.full_like(profile.v, np.nan)
    
    if valid.sum() < window or method == "none":
         profile.uncertainty = uncertainty
         return {"method": "none"}
         
    import pandas as pd
    w = max(int(window), 2)
    s = pd.Series(profile.v)
    min_p = max(2, w // 2 + 1)
    resid = s - s.rolling(w, min_periods=min_p, center=True).mean()
    count = (resid.notna().astype(float)
             .rolling(w, min_periods=1, center=True).sum().values)
    msq = (resid ** 2).rolling(w, min_periods=min_p, center=True).mean().values
    std = np.sqrt(msq / (1.0 - 1.0 / w))
    if method == "standard_deviation":
        uncertainty = std
    elif method == "standard_error":
        uncertainty = std / np.sqrt(np.where(count > 0, count, np.nan))
    else:
        raise ValueError(f"Unknown uncertainty method: {method}")
        
    profile.uncertainty = uncertainty
    prof_rec = ProvenanceRecord(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        operation="uncertainty_estimation",
        parameters={"method": method, "window": window}
    )
    profile.provenance.append(prof_rec)
    return {"method": method, "window": window}

def apply_pipeline(z: np.ndarray, v: np.ndarray, 
                   outlier_method: str = "none", outlier_kwargs: dict = None,
                   smooth_method: str = "none", smooth_kwargs: dict = None,
                   uncert_method: str = "none", uncert_kwargs: dict = None) -> ProcessedProfile:
    """Run the configurable scientific processing pipeline."""
    prof = ProcessedProfile(z=z, original_v=v.copy(), v=v.copy())
    
    if outlier_kwargs is None: outlier_kwargs = {}
    if smooth_kwargs is None: smooth_kwargs = {}
    if uncert_kwargs is None: uncert_kwargs = {}
    
    remove_outliers(prof, outlier_method, **outlier_kwargs)
    smooth_data(prof, smooth_method, **smooth_kwargs)
    compute_uncertainty(prof, uncert_method, **uncert_kwargs)
    
    return prof


def decimate(a: np.ndarray, max_points: int) -> np.ndarray:
    """Even subsample for display. Plot fidelity beyond ~1000 points on a
    1000-px axis is invisible, and the JSON cost is real."""
    if max_points <= 0 or a.size <= max_points:
        return a
    idx = np.linspace(0, a.size - 1, max_points).round().astype(int)
    return a[idx]


def profile_series(task: tuple) -> dict:
    """One profile of the Profiles-tab overlay: load, run the pipeline,
    decimate.  ``task`` is ``(index row, request dict)``.

    Returns ``{"skip": reason}`` when the profile cannot be drawn.
    Module-level so the API can run it on worker processes (see
    :mod:`.parallel`).
    """
    import os
    from . import analysis, readers, vocab
    row, req = task
    if not os.path.exists(row["path"]):
        return {"skip": "file missing from cache"}
    try:
        g = readers.load(row["path"], row["product"])
    except Exception as exc:  # noqa: BLE001
        return {"skip": str(exc)}
    field, vertical = req["field"], req["vertical"]
    src = analysis.fields_with(g, field, vertical)
    if field not in src or vertical not in src:
        return {"skip": f"no {field} on {vertical}"}
    y, x = src[vertical], src[field]
    if req["convert_kelvin"] and field in ("Temp", "temp_dry"):
        x = analysis.to_kelvin(x, g.units.get(field, "C"))
        units = "K"
    else:
        units = g.units.get(field, "") or vocab.info(field)["units"]
    n = min(x.size, y.size)
    prof = apply_pipeline(y[:n], x[:n],
                          outlier_method=req["outlier_method"],
                          outlier_kwargs=req["outlier_kwargs"],
                          smooth_method=req["smooth_method"],
                          smooth_kwargs=req["smooth_kwargs"],
                          uncert_method=req["uncert_method"],
                          uncert_kwargs=req["uncert_kwargs"])
    mp = req["max_points"]
    return {
        "units": units, "product": g.product,
        "series": {
            "granule_id": row["id"],
            "label": f"{g.meta['sat'] or '?'} {g.meta['occ_prn'] or ''} "
                     f"{(g.meta['time_utc'] or '')[11:16]}Z",
            "file_name": g.meta["file_name"],
            "x": decimate(prof.v, mp),
            "original_x": decimate(prof.original_v, mp),
            "y": decimate(prof.z, mp),
            "uncertainty": (decimate(prof.uncertainty, mp)
                            if prof.uncertainty is not None else None),
            "provenance": [p.__dict__ for p in prof.provenance],
            "lat": g.meta["lat"], "lon": g.meta["lon"],
            "local_time": g.meta["local_time"],
            "good": g.meta["good"],
        },
    }
