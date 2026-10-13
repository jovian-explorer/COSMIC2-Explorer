# COSMIC-2 Explorer: Data Availability and Third-Party Data Policy

**Lead Author and Maintainer**: Keshav Aggarwal, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO, Thiruvananthapuram, Kerala, India.

## 1. Overview and Open Access Philosophy

COSMIC-2 Explorer is an open-source scientific software platform designed for the discovery, ingestion, visualisation, and atmospheric analysis of Global Navigation Satellite System Radio Occultation (GNSS-RO) soundings. It downloads from the public UCAR CDAAC archive (no account needed) and processes the data locally.

All data COSMIC-2 Explorer downloads come from the UCAR CDAAC archive. Files from other archives in the same CDAAC netCDF format (for example NOAA NCEI) can be imported from disk.

---

## 2. Primary Data Archives and Access Endpoints

### A. UCAR CDAAC (COSMIC Data Analysis and Archive Center)
* **Operating Institution**: University Corporation for Atmospheric Research (UCAR), Boulder, Colorado, USA.
* **Sponsoring Agencies**: National Science Foundation (NSF), National Oceanic and Atmospheric Administration (NOAA), National Aeronautics and Space Administration (NASA), United States Space Force (USSF).
* **Archive URL**: https://data.cosmic.ucar.edu/
* **Mission Portal**: https://www.cosmic.ucar.edu/
* **Coverage used by the app**: daily tarballs of the FORMOSAT-7 / COSMIC-2 streams `nrt`, `rapid`, `postProc` and `provisional`; the app reads atmPrf, wetPf2, ionPrf, scnLv2 and ivmL2m.
* **Access Policy**: The data are downloadable over HTTPS without registration. UCAR publishes no licence text for them and asks users to cite the data set (doi:10.5065/T353-C093, see section 4).

### B. NOAA NCEI (National Centers for Environmental Information)
* **Operating Institution**: National Oceanic and Atmospheric Administration (NOAA), Department of Commerce, USA.
* **Archive URL**: https://www.ncei.noaa.gov/data/gps-radio-occultation/
* **Mission Portal**: https://www.nesdis.noaa.gov/current-satellite-missions/currently-flying/formosat-7-cosmic-2
* **Access Policy**: U.S. Federal Government open-data policy; free, anonymous access over HTTPS. COSMIC-2 Explorer does not download from NCEI itself.

### C. TASA (Taiwan Space Agency)
* **Operating Institution**: Taiwan Space Agency (TASA), Hsinchu, Taiwan.
* **Mission Portal**: https://www.tasa.org.tw/en-US/
* **Partnership**: Joint international collaboration between American Institute in Taiwan (AIT) and Taipei Economic and Cultural Representative Office (TECRO), executed by NOAA and TASA.

---

## 3. Data Availability Statement for Publications

When publishing scientific findings, atmospheric figures, or derived geophysical datasets produced using COSMIC-2 Explorer, authors should include a Data Availability Statement structured as follows:

> **Data Availability Statement**:
> The COSMIC-2 radio occultation soundings analyzed in this study are publicly available from the University Corporation for Atmospheric Research (UCAR) COSMIC Data Analysis and Archive Center (CDAAC) at https://data.cosmic.ucar.edu/ and the NOAA National Centers for Environmental Information (NCEI) at https://www.ncei.noaa.gov/data/gps-radio-occultation/. The profile analysis was conducted using COSMIC-2 Explorer (Version 0.1.0), https://doi.org/10.5281/zenodo.23329841, available open-source at https://github.com/jovian-explorer/COSMIC2-Explorer.

---

## 4. Suggested Citations

Please cite the data set as UCAR asks and, if you used this software, COSMIC-2 Explorer as well.

### Citation 1: Primary Data Archive (UCAR CDAAC)
* UCAR COSMIC Program, 2019: COSMIC-2 Data Products [Data set]. UCAR/NCAR - COSMIC, Access date [insert date], https://doi.org/10.5065/T353-C093 (the form suggested on https://www.cosmic.ucar.edu/what-we-do/cosmic-2/data).

### Citation 2: COSMIC-2 Explorer Software
* Aggarwal, Keshav (2026). COSMIC-2 Explorer: High-Resolution Radio Occultation Processing, Visualisation, and Atmospheric Profiling System (Version 0.1.0) [Computer software]. Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO, Thiruvananthapuram, Kerala, India. https://doi.org/10.5281/zenodo.23329841

```bibtex
@software{Aggarwal_COSMIC2_Explorer_2026,
  author = {Aggarwal, Keshav},
  title = {{COSMIC-2 Explorer: High-Resolution Radio Occultation Processing, Visualisation, and Atmospheric Profiling System}},
  year = {2026},
  version = {0.1.0},
  doi = {10.5281/zenodo.23329841},
  institution = {Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO},
  address = {Thiruvananthapuram, Kerala, India},
  url = {https://github.com/jovian-explorer/COSMIC2-Explorer}
}
```

---

## 5. Offline Data Handling and Local Privacy

* COSMIC-2 Explorer stores downloaded granules, its index and its exports (CSV, netCDF, JSON, figures) on the local filesystem only: `%LOCALAPPDATA%\COSMIC2Explorer` on Windows, `~/Library/Application Support/COSMIC2Explorer` on macOS, `~/.local/share/COSMIC2Explorer` on Linux, or `COSMIC2_EXPLORER_HOME`.
* The software never transmits downloaded scientific granules, profile coordinates, or user session data to third-party telemetric servers.
* Once data are downloaded, everything except downloads works offline: mathematical rendering (KaTeX), plotting (Plotly.js) and map outlines (TopoJSON) are bundled. The radiosonde comparison downloads NOAA IGRA v2 station files from https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/ the first time they are needed (public, no account) and caches them under `cache/igra`.
