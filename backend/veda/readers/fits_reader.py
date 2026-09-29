"""Astronomical FITS reader and scientific imaging engine for VEDA.

Utilizes astropy.io.fits to parse multi-extension planetary imaging files
(e.g., LORRI, MVIC, UVI, LIR, JunoCam, ISS). Provides rigorous astronomical
contrast stretch functions (ZScale, Percentile, Log, Sqrt, Asinh, HistEq),
false-color palette mapping, and 1D photometric transect / radial profiling.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from astropy.io import fits
from astropy.visualization import (
    AsinhStretch,
    HistEqStretch,
    ImageNormalize,
    LogStretch,
    MinMaxInterval,
    PercentileInterval,
    SqrtStretch,
    ZScaleInterval,
)
import matplotlib.cm as cm
from PIL import Image


@dataclass
class FitsImageData:
    file_path: str
    primary_data: np.ndarray
    error_data: Optional[np.ndarray] = None
    quality_mask: Optional[np.ndarray] = None
    header: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, float] = field(default_factory=dict)


def load_fits_image(file_path: str) -> FitsImageData:
    """Read a FITS file and compute astronomical baseline statistics."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"FITS file not found at {file_path}")

    with fits.open(str(p)) as hdul:
        primary_hdu = hdul[0]
        data = primary_hdu.data
        if data is None and len(hdul) > 1:
            data = hdul[1].data
            raw_hdr = hdul[1].header
        else:
            raw_hdr = primary_hdu.header

        if data is None:
            raise ValueError(f"No image array found in {file_path}")

        # Ensure 2D float64
        arr = np.squeeze(data).astype(np.float64)
        if arr.ndim != 2:
            raise ValueError(f"Expected 2D image array, got shape {arr.shape}")

        error_data = None
        if len(hdul) > 1 and hdul[1].data is not None and hdul[1].data.shape == arr.shape:
            error_data = np.squeeze(hdul[1].data).astype(np.float64)

        quality_data = None
        if len(hdul) > 2 and hdul[2].data is not None and hdul[2].data.shape == arr.shape:
            quality_data = np.squeeze(hdul[2].data).astype(np.int32)

        # Extract header cards
        hdr_dict: Dict[str, Any] = {}
        for card in raw_hdr.cards:
            k = card.keyword.strip()
            if k and k not in ("COMMENT", "HISTORY"):
                hdr_dict[k] = card.value

        # Calculate robust statistics
        finite_mask = np.isfinite(arr)
        if finite_mask.any():
            v_valid = arr[finite_mask]
            stats = {
                "min": float(np.min(v_valid)),
                "max": float(np.max(v_valid)),
                "mean": float(np.mean(v_valid)),
                "median": float(np.median(v_valid)),
                "std": float(np.std(v_valid)),
                "p01": float(np.percentile(v_valid, 1.0)),
                "p05": float(np.percentile(v_valid, 5.0)),
                "p95": float(np.percentile(v_valid, 95.0)),
                "p99": float(np.percentile(v_valid, 99.0)),
                "shape_y": int(arr.shape[0]),
                "shape_x": int(arr.shape[1]),
            }
        else:
            stats = {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0,
                     "shape_y": int(arr.shape[0]), "shape_x": int(arr.shape[1])}

    return FitsImageData(
        file_path=str(p),
        primary_data=arr,
        error_data=error_data,
        quality_mask=quality_data,
        header=hdr_dict,
        stats=stats,
    )


def apply_contrast_stretch(
    image: np.ndarray,
    stretch_method: str = "zscale",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    percentile_low: float = 0.5,
    percentile_high: float = 99.5,
) -> np.ndarray:
    """Normalize 2D array to [0.0, 1.0] using astronomical algorithms."""
    arr = np.nan_to_num(image, nan=0.0, posinf=0.0, neginf=0.0)

    # Determine interval
    interval = None
    if vmin is not None and vmax is not None and vmin < vmax:
        interval = MinMaxInterval()
        arr = np.clip(arr, vmin, vmax)
    elif stretch_method == "zscale":
        interval = ZScaleInterval(contrast=0.25)
    elif stretch_method == "percentile":
        interval = PercentileInterval(percentile_high - percentile_low)
    else:
        interval = MinMaxInterval()

    # Determine stretch
    stretch = None
    if stretch_method == "log":
        stretch = LogStretch(a=1000.0)
    elif stretch_method == "sqrt":
        stretch = SqrtStretch()
    elif stretch_method == "asinh":
        stretch = AsinhStretch(a=0.1)
    elif stretch_method == "histeq":
        stretch = HistEqStretch(arr)
    else:
        stretch = None

    try:
        norm = ImageNormalize(arr, interval=interval, stretch=stretch, clip=True)
        normalized = norm(arr)
    except Exception:
        # Fallback to simple robust minmax
        lo, hi = np.percentile(arr, [1.0, 99.0])
        if hi > lo:
            normalized = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
        else:
            normalized = np.zeros_like(arr)

    return np.clip(normalized, 0.0, 1.0)


def render_to_png(
    image: np.ndarray,
    stretch_method: str = "zscale",
    colormap: str = "gray",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    max_dimension: int = 1024,
) -> bytes:
    """Render a stretched and colormapped astronomical array directly to PNG bytes."""
    norm = apply_contrast_stretch(image, stretch_method, vmin, vmax)

    # Apply Matplotlib colormap
    try:
        cmap = cm.get_cmap(colormap)
    except Exception:
        cmap = cm.get_cmap("gray")

    rgba = (cmap(norm) * 255.0).astype(np.uint8)
    pil_img = Image.fromarray(rgba, mode="RGBA")

    # Downsample if exceeding max_dimension
    if max_dimension > 0 and (pil_img.width > max_dimension or pil_img.height > max_dimension):
        pil_img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def extract_photometric_transect(
    image: np.ndarray,
    x0: float, y0: float,
    x1: float, y1: float,
    num_samples: int = 200,
) -> Dict[str, Any]:
    """Sample pixel intensities along a line segment (x0, y0) -> (x1, y1)."""
    h, w = image.shape
    x0 = max(0.0, min(float(x0), w - 1.0))
    y0 = max(0.0, min(float(y0), h - 1.0))
    x1 = max(0.0, min(float(x1), w - 1.0))
    y1 = max(0.0, min(float(y1), h - 1.0))

    xs = np.linspace(x0, x1, num_samples)
    ys = np.linspace(y0, y1, num_samples)

    # Bilinear interpolation
    x_floor = np.floor(xs).astype(int).clip(0, w - 2)
    y_floor = np.floor(ys).astype(int).clip(0, h - 2)
    dx = xs - x_floor
    dy = ys - y_floor

    top_left = image[y_floor, x_floor]
    top_right = image[y_floor, x_floor + 1]
    bot_left = image[y_floor + 1, x_floor]
    bot_right = image[y_floor + 1, x_floor + 1]

    top = top_left * (1.0 - dx) + top_right * dx
    bot = bot_left * (1.0 - dx) + bot_right * dx
    intensities = top * (1.0 - dy) + bot * dy

    # Distance along slice in pixels
    distances = np.sqrt((xs - x0) ** 2 + (ys - y0) ** 2)

    return {
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "distances_pixels": [round(float(d), 2) for d in distances],
        "intensities": [None if not np.isfinite(v) else round(float(v), 4) for v in intensities],
        "min_intensity": float(np.nanmin(intensities)) if np.isfinite(intensities).any() else 0.0,
        "max_intensity": float(np.nanmax(intensities)) if np.isfinite(intensities).any() else 0.0,
        "mean_intensity": float(np.nanmean(intensities)) if np.isfinite(intensities).any() else 0.0,
    }


def compute_image_histogram(
    image: np.ndarray,
    num_bins: int = 100,
) -> Dict[str, Any]:
    """Compute intensity histogram and cumulative distribution function (CDF)."""
    valid = image[np.isfinite(image)]
    if valid.size == 0:
        return {"bins": [], "counts": [], "cdf": []}

    p01, p99 = np.percentile(valid, [0.5, 99.5])
    clipped = valid[(valid >= p01) & (valid <= p99)]
    if clipped.size == 0:
        clipped = valid

    counts, bin_edges = np.histogram(clipped, bins=num_bins)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    cdf = np.cumsum(counts).astype(float) / counts.sum()

    return {
        "bins": [round(float(b), 4) for b in bin_centers],
        "counts": [int(c) for c in counts],
        "cdf": [round(float(v), 5) for v in cdf],
    }
