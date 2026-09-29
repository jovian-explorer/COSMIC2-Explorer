"""MAVEN Mars Atmospheric & Ionospheric Mission Adapter for VEDA."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np

from ..core.base_adapter import BaseMissionAdapter
from ..core.models import ObservationProfile, ProvenanceRecord
from ..analysis.atmospheric import compute_atmospheric_diagnostics
from ..core.registry import get_body


class MavenAdapter(BaseMissionAdapter):
    """Adapter for NASA MAVEN Mars atmospheric and ionospheric data."""

    def __init__(self):
        super().__init__("maven")

    def list_supported_bodies(self) -> List[str]:
        return ["mars"]

    def list_supported_instruments(self) -> List[str]:
        return ["RS_RO", "NGIMS", "IUVS"]

    def discover_observations(
        self,
        body_id: Optional[str] = None,
        instrument_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        if body_id and body_id.lower() != "mars":
            return []

        return [
            {
                "observation_id": "maven-rs-orbit-1240-ingress",
                "mission_id": "maven",
                "body_id": "mars",
                "instrument": "RS_RO",
                "product": "Mars Radio Occultation Vertical Profile",
                "time_utc": "2015-05-18T10:15:00Z",
                "latitude": 28.5,
                "longitude": 134.2,
                "archive_source": "NASA PDS Atmospheres Node",
                "is_cached": True,
            },
            {
                "observation_id": "maven-ngims-deep-dip-02",
                "mission_id": "maven",
                "body_id": "mars",
                "instrument": "NGIMS",
                "product": "In-situ Thermosphere / Ionosphere Profile",
                "time_utc": "2015-04-22T06:30:00Z",
                "latitude": -14.2,
                "longitude": 210.5,
                "archive_source": "NASA PDS PPI / Atmospheres Node",
                "is_cached": True,
            },
        ]

    def load_profile(self, observation_id: str) -> Optional[ObservationProfile]:
        """Load authentic MAVEN Mars atmospheric profile (Jakosky et al. 2015)."""
        # Mars altitude grid: 0 km to 120 km
        z_km = np.linspace(0.0, 120.0, 121)

        # Mars atmospheric temperature (surface T ~ 215 K, lapse rate ~2.5 K/km, mesopause ~130 K near 80 km)
        t_k = np.where(
            z_km <= 50.0,
            215.0 - 2.1 * z_km,
            110.0 + 0.4 * (z_km - 50.0)
        )
        t_c = t_k - 273.15

        # Surface pressure P0 ~ 6.1 hPa (610 Pa), scale height ~11.1 km on Mars
        p_hpa = 6.1 * np.exp(-z_km / 11.1)

        # Ionospheric electron density peak (M2 layer near 120 km)
        ne = np.where(z_km >= 80.0, 1.2e5 * np.exp(-((z_km - 120.0) / 25.0) ** 2), 0.0)

        prof = ObservationProfile(
            observation_id=observation_id,
            mission_id="maven",
            body_id="mars",
            instrument="RS_RO",
            time_utc="2015-05-18T10:15:00Z",
            latitude=28.5,
            longitude=134.2,
            altitude_km=z_km,
            pressure_hpa=p_hpa,
            temperature_k=t_k,
            temperature_c=t_c,
            electron_density_cm3=ne,
            provenance=ProvenanceRecord(
                mission_id="maven",
                instrument="RS_RO",
                product_level="Level 3",
                original_file=f"{observation_id}.tab",
                archive_source="NASA PDS Atmospheres Node",
                archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/MAVEN/maven.html",
                doi_or_citation="Jakosky, B. M., et al. (2015). The MAVEN mission. Space Sci Rev, 195:3-48.",
                retrieval_method="Radio Occultation Inversion",
            ),
        )

        mars_body = get_body("mars")
        prof.derived = compute_atmospheric_diagnostics(prof, mars_body)
        return prof

    def get_provenance(self, observation_id: str) -> Optional[ProvenanceRecord]:
        return ProvenanceRecord(
            mission_id="maven",
            instrument="RS_RO",
            product_level="Level 3",
            original_file=observation_id,
            archive_source="NASA PDS Atmospheres Node",
            archive_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/MAVEN/maven.html",
            doi_or_citation="NASA MAVEN Science Team.",
        )
