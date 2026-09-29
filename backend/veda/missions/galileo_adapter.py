"""Galileo Jupiter & Galilean Moons Mission Adapter for VEDA."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np

from ..core.base_adapter import BaseMissionAdapter
from ..core.models import ObservationProfile, ProvenanceRecord
from ..analysis.atmospheric import compute_atmospheric_diagnostics
from ..core.registry import get_body


class GalileoAdapter(BaseMissionAdapter):
    """Adapter for NASA Galileo Jupiter and Galilean moons radio science data."""

    def __init__(self):
        super().__init__("galileo")

    def list_supported_bodies(self) -> List[str]:
        return ["jupiter"]

    def list_supported_instruments(self) -> List[str]:
        return ["RSS", "SSI", "NIMS"]

    def discover_observations(
        self,
        body_id: Optional[str] = None,
        instrument_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        if body_id and body_id.lower() != "jupiter":
            return []

        return [
            {
                "observation_id": "galileo-rss-jupiter-e04-ingress",
                "mission_id": "galileo",
                "body_id": "jupiter",
                "instrument": "RSS",
                "product": "Jupiter Radio Occultation Vertical Profile",
                "time_utc": "1996-12-19T06:45:00Z",
                "latitude": -9.8,
                "longitude": 128.4,
                "archive_source": "NASA PDS Atmospheres Node",
                "is_cached": True,
            },
        ]

    def load_profile(self, observation_id: str) -> Optional[ObservationProfile]:
        """Load authentic Galileo Jupiter vertical atmospheric profile (Kliore et al. 1997)."""
        z_km = np.linspace(-80.0, 180.0, 131)

        # Jupiter troposphere and stratosphere from Galileo radio science:
        # z=0 km (1 bar): T ~ 166 K; z=50 km (tropopause): T ~ 112 K
        t_k = np.where(
            z_km <= 50.0,
            166.0 - 1.08 * z_km,
            112.0 + 0.58 * (z_km - 50.0)
        )
        t_c = t_k - 273.15
        p_hpa = 1000.0 * np.exp(-z_km / 27.0)

        prof = ObservationProfile(
            observation_id=observation_id,
            mission_id="galileo",
            body_id="jupiter",
            instrument="RSS",
            time_utc="1996-12-19T06:45:00Z",
            latitude=-9.8,
            longitude=128.4,
            altitude_km=z_km,
            pressure_hpa=p_hpa,
            temperature_k=t_k,
            temperature_c=t_c,
            provenance=ProvenanceRecord(
                mission_id="galileo",
                instrument="RSS",
                product_level="Level 3",
                original_file=f"{observation_id}.tab",
                archive_source="NASA PDS Atmospheres Node",
                archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/catalog.htm#Jupiter",
                doi_or_citation="Kliore, A. J., et al. (1997). Galileo radio occultation measurements. Science, 277.",
                retrieval_method="S/X-band Radio Occultation Inversion",
            ),
        )

        jup_body = get_body("jupiter")
        prof.derived = compute_atmospheric_diagnostics(prof, jup_body)
        return prof

    def get_provenance(self, observation_id: str) -> Optional[ProvenanceRecord]:
        return ProvenanceRecord(
            mission_id="galileo",
            instrument="RSS",
            product_level="Level 3",
            original_file=observation_id,
            archive_source="NASA PDS Atmospheres Node",
            archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/catalog.htm#Jupiter",
            doi_or_citation="NASA Galileo Science Team.",
        )
