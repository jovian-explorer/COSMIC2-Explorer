# COSMIC-2 Explorer: Data Availability and Third-Party Data Policy

**Lead Author and Maintainer**: Keshav Aggarwal, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO, Thiruvananthapuram, Kerala, India.

## 1. Overview and Open Access Philosophy

COSMIC-2 Explorer is an open-source scientific software platform designed for the discovery, ingestion, visualisation, and atmospheric analysis of Global Navigation Satellite System Radio Occultation (GNSS-RO) soundings. The platform connects directly to public-domain space agency data repositories and processes scientific data products locally without proprietary data gatekeeping.

All data retrieved, cached, or processed by COSMIC-2 Explorer originates from publicly accessible archives maintained by national space agencies, scientific consortia, and university archives under open-data mandates.

---

## 2. Primary Data Archives and Access Endpoints

### A. UCAR CDAAC (COSMIC Data Analysis and Archive Center)
* **Operating Institution**: University Corporation for Atmospheric Research (UCAR), Boulder, Colorado, USA.
* **Sponsoring Agencies**: National Science Foundation (NSF), National Oceanic and Atmospheric Administration (NOAA), National Aeronautics and Space Administration (NASA), United States Space Force (USSF).
* **Archive URL**: https://data.cosmic.ucar.edu/
* **Mission Portal**: https://www.cosmic.ucar.edu/
* **Coverage**: Near-real-time (rt), post-processed (postProc), and reprocessed (repro) daily tarballs for FORMOSAT-7 / COSMIC-2 (wetPf2, atmPrf, sonPrf, bfrPrf, ionPrf, podTc2).
* **Access Policy**: Open access for scientific research, atmospheric modeling, and educational purposes. Registration is free and unrestricted via UCAR CDAAC credentials.

### B. NOAA NCEI (National Centers for Environmental Information)
* **Operating Institution**: National Oceanic and Atmospheric Administration (NOAA), Department of Commerce, USA.
* **Archive URL**: https://www.ncei.noaa.gov/data/gps-radio-occultation/
* **Mission Portal**: https://www.nesdis.noaa.gov/current-satellite-missions/currently-flying/formosat-7-cosmic-2
* **Access Policy**: U.S. Federal Government open-data policy (Public Domain / CC0-compatible). Free, anonymous access over HTTPS.

### C. TASA (Taiwan Space Agency)
* **Operating Institution**: Taiwan Space Agency (TASA), Hsinchu, Taiwan.
* **Mission Portal**: https://www.tasa.org.tw/en-US/
* **Partnership**: Joint international collaboration between American Institute in Taiwan (AIT) and Taipei Economic and Cultural Representative Office (TECRO), executed by NOAA and TASA.

---

## 3. Data Availability Statement for Publications

When publishing scientific findings, atmospheric figures, or derived geophysical datasets produced using COSMIC-2 Explorer, authors should include a Data Availability Statement structured as follows:

> **Data Availability Statement**:
> The COSMIC-2 radio occultation soundings analyzed in this study are publicly available from the University Corporation for Atmospheric Research (UCAR) COSMIC Data Analysis and Archive Center (CDAAC) at https://data.cosmic.ucar.edu/ and the NOAA National Centers for Environmental Information (NCEI) at https://www.ncei.noaa.gov/data/gps-radio-occultation/. The processing, validation, and profile analysis were conducted using COSMIC-2 Explorer (Version 0.0.1), available open-source at https://github.com/jovian-explorer/COSMIC2-Explorer.

---

## 4. Citation Requirements

To ensure proper provenance and scientific reproducibility, please provide dual citations: one for the primary data archive and one for the COSMIC-2 Explorer processing environment.

### Citation 1: Primary Data Archive (UCAR CDAAC)
* UCAR COSMIC Program, 2019: COSMIC-2 Data Products. UCAR/NCAR - COSMIC Data Analysis and Archive Center, Boulder, CO, USA, accessed via https://doi.org/10.5065/dp33-mz35.

### Citation 2: COSMIC-2 Explorer Software
* Aggarwal, Keshav (2026). COSMIC-2 Explorer: High-Resolution Radio Occultation Processing, Visualisation, and Atmospheric Profiling System (Version 0.0.1) [Computer software]. Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO, Thiruvananthapuram, Kerala, India.

```bibtex
@software{Aggarwal_COSMIC2_Explorer_2026,
  author = {Aggarwal, Keshav},
  title = {{COSMIC-2 Explorer: High-Resolution Radio Occultation Processing, Visualisation, and Atmospheric Profiling System}},
  year = {2026},
  version = {0.0.1},
  institution = {Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO},
  address = {Thiruvananthapuram, Kerala, India},
  url = {https://github.com/jovian-explorer/COSMIC2-Explorer}
}
```

---

## 5. Offline Data Handling and Local Privacy

* COSMIC-2 Explorer stores all downloaded granules and intermediate NetCDF/Parquet/CSV artifacts strictly on the local filesystem (`%LOCALAPPDATA%\COSMIC2Explorer`).
* The software never transmits downloaded scientific granules, profile coordinates, or user session data to third-party telemetric servers.
* Complete offline functionality is guaranteed: all mathematical rendering (KaTeX) and profile plotting (Plotly.js) run from locally vendored assets.
