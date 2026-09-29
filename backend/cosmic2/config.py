"""Application paths and persisted user settings.

Everything the app writes lives under a single writable root so the frozen
(.exe) build never tries to write next to the executable:

    %LOCALAPPDATA%\\COSMIC2Explorer\\        (Windows)
    ~/.local/share/COSMIC2Explorer/         (Linux/macOS fallback)
        cache/      downloaded + extracted netCDF granules
        exports/    generated figures and data files
        index.sqlite
        settings.json
        logs/
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

APP_NAME = "COSMIC2Explorer"
APP_TITLE = "COSMIC-2 Explorer"
APP_VERSION = "1.0.0"

# Lead Researcher and Maintainer Attribution
LEAD_RESEARCHER = (
    "Keshav Aggarwal, Research Associate at Space Physics Laboratory (SPL), "
    "Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), "
    "Thiruvananthapuram, Kerala, India (Former PMRF Scholar at DAASE, IIT Indore)"
)

# Data Availability Statement
DATA_AVAILABILITY_STATEMENT = (
    "The COSMIC-2 radio occultation soundings processed by this software are publicly available "
    "from the University Corporation for Atmospheric Research (UCAR) COSMIC Data Analysis and "
    "Archive Center (CDAAC) at https://data.cosmic.ucar.edu/ and the NOAA National Centers for "
    "Environmental Information (NCEI) at https://www.ncei.noaa.gov/data/gps-radio-occultation/. "
    "Processing, quality control, and visual analysis are performed locally using COSMIC-2 Explorer."
)

DATA_LICENSES = {
    "cdaac": {
        "name": "UCAR CDAAC Data Terms of Use",
        "type": "Open Access / Public Domain",
        "url": "https://www.cosmic.ucar.edu/what-we-do/cosmic-2/data",
        "terms": "Freely available for scientific research, operational weather prediction, and educational use under UCAR open data policy.",
    },
    "noaa": {
        "name": "NOAA Open Data Policy",
        "type": "U.S. Government Work / CC0-Compatible",
        "url": "https://www.ncei.noaa.gov/",
        "terms": "Public domain information freely accessible to the worldwide scientific community.",
    },
    "software": {
        "name": "MIT License",
        "type": "Open Source",
        "copyright": "Copyright (c) 2026 Keshav Aggarwal, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO",
        "url": "https://github.com/keshav-aggarwal/COSMIC2-Explorer/blob/main/LICENSE",
        "terms": "Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files.",
    },
}

DATA_PORTALS = [
    {
        "id": "cdaac",
        "name": "UCAR CDAAC (COSMIC Data Analysis and Archive Center)",
        "agency": "UCAR / NSF / NOAA / NASA / USSF",
        "url": "https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        "portal_url": "https://www.cosmic.ucar.edu/what-we-do/cosmic-2/data",
        "description": "Primary repository for COSMIC-2 neutral atmosphere (atmPrf, wetPf2) and ionospheric (ionPrf, scnLv2, ivmL2m) products.",
        "streams": ["nrt", "rapid", "postProc", "provisional"],
    },
    {
        "id": "noaa_ncei",
        "name": "NOAA NCEI GPS Radio Occultation Archive",
        "agency": "NOAA / NESDIS",
        "url": "https://www.ncei.noaa.gov/data/gps-radio-occultation/",
        "portal_url": "https://www.nesdis.noaa.gov/current-satellite-missions/currently-flying/formosat-7-cosmic-2",
        "description": "Long-term operational archive for FORMOSAT-7 / COSMIC-2 constellation observations.",
        "streams": ["operational", "reanalysis"],
    },
    {
        "id": "tasa",
        "name": "Taiwan Space Agency (TASA) FORMOSAT-7 Data Portal",
        "agency": "TASA / NSPO",
        "url": "https://www.tasa.org.tw/en-US/",
        "portal_url": "https://tacc.cwb.gov.tw/",
        "description": "Co-lead agency operating the FORMOSAT-7 / COSMIC-2 satellite constellation.",
        "streams": ["nrt", "postcal"],
    },
    {
        "id": "nasa_cddis",
        "name": "NASA CDDIS (Crustal Dynamics Data Information System)",
        "agency": "NASA Earth Science Data and Information System (ESDIS)",
        "url": "https://cddis.nasa.gov/archive/gnss/products/ionex/",
        "portal_url": "https://cddis.nasa.gov/",
        "description": "Global GNSS tracking and precise orbit determination (POD) data portal.",
        "streams": ["pod", "ionex"],
    },
    {
        "id": "isro_issdc",
        "name": "ISRO ISSDC / PRADAN (Planetary & Space Science Data Archive)",
        "agency": "Indian Space Research Organisation (ISRO)",
        "url": "https://pradan.issdc.gov.in/",
        "portal_url": "https://www.issdc.gov.in/",
        "description": "Space Physics Laboratory (SPL/VSSC) planetary radio science and exospheric instruments repository.",
        "streams": ["ch2_dfrs", "mom_menca", "chace2"],
    },
]

# Public CDAAC archive root (no credentials required).
CDAAC_BASE = "https://data.cosmic.ucar.edu/gnss-ro"
# Data citation, quoted in the form UCAR suggests on its COSMIC-2 data page
# (https://www.cosmic.ucar.edu/what-we-do/cosmic-2/data). "{access_date}" is
# filled in by the exporter with the date the user actually retrieved the data.
CITATION_TEMPLATE = (
    "UCAR COSMIC Program, 2019: COSMIC-2 Data Products [Data set]. "
    "UCAR/NCAR - COSMIC, Access date {access_date}, "
    "https://doi.org/10.5065/T353-C093"
)
CITATION_SOURCE = "https://www.cosmic.ucar.edu/what-we-do/cosmic-2/data"


def citation(access_date=None) -> str:
    """Suggested data citation, with today's access date unless given."""
    import datetime as _dt
    d = access_date or _dt.date.today().isoformat()
    return CITATION_TEMPLATE.format(access_date=d)


def _data_root() -> Path:
    env = os.environ.get("COSMIC2_EXPLORER_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / APP_NAME
    return Path(os.path.expanduser("~")) / ".local" / "share" / APP_NAME


DATA_ROOT = _data_root()
CACHE_DIR = DATA_ROOT / "cache"
EXPORT_DIR = DATA_ROOT / "exports"
LOG_DIR = DATA_ROOT / "logs"
DB_PATH = DATA_ROOT / "index.sqlite"
SETTINGS_PATH = DATA_ROOT / "settings.json"


def bundle_root() -> Path:
    """Directory that holds the read-only frontend assets.

    PyInstaller unpacks ``--add-data`` payloads into ``sys._MEIPASS``; in a
    source checkout the frontend sits one level above ``backend/``.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[2]


def frontend_dir() -> Path:
    return bundle_root() / "frontend"


def sampledata_dir() -> Path:
    return bundle_root() / "sampledata"


def ensure_dirs() -> None:
    for d in (DATA_ROOT, CACHE_DIR, EXPORT_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


@dataclass
class Settings:
    """User-tunable options, persisted as JSON."""

    # Download behaviour
    max_profiles_per_download: int = 400
    concurrent_downloads: int = 2
    request_timeout_s: int = 120
    listing_cache_hours: int = 6
    # Disk guard rails
    cache_quota_gb: float = 20.0
    warn_download_mb: int = 500
    # Science defaults
    default_stream: str = "nrt"
    default_product: str = "wetPf2"
    qc_require_good: bool = True
    grid_top_km: float = 60.0
    grid_step_km: float = 0.2
    # Presentation
    plot_dpi: int = 300
    plot_theme: str = "light"
    ui_theme: str = "light"
    ui_font_size: int = 14
    ui_mode: str = "educational"  # "educational" or "research"
    units_temperature: str = "C"  # "C" or "K"
    explain_mode: bool = True  # plain-language captions for non-specialists
    # Network
    user_agent: str = f"{APP_NAME}/{APP_VERSION} (desktop client; python-requests)"
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        ensure_dirs()
        if SETTINGS_PATH.exists():
            try:
                raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            known = {f for f in cls.__dataclass_fields__}
            return cls(**{k: v for k, v in raw.items() if k in known})
        obj = cls()
        obj.save()
        return obj

    def save(self) -> None:
        ensure_dirs()
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)

    def update(self, **kw) -> "Settings":
        for k, v in kw.items():
            if k in self.__dataclass_fields__:
                setattr(self, k, v)
        self.save()
        return self


SETTINGS = Settings.load()
