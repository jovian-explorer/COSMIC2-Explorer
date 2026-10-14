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
APP_VERSION = "0.1.0"

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
        "type": "Open access (no account needed)",
        "url": "https://www.cosmic.ucar.edu/what-we-do/cosmic-2/data",
        "terms": "Downloadable from the CDAAC archive without registration. UCAR asks users to cite the data set as UCAR COSMIC Program (2019), COSMIC-2 Data Products, doi:10.5065/T353-C093.",
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
        "url": "https://github.com/jovian-explorer/COSMIC2-Explorer/blob/main/LICENSE",
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
        "description": "NOAA's long-term archive of radio occultation data, including FORMOSAT-7 / COSMIC-2. COSMIC-2 Explorer downloads from CDAAC only, but reads the same netCDF products if you import them.",
        "streams": ["operational", "reanalysis"],
    },
    {
        "id": "tasa",
        "name": "Taiwan Space Agency (TASA) FORMOSAT-7 Data Portal",
        "agency": "TASA / NSPO",
        "url": "https://www.tasa.org.tw/en-US/",
        "portal_url": "https://tacc.cwb.gov.tw/",
        "description": "Taiwan's space agency, which operates the FORMOSAT-7 / COSMIC-2 satellites with NOAA. Listed for reference.",
        "streams": ["nrt", "postcal"],
    },
    {
        "id": "nasa_cddis",
        "name": "NASA CDDIS (Crustal Dynamics Data Information System)",
        "agency": "NASA Earth Science Data and Information System (ESDIS)",
        "url": "https://cddis.nasa.gov/archive/gnss/products/ionex/",
        "portal_url": "https://cddis.nasa.gov/",
        "description": "Global GNSS tracking, precise orbit and ionosphere (IONEX) products. Listed for reference; COSMIC-2 Explorer does not read these data.",
        "streams": ["pod", "ionex"],
    },
    {
        "id": "isro_issdc",
        "name": "ISRO ISSDC / PRADAN (Planetary & Space Science Data Archive)",
        "agency": "Indian Space Research Organisation (ISRO)",
        "url": "https://pradan.issdc.gov.in/",
        "portal_url": "https://www.issdc.gov.in/",
        "description": "ISRO's archive (ISSDC) for data from Indian space-science missions such as Chandrayaan-2 and the Mars Orbiter Mission. Listed for reference; COSMIC-2 Explorer does not read these data.",
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
    home = Path(os.path.expanduser("~"))
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else home) / APP_NAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / APP_NAME


DATA_ROOT = _data_root()
CACHE_DIR = DATA_ROOT / "cache"
EXPORT_DIR = DATA_ROOT / "exports"
LOG_DIR = DATA_ROOT / "logs"
DB_PATH = DATA_ROOT / "index.sqlite"
SETTINGS_PATH = DATA_ROOT / "settings.json"


def bundle_root() -> Path:
    """Directory that holds the read-only frontend and sample-data assets.

    They ship inside the ``cosmic2`` package, so the same lookup works from a
    source checkout, a pip install and a PyInstaller build (which places the
    package, and its data, under ``sys._MEIPASS/cosmic2``).
    """
    return Path(__file__).resolve().parent


def frontend_dir() -> Path:
    return bundle_root() / "frontend"


def sampledata_dir() -> Path:
    return bundle_root() / "sampledata"


def ensure_dirs() -> None:
    for d in (DATA_ROOT, CACHE_DIR, EXPORT_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


# Allowed values of every user setting (settings_migration.py compares them across
# versions): ("bool",), ("int", lo, hi), ("float", lo, hi) or ("choice", values).
# The stream and product codes are catalog.STREAMS and catalog.PRODUCTS (catalog.py
# imports this module; tests/test_settings_migration.py checks they agree).
SETTING_RULES: dict = {
    "max_profiles_per_download": ("int", 0, 100000),
    "concurrent_downloads": ("int", 1, 16),
    "request_timeout_s": ("int", 5, 3600),
    "listing_cache_hours": ("int", 0, 8760),
    "cache_quota_gb": ("float", 0, 100000),
    "warn_download_mb": ("int", 0, 10_000_000),
    "default_stream": ("choice", ("nrt", "rapid", "postProc", "provisional",
                                  "paz-nrt", "kompsat5-nrt", "metopb-postProc",
                                  "metopc-postProc", "cosmic1-repro2021")),
    "default_product": ("choice", ("atmPrf", "wetPf2", "ionPrf", "scnLv2", "ivmL2m", "avnPrf",
                                   "echPrf", "bfrPrf", "conPhs", "podTc2", "leoOrb")),
    "qc_require_good": ("bool",),
    "grid_top_km": ("float", 1, 1000),
    "grid_step_km": ("float", 0.001, 50),
    "analysis_workers": ("int", 0, 512),
    "plot_dpi": ("int", 50, 1200),
    "plot_theme": ("choice", ("light", "dark")),
    "ui_theme": ("choice", ("light", "dark")),
    "ui_font_size": ("int", 10, 24),
    "ui_mode": ("choice", ("educational", "research")),
    "units_temperature": ("choice", ("C", "K")),
    "explain_mode": ("bool",),
    "auto_update": ("bool",),
}

# Options renamed between versions: old name -> new name (settings_migration.py)
RENAMED_SETTINGS: dict = {}

# Whether this start created settings.json (a first start: nothing to migrate)
SETTINGS_CREATED = False


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
    # Worker processes for per-granule work (composites, diagnostics table,
    # regridded exports, indexing): 0 = automatic (CPUs - 1), 1 = serial.
    analysis_workers: int = 0
    # Presentation
    plot_dpi: int = 300
    plot_theme: str = "light"
    ui_theme: str = "light"
    ui_font_size: int = 14
    ui_mode: str = "educational"  # "educational" or "research"
    units_temperature: str = "C"  # "C" or "K"
    explain_mode: bool = True  # plain-language captions for non-specialists
    # Weekly automatic update of a published build (autoupdate.py): look for a
    # newer release once a week, download it and install it on the next start
    auto_update: bool = True
    # Network
    user_agent: str = f"{APP_NAME}/{APP_VERSION} (desktop client; python-requests)"
    extra: dict = field(default_factory=dict)

    @staticmethod
    def validate(key: str, value):
        """The value as stored for ``key``; ValueError when this version does not
        accept it (an unknown option, a wrong type, a value out of range)."""
        rule = SETTING_RULES.get(key)
        if rule is None:
            if key == "extra" and isinstance(value, dict):
                return value
            raise ValueError(f"{key} is not a setting of this version")
        kind = rule[0]
        if kind == "bool":
            if isinstance(value, bool):
                return value
            raise ValueError(f"{key} must be true or false, not {value!r}")
        if kind == "choice":
            if value in rule[1]:
                return value
            raise ValueError(f"{key} must be one of {', '.join(map(str, rule[1]))}, not {value!r}")
        lo, hi = rule[1], rule[2]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value                 or value in (float("inf"), float("-inf")):
            raise ValueError(f"{key} must be a number, not {value!r}")
        if kind == "int":
            if float(value) != int(value):
                raise ValueError(f"{key} must be a whole number, not {value!r}")
            value = int(value)
        if not lo <= value <= hi:
            raise ValueError(f"{key} must be between {lo:g} and {hi:g}, not {value!r}")
        return value

    def to_dict(self) -> dict:
        return asdict(self)

    def preserved(self) -> dict:
        """Entries of settings.json this version cannot use (options it does not
        have, values outside an option's present range).  They are written back
        unchanged until the user has seen them (settings_migration.py), so that
        starting another version never loses a stored value."""
        if "_preserved" not in self.__dict__:
            object.__setattr__(self, "_preserved", {})
        return self.__dict__["_preserved"]

    @classmethod
    def load(cls) -> "Settings":
        global SETTINGS_CREATED
        ensure_dirs()
        obj = cls()
        if not SETTINGS_PATH.exists():
            SETTINGS_CREATED = True
            try:
                obj.save()
            except OSError:
                pass
            return obj
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        # an option renamed since: its value moves to the new name when valid there
        for old, new in RENAMED_SETTINGS.items():
            if old in raw and new not in raw:
                try:
                    setattr(obj, new, cls.validate(new, raw[old]))
                except ValueError:
                    pass
        for k, v in raw.items():
            if k == "user_agent":
                continue          # always this version's (the stored one names the old version)
            try:
                setattr(obj, k, cls.validate(k, v))
            except ValueError:
                # unknown or invalid here: the default is used, the stored entry kept
                obj.preserved()[k] = v
        return obj

    def save(self) -> None:
        ensure_dirs()
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({**self.to_dict(), **self.preserved()}, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)

    def update(self, **kw) -> "Settings":
        """Set the given options (unknown names are ignored) and save; ValueError,
        with nothing changed, when a value is not allowed."""
        clean = {k: self.validate(k, v) for k, v in kw.items() if k in SETTING_RULES or k == "extra"}
        for k, v in clean.items():
            setattr(self, k, v)
            self.preserved().pop(k, None)       # the user has chosen a value now
        self.save()
        return self


SETTINGS = Settings.load()
