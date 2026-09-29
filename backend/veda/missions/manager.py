"""Central Mission & Body Manager for VEDA.

Coordinates discovery, profile retrieval, imaging extraction, and cross-mission
comparative analysis across all supported planetary spacecraft.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from ..core.base_adapter import BaseMissionAdapter
from ..core.models import ObservationImage, ObservationProfile, ProvenanceRecord
from ..core.registry import BODIES, MISSIONS, get_body, get_mission
from ..analysis.atmospheric import compare_profiles_on_body

# Import adapters
from .cosmic2_adapter import Cosmic2Adapter
from .akatsuki_adapter import AkatsukiAdapter
from .new_horizons_adapter import NewHorizonsAdapter
from .juno_adapter import JunoAdapter
from .cassini_adapter import CassiniAdapter
from .vex_adapter import VenusExpressAdapter
from .maven_adapter import MavenAdapter
from .bepicolombo_adapter import BepiColomboAdapter
from .galileo_adapter import GalileoAdapter


class MissionManager:
    """Singleton manager aggregating all mission adapters."""

    def __init__(self):
        self._adapters: Dict[str, BaseMissionAdapter] = {}
        self._register_default_adapters()

    def _register_default_adapters(self) -> None:
        self.register_adapter(Cosmic2Adapter())
        self.register_adapter(AkatsukiAdapter())
        self.register_adapter(NewHorizonsAdapter())
        self.register_adapter(JunoAdapter())
        self.register_adapter(CassiniAdapter())
        self.register_adapter(VenusExpressAdapter())
        self.register_adapter(MavenAdapter())
        self.register_adapter(BepiColomboAdapter())
        self.register_adapter(GalileoAdapter())

    def register_adapter(self, adapter: BaseMissionAdapter) -> None:
        self._adapters[adapter.mission_id.lower()] = adapter

    def get_adapter(self, mission_id: str) -> Optional[BaseMissionAdapter]:
        return self._adapters.get(mission_id.lower())

    def list_missions(self) -> List[str]:
        return list(self._adapters.keys())

    def discover_by_mission(
        self,
        mission_id: str,
        body_id: Optional[str] = None,
        instrument_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search observations available for a specific spacecraft mission."""
        adapter = self.get_adapter(mission_id)
        if not adapter:
            return []
        return adapter.discover_observations(body_id=body_id, instrument_id=instrument_id, limit=limit)

    def discover_by_body(
        self,
        body_id: str,
        mission_ids: Optional[List[str]] = None,
        limit_per_mission: int = 25,
    ) -> Dict[str, Any]:
        """Search observations across all missions for a specific target body."""
        body = get_body(body_id)
        if not body:
            return {"body_id": body_id, "observations": [], "missions": []}

        target_missions = mission_ids or body.supported_missions
        all_obs: List[Dict[str, Any]] = []
        missions_found: List[str] = []

        for mid in target_missions:
            adapter = self.get_adapter(mid)
            if adapter and (not body_id or body_id.lower() in [b.lower() for b in adapter.list_supported_bodies()]):
                obs = adapter.discover_observations(body_id=body_id, limit=limit_per_mission)
                if obs:
                    all_obs.extend(obs)
                    missions_found.append(mid)

        return {
            "body_id": body.id,
            "body_name": body.name,
            "category": body.category,
            "radius_km": body.radius_km,
            "surface_gravity": body.surface_gravity,
            "gas_constant_r": body.gas_constant_r,
            "reference_pressure_hpa": body.reference_pressure_hpa,
            "missions_queried": target_missions,
            "missions_with_data": list(set(missions_found)),
            "observations_count": len(all_obs),
            "observations": all_obs,
        }

    def load_profile(self, mission_id: str, observation_id: str) -> Optional[ObservationProfile]:
        adapter = self.get_adapter(mission_id)
        if not adapter:
            return None
        return adapter.load_profile(observation_id)

    def load_image(self, mission_id: str, observation_id: str) -> Optional[ObservationImage]:
        adapter = self.get_adapter(mission_id)
        if not adapter:
            return None
        return adapter.load_image(observation_id)

    def compare_on_body(
        self,
        body_id: str,
        selected_observations: List[Dict[str, str]],  # list of {"mission_id": ..., "observation_id": ...}
        variable_name: str = "temperature_k",
    ) -> Dict[str, Any]:
        """Load multiple profiles across missions and compute cross-mission comparison."""
        body = get_body(body_id)
        if not body:
            return {"error": f"Unknown planetary body: {body_id}"}

        loaded_profiles: List[ObservationProfile] = []
        for item in selected_observations:
            m_id = item.get("mission_id")
            o_id = item.get("observation_id")
            if m_id and o_id:
                prof = self.load_profile(m_id, o_id)
                if prof:
                    loaded_profiles.append(prof)

        # Compute multi-mission composite
        return compare_profiles_on_body(
            profiles=loaded_profiles,
            body=body,
            altitude_step_km=0.5 if body_id in ("earth", "mars", "pluto", "venus") else 2.0,
            variable_name=variable_name,
        )


# Global singleton instance
_GLOBAL_MANAGER: Optional[MissionManager] = None

def get_mission_manager() -> MissionManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = MissionManager()
    return _GLOBAL_MANAGER
