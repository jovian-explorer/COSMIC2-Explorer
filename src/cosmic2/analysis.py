"""Derived quantities and diagnostics for COSMIC-2 profiles.

Everything here operates on plain numpy arrays so it is equally usable from
the HTTP API, a notebook, or the test suite.  Physical constants and
algorithm choices are spelled out in the docstrings because the numbers leave
the application as science products.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from . import readers, vocab

# Physical constants (WMO / US Standard Atmosphere conventions)
G0 = 9.80665          # m s-2, standard gravity
R_DRY = 287.0578      # J kg-1 K-1, specific gas constant for dry air
CP_DRY = 1004.6       # J kg-1 K-1, isobaric specific heat of dry air
KAPPA = R_DRY / CP_DRY
P_REF_HPA = 1000.0    # reference pressure for potential temperature
DUCTING_GRADIENT = -157.0   # N-units km-1: critical refractivity gradient
PLASMA_FREQ_COEFF = 8.98e-3  # foF2[MHz] = coeff * sqrt(Ne[cm-3])


# ---------------------------------------------------------------------------
# small numerical helpers
# ---------------------------------------------------------------------------

def _clean_pair(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Drop non-finite pairs and sort by ``x`` ascending."""
    x = np.asarray(x, dtype="float64")
    y = np.asarray(y, dtype="float64")
    n = min(x.size, y.size)
    x, y = x[:n], y[:n]
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    order = np.argsort(x)
    return x[order], y[order]


def interp_to_grid(z: np.ndarray, v: np.ndarray, grid: np.ndarray,
                   max_gap: float | None = None, log: bool = False) -> np.ndarray:
    """Linearly interpolate ``v(z)`` onto ``grid`` (in ``ln v`` if ``log``).

    Points outside the profile's own range become NaN (never extrapolated).
    If ``max_gap`` is given, grid points sitting inside a data gap wider than
    ``max_gap`` are also NaN, so an interpolated line never bridges a hole
    the instrument did not sample.
    """
    zc, vc = _clean_pair(z, v)
    grid = np.asarray(grid, dtype="float64")
    if zc.size < 2:
        return np.full(grid.shape, np.nan)
    out = np.interp(grid, zc, vc, left=np.nan, right=np.nan)
    if log:
        # Interpolate ln(v) between strictly positive neighbours; any interval
        # touching a zero or negative value (noise in Ne, for example) keeps
        # the linear result.
        with np.errstate(invalid="ignore", divide="ignore"):
            lv = np.where(vc > 0, np.log(np.where(vc > 0, vc, 1.0)), np.nan)
            lg = np.exp(np.interp(grid, zc, lv, left=np.nan, right=np.nan))
        out = np.where(np.isfinite(lg), lg, out)
    if max_gap:
        idx = np.searchsorted(zc, grid).clip(1, zc.size - 1)
        gap = zc[idx] - zc[idx - 1]
        out[gap > max_gap] = np.nan
    return out


# Quantities that fall off roughly exponentially with height.  Between two
# levels they are interpolated in ln(v), which is exact for an isothermal
# layer; straight-line interpolation overestimates them in every gap (by ~1 %
# across a 2 km gap in pressure, more for steep electron-density bottomsides).
LOG_INTERP_FIELDS = frozenset({
    "Pres", "pres_dry", "density", "Vp", "sph", "ELEC_dens", "ion_dens",
})


def interp_field(z: np.ndarray, v: np.ndarray, grid: np.ndarray, field: str,
                 max_gap: float | None = None) -> np.ndarray:
    """:func:`interp_to_grid`, in log space for the fields that need it."""
    return interp_to_grid(z, v, grid, max_gap=max_gap,
                          log=field in LOG_INTERP_FIELDS)


def make_grid(top_km: float = 60.0, step_km: float = 0.2,
              bottom_km: float = 0.0) -> np.ndarray:
    if not (step_km > 0) or not (top_km > bottom_km):
        raise ValueError(f"grid needs step > 0 and top > bottom "
                         f"(got step {step_km}, {bottom_km}..{top_km} km)")
    n = int(round((top_km - bottom_km) / step_km)) + 1
    return bottom_km + step_km * np.arange(n)


def _smooth(y: np.ndarray, window: int) -> np.ndarray:
    """Running mean that tolerates NaN and preserves array length."""
    if window <= 1:
        return y.astype("float64")
    k = int(window) | 1
    pad = k // 2
    a = np.asarray(y, dtype="float64")
    finite = np.isfinite(a).astype("float64")
    filled = np.where(np.isfinite(a), a, 0.0)
    kern = np.ones(k)
    num = np.convolve(np.pad(filled, pad, mode="edge"), kern, "valid")
    den = np.convolve(np.pad(finite, pad, mode="edge"), kern, "valid")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den == 0] = np.nan
    return out


def _gradient(z: np.ndarray, v: np.ndarray) -> np.ndarray:
    """d v / d z with NaN-safe one-sided differences at the ends.

    Works for top-down (atmPrf) and bottom-up (wetPf2) profiles alike.  Levels
    are sorted by height first, and repeated heights (which occur in
    atmPrf near the surface) are collapsed, so the derivative never divides
    by a zero height step.
    """
    z = np.asarray(z, dtype="float64")
    v = np.asarray(v, dtype="float64")
    out = np.full(v.shape, np.nan)
    ok = np.isfinite(z) & np.isfinite(v)
    if ok.sum() < 2:
        return out
    zs, idx = np.unique(z[ok], return_index=True)   # sorted, first of repeats
    if zs.size < 2:
        return out
    gs = np.gradient(v[ok][idx], zs)
    out[ok] = np.interp(z[ok], zs, gs)
    return out


def to_kelvin(t: np.ndarray, units: str) -> np.ndarray:
    u = (units or "").lower()
    if u.startswith("k"):
        return np.asarray(t, dtype="float64")
    return np.asarray(t, dtype="float64") + 273.15


# ---------------------------------------------------------------------------
# neutral-atmosphere derived fields
# ---------------------------------------------------------------------------

def potential_temperature(temp_k: np.ndarray, pres_hpa: np.ndarray) -> np.ndarray:
    """theta = T (p0/p)^kappa, with p0 = 1000 hPa."""
    t = np.asarray(temp_k, dtype="float64")
    p = np.asarray(pres_hpa, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        return t * (P_REF_HPA / p) ** KAPPA


def lapse_rate(z_km: np.ndarray, temp_k: np.ndarray) -> np.ndarray:
    """Environmental lapse rate in K/km (positive where T falls with height)."""
    return -_gradient(z_km, temp_k)


def brunt_vaisala_squared(z_km: np.ndarray, temp_k: np.ndarray) -> np.ndarray:
    """N^2 = (g/T)(dT/dz + g/cp), in s^-2.  Negative means static instability."""
    dtdz = _gradient(z_km, temp_k) / 1000.0  # K/m
    with np.errstate(invalid="ignore", divide="ignore"):
        return (G0 / np.asarray(temp_k, dtype="float64")) * (dtdz + G0 / CP_DRY)


def refractivity_gradient(z_km: np.ndarray, n_units: np.ndarray,
                          smooth_levels: int = 5) -> np.ndarray:
    """dN/dz in N-units per km, lightly smoothed to suppress retrieval noise."""
    return _smooth(_gradient(z_km, n_units), smooth_levels)


def tropopause_wmo(z_km: np.ndarray, temp_k: np.ndarray,
                   pres_hpa: np.ndarray | None = None,
                   z_min: float = 5.0, z_max: float = 40.0,
                   threshold: float = 2.0, layer_km: float = 2.0,
                   p_max_hpa: float = 500.0,
                   t_max_k: float | None = None) -> dict:
    """WMO lapse-rate tropopause.

    The lowest level where the lapse rate drops below ``threshold`` K/km
    *and* the mean lapse rate from that level to every level within
    ``layer_km`` above it also stays below the threshold.  Evaluated on a
    uniform 100 m grid.

    The search is restricted to pressures below ``p_max_hpa``.  That floor is
    part of the WMO definition (the tropopause is sought above the 500 hPa
    level), not an optional refinement: COSMIC-2 resolves shallow
    mid-tropospheric inversions that pass the bare 2 K/km test but are not
    the tropopause, and without the floor a ~2 km inversion near 5 km wins on
    tropical profiles.  With no pressure profile supplied the weaker height
    floor ``z_min`` applies instead.

    ``t_max_k`` skips candidate levels warmer than that temperature.  It is
    needed for *dry* temperature (atmPrf ``Temp``), which equals the real
    temperature only where water vapour is negligible: in moist tropical air
    its lapse rate drops below 2 K/km near 6 km (~450-500 hPa), and without
    a guard 220 of 570 COSMIC-2 profiles (2026-06-20 and 2026-09-30) got a
    tropopause there, up to 12 km below CDAAC's ``trhwmo``.  With
    ``DRY_TROPOPAUSE_T_MAX_K`` 568 of 570 agree with ``trhwmo`` within
    0.3 km; CDAAC's own tropopause temperatures never exceeded 233.7 K.
    """
    grid = make_grid(z_max, 0.1, max(z_min - 1.0, 0.0))
    t = interp_to_grid(z_km, temp_k, grid)
    p = interp_to_grid(z_km, pres_hpa, grid, log=True) if pres_hpa is not None else None
    lr = lapse_rate(grid, t)
    step = grid[1] - grid[0]
    span = int(round(layer_km / step))
    # WMO: "2 K/km or less".  The tolerance absorbs rounding in the
    # finite differences so a layer at exactly the threshold qualifies.
    limit = threshold + 1e-9
    method = "WMO lapse-rate 2 K/km" + (
        f", levels colder than {t_max_k:g} K" if t_max_k is not None else "")
    for i, zi in enumerate(grid):
        if zi < z_min or not np.isfinite(lr[i]) or lr[i] > limit:
            continue
        if p is not None and np.isfinite(p[i]) and p[i] > p_max_hpa:
            continue
        if t_max_k is not None and t[i] > t_max_k:
            continue
        top = i + span
        if top > grid.size - 1:
            break  # the full 2 km test layer no longer fits below z_max
        seg_t, seg_z = t[i:top + 1], grid[i:top + 1]
        if not np.isfinite(seg_t).all():
            continue
        # mean lapse rate from zi up to each level in the layer
        with np.errstate(invalid="ignore", divide="ignore"):
            mean_lr = -(seg_t[1:] - seg_t[0]) / (seg_z[1:] - seg_z[0])
        if np.all(mean_lr <= limit):
            return {"height_km": float(zi), "temp_K": float(t[i]),
                    "temp_C": float(t[i] - 273.15), "method": method,
                    "found": True}
    return {"height_km": None, "temp_K": None, "temp_C": None,
            "method": method, "found": False}


# Warmest level accepted as a WMO tropopause on a *dry* temperature profile
# (see tropopause_wmo).  Real tropopauses within COSMIC-2's +/-45 deg of
# latitude are colder; the moist-layer artefact sits at 237-258 K.
DRY_TROPOPAUSE_T_MAX_K = 235.0


def cold_point(z_km: np.ndarray, temp_k: np.ndarray,
               z_min: float = 10.0, z_max: float = 30.0) -> dict:
    """Coldest level in the upper troposphere / lower stratosphere."""
    z, t = _clean_pair(z_km, temp_k)
    sel = (z >= z_min) & (z <= z_max)
    if sel.sum() < 3:
        return {"height_km": None, "temp_K": None, "temp_C": None, "found": False}
    zz, tt = z[sel], t[sel]
    i = int(np.argmin(tt))
    return {"height_km": float(zz[i]), "temp_K": float(tt[i]),
            "temp_C": float(tt[i] - 273.15), "found": True}


def ducting_layers(z_km: np.ndarray, n_units: np.ndarray,
                   critical: float = DUCTING_GRADIENT) -> dict:
    """Layers where dN/dz is at or below the critical gradient.

    Below about -157 N-units/km a radio ray curves faster than the Earth and
    becomes trapped: a "duct".  These layers also mark sharp humidity
    inversions, which is why they are used as a marine boundary-layer proxy.
    """
    z, n = _clean_pair(z_km, n_units)
    if z.size < 5:
        return {"layers": [], "min_gradient": None, "min_gradient_height_km": None,
                "ducting": False}
    grad = refractivity_gradient(z, n)
    trapped = np.isfinite(grad) & (grad <= critical)
    layers = []
    i = 0
    while i < trapped.size:
        if trapped[i]:
            j = i
            while j + 1 < trapped.size and trapped[j + 1]:
                j += 1
            layers.append({"bottom_km": float(z[i]), "top_km": float(z[j]),
                           "thickness_km": float(z[j] - z[i]),
                           "min_gradient": float(np.nanmin(grad[i:j + 1]))})
            i = j + 1
        else:
            i += 1
    k = int(np.nanargmin(grad)) if np.isfinite(grad).any() else None
    return {"layers": layers,
            "min_gradient": float(grad[k]) if k is not None else None,
            "min_gradient_height_km": float(z[k]) if k is not None else None,
            "critical_gradient": critical,
            "ducting": bool(layers)}


def boundary_layer_height(z_km: np.ndarray, n_units: np.ndarray,
                          z_max: float = 6.0) -> dict:
    """Planetary boundary-layer top from the sharpest refractivity gradient.

    The standard RO proxy: within the lowest few km, the level of the minimum
    (most negative) dN/dz marks the capping inversion at the top of the
    well-mixed layer.
    """
    z, n = _clean_pair(z_km, n_units)
    sel = z <= z_max
    if sel.sum() < 10:
        return {"height_km": None, "gradient": None, "found": False}
    zz, nn = z[sel], n[sel]
    grad = refractivity_gradient(zz, nn, smooth_levels=9)
    if not np.isfinite(grad).any():
        return {"height_km": None, "gradient": None, "found": False}
    i = int(np.nanargmin(grad))
    return {"height_km": float(zz[i]), "gradient": float(grad[i]),
            "sharpness": float(abs(grad[i]) / abs(DUCTING_GRADIENT)), "found": True}


GW_METHODS = ("polynomial", "highpass")


def gravity_wave_energy(z_km: np.ndarray, temp_k: np.ndarray,
                        z_lo: float = 20.0, z_hi: float = 40.0,
                        poly_order: int = 4, method: str = "polynomial",
                        cutoff_km: float = 10.0) -> dict:
    """Gravity-wave potential energy density in the stratosphere.

    The temperature is put on a 0.2 km grid and split into a background
    T0 and a perturbation T' = T - T0, by one of two filters:

    ``polynomial`` (default)
        a degree-``poly_order`` polynomial in height fitted over
        ``[z_lo, z_hi]``.  It keeps vertical wavelengths short compared with
        the layer: for a 2 K sine wave on an isothermal 220 K background over
        20-40 km it recovers 98 % of the true Ep at 2 km wavelength, 90 % at
        5 km and 75 % at 10 km (``tests/test_gravity_waves.py``).
    ``highpass``
        a 4th-order Butterworth low-pass with cut-off wavelength
        ``cutoff_km``, run forwards and backwards (zero phase) over the layer
        plus up to 5 km on each side to keep its edge transients out of the
        layer; T0 is the low-passed profile.  The same test wave keeps 99 %
        of its Ep at 2 km wavelength, 98 % at 5 km, a quarter at the cut-off
        (the filter's half-amplitude point) and under 1 % at 15 km.  Tsuda
        et al. (2000) separated waves the same way, keeping vertical
        wavelengths below 10 km in 20-30 km: with ``z_lo=20, z_hi=30,
        method="highpass"`` the 2026 COSMIC-2 sample gives a tropical
        (|lat| < 20) mean of 6.0 J/kg, within their 6-10 J/kg.

    Then

        Ep = 0.5 * (g0 / N)^2 * (T'/T0)^2     [J/kg]

    with N from the background T0, averaged over ``[z_lo, z_hi]``.
    """
    if method not in GW_METHODS:
        raise ValueError(f"method must be one of {GW_METHODS}")
    if not (z_hi > z_lo):
        raise ValueError("z_hi must be above z_lo")
    step = 0.2
    pad = 5.0 if method == "highpass" else 0.0
    grid = make_grid(z_hi + pad, step, max(z_lo - pad, 0.0))
    t = interp_to_grid(z_km, temp_k, grid)
    layer = (grid >= z_lo - 1e-9) & (grid <= z_hi + 1e-9)
    ok = np.isfinite(t)
    empty = {"ep_J_per_kg": None, "t_prime_rms_K": None, "found": False,
             "layer_km": [z_lo, z_hi], "method": method}
    if method == "polynomial":
        sel = ok & layer
        if sel.sum() < poly_order + 3:
            return empty
        t0 = np.polyval(np.polyfit(grid[sel], t[sel], poly_order), grid)
    else:
        # The filter needs a gap-free series: the longest finite run, which
        # must cover the whole layer.
        from scipy.signal import butter, filtfilt
        runs = np.flatnonzero(np.diff(np.concatenate(([0], ok.astype(int), [0]))))
        starts, ends = runs[::2], runs[1::2]
        if not starts.size:
            return empty
        k = int(np.argmax(ends - starts))
        a, b = starts[k], ends[k]
        lay = np.flatnonzero(layer)
        if a > lay[0] or b <= lay[-1] or b - a < 30:
            return empty
        bb, aa = butter(4, step / cutoff_km * 2.0)   # cut-off as a fraction of Nyquist
        t0 = np.full(grid.shape, np.nan)
        # Filter the departure from a straight line: the stratospheric
        # temperature trend would otherwise leak into T' through the
        # filter's end effects (0.04 J/kg on a wave-free linear profile).
        zz = grid[a:b]
        trend = np.polyval(np.polyfit(zz, t[a:b], 1), zz)
        t0[a:b] = trend + filtfilt(bb, aa, t[a:b] - trend,
                                   padlen=min(3 * max(len(aa), len(bb)), b - a - 1))
    tprime = t - t0
    n2 = brunt_vaisala_squared(grid, t0)
    with np.errstate(invalid="ignore", divide="ignore"):
        ep = 0.5 * (G0 ** 2 / n2) * (tprime / t0) ** 2
    use = layer & np.isfinite(ep) & (n2 > 0)
    if not use.any():
        return empty
    out = {"ep_J_per_kg": float(np.mean(ep[use])),
           "t_prime_rms_K": float(np.sqrt(np.mean(tprime[use] ** 2))),
           "layer_km": [z_lo, z_hi], "method": method, "found": True}
    if method == "polynomial":
        out["poly_order"] = poly_order
    else:
        out["cutoff_km"] = cutoff_km
    return out


# ---------------------------------------------------------------------------
# ionosphere
# ---------------------------------------------------------------------------

def ionosphere_peak(z_km: np.ndarray, ne_cm3: np.ndarray,
                    z_min: float = 150.0) -> dict:
    """F2-layer peak density/height, critical frequency and topside scale height.

    ``hmF2`` is refined by fitting a parabola to the three points around the
    discrete maximum.  The topside scale height comes from a straight-line fit
    to ln(Ne) between 50 and 150 km above the peak (Chapman topside).
    """
    z, ne = _clean_pair(z_km, ne_cm3)
    sel = (z >= z_min) & (ne > 0)
    if sel.sum() < 5:
        return {"NmF2_el_cm3": None, "hmF2_km": None, "foF2_MHz": None,
                "topside_scale_height_km": None, "found": False}
    zz, nn = z[sel], ne[sel]
    i = int(np.argmax(nn))
    hm, nm = float(zz[i]), float(nn[i])
    # A maximum on the first or last level is where the profile was cut, not
    # a layer peak (e.g. a profile that ends below the F2 peak).
    at_edge = i == 0 or i == zz.size - 1
    if not at_edge:
        # Vertex of the parabola through the three levels around the maximum,
        # valid for the uneven level spacing of ionPrf.
        x0, x1, x2 = zz[i - 1], zz[i], zz[i + 1]
        y0, y1, y2 = nn[i - 1], nn[i], nn[i + 1]
        d0, d2 = x0 - x1, x2 - x1
        den = d0 * d2 * (d0 - d2)
        a = (d2 * (y0 - y1) - d0 * (y2 - y1)) / den if den else 0.0
        b = (d0 * d0 * (y2 - y1) - d2 * d2 * (y0 - y1)) / den if den else 0.0
        if a < 0:
            dx = -b / (2 * a)
            if d0 <= dx <= d2:
                hm = float(x1 + dx)
                nm = float(y1 + b * dx + a * dx * dx)
    scale_h = None
    top = (zz > hm + 50) & (zz < hm + 150) & (nn > 0)
    if top.sum() >= 5:
        slope = np.polyfit(zz[top], np.log(nn[top]), 1)[0]
        if slope < 0:
            scale_h = float(-1.0 / slope)
    e_layer = None
    esel = (z >= 90) & (z <= 150) & (ne > 0)
    if esel.sum() >= 5:
        ze, nee = z[esel], ne[esel]
        j = int(np.argmax(nee))
        # Only a genuine local maximum inside 90-150 km is an E layer; a
        # maximum on the window edge is just the F-region bottomside rising
        # through 150 km.
        if 0 < j < nee.size - 1:
            e_layer = {"NmE_el_cm3": float(nee[j]), "hmE_km": float(ze[j])}
    # Vertical TEC from the bottom of the profile up to hmF2.  Every level is
    # used, not only those above z_min (which would drop the E and lower F
    # region from the column).
    below = z <= hm
    return {"NmF2_el_cm3": nm, "hmF2_km": hm,
            "foF2_MHz": float(PLASMA_FREQ_COEFF * math.sqrt(nm)) if nm > 0 else None,
            "topside_scale_height_km": scale_h,
            "E_layer": e_layer,
            "vtec_below_peak_TECU": _column_tec(z[below], ne[below]),
            # Whole profile, bottom to top: the quantity CDAAC reports as
            # "tec0" (integrated TEC between bottom and top).
            "vtec_profile_TECU": _column_tec(z, ne),
            "peak_at_profile_edge": at_edge,
            "found": not at_edge}


def _column_tec(z_km: np.ndarray, ne_cm3: np.ndarray) -> float | None:
    """Integrate electron density to TEC units (1 TECU = 1e16 el m-2).

    Negative densities, an Abel-inversion artefact common on the bottomside
    of ionPrf profiles (often -4e4 el/cm3 over the lowest 100 km), count as
    zero.  Integrated as they stand they removed up to 95 % of the column;
    clipped, the whole-profile integral matches CDAAC's ``tec0`` (median
    ratio 1.002 over 119 COSMIC-2 profiles of 2026-09-30).
    """
    if z_km.size < 2:
        return None
    ne_m3 = np.clip(ne_cm3, 0.0, None) * 1e6
    z_m = z_km * 1e3
    return float(np.trapezoid(ne_m3, z_m) / 1e16)


def scintillation_summary(occheight_km: np.ndarray, s4: np.ndarray,
                          sigma_phi: np.ndarray | None = None) -> dict:
    """Peak S4 and where it occurred, plus a simple severity class."""
    z, s = _clean_pair(occheight_km, s4)
    if s.size == 0:
        return {"s4_max": None, "s4_max_height_km": None, "severity": "no data",
                "found": False}
    i = int(np.argmax(s))
    smax = float(s[i])
    sev = ("quiet" if smax < 0.2 else "moderate" if smax < 0.4
           else "strong" if smax < 0.7 else "severe")
    out = {"s4_max": smax, "s4_max_height_km": float(z[i]),
           "s4_mean": float(np.nanmean(s)), "severity": sev,
           "n_samples": int(s.size), "found": True}
    if sigma_phi is not None:
        sp = np.asarray(sigma_phi, dtype="float64")
        if np.isfinite(sp).any():
            out["sigma_phi_max_m"] = float(np.nanmax(sp))
    return out


# ---------------------------------------------------------------------------
# per-granule dispatch
# ---------------------------------------------------------------------------

def derived_fields(g: readers.Granule) -> dict[str, np.ndarray]:
    """Extra arrays computed from a granule, keyed like native variables."""
    out: dict[str, np.ndarray] = {}
    d = g.data
    if g.product in ("atmPrf", "wetPf2"):
        zname = "MSL_alt"
        tname = "Temp" if "Temp" in d else "temp_dry"
        pname = "Pres" if "Pres" in d else "pres_dry"
        nname = "Ref" if "Ref" in d else "ref"
        if zname in d and tname in d:
            z = d[zname]
            tk = to_kelvin(d[tname], g.units.get(tname, "C"))
            out["lapse_rate"] = lapse_rate(z, tk)
            out["buoyancy_freq_sq"] = brunt_vaisala_squared(z, tk)
            # speed of sound cs = sqrt(gamma * R_dry * T)
            out["speed_of_sound"] = np.sqrt(1.4 * R_DRY * tk)
            # scale height H = R_dry * T / g
            out["scale_height"] = (R_DRY * tk) / (G0 * 1000.0)
            # buoyancy period tau_B = 2*pi / sqrt(N^2) in minutes where N^2 > 0
            n2 = out["buoyancy_freq_sq"]
            with np.errstate(invalid="ignore", divide="ignore"):
                out["buoyancy_period"] = np.where(n2 > 0, (2.0 * np.pi / np.sqrt(n2)) / 60.0, np.nan)
            if pname in d:
                out["theta"] = potential_temperature(tk, d[pname])
                out["dtheta_dz"] = _gradient(z, out["theta"])
                # Ideal-gas density, pressure in hPa (x100 for Pa).  Where
                # the product carries water-vapour pressure (wetPf2 "Vp"),
                # the vapour is counted with its own gas constant:
                #   rho = (p - e) / (R_d T) + e / (R_v T)
                # which is ~1 % lighter than dry air in the humid tropics.
                p_pa = d[pname] * 100.0
                e_pa = d["Vp"] * 100.0 if pname == "Pres" and "Vp" in d else None
                out["density"] = moist_air_density(p_pa, tk, e_pa)
        if zname in d and nname in d:
            out["dNdz"] = refractivity_gradient(d[zname], d[nname])
    elif g.product == "ivmL2m" and "uts" in d and "lon" in d:
        # Local solar time of every sample (the file carries only magnetic
        # local time, "mlt").
        n = min(d["uts"].size, d["lon"].size)
        out["slt"] = solar_local_time(d["uts"][:n], d["lon"][:n])
    return out


def fields_with(g: readers.Granule, *names: str) -> dict[str, np.ndarray]:
    """The granule's arrays, plus the derived fields only when one of
    ``names`` is not a native variable.  Deriving every field costs ~10 % of
    a composite or profile plot of a native quantity such as Temp."""
    src = dict(g.data)
    if any(n not in src for n in names):
        src.update(derived_fields(g))
    return src


R_VAPOUR = 461.5       # J kg-1 K-1, specific gas constant for water vapour


def moist_air_density(p_pa: np.ndarray, temp_k: np.ndarray,
                      e_pa: np.ndarray | None = None) -> np.ndarray:
    """Air density in kg m-3 from total pressure, temperature and (optionally)
    water-vapour partial pressure, all in SI units."""
    p = np.asarray(p_pa, dtype="float64")
    t = np.asarray(temp_k, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        if e_pa is None:
            return p / (R_DRY * t)
        e = np.asarray(e_pa, dtype="float64")
        return (p - e) / (R_DRY * t) + e / (R_VAPOUR * t)


def solar_local_time(epoch_s: np.ndarray, lon_deg: np.ndarray) -> np.ndarray:
    """Mean local solar time in hours from UNIX time and east longitude."""
    t = np.asarray(epoch_s, dtype="float64")
    lon = np.asarray(lon_deg, dtype="float64")
    return ((t % 86400.0) / 3600.0 + lon / 15.0) % 24.0


def diagnostics(g: readers.Granule) -> dict:
    """All scalar diagnostics appropriate to the granule's product."""
    d = g.data
    res: dict = {"product": g.product}
    if g.product in ("atmPrf", "wetPf2"):
        z = d.get("MSL_alt")
        tname = "Temp" if "Temp" in d else "temp_dry"
        nname = "Ref" if "Ref" in d else "ref"
        if z is not None and tname in d:
            tk = to_kelvin(d[tname], g.units.get(tname, "C"))
            pres = d.get("Pres", d.get("pres_dry"))
            # atmPrf "Temp" is dry temperature (wetPf2's is the moist
            # retrieval): guard against the moist-layer artefact.
            dry = g.product == "atmPrf" or tname == "temp_dry"
            res["tropopause"] = tropopause_wmo(
                z, tk, pres, t_max_k=DRY_TROPOPAUSE_T_MAX_K if dry else None)
            res["cold_point"] = cold_point(z, tk)
            res["gravity_waves"] = gravity_wave_energy(z, tk)
        if z is not None and nname in d:
            res["ducting"] = ducting_layers(z, d[nname])
            res["boundary_layer"] = boundary_layer_height(z, d[nname])
        if "sph" in d and z is not None:
            q = d["sph"]
            ok = np.isfinite(q) & np.isfinite(z)
            if ok.sum() > 5:
                pres = d.get("Pres")
                res["column_water_vapour_mm"] = _iwv_mm(
                    z[ok], q[ok], None if pres is None else pres[ok])
                # The integral starts at the lowest retrieved level, so the
                # column below it is missing; state where that was.
                res["column_water_vapour_bottom_km"] = float(np.min(z[ok]))
    elif g.product == "ionPrf":
        if "MSL_alt" in d and "ELEC_dens" in d:
            res["ionosphere"] = ionosphere_peak(d["MSL_alt"], d["ELEC_dens"])
    elif g.product == "scnLv2":
        res["scintillation"] = scintillation_summary(
            d.get("occheight", np.array([])), d.get("s4_L1", np.array([])),
            d.get("sigma_phi_L1"))
    elif g.product == "ivmL2m":
        dens = d.get("ion_dens")
        if dens is not None and np.isfinite(dens).any():
            res["insitu"] = {
                "ion_dens_median_Ncc": float(np.nanmedian(dens)),
                "ion_dens_max_Ncc": float(np.nanmax(dens)),
                "ion_temp_median_K": float(np.nanmedian(d["ion_temp"]))
                if "ion_temp" in d and np.isfinite(d["ion_temp"]).any() else None,
                "zonal_drift_median_ms": float(np.nanmedian(d["iv_zon"]))
                if "iv_zon" in d and np.isfinite(d["iv_zon"]).any() else None,
            }
    # archive's own values, for comparison with ours
    res["archive_values"] = g.meta.get("extras", {})
    return res


def diagnostics_row(r: dict) -> dict | None:
    """Flat ``{column: scalar}`` diagnostics for one index row (``None`` if
    the granule cannot be read).  Module-level so it can run in a worker
    process."""
    try:
        g = readers.load(r["path"], r["product"])
        d = diagnostics(g)
    except Exception:
        return None
    flat = {"granule_id": r["id"], "file_name": r["file_name"],
            "product": r["product"], "time_utc": r["time_utc"],
            "lat": r["lat"], "lon": r["lon"], "local_time": r["local_time"],
            "sat": r["sat"], "good": r["good"]}
    for key, val in d.items():
        if key in ("product", "archive_values"):
            continue
        if isinstance(val, dict):
            for k2, v2 in val.items():
                if isinstance(v2, (int, float, str, bool)) or v2 is None:
                    flat[f"{key}.{k2}"] = v2
        else:
            flat[key] = val
    return flat


def _iwv_mm(z_km: np.ndarray, q_g_kg: np.ndarray,
            pres_hpa: np.ndarray | None) -> float | None:
    """Integrated water vapour in mm, from specific humidity and pressure.

    IWV = (1/g) * integral q dp.  Falls back to None without pressure.
    ``pres_hpa`` must be aligned level-for-level with ``q_g_kg``.
    """
    if pres_hpa is None:
        return None
    p = np.asarray(pres_hpa, dtype="float64")[:q_g_kg.size]
    q = np.asarray(q_g_kg, dtype="float64") / 1000.0
    ok = np.isfinite(p) & np.isfinite(q)
    if ok.sum() < 5:
        return None
    pp, qq = p[ok] * 100.0, q[ok]        # Pa, kg/kg
    order = np.argsort(pp)
    return float(abs(np.trapezoid(qq[order], pp[order])) / G0)


# ---------------------------------------------------------------------------
# multi-profile composites
# ---------------------------------------------------------------------------

LAT_BANDS = [(-90, -60, "Antarctic"), (-60, -30, "S mid-latitude"),
             (-30, -10, "S subtropics"), (-10, 10, "Equatorial"),
             (10, 30, "N subtropics"), (30, 60, "N mid-latitude"),
             (60, 90, "Arctic")]


def band_of(lat: float | None) -> str:
    if lat is None:
        return "unknown"
    for lo, hi, name in LAT_BANDS:
        if lo <= lat < hi:
            return name
    return "Arctic" if (lat or 0) >= 60 else "unknown"


def _group_key(meta: dict, group_by: str) -> str:
    if group_by == "lat_band":
        return band_of(meta.get("lat"))
    if group_by == "hemisphere":
        lat = meta.get("lat")
        return "unknown" if lat is None else ("North" if lat >= 0 else "South")
    if group_by == "day_night":
        lt = meta.get("local_time")
        if lt is None:
            return "unknown"
        return "day (06-18 LT)" if 6 <= lt < 18 else "night (18-06 LT)"
    if group_by == "date":
        return meta.get("date") or "unknown"
    if group_by == "product":
        return meta.get("product") or "unknown"
    if group_by == "satellite":
        return meta.get("sat") or "unknown"
    return "all"


@dataclass
class Composite:
    field: str
    vertical: str
    grid: np.ndarray
    groups: dict[str, dict]
    n_profiles: int
    units: str = ""
    min_count: int = 3
    dropped_groups: dict = field(default_factory=dict)
    quantity: str = ""   # vocabulary key when it differs from the name

    def to_json(self) -> dict:
        def _l(a):
            # Full precision: fixed decimal rounding erased small fields
            # such as N^2 or density at 60 km.
            return [None if (v is None or not np.isfinite(v)) else float(v)
                    for v in np.asarray(a, dtype="float64")]
        return {
            "field": self.field, "vertical": self.vertical,
            "units": self.units, "n_profiles": self.n_profiles,
            "grid": _l(self.grid),
            "min_count": self.min_count,
            "dropped_groups": self.dropped_groups,
            "field_label": vocab.axis_title(self.quantity or self.field, self.units),
            "vertical_label": vocab.axis_title(self.vertical),
            "groups": {
                name: {
                    "n": g["n"], "n_per_level": [int(v) for v in g["count"]],
                    "mean": _l(g["mean"]), "median": _l(g["median"]),
                    "std": _l(g["std"]), "p10": _l(g["p10"]), "p90": _l(g["p90"]),
                }
                for name, g in self.groups.items()
            },
        }


def _composite_column(task: tuple) -> tuple[str, np.ndarray, str] | None:
    """One profile of a composite: ``(group key, gridded column, units)``.

    Module-level so it can run in a worker process (see :mod:`.parallel`).
    """
    path, meta, field, vertical, grid, group_by, convert_kelvin = task
    try:
        g = readers.load(path, meta.get("product"))
    except Exception:
        return None
    src = fields_with(g, field, vertical)
    if field not in src or vertical not in src:
        return None
    v = src[field]
    if convert_kelvin and field in ("Temp", "temp_dry"):
        v = to_kelvin(v, g.units.get(field, "C"))
        units = "K"
    else:
        units = g.units.get(field, "") or vocab.info(field)["units"]
    col = interp_field(src[vertical], v, grid, field, max_gap=2.0)
    if not np.isfinite(col).any():
        return None
    # The granule's own metadata, completed by the index row: "date"
    # (and the processing stream) exist only in the index, so grouping by
    # date put every profile under "unknown" before.
    gmeta = {**meta, **{k: v for k, v in g.meta.items() if v is not None}}
    return _group_key(gmeta, group_by), col, units, vocab.quantity(field, g.product)


def composite(granule_paths: Sequence[tuple[str, dict]], field: str,
              vertical: str = "MSL_alt", group_by: str = "all",
              top_km: float = 60.0, step_km: float = 0.5,
              good_only: bool = True, min_count: int = 3,
              convert_kelvin: bool = False,
              workers: int | None = None) -> Composite:
    """Mean/median/spread profile on a common grid, optionally grouped.

    ``granule_paths`` is a sequence of ``(path, index_metadata)``.  Each
    profile is interpolated onto the shared grid before averaging, which is
    the correct order of operations: averaging raw levels of different
    profiles would mix heights.  Granules are read on ``workers`` processes
    (``None``: the Settings value; see :mod:`.parallel`).
    """
    from .parallel import pmap
    grid = make_grid(top_km, step_km)
    tasks = [(path, meta, field, vertical, grid, group_by, convert_kelvin)
             for path, meta in granule_paths
             if not (good_only and not meta.get("good", True))]
    buckets: dict[str, list[np.ndarray]] = {}
    units = ""
    used = 0
    results = [r for r in pmap(_composite_column, tasks, workers=workers)
               if r is not None]
    # Never average different quantities that share a variable name (atmPrf
    # dry "Temp" with wetPf2 moist "Temp"): if the selection holds both, each
    # group is split and labelled by quantity.
    quantities = {r[3] for r in results}
    for key, col, u, qty in results:
        if len(quantities) > 1:
            key = f"{key} - {vocab.info(qty)['label']}"
        units = units or u
        buckets.setdefault(key, []).append(col)
        used += 1

    groups: dict[str, dict] = {}
    for name, cols in buckets.items():
        m = np.vstack(cols)
        count = np.isfinite(m).sum(axis=0)
        # Levels sampled by no profile legitimately produce all-NaN slices.
        with np.errstate(invalid="ignore", all="ignore"), \
                warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mean = np.nanmean(m, axis=0)
            median = np.nanmedian(m, axis=0)
            # Sample std; undefined (NaN) where only one profile reaches a
            # level, rather than a misleading zero-width spread band.
            std = np.nanstd(m, axis=0, ddof=1)
            p10 = np.nanpercentile(m, 10, axis=0)
            p90 = np.nanpercentile(m, 90, axis=0)
        thin = count < min_count
        for a in (mean, median, std, p10, p90):
            a[thin] = np.nan
        groups[name] = {"n": int(m.shape[0]), "count": count, "mean": mean,
                        "median": median, "std": std, "p10": p10, "p90": p90}
    # A group with fewer than min_count profiles is blank at every level, so
    # keeping it would put an entry in the key with no mark beside it. Drop it
    # and report it instead, so the omission is stated rather than silent.
    dropped = {n: g["n"] for n, g in groups.items()
               if not np.isfinite(g["mean"]).any()}
    groups = {n: g for n, g in groups.items() if n not in dropped}
    ordered = dict(sorted(groups.items(), key=lambda kv: -kv[1]["n"]))
    return Composite(field, vertical, grid, ordered, used, units,
                     min_count=min_count, dropped_groups=dropped,
                     quantity=next(iter(quantities)) if len(quantities) == 1 else "")


def anomaly_against(reference: np.ndarray, grid: np.ndarray,
                    z: np.ndarray, v: np.ndarray, percent: bool = True) -> np.ndarray:
    """Departure of one profile from a reference profile on ``grid``."""
    col = interp_to_grid(z, v, grid)
    with np.errstate(invalid="ignore", divide="ignore"):
        diff = col - reference
        return 100.0 * diff / reference if percent else diff
