"""FastAPI route definitions for VEDA multi-mission scientific platform."""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ..core.registry import BODIES, MISSIONS, get_body, get_mission, list_bodies, list_missions, get_missions_for_body
from ..missions.manager import get_mission_manager
from ..readers.fits_reader import (
    compute_image_histogram,
    extract_photometric_transect,
    load_fits_image,
    render_to_png,
)

router = APIRouter(prefix="/api/veda", tags=["VEDA Multi-Mission"])


# ---------------------------------------------------------------------------
# Platform & Metadata Endpoints
# ---------------------------------------------------------------------------

@router.get("/info")
def platform_info() -> dict:
    """Platform overview, version, and supported assets."""
    mgr = get_mission_manager()
    return {
        "title": "VEDA: Visualization, Exploration, and Data Analysis",
        "version": "2.0.0",
        "description": "Multi-Mission Planetary Science Visualization & Comparative Analysis Platform",
        "agencies_supported": ["NASA", "ESA", "JAXA", "NOAA"],
        "missions_count": len(mgr.list_missions()),
        "bodies_count": len(BODIES),
        "missions": mgr.list_missions(),
        "bodies": list(BODIES.keys()),
    }


@router.get("/missions")
def get_missions() -> List[dict]:
    """List all supported spacecraft missions."""
    return list_missions()


@router.get("/missions/{mission_id}")
def get_mission_details(mission_id: str) -> dict:
    """Get metadata and instrument payloads for a specific mission."""
    m = get_mission(mission_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")
    return {
        "id": m.id,
        "name": m.name,
        "agency": m.agency,
        "launch_date": m.launch_date,
        "mission_status": m.mission_status,
        "primary_targets": m.primary_targets,
        "authoritative_archive": m.authoritative_archive,
        "archive_url": m.archive_url,
        "citation": m.citation,
        "description": m.description,
        "instruments": [
            {
                "id": i.id,
                "name": i.name,
                "type": i.instrument_type,
                "targets": i.measurement_targets,
                "description": i.description,
            }
            for i in m.instruments
        ],
    }


@router.get("/bodies")
def get_planetary_bodies() -> List[dict]:
    """List all supported target bodies with physical constants."""
    return list_bodies()


@router.get("/bodies/{body_id}")
def get_body_details(body_id: str) -> dict:
    """Get detailed planetary constants and missions that observed this body."""
    b = get_body(body_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"Body '{body_id}' not found")
    missions = get_missions_for_body(body_id)
    return {
        "id": b.id,
        "name": b.name,
        "category": b.category,
        "radius_km": b.radius_km,
        "surface_gravity": b.surface_gravity,
        "mean_molecular_weight": b.mean_molecular_weight,
        "gas_constant_r": b.gas_constant_r,
        "reference_pressure_hpa": b.reference_pressure_hpa,
        "atmospheric_composition": b.atmospheric_composition,
        "description": b.description,
        "supported_missions": b.supported_missions,
        "missions": missions,
    }


# ---------------------------------------------------------------------------
# MODE 1: BY MISSION
# ---------------------------------------------------------------------------

@router.get("/explore/mission/{mission_id}")
def explore_by_mission(
    mission_id: str,
    body_id: Optional[str] = None,
    instrument_id: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Retrieve observations available for a selected spacecraft mission."""
    mgr = get_mission_manager()
    m = get_mission(mission_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")

    obs = mgr.discover_by_mission(mission_id, body_id=body_id, instrument_id=instrument_id, limit=limit)
    return {
        "mission_id": m.id,
        "mission_name": m.name,
        "agency": m.agency,
        "archive": m.authoritative_archive,
        "archive_url": m.archive_url,
        "total_found": len(obs),
        "observations": obs,
    }


# ---------------------------------------------------------------------------
# MODE 2: BY PLANET / TARGET BODY
# ---------------------------------------------------------------------------

@router.get("/explore/body/{body_id}")
def explore_by_body(
    body_id: str,
    missions: Optional[str] = None,  # comma-separated mission IDs e.g. "akatsuki,vex"
    limit_per_mission: int = 25,
) -> dict:
    """Retrieve multi-mission observations for a selected target body."""
    mgr = get_mission_manager()
    b = get_body(body_id)
    if not b:
        raise HTTPException(status_code=404, detail=f"Body '{body_id}' not found")

    mission_list = [m.strip() for m in missions.split(",")] if missions else None
    return mgr.discover_by_body(body_id, mission_ids=mission_list, limit_per_mission=limit_per_mission)


class CrossCompareRequest(BaseModel):
    observations: List[Dict[str, str]]  # list of {"mission_id": ..., "observation_id": ...}
    variable: str = "temperature_k"  # "temperature_k", "temperature_c", "pressure_hpa", "lapse_rate", "buoyancy_freq_sq"


@router.post("/compare/body/{body_id}")
def compare_missions_on_body(
    body_id: str,
    req: CrossCompareRequest,
) -> dict:
    """Multi-mission comparative vertical profile overlay and composite calculation."""
    mgr = get_mission_manager()
    return mgr.compare_on_body(body_id, req.observations, variable_name=req.variable)


# ---------------------------------------------------------------------------
# Observation Data Retrieval (Profiles & Images)
# ---------------------------------------------------------------------------

@router.get("/profile/{mission_id}/{observation_id:path}")
def get_observation_profile(
    mission_id: str,
    observation_id: str,
    decimate_max: int = 600,
) -> dict:
    """Load normalized 1D profile with body-specific derived thermodynamics."""
    mgr = get_mission_manager()
    prof = mgr.load_profile(mission_id, observation_id)
    if not prof:
        raise HTTPException(status_code=404, detail=f"Profile '{observation_id}' for mission '{mission_id}' not found")
    return prof.to_dict(decimate_max=decimate_max)


@router.get("/image/{mission_id}/{observation_id:path}")
def get_image_metadata(
    mission_id: str,
    observation_id: str,
) -> dict:
    """Get metadata for an astronomical camera observation."""
    mgr = get_mission_manager()
    img = mgr.load_image(mission_id, observation_id)
    if not img:
        raise HTTPException(status_code=404, detail=f"Image observation '{observation_id}' not found")
    return img.to_dict()


@router.get("/image/{mission_id}/{observation_id:path}/render")
def render_image(
    mission_id: str,
    observation_id: str,
    stretch: str = "zscale",  # "zscale", "percentile", "linear", "log", "sqrt", "asinh", "histeq"
    colormap: str = "inferno",  # "gray", "inferno", "viridis", "plasma", "magma", "cividis", "twilight"
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    max_dim: int = 1024,
) -> Response:
    """Render astronomical science image array to stretched PNG."""
    mgr = get_mission_manager()
    img = mgr.load_image(mission_id, observation_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image observation not found")

    # If local FITS file exists, render with requested astronomical stretch
    if img.local_path and (img.local_path.endswith(".fit") or img.local_path.endswith(".fits")):
        try:
            fits_data = load_fits_image(img.local_path)
            png_bytes = render_to_png(fits_data.primary_data, stretch_method=stretch,
                                      colormap=colormap, vmin=vmin, vmax=vmax, max_dimension=max_dim)
            return Response(content=png_bytes, media_type="image/png")
        except Exception as e:
            pass

    # If browse image is available locally, serve it
    if img.local_path and (img.local_path.endswith(".jpg") or img.local_path.endswith(".png")):
        with open(img.local_path, "rb") as f:
            return Response(content=f.read(), media_type="image/jpeg" if img.local_path.endswith(".jpg") else "image/png")

    raise HTTPException(status_code=404, detail="Image data unavailable")


class TransectRequest(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float
    num_samples: int = 200


@router.post("/image/{mission_id}/{observation_id:path}/transect")
def get_image_transect(
    mission_id: str,
    observation_id: str,
    req: TransectRequest,
) -> dict:
    """Compute 1D photometric line slice along (x0, y0) -> (x1, y1)."""
    mgr = get_mission_manager()
    img = mgr.load_image(mission_id, observation_id)
    if not img or not img.local_path:
        raise HTTPException(status_code=404, detail="Image not found for transect")

    try:
        fits_data = load_fits_image(img.local_path)
        return extract_photometric_transect(fits_data.primary_data, req.x0, req.y0, req.x1, req.y1, req.num_samples)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transect computation failed: {e}")


@router.get("/image/{mission_id}/{observation_id:path}/histogram")
def get_image_histogram_endpoint(
    mission_id: str,
    observation_id: str,
    bins: int = 100,
) -> dict:
    """Compute pixel intensity histogram and CDF."""
    mgr = get_mission_manager()
    img = mgr.load_image(mission_id, observation_id)
    if not img or not img.local_path:
        raise HTTPException(status_code=404, detail="Image not found for histogram")

    try:
        fits_data = load_fits_image(img.local_path)
        return compute_image_histogram(fits_data.primary_data, num_bins=bins)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Histogram computation failed: {e}")
