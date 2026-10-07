# COSMIC-2 Explorer

A desktop GUI and analysis environment for the FORMOSAT-7 / COSMIC-2 radio occultation profiles published by UCAR CDAAC: find and download them, plot and compare them, compute diagnostics, and export data and figures. Everything except downloading works offline once the data are on your computer.

The retrievals themselves (bending angle, refractivity, temperature, humidity, electron density) are CDAAC's; the app reads those files and computes its diagnostics from them.

---

## Author and Affiliation

* **Lead Developer and Researcher**: Keshav Aggarwal
* **Current Affiliation**: Research Associate, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India
* **Former Affiliation**: Prime Minister's Research Fellow (PMRF Scholar), Department of Astronomy, Astrophysics and Space Engineering (DAASE), Indian Institute of Technology Indore (IIT Indore), Madhya Pradesh, India
* **Repository**: https://github.com/jovian-explorer/COSMIC2-Explorer

---

## Key Features

1. **Offline once downloaded**: KaTeX (equations), Plotly.js (plots) and the TopoJSON map outlines are bundled, so nothing but downloading needs a network.
2. **Five COSMIC-2 products**: reads `wetPf2`, `atmPrf`, `ionPrf`, `scnLv2` and `ivmL2m`. Downloads come from UCAR CDAAC; files in the same format from elsewhere (for example NOAA NCEI) can be dropped onto the window to be indexed.
3. **Diagnostics**: from CDAAC's retrieved (Abel-inverted) profiles the app computes the cold-point tropopause, the WMO lapse-rate tropopause (searched above 500 hPa, and on dry temperature only below 235 K), density ($\rho$, including water vapour where available), scale height ($H$), potential temperature ($\theta$), Brunt-Vaisala frequency ($N_{BV}^2$), F2 and E layer peaks with foF2, vertical TEC, integrated water vapour, ducting layers, boundary-layer height and gravity-wave potential energy ($E_p$, 20-40 km). Where the file carries CDAAC's own value (tropopause, cold point, NmF2, hmF2, TEC, S4) the two are shown side by side.
4. **Interactive plots**: overlay up to 200 profiles of any quantity on any height axis; optionally filter outliers (sigma, MAD, IQR, percentile) and smooth (moving average, Gaussian, median, Savitzky-Golay) on screen, beside the raw profile; average profiles in groups (latitude band, hemisphere, day/night, date, product, satellite) with their spread or the 95 % confidence interval of the mean; and scatter any per-profile diagnostic against another.
5. **Statistics**: counts by product, latitude and local time, the archive's quality flags, and penetration depth (lowest retrieved level, above sea level and, where the matching wetPf2 gives the terrain height, above the ground) for the current search.
   The same tab draws **zonal-mean latitude-height sections** of any quantity (temperature, refractivity, electron density, ...): the mean, spread or count in each latitude band and height, or each band's departure in percent from the mean of all profiles at that height.
   It also maps any per-profile diagnostic (gravity-wave energy, tropopause height, foF2, ...) in latitude-longitude cells with its zonal mean; the gravity-wave energy can be recomputed for any layer with a polynomial or high-pass background.
6. **Validation against radiosondes**: pairs each atmPrf or wetPf2 profile with the nearest NOAA IGRA v2 radiosonde within a chosen distance and time (300 km and 3 h by default) and shows the mean and spread of the differences in temperature, refractivity and specific humidity by geopotential height, with the list of pairs and an optional CSV. Station files are downloaded from NOAA NCEI on first use (no account) and cached.
7. **Parallel Processing**: Composites, diagnostics tables, regridded exports and indexing run on a user-chosen number of CPU worker processes.
8. **Exports**: Matplotlib figures (PNG at 300 dpi by default, PDF, SVG, EPS), regridded netCDF-4 with CF-style attributes and UDUNITS units, CSV tables and JSON. Data files carry their provenance (input files, software version, data citation); figure files do not.

---

## Install

### Option 1: download the app (no Python needed)

Grab the archive for your OS from the [Releases page](https://github.com/jovian-explorer/COSMIC2-Explorer/releases):

| OS | File | Run |
|---|---|---|
| Windows | `COSMIC2-Explorer-<version>-windows-x64.zip` | unzip, double-click `COSMIC2-Explorer\COSMIC2-Explorer.exe` |
| macOS | `COSMIC2-Explorer-<version>-macos-arm64.zip` | unzip, right-click `COSMIC2-Explorer/COSMIC2-Explorer.app` and choose **Open** the first time (the app is not notarised) |
| Linux | `COSMIC2-Explorer-<version>-linux-x64.tar.gz` | `tar xzf ...` then `./COSMIC2-Explorer/COSMIC2-Explorer` |

Each archive unpacks to one `COSMIC2-Explorer` folder. Keep the app in that folder: the weekly automatic update replaces the folder with the new build (and only a folder that holds its `INSTALL_FOLDER.json`), so keep nothing else in it. Your downloads, exports and settings live in a separate data folder and are never touched by an update.

#### Automatic updates

A downloaded build looks for a newer release once a week (**Settings > Updates**; on by default, with **Check now**). It asks the GitHub releases API of this repository anonymously, like any visitor (a `GITHUB_TOKEN` or `GH_TOKEN` in the environment, or a logged-in `gh`, is used when present, and only towards api.github.com). When a newer release exists, the archive for your platform is downloaded into the data folder in the background and checked against the SHA-256 digest GitHub lists for it (or the release's `SHA256SUMS.txt`); an archive that fails the check is discarded. The next time you start the app it closes, a small script swaps the `COSMIC2-Explorer` folder for the new one (the old one is kept as `COSMIC2-Explorer.previous` until the new build has started) and starts the new build with the same command-line arguments. Your settings are kept as they are: the first time the new build starts, a panel shows what is new in the release and lists the settings that are new (with their defaults), changed, no longer allowed or no longer used, so you can review them; closing it changes nothing. Copies run from source or with pip, and an app moved out of its unpacked folder, never update themselves.

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
* Penetration depth is the lowest retrieved level of good atmPrf/wetPf2 profiles. Above the ground it uses the terrain height stored in the wetPf2 retrieved from the same atmPrf; on the 600 atmPrf profiles of 2026-06-20 and 2026-09-30, 84.5 % reach within 1 km of the ground (76.8 % below 1 km above sea level), in line with the more than 80 % reported by Schreiner et al. (2020).
* The Statistics tab compares each atmPrf with the wetPf2 retrieved from it (the wetPf2 file names its atmPrf, so the pairing is exact). On the 549 real 2026 pairs the observed refractivity is 0.65 % below the 1D-Var analysis at 0.5 km and within 0.05 % of it from 3 to 30 km; the dry temperatures of the two files agree within 0.1 K from 3 to 15 km; and the moisture effect (temperature minus dry temperature) is 56 K at 0.5 km, 1 K at 10 km and under 0.1 K above 14 km, matching 77.6 P_dry / N from the Smith-Weintraub refractivity of the wetPf2 state within 1 % up to 12 km.
* The radiosonde comparison works on geopotential height: wetPf2's own `gph`, or atmPrf's height converted with Mahoney's (2001) normal gravity (within 2 m of wetPf2's `gph` on the real sample). Sonde refractivity is 77.6 p/T + 3.73e5 e/T^2 with e from the dew point (Bolton 1980); sonde humidity is compared only where the sonde is warmer than -40 C. On the 2026 sample (45 wetPf2-sonde pairs within 300 km and 3 h) the mean temperature difference stays within 0.5 K from 0 to 25 km (standard deviation 1-1.7 K), refractivity within 0.6 % from 3 to 30 km, and refractivity is 2.6 % low at 0-1 km, like the 3-4 % negative bias near the surface reported by Ho et al. (2020).
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

PyInstaller can only build for the OS it runs on. Pushing a tag `v<version>` or `v<version>-build.<n>` (`<version>` as in `pyproject.toml`) runs `.github/workflows/release.yml`, which builds Windows, macOS and Linux with `--archive --tag <tag>`, and attaches the three archives and `SHA256SUMS.txt` to a GitHub Release. Only builds stamped with a tag update themselves; releases are ordered by tag, so a later build of the same version is `v<version>-build.<n+1>`.

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
| `wetPf2` | Neutral atmosphere: temperature, pressure, humidity from CDAAC's 1D-Var retrieval, every 50 m to 20 km and every 100 m above, to 60 km |
| `atmPrf` | Bending angle, refractivity, dry temperature and pressure at native resolution (~3800 levels, up to 80 km) |
| `ionPrf` | Ionospheric electron density profile, up to the satellite's orbit (about 550-580 km) |
| `scnLv2` | Signal scintillation indices (S4, sigma-phi) |
| `ivmL2m` | In-situ plasma density, temperature and drift at spacecraft altitude |

Streams: `nrt` (near-real-time, about 30-120 minutes after observation), `rapid` (reprocessed within days; scnLv2 and ivmL2m), `postProc` (final, weeks to months later), `provisional` (space weather; ionPrf).

---

## Data Availability and Licensing

* **License**: MIT License (see [LICENSE](LICENSE))
* **Data Policy**: See [DATA_POLICY.md](DATA_POLICY.md) for UCAR CDAAC and NOAA NCEI data access and the suggested citations.
* **Third-Party Licenses**: See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for KaTeX, Plotly.js, TopoJSON, FastAPI, NumPy, SciPy, pandas, Matplotlib, netCDF4, Requests and pywebview licenses.

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
* Statistics, latitude-height sections and diagnostic maps against hand-computed cases; gravity-wave energy against a wave of known energy; the radiosonde pipeline against a synthetic sonde built from a profile's own fields, and IGRA file parsing on real records
* Every tab and main action in Chromium with no script errors (skipped unless Playwright and its Chromium are installed)
* Strict zero em/en-dash compliance and local asset integrity
* Windows double-click launch of a built EXE (skipped unless `dist/COSMIC2-Explorer.exe` or `COSMIC2_EXE` exists)
* Every DOI shown in the app is on a list checked against doi.org (re-resolved with `COSMIC2_NETWORK_TESTS=1`)
* Live CDAAC download (opt-in: `COSMIC2_NETWORK_TESTS=1`)
