"""Scientific processing pipeline for COSMIC-2 data.

Handles configurable outlier removal, smoothing/filtering, uncertainty
estimation, and tracks data provenance at every step.
"""
import datetime
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ProvenanceRecord:
    timestamp: str
    operation: str
    parameters: dict
    software_version: str = "0.0.1"

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

def remove_outliers(profile: ProcessedProfile, method: str, threshold: float = 3.0, **kwargs) -> dict:
    """Configurable outlier removal.
    Methods: sigma, mad, iqr, percentile, none
    """
    valid = profile.mask & np.isfinite(profile.v)
    v_valid = profile.v[valid]
    
    if valid.sum() < 3 or method == "none":
        return {"method": "none", "removed": 0, "percent": 0.0}

    outlier_mask = np.zeros_like(profile.v, dtype=bool)

    if method == "sigma":
        mean = np.mean(v_valid)
        std = np.std(v_valid)
        outlier_mask[valid] = np.abs(profile.v[valid] - mean) > threshold * std
    elif method == "mad":
        median = np.median(v_valid)
        mad = np.median(np.abs(v_valid - median))
        if mad == 0:
            mad = 1e-6
        outlier_mask[valid] = np.abs(profile.v[valid] - median) > threshold * 1.4826 * mad
    elif method == "iqr":
        q25, q75 = np.percentile(v_valid, [25, 75])
        iqr = q75 - q25
        lower = q25 - threshold * iqr
        upper = q75 + threshold * iqr
        outlier_mask[valid] = (profile.v[valid] < lower) | (profile.v[valid] > upper)
    elif method == "percentile":
        lower_p = kwargs.get("lower", 5.0)
        upper_p = kwargs.get("upper", 95.0)
        low_val, high_val = np.percentile(v_valid, [lower_p, upper_p])
        outlier_mask[valid] = (profile.v[valid] < low_val) | (profile.v[valid] > high_val)
    else:
        raise ValueError(f"Unknown outlier method: {method}")

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
        if valid.sum() > win and polyorder < win:
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
