"""Model of the public CDAAC COSMIC-2 archive.

Layout verified against data.cosmic.ucar.edu::

    /gnss-ro/cosmic2/<stream>/<level>/<YYYY>/<DDD>/<product>_<tag>_<YYYY>_<DDD>.tar.gz

`stream` is the processing latency/maturity class (nrt, rapid, postProc,
provisional); `level` is the product level.  Each day is one gzipped tar per
product holding one netCDF granule per occultation.

Nothing here assumes which products exist on a given day: directory indexes
are listed live and cached, so new products appear without a code change.
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable

import requests

from .config import CDAAC_BASE, SETTINGS

# --------------------------------------------------------------------------
# Streams and collections
# --------------------------------------------------------------------------

STREAMS: dict[str, dict] = {
    "nrt": {
        "label": "Near-real-time",
        "blurb": "Produced within ~30-120 min of observation. Best for recent dates; "
                 "orbit and clock solutions are predicted rather than final.",
        "levels": ["level2", "level1b", "level3"],
    },
    "rapid": {
        "label": "Rapid",
        "blurb": "Reprocessed within days with better orbits. Ionosphere and "
                 "scintillation products live here.",
        "levels": ["level2", "level1b", "level3"],
    },
    "postProc": {
        "label": "Post-processed",
        "blurb": "Final reprocessing with the best available orbits and a frozen "
                 "software version. Use this for climate-quality work.",
        "levels": ["level2", "level1b"],
    },
    "provisional": {
        "label": "Provisional (space weather)",
        "blurb": "Provisional space-weather release, including ionospheric "
                 "electron-density profiles (ionPrf).",
        "levels": ["spaceWeather/level2"],
    },
    # Other radio occultation missions CDAAC processes into the same formats,
    # for comparison with COSMIC-2.  Their stream codes carry the mission, so
    # their files get their own cache folder, dataset key and index stream,
    # and deleting one never touches COSMIC-2 granules of the same day.
    "paz-nrt": {
        "label": "PAZ near-real-time (another mission)",
        "blurb": "Near-real-time profiles from the Spanish PAZ satellite (polar orbit, "
                 "so it also covers the high latitudes COSMIC-2 does not), processed by "
                 "CDAAC into the same atmPrf, wetPf2, echPrf and avnPrf files. Use it to "
                 "compare missions on the Statistics tab.",
        "levels": ["level2"],
        "mission": "paz",
    },
    "kompsat5-nrt": {
        "label": "KOMPSAT-5 near-real-time (another mission)",
        "blurb": "Near-real-time profiles from the Korean KOMPSAT-5 satellite, processed "
                 "by CDAAC into the same atmPrf, wetPf2, echPrf and avnPrf files (fewer a "
                 "day than PAZ). Use it to compare missions on the Statistics tab.",
        "levels": ["level2"],
        "mission": "kompsat5",
    },
}

# Satellite codes of the missions above, as in the file names (C2E1-C2E6 for COSMIC-2)
MISSION_SATS = {"paz": ("PAZ1",), "kompsat5": ("KOM5",)}


def mission_of(stream: str) -> str:
    """The archive directory of a stream's mission ("cosmic2" unless the
    stream code names another one)."""
    return STREAMS.get(stream, {}).get("mission", "cosmic2")

# (stream, level) pairs that are known to contain YYYY/DDD tarballs.
COLLECTIONS: list[tuple[str, str]] = [
    ("nrt", "level2"),
    ("nrt", "level1b"),
    ("rapid", "level2"),
    ("rapid", "level1b"),
    ("postProc", "level2"),
    ("postProc", "level1b"),
    ("provisional", "spaceWeather/level2"),
    ("paz-nrt", "level2"),
    ("kompsat5-nrt", "level2"),
]

# --------------------------------------------------------------------------
# Product registry
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Product:
    code: str
    label: str
    kind: str          # "neutral" | "ionosphere" | "scintillation" | "insitu" | "orbit"
    reader: str        # key into readers.READERS ("" = no reader yet)
    blurb: str
    plain: str         # one sentence for non-specialists
    size_class: str    # "small" (<50 MB) | "medium" (<400 MB) | "large" (>1 GB)
    key_vars: tuple[str, ...] = ()
    reference: str = ""
    doi: str = ""
    archive_url: str = ""
    processing_chain: str = ""
    # UCAR publishes no licence text for these data; it asks for a citation.
    license: str = ("Openly available from UCAR CDAAC without an account; "
                    "cite UCAR COSMIC Program (2019), doi:10.5065/T353-C093")


PRODUCTS: dict[str, Product] = {p.code: p for p in [
    Product(
        "atmPrf", "Atmospheric profile (dry)", "neutral", "atmPrf",
        "Bending angle, refractivity and the dry-air temperature/pressure retrieval "
        "on the native high-resolution vertical grid (~3800 levels, from the lowest "
        "level reached up to 80 km).",
        "The raw bend of the GPS radio signal through the air, plus the temperature "
        "you get from it if you ignore water vapour.",
        "large",
        ("Bend_ang", "Ref", "Temp", "Pres", "MSL_alt", "Impact_height"),
        reference="Schreiner, W. S., et al. (2020), COSMIC-2 radio occultation constellation: first results, Geophys. Res. Lett., 47, e2019GL086841",
        doi="10.1029/2019GL086841",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        processing_chain="L1b excess phase -> Doppler frequency shift -> geometric optical impact parameter -> dual-frequency ionospheric combination -> Abel integral inversion -> hydrostatic downward integration for dry temperature and pressure."
    ),
    Product(
        "wetPf2", "Moist-air profile (1D-Var)", "neutral", "wetPf2",
        "Temperature, pressure, water-vapour pressure, specific humidity and relative "
        "humidity from the 1D-Var retrieval, every 50 m up to 20 km and every 100 m "
        "above, to 60 km.",
        "Temperature and humidity through the atmosphere, on neat even height steps. "
        "This is the friendliest product to start with.",
        "medium",
        ("Temp", "Pres", "Vp", "sph", "rh", "ref", "gph", "MSL_alt"),
        reference="Healy, S. B., & Eyre, J. R. (2000), Q. J. R. Meteorol. Soc., 126, 1661-1683",
        doi="10.1002/qj.49712656606",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/wetPf2/",
        processing_chain="Level 2 refractivity combined with a numerical weather prediction background via 1D-Var optimal estimation to separate temperature and water vapour (50 m levels to 20 km, 100 m above)."
    ),
    Product(
        "ionPrf", "Ionospheric electron density", "ionosphere", "ionPrf",
        "Abel-inverted electron-density profile and calibrated TEC, up to the "
        "satellite's orbit (about 550-580 km).",
        "How many free electrons sit at each altitude high above the ground - the "
        "layer that bends radio signals and disrupts GPS.",
        "small",
        ("ELEC_dens", "TEC_cal", "MSL_alt"),
        reference="Syndergaard, S. (2000), Radio Sci., 35(3), 865-883",
        doi="10.1029/1999RS002199",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/provisional/spaceWeather/level2/ionPrf/",
        processing_chain="Calibrated dual-frequency excess phase L1-L2 -> ionospheric bending angle -> Abel transform inversion under local spherical symmetry assumption to yield the electron density profile up to the satellite's orbit."
    ),
    Product(
        "scnLv2", "Scintillation (S4)", "scintillation", "scnLv2",
        "Amplitude (S4) and phase scintillation indices per 1 s bin along the ray, "
        "with SNR, elevation and occultation height. Each file is placed at the "
        "tangent point of the ray at its S4 maximum.",
        "A measure of how much the signal flickers - a fingerprint of turbulent "
        "patches in the ionosphere.",
        "small",
        ("s4_L1", "sigma_phi_L1", "occheight", "elevation"),
        reference="Carrano, C. S., et al. (2011), Multiple phase screen modeling of ionospheric scintillation along radio occultation raypaths, Radio Sci., 46, RS0D07",
        doi="10.1029/2010RS004591",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        processing_chain="50 Hz raw SNR and carrier phase detrended over 1-second sliding windows -> calculation of amplitude scintillation index S4 and phase scintillation sigma-phi along ray path."
    ),
    Product(
        "ivmL2m", "Ion Velocity Meter (in-situ)", "insitu", "ivmL2m",
        "In-situ ion density, ion temperature and 3-component ion drift measured at "
        "the spacecraft (~550 km), 1 Hz along track.",
        "Measured right at the satellite: how dense the plasma is and which way it "
        "is drifting.",
        "medium",
        ("ion_dens", "ion_temp", "iv_zon", "iv_mer", "alt", "lat", "lon"),
        reference="Heelis, R. A., et al. (2017), Ion velocity measurements for the Ionospheric Connections Explorer, Space Sci. Rev., 212, 615-629 (the COSMIC-2 IVM is the same University of Texas at Dallas design)",
        doi="10.1007/s11214-017-0383-3",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        processing_chain="In-situ Ion Velocity Meter (IVM) planar ion trap measurements at ~550 km orbit: retarding potential analysis yields ion density and temperature, drift meter yields 3-component plasma velocity vectors."
    ),
    Product(
        "avnPrf", "NCEP model profile at the occultation", "neutral", "avnPrf",
        "NCEP global model temperature, pressure, water vapour pressure and "
        "refractivity, converted from GRIB and interpolated along the path of one "
        "occultation (the files' history attribute); about 50 levels. Named like "
        "the atmPrf of that occultation, so the two pair exactly.",
        "What the US weather model said the atmosphere was at the same place and time.",
        "small",
        ("Temp", "Pres", "Vp", "Ref", "MSL_alt"),
        reference="Schreiner, W. S., et al. (2020), COSMIC-2 radio occultation constellation: first results, Geophys. Res. Lett., 47, e2019GL086841",
        doi="10.1029/2019GL086841",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/",
        processing_chain="NCEP model GRIB fields -> wgrib2 -> interpolated to the occultation's tangent-point path and time by CDAAC (makeAncPrfRT)."
    ),
    Product(
        "echPrf", "ECMWF model profile at the occultation", "neutral", "echPrf",
        "ECMWF temperature, pressure, water vapour pressure, refractivity and "
        "simulated bending angle colocated with one occultation along its path "
        "(about 135 levels); the files name the ECMWF fields used. Named like the "
        "atmPrf of that occultation, so the two pair exactly. It is also the first "
        "guess of that occultation's wetPf2 1D-Var (the wetPf2 attribute fgsPrf names "
        "it), and it carries the model profile's ducting diagnostics (ductid, zsr, "
        "dzsr, dndz, dzbot).",
        "What the European weather model said the atmosphere was at the same place and time.",
        "small",
        ("Temp", "Pres", "Vp", "Ref", "Bend_ang", "MSL_alt"),
        reference="UCAR CDAAC file formats: echPrf, profiles from ECMWF gridded fields colocated with occultations",
        doi="",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/",
        processing_chain="ECMWF gridded fields (Model_File_1/2 attributes) interpolated by CDAAC to the occultation's tangent-point path and time."
    ),
    Product(
        "bfrPrf", "BUFR bulletin", "neutral", "",
        "Operational BUFR encoding of the bending-angle profile.",
        "The packed format weather centres feed into their forecast models.",
        "small",
        reference="WMO Manual on Codes (WMO-No. 306), Volume I.2",
        doi="",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/bfrPrf/",
        processing_chain="Binary Universal Form for the Representation of meteorological data (BUFR) encoding for operational assimilation into global NWP centers."
    ),
    Product(
        "conPhs", "Calibrated excess phase", "orbit", "",
        "Level 1b excess phase and amplitude - the input to the retrieval chain.",
        "The most raw measurement: how much the signal was delayed, moment by moment.",
        "large",
        reference="Schreiner, W. S., et al. (2020), COSMIC-2 radio occultation constellation: first results, Geophys. Res. Lett., 47, e2019GL086841",
        doi="10.1029/2019GL086841",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level1b/conPhs/",
        processing_chain="High-rate 50 Hz carrier phase observations combined with precise satellite orbit and clock corrections to compute atmospheric excess phase."
    ),
    Product(
        "podTc2", "Precise orbit TEC", "ionosphere", "",
        "Absolute TEC along the receiver-to-GNSS link from the POD antenna.",
        "Total electron content measured on the satellite's navigation antenna.",
        "medium",
        reference="Weiss, J.-P., et al. (2022), COSMIC-2 mission summary at three years in orbit, Atmosphere, 13, 1409",
        doi="10.3390/atmos13091409",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/podTc2/",
        processing_chain="Geometry-free linear combination of dual-frequency carrier phases from the upward-looking precise orbit determination (POD) antennas."
    ),
    Product(
        "leoOrb", "LEO orbit solution", "orbit", "",
        "Spacecraft position and velocity.",
        "Where each satellite was, second by second.",
        "medium",
        reference="Weiss, J.-P., et al. (2022), COSMIC-2 mission summary at three years in orbit, Atmosphere, 13, 1409",
        doi="10.3390/atmos13091409",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level1b/leoOrb/",
        processing_chain="CDAAC precise orbit determination of the COSMIC-2 spacecraft from its GNSS navigation antennas."
    ),
]}


def describe_product(code: str) -> Product:
    if code in PRODUCTS:
        return PRODUCTS[code]
    return Product(code, code, "other", "", "Undocumented CDAAC product.",
                   "An extra data product from the archive.", "medium")


def readable_products() -> list[str]:
    return [c for c, p in PRODUCTS.items() if p.reader]


# --------------------------------------------------------------------------
# Remote listing
# --------------------------------------------------------------------------

_HREF = re.compile(r'href="([^"?][^"]*)"', re.I)
_TARBALL = re.compile(
    r"^(?P<product>[A-Za-z0-9]+)_(?P<tag>[A-Za-z0-9]+)_(?P<year>\d{4})_(?P<doy>\d{3})\.tar\.gz$"
)


@dataclass
class RemoteFile:
    product: str
    tag: str
    year: int
    doy: int
    name: str
    url: str
    size_bytes: int | None = None

    @property
    def date(self) -> dt.date:
        return doy_to_date(self.year, self.doy)


def doy_to_date(year: int, doy: int) -> dt.date:
    return dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)


def date_to_doy(d: dt.date) -> tuple[int, int]:
    return d.year, d.timetuple().tm_yday


def collection_url(stream: str, level: str) -> str:
    mission = mission_of(stream)
    if mission != "cosmic2":
        # "paz-nrt" -> gnss-ro/paz/nrt/<level>
        return f"{CDAAC_BASE}/{mission}/{stream.split('-', 1)[1]}/{level}"
    return f"{CDAAC_BASE}/cosmic2/{stream}/{level}"


# Parallel HTTP requests used to build a day manifest (kept modest: this is
# a public archive).
MANIFEST_WORKERS = 8


def day_url(stream: str, level: str, year: int, doy: int) -> str:
    return f"{collection_url(stream, level)}/{year}/{doy:03d}"


class Archive:
    """Thin, cached HTTP client for the CDAAC directory tree."""

    def __init__(self, settings=SETTINGS):
        self.settings = settings
        self._session = requests.Session()
        self._session.headers["User-Agent"] = settings.user_agent
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._lock = threading.Lock()

    # -- low level ------------------------------------------------------
    def session(self) -> requests.Session:
        return self._session

    def _ttl(self) -> float:
        return max(0.0, self.settings.listing_cache_hours) * 3600.0

    # A missing or empty directory is remembered only briefly: today's
    # directory 404s until CDAAC publishes its first file, and caching that
    # answer for the full listing TTL (6 h by default) hid new data for hours.
    NEGATIVE_TTL_S = 300.0

    def list_dir(self, url: str, use_cache: bool = True) -> list[str]:
        """Return the entry names of an Apache-style directory index."""
        if not url.endswith("/"):
            url += "/"
        now = time.time()
        with self._lock:
            hit = self._cache.get(url)
            if use_cache and hit:
                ttl = self._ttl() if hit[1] else min(self._ttl(), self.NEGATIVE_TTL_S)
                if now - hit[0] < ttl:
                    return hit[1]
        r = self._session.get(url, timeout=self.settings.request_timeout_s)
        if r.status_code == 404:
            entries: list[str] = []
        else:
            r.raise_for_status()
            entries = [
                h for h in _HREF.findall(r.text)
                if not h.startswith(("/", "http", "?", "#")) and h != "../"
            ]
        with self._lock:
            self._cache[url] = (now, entries)
        return entries

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # -- tree walk ------------------------------------------------------
    def years(self, stream: str, level: str) -> list[int]:
        out = []
        for e in self.list_dir(collection_url(stream, level)):
            m = re.fullmatch(r"(\d{4})/", e)
            if m:
                out.append(int(m.group(1)))
        return sorted(out)

    def doys(self, stream: str, level: str, year: int) -> list[int]:
        out = []
        for e in self.list_dir(f"{collection_url(stream, level)}/{year}"):
            m = re.fullmatch(r"(\d{3})/", e)
            if m:
                out.append(int(m.group(1)))
        return sorted(out)

    def files(self, stream: str, level: str, year: int, doy: int) -> list[RemoteFile]:
        base = day_url(stream, level, year, doy)
        out = []
        for e in self.list_dir(base):
            m = _TARBALL.match(e)
            if m:
                out.append(RemoteFile(
                    product=m.group("product"), tag=m.group("tag"),
                    year=int(m.group("year")), doy=int(m.group("doy")),
                    name=e, url=f"{base}/{e}",
                ))
        return sorted(out, key=lambda f: f.product)

    def head_size(self, url: str) -> int | None:
        try:
            r = self._session.head(url, timeout=self.settings.request_timeout_s,
                                   allow_redirects=True)
            if r.ok and "Content-Length" in r.headers:
                return int(r.headers["Content-Length"])
        except (requests.RequestException, ValueError):
            pass
        return None

    def day_manifest(self, date: dt.date, streams: Iterable[str] | None = None,
                     with_sizes: bool = True) -> list[dict]:
        """Everything available for one calendar day, across collections.

        The collection listings and the per-file HEAD requests (for sizes)
        are independent round trips, so they run on a small thread pool: a
        day with ~40 files took ~50 sequential requests before.
        """
        year, doy = date_to_doy(date)
        wanted = set(streams) if streams else None
        # Other missions are listed only when asked for by their stream code.
        colls = [(s, l) for s, l in COLLECTIONS
                 if (s in wanted if wanted else mission_of(s) == "cosmic2")]

        def listing(coll):
            try:
                return self.files(coll[0], coll[1], year, doy)
            except requests.RequestException:
                return []

        with ThreadPoolExecutor(max_workers=MANIFEST_WORKERS) as pool:
            found = list(pool.map(listing, colls))
            entries = [(s, l, f) for (s, l), fs in zip(colls, found) for f in fs]
            sizes = (list(pool.map(lambda e: self.head_size(e[2].url), entries))
                     if with_sizes else [None] * len(entries))
        rows: list[dict] = []
        for (stream, level, f), size in zip(entries, sizes):
            p = describe_product(f.product)
            rows.append({
                "stream": stream, "level": level, "product": f.product,
                "label": p.label, "kind": p.kind, "blurb": p.blurb,
                "plain": p.plain, "readable": bool(p.reader),
                "key_vars": list(p.key_vars), "size_class": p.size_class,
                "name": f.name, "url": f.url, "size_bytes": size,
                "year": year, "doy": doy, "date": date.isoformat(),
            })
        return rows

    def latest_available(self, stream: str = "nrt", level: str = "level2",
                         product: str | None = None, search_days: int = 14
                         ) -> dict | None:
        """Walk backwards from today for the most recent day that has data."""
        today = dt.datetime.now(dt.timezone.utc).date()
        for back in range(search_days):
            d = today - dt.timedelta(days=back)
            year, doy = date_to_doy(d)
            try:
                found = self.files(stream, level, year, doy)
            except requests.RequestException:
                continue
            if product:
                found = [f for f in found if f.product == product]
            if found:
                return {"date": d.isoformat(), "year": year, "doy": doy,
                        "products": sorted({f.product for f in found})}
        return None
