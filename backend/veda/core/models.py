"""Unified scientific data models for VEDA multi-mission platform.

Defines standardized representations for planetary bodies, spacecraft missions,
atmospheric/ionospheric profiles, and astronomical imaging products.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np


@dataclass
class BodyInfo:
    """Astronomical planetary body or moon with thermodynamic properties."""
    id: str
    name: str
    category: str  # "terrestrial_planet", "gas_giant", "ice_giant", "dwarf_planet", "moon", "kbo"
    radius_km: float
    surface_gravity: float  # m/s^2 at reference surface
    mean_molecular_weight: float  # g/mol
    gas_constant_r: float  # J / (kg K), R_specific = R_universal / mu
    isobaric_heat_capacity_cp: float  # J / (kg K)
    reference_pressure_hpa: float  # hPa (for potential temperature calculation)
    atmospheric_composition: Dict[str, float]  # gas name -> fraction percentage
    description: str
    supported_missions: List[str] = field(default_factory=list)


@dataclass
class InstrumentInfo:
    """Scientific payload instrument definition."""
    id: str
    name: str
    instrument_type: str  # "radio_science", "camera", "spectrometer", "plasma", "dust_counter"
    measurement_targets: List[str]  # e.g. ["neutral_atmosphere", "ionosphere", "surface", "space_weather"]
    description: str


@dataclass
class MissionInfo:
    """Planetary exploration spacecraft mission."""
    id: str
    name: str
    agency: str  # "NASA", "ESA", "JAXA", "NOAA", "NASA/ESA/ASI"
    launch_date: str
    mission_status: str  # "completed", "extended_mission", "operational"
    primary_targets: List[str]  # body IDs
    instruments: List[InstrumentInfo] = field(default_factory=list)
    authoritative_archive: str = ""
    archive_url: str = ""
    citation: str = ""
    description: str = ""


@dataclass
class ProvenanceRecord:
    """Provenance audit trail for a scientific product."""
    mission_id: str
    instrument: str
    product_level: str
    original_file: str
    archive_source: str
    archive_url: str
    doi_or_citation: str
    retrieval_method: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObservationProfile:
    """Unified 1D vertical profile (atmosphere, ionosphere, plasma)."""
    observation_id: str
    mission_id: str
    body_id: str
    instrument: str
    time_utc: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_km: np.ndarray = field(default_factory=lambda: np.array([]))
    pressure_hpa: Optional[np.ndarray] = None
    temperature_k: Optional[np.ndarray] = None
    temperature_c: Optional[np.ndarray] = None
    refractivity: Optional[np.ndarray] = None
    electron_density_cm3: Optional[np.ndarray] = None
    derived: Dict[str, np.ndarray] = field(default_factory=dict)
    provenance: Optional[ProvenanceRecord] = None
    raw_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, decimate_max: int = 600) -> dict:
        """Serialize for frontend delivery with smart decimation for performance."""
        def _dec(arr: Optional[np.ndarray]) -> Optional[List[Optional[float]]]:
            if arr is None or arr.size == 0:
                return None
            flat = np.asarray(arr, dtype=np.float64)
            if decimate_max > 0 and flat.size > decimate_max:
                idx = np.linspace(0, flat.size - 1, decimate_max).round().astype(int)
                flat = flat[idx]
            return [None if not np.isfinite(x) else round(float(x), 5) for x in flat]

        prov_dict = None
        if self.provenance:
            prov_dict = {
                "mission_id": self.provenance.mission_id,
                "instrument": self.provenance.instrument,
                "product_level": self.provenance.product_level,
                "original_file": self.provenance.original_file,
                "archive_source": self.provenance.archive_source,
                "archive_url": self.provenance.archive_url,
                "citation": self.provenance.doi_or_citation,
                "retrieval_method": self.provenance.retrieval_method,
            }

        der_dict = {}
        for k, v in self.derived.items():
            der_dict[k] = _dec(v)

        return {
            "observation_id": self.observation_id,
            "mission_id": self.mission_id,
            "body_id": self.body_id,
            "instrument": self.instrument,
            "time_utc": self.time_utc,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_km": _dec(self.altitude_km),
            "pressure_hpa": _dec(self.pressure_hpa),
            "temperature_k": _dec(self.temperature_k),
            "temperature_c": _dec(self.temperature_c),
            "refractivity": _dec(self.refractivity),
            "electron_density_cm3": _dec(self.electron_density_cm3),
            "derived": der_dict,
            "provenance": prov_dict,
            "n_points": int(self.altitude_km.size) if self.altitude_km is not None else 0,
        }


@dataclass
class ObservationImage:
    """Unified astronomical camera imaging observation product."""
    observation_id: str
    mission_id: str
    body_id: str
    instrument: str
    time_utc: str
    target_name: str
    filter_name: str
    exposure_seconds: float
    target_distance_km: Optional[float] = None
    solar_phase_angle_deg: Optional[float] = None
    browse_url: str = ""
    fits_url: str = ""
    local_path: Optional[str] = None
    provenance: Optional[ProvenanceRecord] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "mission_id": self.mission_id,
            "body_id": self.body_id,
            "instrument": self.instrument,
            "time_utc": self.time_utc,
            "target_name": self.target_name,
            "filter_name": self.filter_name,
            "exposure_seconds": self.exposure_seconds,
            "target_distance_km": self.target_distance_km,
            "solar_phase_angle_deg": self.solar_phase_angle_deg,
            "browse_url": self.browse_url,
            "fits_url": self.fits_url,
            "is_cached": bool(self.local_path),
            "provenance": {
                "archive_source": self.provenance.archive_source if self.provenance else "",
                "archive_url": self.provenance.archive_url if self.provenance else "",
                "citation": self.provenance.doi_or_citation if self.provenance else "",
            } if self.provenance else None,
        }
