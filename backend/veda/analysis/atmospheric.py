"""Multi-planet thermodynamic and atmospheric analysis engine for VEDA.

Applies body-specific thermodynamic constants (surface gravity, specific gas
constant R, isobaric heat capacity Cp, reference pressure) to calculate:
- Environmental lapse rate (-dT/dz)
- Potential temperature (theta) via Poisson equation
- Brunt-Vaisala buoyancy frequency squared (N^2)
- Mass density (rho)
- Scale height (H)
- Cross-mission comparative composites with +/- 1 sigma envelopes
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from ..core.models import BodyInfo, ObservationProfile
from ..core.registry import get_body


def _gradient_nan_safe(z_km: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Compute dv/dz robustly in presence of non-finite values."""
    z = np.asarray(z_km, dtype=np.float64)
    val = np.asarray(v, dtype=np.float64)
    out = np.full(val.shape, np.nan, dtype=np.float64)
    ok = np.isfinite(z) & np.isfinite(val)
    if ok.sum() < 2:
        return out
    out[ok] = np.gradient(val[ok], z[ok])
    return out


def compute_atmospheric_diagnostics(
    profile: ObservationProfile,
    body: Optional[BodyInfo] = None,
) -> Dict[str, np.ndarray]:
    """Compute full suite of thermodynamic derived quantities for a profile."""
    if body is None:
        body = get_body(profile.body_id)
    if body is None:
        # Default to Earth constants if unknown body
        body = get_body("earth")

    derived: Dict[str, np.ndarray] = {}
    z = profile.altitude_km
    if z is None or z.size < 2:
        return derived

    t_k = profile.temperature_k
    if t_k is None and profile.temperature_c is not None:
        t_k = profile.temperature_c + 273.15
        profile.temperature_k = t_k
    elif profile.temperature_c is None and t_k is not None:
        profile.temperature_c = t_k - 273.15

    if t_k is None:
        return derived

    # 1. Environmental Lapse Rate (-dT/dz) in K/km
    dtdz = _gradient_nan_safe(z, t_k)
    lapse_rate = -dtdz
    derived["lapse_rate"] = lapse_rate

    # 2. Local gravitational acceleration with altitude g(z) = g0 * (R / (R + z))^2
    r_body = body.radius_km
    g0 = body.surface_gravity
    gz = g0 * (r_body / (r_body + np.clip(z, 0.0, None))) ** 2

    # 3. Scale Height H = R_spec * T / g(z) in km
    r_spec = body.gas_constant_r
    with np.errstate(invalid="ignore", divide="ignore"):
        h_scale = (r_spec * t_k) / (gz * 1000.0)
    derived["scale_height"] = h_scale

    # 4. Pressure and Potential Temperature
    p_hpa = profile.pressure_hpa
    if p_hpa is not None and p_hpa.size == z.size:
        # Poisson constant kappa = R / Cp
        cp = body.isobaric_heat_capacity_cp
        kappa = r_spec / cp
        p_ref = body.reference_pressure_hpa

        with np.errstate(invalid="ignore", divide="ignore"):
            theta = t_k * (p_ref / np.where(p_hpa > 0, p_hpa, np.nan)) ** kappa
            # Mass density rho = P / (R * T) in kg/m^3 (P in Pa = hPa * 100)
            rho = (p_hpa * 100.0) / (r_spec * t_k)

        derived["potential_temperature"] = theta
        derived["density"] = rho

        # Brunt-Vaisala frequency squared N^2 = (g / theta) * (d_theta / dz)
        # Or equivalently: N^2 = (g / T) * (dT/dz + g/Cp)
        # Note: z is in km, so dtdz is in K/km = 1e-3 K/m; gz is in m/s^2; Cp is in J/(kg K)
        dtdz_m = dtdz / 1000.0
        with np.errstate(invalid="ignore", divide="ignore"):
            n2 = (gz / t_k) * (dtdz_m + gz / cp)
        derived["buoyancy_freq_sq"] = n2

    return derived


def compare_profiles_on_body(
    profiles: List[ObservationProfile],
    body: BodyInfo,
    altitude_step_km: float = 0.5,
    variable_name: str = "temperature_k",
) -> Dict[str, Any]:
    """Cross-compare multi-mission profiles for a target planetary body.

    Interpolates all profiles onto a uniform vertical grid and calculates
    multi-spacecraft composite mean, dispersion (+/- 1 sigma), and mission groups.
    """
    if not profiles:
        return {"grid_km": [], "composite_mean": [], "composite_std": [], "profiles": []}

    # Determine altitude span covering the observations
    all_z = [p.altitude_km for p in profiles if p.altitude_km is not None and p.altitude_km.size > 0]
    if not all_z:
        return {"grid_km": [], "composite_mean": [], "composite_std": [], "profiles": []}

    z_mins = [float(np.nanmin(z)) for z in all_z if np.isfinite(z).any()]
    z_maxs = [float(np.nanmax(z)) for z in all_z if np.isfinite(z).any()]
    if not z_mins or not z_maxs:
        return {"grid_km": [], "composite_mean": [], "composite_std": [], "profiles": []}

    grid_lo = max(0.0, float(np.min(z_mins)))
    grid_hi = float(np.max(z_maxs))
    if grid_hi <= grid_lo:
        grid_hi = grid_lo + 10.0

    num_steps = int(round((grid_hi - grid_lo) / altitude_step_km)) + 1
    z_grid = np.linspace(grid_lo, grid_hi, max(num_steps, 2))

    interpolated_matrix = []
    profile_summaries = []

    for p in profiles:
        # Extract target variable
        v = None
        if variable_name == "temperature_k":
            v = p.temperature_k
        elif variable_name == "temperature_c":
            v = p.temperature_c
        elif variable_name == "pressure_hpa":
            v = p.pressure_hpa
        elif variable_name == "refractivity":
            v = p.refractivity
        elif variable_name == "electron_density_cm3":
            v = p.electron_density_cm3
        elif variable_name in p.derived:
            v = p.derived[variable_name]

        if v is None or p.altitude_km is None or p.altitude_km.size < 2:
            continue

        z_p = p.altitude_km
        ok = np.isfinite(z_p) & np.isfinite(v)
        if ok.sum() < 2:
            continue

        z_clean = z_p[ok]
        v_clean = v[ok]
        sort_idx = np.argsort(z_clean)
        z_clean, v_clean = z_clean[sort_idx], v_clean[sort_idx]

        # Interpolate onto common body grid (never extrapolate beyond profile range)
        v_interp = np.interp(z_grid, z_clean, v_clean, left=np.nan, right=np.nan)
        interpolated_matrix.append(v_interp)

        profile_summaries.append({
            "observation_id": p.observation_id,
            "mission_id": p.mission_id,
            "instrument": p.instrument,
            "time_utc": p.time_utc,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "n_points": int(v_clean.size),
            "z_range_km": [round(float(np.min(z_clean)), 2), round(float(np.max(z_clean)), 2)],
        })

    if not interpolated_matrix:
        return {"grid_km": [round(float(z), 2) for z in z_grid],
                "composite_mean": [], "composite_std": [], "profiles": []}

    mat = np.array(interpolated_matrix)  # shape: (n_profiles, n_grid)
    with np.errstate(invalid="ignore"):
        mean_v = np.nanmean(mat, axis=0)
        std_v = np.nanstd(mat, axis=0)

    return {
        "body_id": body.id,
        "body_name": body.name,
        "variable_name": variable_name,
        "grid_km": [round(float(z), 2) for z in z_grid],
        "composite_mean": [None if not np.isfinite(x) else round(float(x), 4) for x in mean_v],
        "composite_std": [None if not np.isfinite(x) else round(float(x), 4) for x in std_v],
        "composite_plus_1sigma": [None if not np.isfinite(m + s) else round(float(m + s), 4) for m, s in zip(mean_v, std_v)],
        "composite_minus_1sigma": [None if not np.isfinite(m - s) else round(float(m - s), 4) for m, s in zip(mean_v, std_v)],
        "profile_count": len(profile_summaries),
        "profiles": profile_summaries,
    }
