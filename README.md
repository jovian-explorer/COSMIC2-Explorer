# COSMIC-2 Explorer

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23329841.svg)](https://doi.org/10.5281/zenodo.23329841)

A desktop GUI and analysis environment for the FORMOSAT-7 / COSMIC-2 radio occultation profiles published by UCAR CDAAC: find and download them, plot and compare them, compute diagnostics, and export data and figures. Everything except downloading works offline once the data are on your computer.

The retrievals themselves (bending angle, refractivity, temperature, humidity, electron density) are CDAAC's; the app reads those files and computes its diagnostics from them.

> **COSMIC-2 Explorer is public** (version 0.1.0). It is ready for use and for testing; results can still change between versions. Please report problems, wrong results and suggestions through **Feedback** in the app or on the [issue tracker](https://github.com/jovian-explorer/COSMIC2-Explorer/issues/new/choose). To cite COSMIC-2 Explorer, use the DOI [10.5281/zenodo.23329841](https://doi.org/10.5281/zenodo.23329841) (all versions; see [CITATION.cff](CITATION.cff)).

### In plain words

Six COSMIC-2 satellites watch GPS and other navigation signals bend as they pass through the air on their way to the satellite. How much a signal bends tells how dense the air is along its path, and from that comes a vertical profile of temperature, humidity and pressure up to about 40-60 km, and higher up of the free electrons of the ionosphere. Thousands of such profiles are measured every day between about 45 S and 45 N, and anyone can download them from UCAR. With this app you can:

* see where and when they were measured, on a map;
* plot temperature, humidity or electron density against height, one profile or hundreds;
* find the tropopause, the top of the boundary layer, the ionosphere's peak and other features;
* average profiles by latitude, season or time of day, and compare them with weather models, weather balloons and other satellites;
* export the numbers (CSV, netCDF) and publication-ready figures.

### Quick start

1. Download the app for your computer from the [Releases page](https://github.com/jovian-explorer/COSMIC2-Explorer/releases), unzip it and double-click `COSMIC2-Explorer` (details under [Install](#install)). No Python, no account.
2. The first time it opens it shows the example files that come with it (real profiles of 19 July 2026): on the **Explore** tab tick a few rows of the table, then open **Profiles** and press **Draw**.
3. To look at another day, open **Get data**, pick a date, press **Show what is available** and fetch a product (`wetPf2` is the friendliest: temperature and humidity). Every tab has a short explanation of what it shows, a word with a dotted underline explains itself when you point at it, and **Help** starts with a list of the words the screens use before it explains the science.

---

## Author and Affiliation

* **Lead Developer and Researcher**: Keshav Aggarwal
* **Current Affiliation**: Research Associate, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India
* **Former Affiliation**: Prime Minister's Research Fellow (PMRF Scholar), Department of Astronomy, Astrophysics and Space Engineering (DAASE), Indian Institute of Technology Indore (IIT Indore), Madhya Pradesh, India
* **Repository**: https://github.com/jovian-explorer/COSMIC2-Explorer

---

## Key Features

1. **Offline once downloaded**: KaTeX (equations), Plotly.js (plots) and the TopoJSON map outlines are bundled, so nothing but downloading needs a network.
2. **Seven COSMIC-2 products**: reads `wetPf2`, `atmPrf`, `ionPrf`, `scnLv2` and `ivmL2m`, and the ECMWF and NCEP model profiles CDAAC colocates with each occultation (`echPrf`, `avnPrf`). Downloads come from UCAR CDAAC, one day or a range of up to 31 days (one download per day) at a time; files in the same format from elsewhere (for example NOAA NCEI) can be dropped onto the window to be indexed.
3. **Diagnostics**: from CDAAC's retrieved (Abel-inverted) profiles the app computes the cold-point tropopause, the WMO lapse-rate tropopause (searched above 500 hPa, and on dry temperature only below 235 K), density ($\rho$, including water vapour where available), scale height ($H$), potential temperature ($\theta$), Brunt-Vaisala frequency ($N_{BV}^2$), F2 and E layer peaks with foF2, vertical TEC, integrated water vapour, the steepest refractivity gradient (a retrieved profile cannot show a duct: under one it is biased low, see section 6), the boundary-layer top (atmPrf only: where refractivity falls fastest, from 300 m line fits, accepted when the profile reaches 0.5 km, the top is below 3.5 km and N falls faster than 50 N-units/km; Ao et al. 2012, Guo et al. 2011; checked against IGRA radiosondes in the help, section O) and gravity-wave potential energy ($E_p$, 20-40 km). Where the file carries CDAAC's own value (tropopause, cold point, NmF2, hmF2, TEC, S4) the two are shown side by side.
4. **Interactive plots**: overlay up to 200 profiles of any quantity on any height axis; optionally filter outliers (sigma, MAD, IQR, percentile) and smooth (moving average, Gaussian, median, Savitzky-Golay) on screen, beside the raw profile; average profiles in groups (latitude band, hemisphere, day/night, date, product, satellite) with their spread or the 95 % confidence interval of the mean; and scatter any per-profile diagnostic against another.
5. **Statistics**: counts by product, latitude and local time, the archive's quality flags, and penetration depth (lowest retrieved level, above sea level and, where the matching wetPf2 gives the terrain height, above the ground) for the current search.
   The same tab draws **zonal-mean latitude-height sections** of any quantity (temperature, refractivity, electron density, ...): the mean, spread or count in each latitude band and height, or each band's departure in percent from the mean of all profiles at that height.
   It also maps any per-profile diagnostic (gravity-wave energy, tropopause height, foF2, ...) in latitude-longitude cells with its zonal mean; the gravity-wave energy can be recomputed for any layer with a polynomial or high-pass background.
   A table gives the WMO tropopause and the cold point by latitude band with 95 % confidence intervals, beside CDAAC's own values (from atmPrf).
6. **Comparison with weather models and error estimates**: each occultation against the ECMWF (echPrf) and NCEP (avnPrf) profiles CDAAC colocates with it, as RO minus model by height (refractivity, temperature, and bending angle against ECMWF by impact height), RO minus ECMWF refractivity with and without a duct that ECMWF diagnoses (echPrf `ductid`) and around it, which shows the retrieval's negative bias below ducts, and the three-cornered hat (Rieckh et al. 2021) for the refractivity error of RO, ECMWF and NCEP with bootstrap 95 % intervals.
7. **Comparison with other missions**: COSMIC-2 against PAZ, KOMPSAT-5, Metop-A, Metop-B, Metop-C or TanDEM-X (downloaded through their own streams), by height with 95 % intervals: collocated pairs, the same pairs less ECMWF's difference between their two occultations (Gilpin et al. 2018), and the double difference through ECMWF over the latitudes both missions cover. With another mission on disk, the Explore satellite filter can choose COSMIC-2 as a whole, so other statistics leave it out.
8. **Validation against radiosondes**: pairs each atmPrf or wetPf2 profile with the nearest NOAA IGRA v2 radiosonde within a chosen distance and time (300 km and 3 h by default) and shows the mean and spread of the differences in temperature, refractivity and specific humidity by geopotential height, with the list of pairs and an optional CSV; with atmPrf it also compares the boundary-layer tops found in both profiles (occultation against sonde, with mean, spread and correlation). Station files are downloaded from NOAA NCEI on first use (no account) and cached.
9. **Parallel Processing**: Composites, diagnostics tables, regridded exports and indexing run on a user-chosen number of CPU worker processes.
10. **Exports**: Matplotlib figures (PNG at 300 dpi by default, PDF, SVG, EPS), regridded netCDF-4 with CF-style attributes and UDUNITS units, CSV tables and JSON. Every on-screen plot also has a toolbar button that saves the numbers it draws, with its title and caption, as a CSV in the exports folder. Data files carry their provenance (input files, software version, data citation); figure files do not.

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
On first launch the app loads the 12 real granules (7 products) that ship with it, so every feature can be tried offline; **"Load the bundled example profiles"** on the Get data tab loads them again.

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
* Pressure, density, vapour pressure, specific humidity, refractivity and electron density (and bending angle, by impact height) are interpolated in log space when profiles are put on a common grid.
* Times are UTC. CDAAC's date and time attributes are GPS time (18 s ahead of UTC since 2017; they equal the files' GPS-second fields, and scnLv2's Earth rotation angle confirms it), so the app subtracts the leap seconds. A time shown in the app is therefore 18 s earlier than the one written in the file.
* Setting or rising: `irs` (atmPrf, wetPf2) and `setting` (ionPrf) are 1 for a setting occultation, as CDAAC's atmPrf format says (the wetPf2 attribute text has it the other way round). The files bear the format out: on 2026-09-16 every one of 2044 wetPf2 has `irs = 1` exactly when the ionPrf of the same occultation is setting by its bottom and top times, and PAZ, which records setting occultations only (Padullés et al. 2020), has `irs = 1` throughout. The satellite's look direction relative to its motion agrees: backwards (setting) for every PAZ atmPrf and for every KOMPSAT-5 atmPrf with `irs = 1`, forwards for every KOMPSAT-5 one with `irs = -1` (2026-09-26 and 27). The same holds for the other missions: for Metop-A (2021-10-27) and Metop-C (2026-05-31) occultations within 45 degrees of the equator, every `irs = 1` profile looks backwards and every `irs = -1` one forwards (judged from the occultation-plane azimuth and the direction of the sun-synchronous orbit at that local time); all 96 such TanDEM-X profiles of 2026-05-31 have `irs = -1` and look forwards, so TanDEM-X records rising occultations, and the 2019-12-10 COSMIC-1 files, from its last satellite, are rising too (the ionPrf bottom times come before the top times in all 23).
* Each atmPrf, wetPf2 or echPrf is placed at CDAAC's reference tangent point, a few kilometres up (a median 3.4 km on 300 atmPrf of COSMIC-2, Metop and TanDEM-X); the tangent point moves a median 113 km (244 km for 1 in 10) between the lowest level and 30 km, so collocation distances hold at that point only.
* CDAAC's post-processed ECMWF profiles (echPrf of the `postProc` streams) of October 2021 come from ECMWF analysis files (`ecmAnc`) whose refractivity is about 0.35 % above the occultations', ERA5's (`er5Prf`) and GFS's (`gfsPrf`): Metop-A, -B and -C minus echPrf is -0.30 to -0.38 % from 10 to 30 km on every day checked from 2021-10-01 to 10-31 (the first 110-150 good profiles of each), against within 0.06 % from 09-15 to 09-29 and 11-01 to 11-10, while the same occultations minus ERA5 and GFS stay within 0.1 % throughout. PAZ and KOMPSAT-5 post-processed files show the same (PAZ on 2021-10-05 and 10-27, KOMPSAT-5 on 10-05, 10-15 and 10-27: -0.28 to -0.42 % against echPrf, -0.07 to +0.03 % against ERA5; within 0.1 % against both on 09-20 and 09-29, and for KOMPSAT-5 in November), so every mission's post-processed echPrf of that month are affected. The bending angles show the same step, and the near-real-time echPrf (forecast files, `ecmFcc`) do not. The Statistics captions say when a comparison uses those profiles.
* Near-real-time against post-processed: on 601 PAZ occultations good in both streams (2026-05-15, 23 and 31), refractivity differs by under 0.03 % on average from 1 to 30 km (scatter 0.08 % at 10 km, up to 0.4 % at 1 and 20-35 km), the wetPf2 temperature by under 0.2 K up to 30 km; the post-processed stream holds about a tenth more occultations (756 against 689). For KOMPSAT-5 on the same days it holds three times as many (422 against 141; 288 against 138 without 05-15), with differences under 0.07 % in refractivity on average up to 30 km on the 67 good in both.
* Profile error bars are the running scatter of the values about their running mean (an estimate of level-to-level noise), not a retrieval uncertainty.
* The integrated water vapour starts at the lowest retrieved level; the height of that level is given alongside the value.
* Penetration depth is the lowest retrieved level of good atmPrf/wetPf2 profiles. Above the ground it uses the terrain height stored in the wetPf2 retrieved from the same atmPrf; on the 600 atmPrf profiles of 2026-06-20 and 2026-09-30, 84.5 % reach within 1 km of the ground (76.8 % below 1 km above sea level), in line with the more than 80 % reported by Schreiner et al. (2020).
* The Statistics tab compares each atmPrf with the wetPf2 retrieved from it (the wetPf2 file names its atmPrf, so the pairing is exact). On the 549 real 2026 pairs the observed refractivity is 0.65 % below the 1D-Var analysis at 0.5 km and within 0.05 % of it from 3 to 30 km; the dry temperatures of the two files agree within 0.1 K from 3 to 15 km; and the moisture effect (temperature minus dry temperature) is 56 K at 0.5 km, 1 K at 10 km and under 0.1 K above 14 km, matching 77.6 P_dry / N from the Smith-Weintraub refractivity of the wetPf2 state within 1 % up to 12 km.
* The radiosonde comparison pairs each profile with the nearest sounding by launch point and time, then uses a level only where the occultation's own tangent point at that level is within the distance limit of the launch point; the balloon's drift (about 20 km in the upper troposphere, 50 km in the lower stratosphere; Seidel et al. 2011) is not in IGRA and is not accounted for. It works on geopotential height: wetPf2's own `gph`, or atmPrf's height converted with Mahoney's (2001) normal gravity (within 2 m of wetPf2's `gph` on the real sample). Sonde refractivity is 77.6 p/T + 3.73e5 e/T^2 with e from the dew point (Bolton 1980); sonde humidity is compared only where the sonde is warmer than -40 C. On the 2026 sample (45 wetPf2-sonde pairs within 300 km and 3 h) the mean temperature difference stays within 0.5 K from 0 to 25 km (standard deviation 1-1.7 K), refractivity within 0.6 % from 3 to 30 km, and refractivity is 2.6 % low at 0-1 km, like the 3-4 % negative bias near the surface reported by Ho et al. (2020).
* Scintillation files (`scnLv2`) are placed at the tangent point of the ray at the S4 maximum, computed from the file's own satellite and transmitter positions: CDAAC's `lat/lon/alt_s4max_L1` are the satellite's position (about 570 km up, a median 1947 km from the tangent point on 602 files), and they lie a median 8.4 km from CDAAC's ionPrf tangent point at the same height (279 occultations of 2026-06-19). The files exist only for occultations in which the receiver's own S4 passed a set threshold (COSMIC-2 Space Weather Data Release 5), so statistics over them describe scintillating occultations, not how often scintillation occurs.
* Exports contain the archive values and derived fields. The outlier, smoothing and uncertainty settings on the Profiles tab affect the on-screen plot only, and the export provenance says so.

### Platform notes

* **Windows**: the native window uses Microsoft Edge WebView2, which ships with Windows 10 and 11.
* **macOS**: uses the built-in WebKit; nothing extra to install.
* **Linux**: from pip, the native window needs a GUI backend for pywebview: Qt (`pip install "cosmic2-explorer[qt] @ git+https://github.com/jovian-explorer/COSMIC2-Explorer.git"`) or GTK (the WebKitGTK system package, e.g. `sudo apt install gir1.2-webkit2-4.1`, plus `pip install pywebview[gtk]`). Without one, the app opens in your default browser automatically. The downloaded Linux build always uses the browser.

---

## Using it from Python

The readers and diagnostics behind the app are ordinary Python functions, so a script or notebook can use them without opening the window (install with Option 2 or 3 above). [`examples/headless.py`](examples/headless.py) runs on the bundled example files, or on a folder of your own CDAAC files: `python examples/headless.py path/to/folder`.

```python
from cosmic2 import analysis, exporters, readers
from cosmic2.config import sampledata_dir

path = str(next(sampledata_dir().glob("wetPf2_*")))
meta = readers.quick_meta(path)            # time (UTC), lat, lon, setting/rising, quality ...
g = readers.load(path)                     # g.data: variables as numpy arrays, g.units
d = analysis.diagnostics(g)                # tropopause, cold point, gravity waves, ducting ...
extra = analysis.derived_fields(g)         # potential temperature, N^2, density ...
comp = analysis.composite([(path, meta)], "Temp", top_km=30, min_count=1)
exporters.export_profiles_csv([meta])      # CSV with provenance in the exports folder
```

The comparisons of the Statistics tab are functions too. Against the weather models CDAAC colocates with each occultation (echPrf, avnPrf), and against another mission once its files are downloaded (here PAZ: `paz-nrt` or `paz-postProc` wetPf2 and echPrf for the same days):

```python
from cosmic2 import missions, nwp, readers
from cosmic2.config import sampledata_dir

rows = [readers.quick_meta(str(p)) for p in sampledata_dir().iterdir() if p.name.endswith("_nc")]
groups = nwp.stamp_groups([r for r in rows if r["product"] == "atmPrf"], rows)
diff = nwp.model_differences(groups, "refractivity", top_km=30, min_count=1)
ecmwf = diff["models"]["echPrf"]          # mean, std, n ... in % on diff["grid"] (km)
print(nwp.october_2021_echprf(groups), "occultations use the October 2021 ECMWF files")
cmp = missions.compare(rows, rows, other="paz", quantity="temperature", min_count=1)
print(cmp["n_cosmic2"], "COSMIC-2 and", cmp["n_other"], "PAZ profiles;",
      cmp["collocated"]["n_pairs"], "collocated pairs")
```

Downloading works the same way, through the app's own download queue; the files and the index are the app's, so they show up in the window too:

```python
import time
from cosmic2 import fetch, store

job = fetch.manager().submit_download(stream="metopc-postProc", level="level2",
                                      product="wetPf2", date="2026-05-31", max_profiles=50)
while job.state in ("queued", "running"):
    time.sleep(1)
rows = store.query_granules(products=["wetPf2"], sats=["MTPC"], limit=1000)["granules"]
```

| Module | What it gives you |
|---|---|
| `cosmic2.readers` | `load(path)` reads any supported product into a `Granule`; `quick_meta(path)` the one-line summary the index stores |
| `cosmic2.analysis` | `diagnostics(granule)`, `derived_fields(granule)`, `composite(...)` and the single-profile functions (`tropopause_wmo`, `cold_point`, `ionosphere_peak`, ...) |
| `cosmic2.climatology` | `cross_section`, `diagnostic_map`, `tropopause_table`, `pair_rows` / `product_differences` |
| `cosmic2.exporters` | `export_profiles_csv`, `export_grid_csv`, `export_netcdf`, `export_metadata_csv` |
| `cosmic2.fetch`, `cosmic2.store` | downloading from CDAAC and the local index the app searches |

Exports go to the app's data folder (`exports/`); set `COSMIC2_EXPLORER_HOME` to use another. These are the app's own functions, not a separate stable API: names can change between releases, and the CHANGELOG says when they do.

---

## Building the standalone app

```bash
pip install -e ".[build]"
python scripts/build_exe.py            # dist/COSMIC2-Explorer/COSMIC2-Explorer(.exe), macOS dist/COSMIC2-Explorer.app
python scripts/build_exe.py --archive  # plus the release archive for this OS
```

PyInstaller can only build for the OS it runs on. Releases are published about once a month: every Monday `.github/workflows/release.yml` checks that main has new commits, that the latest release is at least 30 days old and that CI passed on main's head, and only then tags it `v<version>` (`<version>` as in `pyproject.toml`), or `v<version>-build.<n+1>` when that tag exists. Running the workflow by hand, or pushing such a tag, publishes at once. The workflow builds Windows, macOS and Linux with `--archive --tag <tag>`, and attaches the three archives and `SHA256SUMS.txt` to a GitHub Release. Only builds stamped with a tag update themselves; releases are ordered by tag, so a later build of the same version is `v<version>-build.<n+1>`. After a successful publish the workflow deletes every release except the two newest (drafts are left alone); the tags are kept, so an installed copy several releases behind still updates straight to the newest release and can link the full comparison from its own tag.

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
│   ├── exporters.py          CSV / netCDF-4 / JSON export
│   ├── vocab.py              Variable labels, units, physical definitions
│   ├── config.py             Paths, settings, citation
│   ├── frontend/             Static HTML/CSS/JS (no build step), bundled Plotly, TopoJSON, KaTeX
│   └── sampledata/           12 real CDAAC granules (7 products) for offline use
├── examples/headless.py      Using the readers and diagnostics from a script
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
| `ivmL2m` | In-situ plasma density and temperature at spacecraft altitude (the drift fields are empty in every file checked: UCAR masks them until validated) |
| `echPrf` | ECMWF model temperature, pressure, water vapour, refractivity and simulated bending angle along the path of each occultation (same file stamp as its atmPrf) |
| `avnPrf` | NCEP model temperature, pressure, water vapour and refractivity along the path of each occultation (same file stamp as its atmPrf) |

Streams: `nrt` (near-real-time, about 30-120 minutes after observation), `rapid` (reprocessed within days; scnLv2 and ivmL2m), `postProc` (final orbits; for COSMIC-2 only ivmL2m of 2019-08-01 to 2022-05-31 and podTc2 of 2020, no atmPrf, wetPf2 or ionPrf), `provisional` (space weather; ionPrf). Two more streams fetch other radio occultation missions that CDAAC processes into the same files, for comparison with COSMIC-2: `paz-nrt` (PAZ, a polar orbit; 210-223 profiles a day on the 2026 sample days) and `kompsat5-nrt` (KOMPSAT-5; 78-85 a day), `paz-postProc` and `kompsat5-postProc` (the same missions reprocessed with final orbits, from 2018 and 2015 to about four months ago; an occultation held twice, downloaded from both streams or also imported from disk, counts once: as its post-processed copy, else the downloaded one (Explore says how many copies were left out; choosing a stream in its Stream filter gets all of that stream's files)), `metopb-postProc` and `metopc-postProc` (Metop-B and -C, polar orbits; post-processed only, about four months behind; 375 and 395 wetPf2 on 2026-05-31; `metopa-postProc` for Metop-A from 2016 to its end in November 2021, 427 wetPf2 on 2021-10-27), `tdx-postProc` (TanDEM-X, polar orbit, post-processed; 168 wetPf2 on 2026-05-31) and `cosmic1-repro2021` (COSMIC-1, the predecessor mission, reprocessed as one record for 2006-2019; 2207 wetPf2 on 2008-06-28, 66 on 2019-12-10, when one satellite was left). They are kept in their own cache folders and datasets, and "Show what is available" lists them only when one of them is the chosen stream.

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
* Statistics, latitude-height sections and diagnostic maps against hand-computed cases; gravity-wave energy against a wave of known energy; the radiosonde pipeline against a synthetic sonde built from a profile's own fields (including the boundary-layer tops of both), and IGRA file parsing on real records
* The boundary-layer top on synthetic profiles (steepest fall, acceptance tests) and only from observed refractivity
* The scintillation geometry: the files' inertial satellite positions turned Earth-fixed land on their own latitude and longitude, the ray's closest point on their `occheight`, and each file is placed at the tangent point of its S4 maximum
* Every tab and main action in Chromium with no script errors (skipped unless Playwright and its Chromium are installed)
* Strict zero em/en-dash compliance and local asset integrity
* Windows double-click launch of a built EXE (skipped unless `dist/COSMIC2-Explorer/COSMIC2-Explorer.exe` or `COSMIC2_EXE` exists), including that a hard kill leaves no `_MEI*` folder in `%TEMP%`
* Every DOI shown in the app is on a list checked against doi.org (re-resolved with `COSMIC2_NETWORK_TESTS=1`)
* Every "CDAAC Archive" link is an archive folder (opened with `COSMIC2_NETWORK_TESTS=1`)
* Live CDAAC download (opt-in: `COSMIC2_NETWORK_TESTS=1`)
