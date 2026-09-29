"""COSMIC-2 Earth GNSS Radio Occultation Mission Adapter for VEDA."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from ..core.base_adapter import BaseMissionAdapter
from ..core.models import ObservationProfile, ProvenanceRecord
from ..analysis.atmospheric import compute_atmospheric_diagnostics
from ..core.registry import get_body


class Cosmic2Adapter(BaseMissionAdapter):
    """Adapter for COSMIC-2 constellation radio occultation data."""

    def __init__(self, sampledata_dir: Optional[str] = None):
        super().__init__("cosmic2")
        self.sampledata_dir = sampledata_dir or str(
            Path(__file__).resolve().parents[3] / "sampledata"
        )

    def list_supported_bodies(self) -> List[str]:
        return ["earth"]

    def list_supported_instruments(self) -> List[str]:
        return ["TGRS", "IVM"]

    def discover_observations(
        self,
        body_id: Optional[str] = None,
        instrument_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if body_id and body_id.lower() != "earth":
            return []

        results = []
        d = Path(self.sampledata_dir)
        if d.is_dir():
            for f in sorted(d.glob("*_nc")):
                name = f.name
                product = name.split("_")[0] if "_" in name else "unknown"
                results.append({
                    "observation_id": name,
                    "mission_id": "cosmic2",
                    "body_id": "earth",
                    "instrument": "TGRS" if product in ("wetPf2", "atmPrf", "ionPrf", "scnLv2") else "IVM",
                    "product": product,
                    "time_utc": "2026-07-19T00:00:00Z",  # extracted from day 200 of 2026
                    "archive_source": "UCAR CDAAC",
                    "is_cached": True,
                    "file_path": str(f),
                })
                if len(results) >= limit:
                    break
        return results

    def load_profile(self, observation_id: str) -> Optional[ObservationProfile]:
        d = Path(self.sampledata_dir)
        target_file = d / observation_id
        if not target_file.exists():
            for f in d.glob(f"*{observation_id}*"):
                target_file = f
                break

        if not target_file.exists():
            return None

        # Import readers from existing cosmic2 package
        try:
            from cosmic2 import readers
            product = target_file.name.split("_")[0] if "_" in target_file.name else "wetPf2"
            granule = readers.load(str(target_file), product)
            data = granule.data

            z = data.get("MSL_alt", np.array([]))
            p = data.get("Pres", data.get("pres_dry"))
            t_c = data.get("Temp", data.get("temp_dry"))
            t_k = t_c + 273.15 if t_c is not None else None
            ref = data.get("Ref", data.get("ref"))
            ne = data.get("ELEC_dens")

            prof = ObservationProfile(
                observation_id=observation_id,
                mission_id="cosmic2",
                body_id="earth",
                instrument="TGRS",
                time_utc=granule.meta.get("time_utc") or "2026-07-19T00:00:00Z",
                latitude=granule.meta.get("lat"),
                longitude=granule.meta.get("lon"),
                altitude_km=z,
                pressure_hpa=p,
                temperature_k=t_k,
                temperature_c=t_c,
                refractivity=ref,
                electron_density_cm3=ne,
                provenance=ProvenanceRecord(
                    mission_id="cosmic2",
                    instrument="TGRS",
                    product_level="Level 2",
                    original_file=target_file.name,
                    archive_source="UCAR CDAAC",
                    archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
                    doi_or_citation="UCAR/CDAAC COSMIC-2 Neutral Atmosphere and Ionosphere Data",
                    retrieval_method="1D-Var / Abel Inversion",
                ),
            )

            # Compute Earth thermodynamic diagnostics
            prof.derived = compute_atmospheric_diagnostics(prof, get_body("earth"))
            return prof

        except Exception as e:
            return None

    def get_provenance(self, observation_id: str) -> Optional[ProvenanceRecord]:
        return ProvenanceRecord(
            mission_id="cosmic2",
            instrument="TGRS",
            product_level="Level 2",
            original_file=observation_id,
            archive_source="UCAR CDAAC",
            archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
            doi_or_citation="UCAR/CDAAC COSMIC-2 Data (2020-present)",
        )
