# COSMIC-2 Explorer: Build and Verification Status

**Status Updated**: 2026-09-20
**Lead Researcher**: Keshav Aggarwal, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India (Former PMRF Scholar at DAASE, IIT Indore).

---

## 1. System Overview

COSMIC-2 Explorer is a high-resolution, production-grade scientific desktop visualization and atmospheric analysis platform tailored for Global Navigation Satellite System Radio Occultation (GNSS-RO) soundings from the FORMOSAT-7 / COSMIC-2 constellation. The platform also natively integrates the VEDA multi-mission scientific framework for comparative planetary atmospheric investigations.

---

## 2. Completed Milestones

### A. Scientific Analysis and Diagnostics
* **Refractivity & Abel Inversion**: Implements the Smith-Weintraub equation for microwave refractivity $N$ and numerical Abel transform inversion to retrieve atmospheric refractivity $\mu(r)$ and dry temperature $T_{dry}$.
* **Tropopause Detection**: Automated detection of cold point tropopause (CPT) and WMO lapse-rate tropopause (LRT) with definitional 500 hPa pressure floor guard to prevent shallow boundary layer inversions.
* **Atmospheric Scaling**: Rigorous analytical calculation of atmospheric scale height ($H = R_{dry} T / g$) and atmospheric density ($\rho = P / (R_{dry} T)$).
* **Ionospheric Soundings**: F2-peak electron density ($N_mF_2$), peak height ($h_mF_2$), and critical frequency ($f_oF_2$) extracted from `ionPrf` soundings.
* **Data Cleansing**: Outlier removal algorithms (Sigma, MAD, IQR, Percentile) and vertical profile smoothing (Gaussian, Savitzky-Golay, Median filtering).

### B. Offline Mathematics and Visualization
* **Local KaTeX Package**: Bundled offline KaTeX 0.16.8 (JavaScript engine, CSS stylesheets, and WOFF2 fonts) in `frontend/vendor/katex/`. All mathematical formulas render locally without external CDN calls.
* **Plotly.js and TopoJSON**: Bundled offline Plotly.js chart engine and Land 110m TopoJSON datasets for geographical mapping.
* **Visual Identity and Icons**: Dedicated mission emblem and application icons generated and embedded in multi-resolution ICO formats (`build/cosmic2.ico`, `dist/cosmic2.ico`, `frontend/assets/cosmic2.ico`).

### C. Third-Party Data Compliance and Licensing
* **MIT License**: Full root `LICENSE` file created for Keshav Aggarwal, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO.
* **Data Policy Statement**: Complete `DATA_POLICY.md` detailing public access to UCAR CDAAC and NOAA NCEI repositories, data availability statements for scientific journals, and BibTeX dual-citation instructions.
* **Third-Party Disclosures**: `THIRD_PARTY_LICENSES.md` documenting open-source licenses for KaTeX, Plotly.js, TopoJSON, FastAPI, NumPy, SciPy, Matplotlib, netCDF4, and pywebview.

### D. Windows Desktop Shell and Packaging
* **Explorer Launch Hardening**: Neutralized Windows Explorer launch issues (`console=False`) where standard I/O streams are null. Added explicit `sys.stdin/stdout/stderr` stubs and automatic fallback from WebView2 to system browser.
* **PyInstaller Single-File Executable**: Configured `build/app.spec` with embedded `cosmic2.ico`, datas, and VEDA hidden imports.

---

## 3. Active Verification Suite

Run all verification tests from the project root:

```powershell
python -m pytest tests/ -v
```

Tests cover:
* `tests/test_cosmic2.py`: 36 tests covering vocab, readers, analysis, API, and exporters.
* `tests/test_pipeline.py`: 10 tests covering outlier methods, smoothing filters, and uncertainty calculation.
* `tests/test_explorer_launch.py`: Standalone launch tests simulating Windows Explorer double-click execution.
* `tests/test_compliance_and_assets.py`: Codebase compliance tests verifying zero em/en-dashes, document integrity, and KaTeX local assets.
