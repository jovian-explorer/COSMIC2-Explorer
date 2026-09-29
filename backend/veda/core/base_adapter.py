"""Abstract base adapter interface for VEDA mission plugins.

Ensures every spacecraft mission integration adheres to a strictly normalized
contract for data discovery, profile loading, imaging retrieval, and provenance.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .models import ObservationImage, ObservationProfile, ProvenanceRecord


class BaseMissionAdapter(ABC):
    """Abstract interface that all VEDA mission adapters must implement."""

    def __init__(self, mission_id: str):
        self.mission_id = mission_id

    @abstractmethod
    def list_supported_bodies(self) -> List[str]:
        """Return list of planetary body IDs observed by this mission."""
        pass

    @abstractmethod
    def list_supported_instruments(self) -> List[str]:
        """Return list of instrument IDs supported by this adapter."""
        pass

    @abstractmethod
    def discover_observations(
        self,
        body_id: Optional[str] = None,
        instrument_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query available observations matching search criteria."""
        pass

    @abstractmethod
    def load_profile(self, observation_id: str) -> Optional[ObservationProfile]:
        """Load and normalize a 1D vertical profile (atmosphere/ionosphere/plasma)."""
        pass

    def load_image(self, observation_id: str) -> Optional[ObservationImage]:
        """Load an imaging observation (optional, for camera payloads)."""
        return None

    @abstractmethod
    def get_provenance(self, observation_id: str) -> Optional[ProvenanceRecord]:
        """Retrieve full authoritative archive provenance."""
        pass
