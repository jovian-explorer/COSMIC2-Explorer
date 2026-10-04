# COSMIC-2 Explorer

A production-quality scientific desktop GUI and analysis environment for UCAR/CDAAC COSMIC-2 radio occultation data and comparative planetary atmospheric profiles. Runs entirely offline once data has been downloaded.

---

## Author and Affiliation

* **Lead Developer and Researcher**: Keshav Aggarwal
* **Current Affiliation**: Research Associate, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India
* **Former Affiliation**: Prime Minister's Research Fellow (PMRF Scholar), Department of Astronomy, Astrophysics and Space Engineering (DAASE), Indian Institute of Technology Indore (IIT Indore), Madhya Pradesh, India
* **Repository**: https://github.com/jovian-explorer/COSMIC2-Explorer

---

## Key Features

1. **Complete Offline-First Architecture**: 100% offline mathematical typesetting via bundled KaTeX fonts and engine, local TopoJSON map rendering, and bundled Plotly.js plotting.
2. **Robust Multi-Product Ingestion**: Supports FORMOSAT-7 / COSMIC-2 products (`wetPf2`, `atmPrf`, `ionPrf`, `scnLv2`, `ivmL2m`) from UCAR CDAAC and NOAA NCEI.
3. **Advanced Scientific Diagnostics**: Starting from CDAAC's retrieved (Abel-inverted) profiles, computes cold point tropopause height/temperature, WMO lapse-rate tropopause (with 500 hPa floor guard), atmospheric density ($\rho$, including water vapour where available), atmospheric scale height ($H$), potential temperature ($\theta$), Brunt-Vaisala frequency ($N_{BV}^2$), F2 and E layer peaks, vertical TEC, integrated water vapour, ducting layers, boundary-layer height and gravity-wave potential energy.
4. **Interactive Filtering and Visualisation**: Visualise raw versus processed profiles, filter outliers (Sigma, MAD, IQR, Percentile), smooth soundings (Gaussian, Median, Savitzky-Golay), and compute composite latitudinal bands.
5. **Parallel Processing**: Composites, diagnostics tables, regridded exports and indexing run on a user-chosen number of CPU worker processes.
6. **Publication-Ready Exports**: Generates 300 dpi publication raster/vector figures (PNG, PDF, SVG, EPS), regridded NetCDF-4 files with CF-1.8 metadata, CSV tables, JSON bundles, and complete provenance tracking.

---

## Install

### Option 1: download the app (no Python needed)

Grab the archive for your OS from the [Releases page](https://github.com/jovian-explorer/COSMIC2-Explorer/releases):

| OS | File | Run |
|---|---|---|
| Windows | `COSMIC2-Explorer-<version>-windows-x64.zip` | unzip, double-click `COSMIC2-Explorer.exe` |
| macOS | `COSMIC2-Explorer-<version>-macos-<arch>.zip` | unzip, right-click `COSMIC2-Explorer.app` and choose **Open** the first time (the app is not notarised) |
| Linux | `COSMIC2-Explorer-<version>-linux-x64.tar.gz` | `tar xzf ...` then `./COSMIC2-Explorer` |

### Option 2: install with pip (any OS, Python 3.10+)

```bash
pip install "git+https://github.com/jovian-explorer/COSMIC2-Explorer.git"
cosmic2-explorer                 # native window, or your browser as a fallback
```

The repository is private, so pip needs GitHub access (for example a logged-in `gh` or a credential helper).

### Option 3: development setup

```bash
git clone https://github.com/jovian-explorer/COSMIC2-Explorer.git
cd COSMIC2-Explorer
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

---

## Running

```bash
cosmic2-explorer                 # native window (pywebview)
cosmic2-explorer --browser       # open in the default browser instead
cosmic2-explorer --no-window     # server only; open the printed URL yourself
cosmic2-explorer-server --port 8765   # backend only, fixed port, with API docs at /api/docs
cosmic2-explorer --workers 4     # use up to 4 worker processes this session
python -m cosmic2                # same as cosmic2-explorer
```

The app binds 127.0.0.1 on the first free port from 8765, so it runs alongside other local apps.
On first launch with no data, press **"Load the bundled example profiles"** to index 8 real granules that ship with the app and explore every feature offline.

Your data (downloads, index, exports, settings, logs) lives in a per-user folder, never next to the app:

| OS | Location |
|---|---|
| Windows | `%LOCALAPPDATA%\COSMIC2Explorer` |
| macOS | `~/Library/Application Support/COSMIC2Explorer` |
| Linux | `$XDG_DATA_HOME/COSMIC2Explorer` (default `~/.local/share/COSMIC2Explorer`) |

Set `COSMIC2_EXPLORER_HOME` to use another folder.

### CPU workers

Work that reads many granules (composites, profile plots, the diagnostics table, regridded CSV and netCDF exports, importing files, "Rebuild index") is spread over worker processes when a job has 24 or more granules. Choose the number in **Settings > Performance > CPU workers**: `0` (default) uses one fewer than the number of CPUs, `1` runs everything in the main process, any other number caps the pool. `--workers N` on the command line overrides the setting for one session. Results are identical to a serial run; if the pool fails for any reason the job is rerun serially. The workers are started in the background as soon as the app opens (and again when the setting changes), so the first large job does not wait for them; on Windows and macOS each worker takes a second or more to start.

### Notes on the science

* In `atmPrf`, the variables `Temp` and `Pres` are the **dry** temperature and pressure (refractivity inverted with no water vapour). In `wetPf2` the same names hold the 1D-Var moist retrieval. The app labels them accordingly and never averages one with the other in a composite.
* The WMO tropopause on `atmPrf` dry temperature only considers levels colder than 235 K: lower down, water vapour makes the dry temperature's lapse rate fall below 2 K/km and the test would fire near 6 km in the tropics. On `wetPf2` the moist temperature is used as it is.
* Pressure, density, vapour pressure, specific humidity and electron density are interpolated in log space when profiles are put on a common grid.
* Profile error bars are the running scatter of the values about their running mean (an estimate of level-to-level noise), not a retrieval uncertainty.
* The integrated water vapour starts at the lowest retrieved level; the height of that level is given alongside the value.
* Exports contain the archive values and derived fields. The outlier, smoothing and uncertainty settings on the Profiles tab affect the on-screen plot only, and the export provenance says so.

### Platform notes

* **Windows**: the native window uses Microsoft Edge WebView2, which ships with Windows 10 and 11.
* **macOS**: uses the built-in WebKit; nothing extra to install.
* **Linux**: from pip, the native window needs a GUI backend for pywebview: Qt (`pip install "cosmic2-explorer[qt] @ git+https://github.com/jovian-explorer/COSMIC2-Explorer.git"`) or GTK (the WebKitGTK system package, e.g. `sudo apt install gir1.2-webkit2-4.1`, plus `pip install pywebview[gtk]`). Without one, the app opens in your default browser automatically. The downloaded Linux build always uses the browser.

---

## Building the standalone app

```bash
pip install -e ".[build]"
python scripts/build_exe.py            # dist/COSMIC2-Explorer(.exe|.app)
python scripts/build_exe.py --archive  # plus the release archive for this OS
```

PyInstaller can only build for the OS it runs on. Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds Windows, macOS and Linux and attaches all three archives to a GitHub Release.

---

## Directory Architecture

```
COSMIC2-Explorer/
├── src/cosmic2/              Installable Python package
│   ├── app.py                Desktop entry point (starts server, opens window)
│   ├── server.py             Standalone server (development, headless use)
│   ├── api.py                FastAPI routes (HTTP interface) and static host
│   ├── catalog.py            CDAAC archive discovery
│   ├── fetch.py              Streaming download and job manager
│   ├── readers.py            netCDF readers to normalised Granule objects
│   ├── pipeline.py           Outlier removal, smoothing, uncertainty
│   ├── parallel.py           Worker-process pool for per-granule work
│   ├── store.py              SQLite metadata index
│   ├── analysis.py           Science layer (tropopause, diagnostics, composites)
│   ├── plotting.py           Matplotlib publication figures
│   ├── exporters.py          CSV / netCDF-4 / JSON / ZIP export
│   ├── vocab.py              Variable labels, units, physical definitions
│   ├── config.py             Paths, settings, citation
│   ├── frontend/             Static HTML/CSS/JS (no build step), bundled Plotly, TopoJSON, KaTeX
│   └── sampledata/           8 real CDAAC granules (5 products) for offline use
├── tests/                    Pytest suite: science, API, exports, frontend, compliance, EXE launch
├── packaging/                PyInstaller spec (Windows, macOS, Linux) and launcher
├── scripts/build_exe.py      Cross-platform build script
├── images/                   Branding and media kit
├── .github/workflows/        CI (3 OS) and tagged release builds
├── LICENSE                   MIT Open Source License
├── DATA_POLICY.md            UCAR CDAAC, NOAA NCEI, and TASA data availability terms
└── THIRD_PARTY_LICENSES.md   Third-party open-source software licenses
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

* **License**: MIT License (see [LICENSE](LICENSE))
* **Data Policy**: See [DATA_POLICY.md](DATA_POLICY.md) for full terms on UCAR CDAAC and NOAA NCEI public domain data access, along with mandatory publication citations.
* **Third-Party Licenses**: See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for KaTeX, Plotly.js, TopoJSON, FastAPI, NumPy, SciPy, Matplotlib, NetCDF4, and PyWebView licenses.

---

## Running the Verification Suite

```bash
python -m pytest
COSMIC2_NETWORK_TESTS=1 python -m pytest tests/test_network.py   # live CDAAC download
```

See [CHANGELOG.md](CHANGELOG.md) for what changed between versions.

The test suite validates:
* Variable labels and unit normalisation (`Celsius_degree` to `deg C`, etc.)
* NetCDF readers, metadata extraction, sentinel filtering
* Tropopause identification, ionospheric peak and TEC, water vapour, density and interpolation, checked against synthetic profiles with known answers
* Reader handling of fill values, packing, local times and longitudes
* Full-precision CSV/netCDF exports with UDUNITS unit strings, and figure rendering (captions, fonts, themes)
* Worker-process results identical to serial runs
* FastAPI endpoints and export pipelines (against a server on a free port with a throwaway data folder)
* Frontend DOM targets and module exports
* Strict zero em/en-dash compliance and local asset integrity
* Windows double-click launch of a built EXE (skipped unless `dist/COSMIC2-Explorer.exe` or `COSMIC2_EXE` exists)
* Live CDAAC download (opt-in: `COSMIC2_NETWORK_TESTS=1`)
