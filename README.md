# COSMIC-2 Explorer

A production-quality scientific desktop GUI and analysis environment for UCAR/CDAAC COSMIC-2 radio occultation data and comparative planetary atmospheric profiles. Runs entirely offline once data has been downloaded.

---

## Author and Affiliation

* **Lead Developer and Researcher**: Keshav Aggarwal
* **Current Affiliation**: Research Associate, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India
* **Former Affiliation**: Prime Minister's Research Fellow (PMRF Scholar), Department of Astronomy, Astrophysics and Space Engineering (DAASE), Indian Institute of Technology Indore (IIT Indore), Madhya Pradesh, India
* **Repository**: https://github.com/keshav-aggarwal/COSMIC2-Explorer

---

## Key Features

1. **Complete Offline-First Architecture**: 100% offline mathematical typesetting via bundled KaTeX fonts and engine, local TopoJSON map rendering, and bundled Plotly.js plotting.
2. **Robust Multi-Product Ingestion**: Supports FORMOSAT-7 / COSMIC-2 products (`wetPf2`, `atmPrf`, `ionPrf`, `scnLv2`, `ivmL2m`) from UCAR CDAAC and NOAA NCEI.
3. **Advanced Scientific Diagnostics**: Computes Abel transform inversion, cold point tropopause height/temperature, WMO lapse-rate tropopause (with 500 hPa floor guard), atmospheric density ($\rho$), atmospheric scale height ($H$), potential temperature ($\theta$), Brunt-Vaisala frequency ($N_{BV}^2$), and vertical TEC.
4. **VEDA Multi-Mission Planetary Science**: Seamlessly integrates the VEDA package for cross-body atmospheric comparison (Earth, Mars, Venus, Jupiter, Saturn, Mercury, Pluto) across NASA, ESA, JAXA, and ISRO missions.
5. **Interactive Filtering and Visualisation**: Visualise raw versus processed profiles, filter outliers (Sigma, MAD, IQR, Percentile), smooth soundings (Gaussian, Median, Savitzky-Golay), and compute composite latitudinal bands.
6. **Publication-Ready Exports**: Generates 300 dpi publication raster/vector figures (PNG, PDF, SVG, EPS), regridded NetCDF-4 files with CF-1.8 metadata, CSV tables, JSON bundles, and complete provenance tracking.

---

## Quick Start

```powershell
# From C:\Users\kesha\Desktop\COSMIC2-Explorer
cd backend
python app.py --browser          # opens the app in your default browser
python app.py                    # native window via pywebview (WebView2)
python app.py --no-window        # server only; keep running, open manually
```

On first launch with no data: press **"Load the bundled example profiles"** to index 8 real granules that ship with the app and explore every feature offline.

---

## Directory Architecture

```
COSMIC2-Explorer/
├── backend/                  Python application and scientific core
│   ├── app.py                Desktop entry point (starts server, opens window)
│   ├── server.py             Standalone server (for development)
│   ├── cosmic2/              Core Python package for COSMIC-2
│   │   ├── api.py            FastAPI routes (HTTP interface)
│   │   ├── catalog.py        CDAAC archive discovery
│   │   ├── fetch.py          Streaming download and job manager
│   │   ├── readers.py        netCDF readers to normalised Granule objects
│   │   ├── store.py          SQLite metadata index
│   │   ├── analysis.py       Science layer (tropopause, diagnostics, composites)
│   │   ├── plotting.py       Matplotlib publication figures
│   │   ├── exporters.py      CSV / netCDF-4 / JSON / ZIP export
│   │   ├── vocab.py          Variable labels, units, physical definitions
│   │   └── config.py         Paths, settings, citation
│   └── veda/                 Multi-mission planetary occultation package
│       ├── api/              VEDA API endpoints
│       ├── core/             Mission registry, models, adapters
│       ├── missions/         Mission adapters (Akatsuki, Cassini, Juno, etc.)
│       ├── analysis/         Planetary atmospheric profiling
│       └── readers/          PDS3, FITS, netCDF readers
│
├── frontend/                 Static HTML/CSS/JS (no build step)
│   ├── index.html            Single-page application shell
│   ├── help.html             Offline scientific manual with KaTeX equations
│   ├── css/app.css           Modern responsive interface stylesheet
│   ├── assets/               Icons and emblems (cosmic2_logo.png, cosmic2.ico)
│   ├── js/
│   │   ├── main.js           Bootstrap: boots API, wires tabs, modal logic
│   │   ├── api.js            Fetch wrappers and shared client state
│   │   ├── ui.js             DOM helpers, Plotly defaults, formatters, KaTeX rendering
│   │   ├── tabs_data.js      "Get data" and "Explore" tabs
│   │   └── tabs_science.js   "Profiles", "Compare" and "Export" tabs
│   └── vendor/               Bundled Plotly.js, TopoJSON, and offline KaTeX package
│
├── sampledata/               8 real CDAAC granules (5 products) for offline use
├── tests/                    Pytest test suite covering science, launch, and compliance
├── build/                    PyInstaller specifications and icon assets
├── dist/                     Packaged single-file standalone Windows executable
├── LICENSE                   MIT Open Source License
├── DATA_POLICY.md            UCAR CDAAC, NOAA NCEI, and TASA data availability terms
├── THIRD_PARTY_LICENSES.md   Third-party open-source software licenses
├── launch.ps1                PowerShell launcher script
└── STATUS.md                 Project implementation and verification status
```

---

## Supported COSMIC-2 Products

All data is fetched from the public CDAAC HTTP archive (no account required for public data streams):

```
https://data.cosmic.ucar.edu/gnss-ro/cosmic2/<stream>/<level>/<YYYY>/<DDD>/
```

Supported products:

| Product | Description |
|---|---|
| `wetPf2` | Neutral atmosphere: temperature, pressure, humidity on 100 m grid to 60 km (1D-Var) |
| `atmPrf` | Bending angle, refractivity, dry temperature at native resolution |
| `ionPrf` | Ionospheric electron density profile to ~800 km |
| `scnLv2` | Signal scintillation indices (S4, sigma-phi) |
| `ivmL2m` | In-situ plasma density, temperature and drift at spacecraft altitude |

Streams: `nrt` (near-real-time, within hours), `rapid` (~24 h), `postProc` (final, weeks to months), `provisional`.

---

## Data Availability and Licensing

* **License**: MIT License (see [LICENSE](file:///C:/Users/kesha/Desktop/COSMIC2-Explorer/LICENSE))
* **Data Policy**: See [DATA_POLICY.md](file:///C:/Users/kesha/Desktop/COSMIC2-Explorer/DATA_POLICY.md) for full terms on UCAR CDAAC and NOAA NCEI public domain data access, along with mandatory publication citations.
* **Third-Party Licenses**: See [THIRD_PARTY_LICENSES.md](file:///C:/Users/kesha/Desktop/COSMIC2-Explorer/THIRD_PARTY_LICENSES.md) for KaTeX, Plotly.js, TopoJSON, FastAPI, NumPy, SciPy, Matplotlib, NetCDF4, and PyWebView licenses.

---

## Running the Verification Suite

```powershell
python -m pytest tests/ -v
```

The test suite validates:
* Variable labels and unit normalisation (`Celsius_degree` to `deg C`, etc.)
* NetCDF readers, metadata extraction, sentinel filtering
* Abel inversion, tropopause identification, derived scale height and density
* FastAPI endpoints and export pipelines
* Windows double-click standalone executable launch and lifecycle
* Strict zero em/en-dash compliance and local asset integrity
