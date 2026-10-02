"""Human-readable vocabulary for CDAAC variables.

Two audiences are served from one table: ``label``/``units`` for the
scientist, ``plain`` for the curious visitor.  ``role`` tells the UI whether a
variable is a sensible vertical coordinate, a plottable field, or metadata.
"""
from __future__ import annotations

VERTICAL = "vertical"      # usable as the y-axis of a profile plot
FIELD = "field"            # usable as the x-axis of a profile plot
COORD = "coord"            # geolocation / time, plottable but rarely the point
AUX = "aux"                # flags, diagnostics, ancillary geometry

VAR_INFO: dict[str, dict] = {
    # ---- vertical coordinates ----------------------------------------
    "MSL_alt": dict(
        label="Altitude above mean sea level", units="km",
        plain="Height above mean sea level geoid.", role=VERTICAL,
        formula=r"z = r - R_E(\phi)",
        reference="BIPM / IERS Conventions (2010); UCAR CDAAC Processing Handbook",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 2 Georeferenced Vertical Coordinate",
        algorithm="Geometric height above WGS-84 reference ellipsoid transformed to mean sea level using EGM96 geoid undulations."
    ),
    "gph": dict(
        label="Geopotential height", units="km",
        plain="Height corrected for how gravity weakens with altitude.", role=VERTICAL,
        formula=r"Z = \frac{1}{g_0} \int_0^z g(\phi, z')\,dz'",
        reference="WMO Guide to Meteorological Instruments and Methods of Observation (WMO-No. 8)",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 2 Geopotential Vertical Coordinate",
        algorithm="Numerical integration of gravity along geometric altitude, normalized by standard gravity g0 = 9.80665 m/s^2."
    ),
    "Impact_height": dict(
        label="Impact height", units="km",
        plain="Height of the straight-line ray path - the natural vertical coordinate for bending angle.",
        role=VERTICAL,
        formula=r"h_{imp} = a - R_c",
        reference="Kursinski et al. (1997), J. Geophys. Res., 102(D19), 23429-23465",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 1b / Level 2 Impact Parameter Coordinate",
        algorithm="Impact parameter 'a = n*r*sin(phi)' minus local center-of-curvature radius Rc."
    ),
    "Imp_height_corr": dict(
        label="Impact height (corrected)", units="km",
        plain="Impact height after spherical symmetry geometry correction.", role=VERTICAL,
        formula=r"h_{imp,corr} = a_{corr} - R_c",
        reference="Syndergaard, S. (1998), Radio Sci., 33(3), 665-679",
        doi="10.1029/98RS00057",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 1b Calibrated Geometry",
        algorithm="Impact height with correction for Earth oblateness and local ellipsoidal curvature."
    ),
    "occheight": dict(
        label="Occultation (tangent point) height", units="km",
        plain="Height of the point where the ray grazes closest to Earth.", role=VERTICAL,
        formula=r"r_{tan} = \sqrt{x_{tp}^2 + y_{tp}^2 + z_{tp}^2} - R_E",
        reference="Kursinski et al. (1997), J. Geophys. Res., 102(D19), 23429-23465",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        data_level="Level 2 Tangent Point Coordinate",
        algorithm="Geocentric distance of the ray-path tangent point minus local Earth radius."
    ),
    "alt": dict(
        label="Spacecraft altitude", units="km",
        plain="Orbit altitude of the satellite itself.", role=VERTICAL,
        formula=r"h_{sc} = \|\mathbf{r}_{sc}\| - R_E",
        reference="Weiss et al. (2020), Space Sci. Rev., 216, 128",
        doi="10.1007/s11214-020-00756-w",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 1b Orbit State",
        algorithm="Spacecraft orbital altitude above WGS-84 ellipsoid from TriG precise orbit determination."
    ),
    "Pres": dict(
        label="Pressure", units="hPa",
        plain="Air pressure - the weight of the atmosphere above you.", role=FIELD,
        formula=r"P(z) = P(z_{top}) + \int_z^{z_{top}} \rho(z') g(z') dz'",
        reference="Healy, S. B., & Eyre, J. R. (2000), Q. J. R. Meteorol. Soc., 126, 1661-1680",
        doi="10.1002/qj.49712656606",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/wetPf2/",
        data_level="Level 2 (1D-Var Optimal Estimation)",
        algorithm="Hydrostatic equilibrium integrated downward coupled with 1D-Var variational assimilation."
    ),
    "pres_dry": dict(
        label="Dry pressure", units="hPa",
        plain="Pressure worked out while ignoring water vapour.", role=FIELD,
        formula=r"P_{dry}(z) = \frac{k_B}{\bar{m}_{dry}} \int_z^\infty \rho_{dry}(z') g(z') dz'",
        reference="Scherllin-Pirscher et al. (2017), Atmos. Meas. Tech., 10, 1211-1226",
        doi="10.5194/amt-10-1211-2017",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 2 (Native Abel Inversion)",
        algorithm="Hydrostatic downward integration assuming zero atmospheric moisture contribution."
    ),

    # ---- neutral atmosphere fields -----------------------------------
    "Temp": dict(
        label="Temperature", units="C",
        plain="Thermodynamic temperature from 1D-Var retrieval.", role=FIELD,
        formula=r"T = T_b + \mathbf{K} (y - H(x_b))",
        reference="Rodgers, C. D. (2000), Inverse Methods for Atmospheric Sounding, World Scientific",
        doi="10.1142/3171",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/wetPf2/",
        data_level="Level 2 (1D-Var Retrieval)",
        algorithm="Optimal estimation combining observed refractivity profile with ECMWF/GFS background."
    ),
    "temp_dry": dict(
        label="Dry temperature", units="C",
        plain="Temperature assuming the air holds no water vapour. Highly accurate above 10 km.",
        role=FIELD,
        formula=r"T_{dry}(z) = \frac{\bar{m}_{dry}}{k_B N(z)} \int_z^\infty g(z') N(z') dz'",
        reference="Kursinski et al. (1997), J. Geophys. Res., 102(D19), 23429-23465",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 2 (Abel Inversion)",
        algorithm="Downward quadrature integration of refractivity under hydrostatic balance ignoring water vapor."
    ),
    "Vp": dict(
        label="Water-vapour partial pressure", units="hPa",
        plain="The share of the air pressure contributed by water vapour.", role=FIELD,
        formula=r"e = \frac{q \cdot P}{\epsilon + (1 - \epsilon) q}",
        reference="Healy & Eyre (2000), QJRMS, 126, 1661-1680",
        doi="10.1002/qj.49712656606",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/wetPf2/",
        data_level="Level 2 (1D-Var Retrieval)",
        algorithm="Water vapor partial pressure extracted via 1D-Var optimal estimation."
    ),
    "sph": dict(
        label="Specific humidity", units="g/kg",
        plain="Grams of water vapour in each kilogram of moist air.", role=FIELD,
        formula=r"q = \frac{\epsilon e}{P - (1 - \epsilon) e}",
        reference="Healy & Eyre (2000), QJRMS, 126, 1661-1680",
        doi="10.1002/qj.49712656606",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/wetPf2/",
        data_level="Level 2 (1D-Var Retrieval)",
        algorithm="Mass mixing ratio of water vapor per unit moist air."
    ),
    "rh": dict(
        label="Relative humidity", units="%",
        plain="How close the air is to being saturated with water vapor.", role=FIELD,
        formula=r"RH = 100 \times \frac{e}{e_s(T)}",
        reference="Goff, J. A. (1957), Saturation vapor pressure over water, Trans. ASHVE",
        doi="10.1002/qj.49712656606",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/wetPf2/",
        data_level="Level 2 (1D-Var Retrieval)",
        algorithm="Ratio of water vapor partial pressure to saturation vapor pressure computed via Goff-Gratch formulation."
    ),
    "ref": dict(
        label="Refractivity", units="N-units",
        plain="How strongly the air bends radio waves.", role=FIELD,
        formula=r"N = (n - 1) \times 10^6 \approx 77.6 \frac{P}{T} + 3.73 \times 10^5 \frac{e}{T^2}",
        reference="Smith, E. K., & Weintraub, S. (1953), Proc. IRE, 41(8), 1035-1037",
        doi="10.1109/JRPROC.1953.274297",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/wetPf2/",
        data_level="Level 2 (1D-Var Grid)",
        algorithm="Radio refractivity interpolated or re-evaluated from 1D-Var analysis fields."
    ),
    "Ref": dict(
        label="Refractivity", units="N-units",
        plain="How strongly the air bends radio waves, native Abel inversion.", role=FIELD,
        formula=r"N(r) = 10^6 \left( \exp\left[\frac{1}{\pi} \int_a^\infty \frac{\alpha(x)}{\sqrt{x^2 - a^2}} dx\right] - 1 \right)",
        reference="Fjeldbo, G., Kliore, A. J., & Eshleman, V. R. (1971), Astron. J., 76, 123-140",
        doi="10.1086/111096",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 2 (Abel Inversion)",
        algorithm="Inverted from bending angle profile alpha(a) via the standard Abel integral transform."
    ),
    "Ref_L1": dict(
        label="Refractivity from L1 only", units="N-units",
        plain="Refractivity from just the primary L1 radio frequency.", role=FIELD,
        formula=r"N_{L1} = (n_{L1} - 1) \times 10^6",
        reference="Kursinski et al. (1997), J. Geophys. Res., 102(D19), 23429-23465",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 2 Single-Frequency Diagnostic",
        algorithm="Abel inversion applied directly to L1 bending angles before dual-frequency ionospheric combination."
    ),
    "Bend_ang": dict(
        label="Bending angle (ionosphere-corrected)", units="rad",
        plain="The angle by which the atmosphere bent the radio ray. The fundamental RO measurement.",
        role=FIELD,
        formula=r"\alpha(a) = \frac{f_1^2 \alpha_1(a) - f_2^2 \alpha_2(a)}{f_1^2 - f_2^2}",
        reference="Vorob'ev, V. V., & Krasil'nikova, T. G. (1994), Izvestiya Atmos. Ocean. Phys., 29, 602-609",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 2 (Calibrated Neutral Bending)",
        algorithm="Dual-frequency linear combination of L1 and L2 bending angles to eliminate first-order ionospheric dispersion."
    ),
    "Bend_ang1": dict(
        label="Bending angle, L1", units="rad",
        plain="Bending measured on the first radio frequency (1575.42 MHz).", role=FIELD,
        formula=r"\alpha_1(a) = -\int_{-\infty}^\infty \frac{1}{n} \frac{\partial n}{\partial r} \frac{a}{r} ds",
        reference="Kursinski et al. (1997), J. Geophys. Res., 102(D19), 23429-23465",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 1b / Level 2 Frequency-Specific Bending",
        algorithm="Doppler frequency shift converted to ray bending angle using geometric optical equations."
    ),
    "Bend_ang2": dict(
        label="Bending angle, L2", units="rad",
        plain="Bending measured on the second radio frequency (1227.60 MHz).", role=FIELD,
        formula=r"\alpha_2(a) = -\int_{-\infty}^\infty \frac{1}{n} \frac{\partial n}{\partial r} \frac{a}{r} ds",
        reference="Kursinski et al. (1997), J. Geophys. Res., 102(D19), 23429-23465",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 1b / Level 2 Frequency-Specific Bending",
        algorithm="Doppler frequency shift converted to ray bending angle on GPS L2 carrier frequency."
    ),
    "Bend_ang_stdv": dict(
        label="Bending-angle standard deviation", units="rad",
        plain="Uncertainty on the bending angle.", role=AUX,
        formula=r"\sigma_\alpha(a)",
        reference="Schreiner et al. (2020), Atmos. Meas. Tech., 13, 6499-6519",
        doi="10.5194/amt-13-6499-2020",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 2 Quality Metric",
        algorithm="Estimated observational noise from Doppler tracking residuals."
    ),
    "Bend_ang_conf": dict(
        label="Bending-angle confidence", units="%",
        plain="A quality score for the bending angle.", role=AUX,
        formula=r"C_{bend} \in [0, 100]",
        reference="Schreiner et al. (2020), Atmos. Meas. Tech., 13, 6499-6519",
        doi="10.5194/amt-13-6499-2020",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/nrt/level2/atmPrf/",
        data_level="Level 2 Quality Metric",
        algorithm="Statistical confidence score evaluated by CDAAC quality control pipeline."
    ),

    # ---- ionosphere ---------------------------------------------------
    "ELEC_dens": dict(
        label="Electron density", units="el/cm3",
        plain="How many free electrons sit in each cubic centimetre.", role=FIELD,
        formula=r"N_e(r) = -\frac{f^2}{40.3 \pi} \int_r^{r_{leo}} \frac{d\alpha_{iono}/da}{\sqrt{a^2 - r^2}} da",
        reference="Schreiner, W. S., et al. (1999), Geophys. Res. Lett., 26(15), 2339-2342",
        doi="10.1029/1999GL900508",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/provisional/spaceWeather/level2/ionPrf/",
        data_level="Level 2 (Ionospheric Abel Inversion)",
        algorithm="Abel transform applied to ionospheric excess phase or bending angle under spherical symmetry."
    ),
    "TEC_cal": dict(
        label="Calibrated TEC", units="TECU",
        plain="Total electron content along the signal path.", role=FIELD,
        formula=r"TEC = \frac{1}{40.3} \frac{f_1^2 f_2^2}{f_1^2 - f_2^2} (L_1 - L_2)",
        reference="Syndergaard, S. (2000), Radio Science, 35(3), 865-883",
        doi="10.1029/2000RS002319",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/provisional/spaceWeather/level2/ionPrf/",
        data_level="Level 2 (Calibrated Path Integral)",
        algorithm="Differential code/phase TEC calibrated using precise satellite clock and orbit ephemerides."
    ),
    "ion_dens": dict(
        label="Ion density (in-situ)", units="N/cc",
        plain="Plasma density measured right at the spacecraft.", role=FIELD,
        formula=r"N_i = \frac{I_{sat}}{q_e A v_{sc}}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM)",
        algorithm="In-situ planar ion trap saturation current normalized by spacecraft orbital speed and sensor aperture."
    ),
    "ion_temp": dict(
        label="Ion temperature", units="K",
        plain="Temperature of the charged plasma particles.", role=FIELD,
        formula=r"T_i = \frac{m_i}{2 k_B} v_{thermal}^2",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM)",
        algorithm="Ion velocity distribution Maxwellian temperature fit from Retarding Potential Analyzer (RPA)."
    ),
    "ap_pot": dict(
        label="Spacecraft potential", units="V",
        plain="Electrical charge the spacecraft built up relative to ambient plasma.", role=AUX,
        formula=r"\Phi_{sc}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM Diagnostic)",
        algorithm="Floating potential of spacecraft body determined from IVM sensor characteristics."
    ),
    "iv_zon": dict(
        label="Zonal ion drift", units="m/s",
        plain="East-west speed of the ionospheric plasma.", role=FIELD,
        formula=r"v_{i,zon} = \frac{\mathbf{E} \times \mathbf{B}}{B^2} \cdot \hat{\mathbf{e}}_{\phi}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM Drift)",
        algorithm="Cross-track plasma drift component in the local geomagnetic zonal direction."
    ),
    "iv_mer": dict(
        label="Meridional ion drift", units="m/s",
        plain="North-south speed of the ionospheric plasma.", role=FIELD,
        formula=r"v_{i,mer} = \frac{\mathbf{E} \times \mathbf{B}}{B^2} \cdot \hat{\mathbf{e}}_{\theta}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM Drift)",
        algorithm="Cross-track plasma drift component in the local geomagnetic meridional direction."
    ),
    "iv_par": dict(
        label="Field-parallel ion drift", units="m/s",
        plain="Plasma speed along the geomagnetic field lines.", role=FIELD,
        formula=r"v_{i,\parallel} = \mathbf{v}_i \cdot \frac{\mathbf{B}}{\|B\|}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM Drift)",
        algorithm="Component of plasma velocity vector parallel to Earth's ambient magnetic field."
    ),
    "iv_ew": dict(
        label="Ion drift, east", units="m/s", plain="Geographic eastward plasma speed.",
        role=FIELD, formula=r"v_{i,east}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM Drift)", algorithm="Geographic east component of ion drift."
    ),
    "iv_ns": dict(
        label="Ion drift, north", units="m/s", plain="Geographic northward plasma speed.",
        role=FIELD, formula=r"v_{i,north}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM Drift)", algorithm="Geographic north component of ion drift."
    ),
    "iv_ud": dict(
        label="Ion drift, up", units="m/s", plain="Vertical upward plasma speed.",
        role=FIELD, formula=r"v_{i,up}",
        reference="Klenzing, J., et al. (2020), Space Sci. Rev., 216, 142",
        doi="10.1007/s11214-020-00762-y", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/ivmL2m/",
        data_level="Level 2 (In-Situ IVM Drift)", algorithm="Radial upward component of ion drift."
    ),
    "mlt": dict(
        label="Magnetic local time", units="h",
        plain="Local time measured against the geomagnetic dipole pole.", role=COORD,
        formula=r"MLT \in [0, 24]\,\mathrm{h}",
        reference="Laundal, K. M., & Richmond, A. D. (2017), Space Sci. Rev., 206, 27-59",
        doi="10.1007/s11214-016-0275-y", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 2 Coordinate", algorithm="Magnetic local time derived from IGRF / Apex magnetic coordinates."
    ),
    "slt": dict(
        label="Local solar time", units="h",
        plain="Clock time set by the Sun's position at the sample's longitude.", role=COORD,
        formula=r"LT = (t_{UTC} + \lambda / 15^\circ) \bmod 24\,\mathrm{h}",
        reference="Laundal, K. M., & Richmond, A. D. (2017), Space Sci. Rev., 206, 27-59",
        doi="10.1007/s11214-016-0275-y", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Coordinate", algorithm="Mean solar time from UTC and geographic longitude (computed by this application)."
    ),
    "mlat": dict(
        label="Magnetic latitude", units="deg",
        plain="Latitude measured from the geomagnetic equator.", role=COORD,
        formula=r"\lambda_m \in [-90^\circ, +90^\circ]",
        reference="Laundal, K. M., & Richmond, A. D. (2017), Space Sci. Rev., 206, 27-59",
        doi="10.1007/s11214-016-0275-y", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 2 Coordinate", algorithm="Geomagnetic latitude computed using the International Geomagnetic Reference Field (IGRF)."
    ),

    # ---- scintillation -------------------------------------------------
    "s4_L1": dict(
        label="S4 index, L1", units="-",
        plain="How much the signal strength flickered (0 = steady, >0.3 = strong turbulence).", role=FIELD,
        formula=r"S_4 = \sqrt{\frac{\langle I^2 \rangle - \langle I \rangle^2}{\langle I \rangle^2}}",
        reference="Briggs, B. H., & Parkin, I. A. (1963), J. Atmos. Terr. Phys., 25(6), 339-365",
        doi="10.1016/0021-9169(63)90150-8",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        data_level="Level 2 (Scintillation Diagnostic)",
        algorithm="Normalized variance of received signal intensity I = (SNR)^2 over 1-second detrended intervals."
    ),
    "s4_L2": dict(
        label="S4 index, L2", units="-",
        plain="Signal flicker on the second radio frequency.", role=FIELD,
        formula=r"S_{4,L2} = \sqrt{\frac{\langle I_2^2 \rangle - \langle I_2 \rangle^2}{\langle I_2 \rangle^2}}",
        reference="Carrano, C. S., et al. (2011), Radio Science, 46, RS0D07",
        doi="10.1029/2011RS004707",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        data_level="Level 2 (Scintillation Diagnostic)",
        algorithm="Normalized variance of received intensity on the L2 frequency channel."
    ),
    "sigma_phi_L1": dict(
        label="Phase scintillation sigma-phi, L1", units="m",
        plain="How much the signal's phase jittered on L1.", role=FIELD,
        formula=r"\sigma_{\phi,L1} = \sqrt{\langle (\phi_1 - \bar{\phi}_1)^2 \rangle}",
        reference="Carrano, C. S., et al. (2011), Radio Science, 46, RS0D07",
        doi="10.1029/2011RS004707",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        data_level="Level 2 (Scintillation Diagnostic)",
        algorithm="Standard deviation of detrended high-rate carrier phase on L1."
    ),
    "sigma_phi_L2": dict(
        label="Phase scintillation sigma-phi, L2", units="m",
        plain="Phase jitter on the second frequency.", role=FIELD,
        formula=r"\sigma_{\phi,L2} = \sqrt{\langle (\phi_2 - \bar{\phi}_2)^2 \rangle}",
        reference="Carrano, C. S., et al. (2011), Radio Science, 46, RS0D07",
        doi="10.1029/2011RS004707",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        data_level="Level 2 (Scintillation Diagnostic)",
        algorithm="Standard deviation of detrended high-rate carrier phase on L2."
    ),
    "L1_SNR": dict(
        label="L1 signal-to-noise ratio", units="0.1 V/V",
        plain="Received signal amplitude on L1.", role=FIELD,
        formula=r"\mathrm{SNR}_1",
        reference="Schreiner et al. (2020), Atmos. Meas. Tech., 13, 6499-6519",
        doi="10.5194/amt-13-6499-2020",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        data_level="Level 1b Signal Diagnostic",
        algorithm="Carrier signal amplitude divided by noise floor estimate."
    ),
    "L2_SNR": dict(
        label="L2 signal-to-noise ratio", units="0.1 V/V",
        plain="Strength of the second frequency signal.", role=FIELD,
        formula=r"\mathrm{SNR}_2",
        reference="Schreiner et al. (2020), Atmos. Meas. Tech., 13, 6499-6519",
        doi="10.5194/amt-13-6499-2020",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/rapid/level2/scnLv2/",
        data_level="Level 1b Signal Diagnostic",
        algorithm="Carrier signal amplitude on L2 divided by noise floor estimate."
    ),
    "elevation": dict(
        label="Elevation angle", units="deg",
        plain="How high above the horizon the transmitter appeared.", role=COORD,
        formula=r"\theta_{el} \in [-90^\circ, +90^\circ]",
        reference="Kursinski et al. (1997), JGR, 102, 23429-23465",
        doi="10.1029/97RG02808", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 1b Geometry", algorithm="Transmitter elevation angle relative to receiver local horizon."
    ),
    "slip_L1": dict(
        label="Cycle slips, L1", units="count",
        plain="Times the receiver lost lock on the signal on L1.", role=AUX,
        formula=r"\Delta N_{slip,1}",
        reference="Hofmann-Wellenhof et al. (2008), GNSS Global Navigation Satellite Systems, Springer",
        doi="10.1007/978-3-211-73017-1", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 1b Tracking Flag", algorithm="Integer cycle slip counter identified by carrier phase discontinuity."
    ),
    "slip_L2": dict(
        label="Cycle slips, L2", units="count",
        plain="Lock losses on the second frequency.", role=AUX,
        formula=r"\Delta N_{slip,2}",
        reference="Hofmann-Wellenhof et al. (2008), GNSS Global Navigation Satellite Systems, Springer",
        doi="10.1007/978-3-211-73017-1", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 1b Tracking Flag", algorithm="Integer cycle slip counter identified on L2 carrier."
    ),
    "RFI": dict(
        label="Radio-frequency interference flag", units="-",
        plain="Marks samples contaminated by terrestrial or spaceborne interference.", role=AUX,
        formula=r"\mathrm{Flag}_{RFI} \in \{0, 1\}",
        reference="Schreiner et al. (2020), Atmos. Meas. Tech., 13, 6499-6519",
        doi="10.5194/amt-13-6499-2020", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Level 1b Quality Flag", algorithm="Binary threshold detector flagging anomalous SNR degradations."
    ),

    # ---- geolocation ---------------------------------------------------
    "Lat": dict(label="Latitude", units="deg N", plain="North-south position.", role=COORD,
                formula=r"\phi \in [-90^\circ, +90^\circ]", reference="WGS-84 Geodetic Reference System",
                doi="10.1029/97RG02808", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
                data_level="Level 2 Coordinate", algorithm="WGS-84 geodetic latitude of occultation tangent point."),
    "Lon": dict(label="Longitude", units="deg E", plain="East-west position.", role=COORD,
                formula=r"\lambda \in [-180^\circ, +180^\circ]", reference="WGS-84 Geodetic Reference System",
                doi="10.1029/97RG02808", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
                data_level="Level 2 Coordinate", algorithm="WGS-84 geodetic longitude of occultation tangent point."),
    "lat": dict(label="Latitude", units="deg N", plain="North-south position.", role=COORD,
                formula=r"\phi", reference="WGS-84", doi="10.1029/97RG02808",
                archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/", data_level="Level 2 Coordinate",
                algorithm="Latitude coordinate."),
    "lon": dict(label="Longitude", units="deg E", plain="East-west position.", role=COORD,
                formula=r"\lambda", reference="WGS-84", doi="10.1029/97RG02808",
                archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/", data_level="Level 2 Coordinate",
                algorithm="Longitude coordinate."),
    "GEO_lat": dict(label="Latitude", units="deg N", plain="North-south position.", role=COORD,
                    formula=r"\phi", reference="WGS-84", doi="10.1029/97RG02808",
                    archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/", data_level="Level 2 Coordinate",
                    algorithm="Geographic latitude."),
    "GEO_lon": dict(label="Longitude", units="deg E", plain="East-west position.", role=COORD,
                    formula=r"\lambda", reference="WGS-84", doi="10.1029/97RG02808",
                    archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/", data_level="Level 2 Coordinate",
                    algorithm="Geographic longitude."),
    "Azim": dict(label="Ray azimuth", units="deg", plain="Compass direction the ray travelled.", role=AUX,
                 formula=r"\psi_{ray} \in [0^\circ, 360^\circ]", reference="CDAAC Handbook",
                 doi="10.1029/97RG02808", archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
                 data_level="Level 2 Geometry", algorithm="Geodetic azimuth of radio ray tangent point direction."),
    "OCC_azi": dict(label="Occultation azimuth", units="deg", plain="Compass direction of the measurement.", role=AUX,
                    formula=r"\psi_{occ}", reference="CDAAC Handbook", doi="10.1029/97RG02808",
                    archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/", data_level="Level 2 Geometry",
                    algorithm="Azimuth angle from transmitter to receiver tangent point."),
    "time": dict(label="Time", units="s", plain="Seconds since the start of the record.", role=COORD,
                 formula=r"t - t_0", reference="CDAAC Handbook", doi="10.1029/97RG02808",
                 archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/", data_level="Level 2 Coordinate",
                 algorithm="Relative elapsed duration of occultation sounding."),
    "uts": dict(label="Time (UTC)", units="s since 1970-01-01", plain="Clock time of each sample.", role=COORD,
                formula=r"t_{UTC}", reference="IERS / BIPM Time Standards", doi="10.1029/97RG02808",
                archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/", data_level="Level 2 Coordinate",
                algorithm="Universal Coordinated Time Unix epoch seconds."),

    # ---- derived by this application -----------------------------------
    "theta": dict(
        label="Potential temperature", units="K",
        plain="Temperature an air parcel would have if brought adiabatically to 1000 hPa.", role=FIELD,
        formula=r"\theta = T \left(\frac{P_0}{P}\right)^\kappa, \quad \kappa = \frac{R_{dry}}{c_p} \approx 0.286",
        reference="Holton, J. R., & Hakim, G. J. (2012), An Introduction to Dynamic Meteorology, Academic Press",
        doi="10.1016/C2009-0-63394-8",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Poisson potential temperature evaluated with standard reference pressure P0 = 1000 hPa."
    ),
    "lapse_rate": dict(
        label="Lapse rate", units="K/km",
        plain="How fast temperature falls with height.", role=FIELD,
        formula=r"\Gamma = -\frac{dT}{dz}",
        reference="WMO International Meteorological Vocabulary (WMO-No. 182)",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Negative vertical derivative of temperature with respect to height."
    ),
    "dNdz": dict(
        label="Refractivity gradient", units="N-units/km",
        plain="How quickly the bending power changes with height. Values below -157 cause radio ducting.",
        role=FIELD,
        formula=r"\frac{dN}{dz}",
        reference="Bean, B. R., & Dutton, E. J. (1968), Radio Meteorology, Dover",
        doi="10.6028/NBS.MONO.92",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Vertical gradient of refractivity; values below -157 N-units/km indicate super-refraction and radio ducting."
    ),
    "N_anom_pct": dict(
        label="Refractivity anomaly", units="%",
        plain="Departure from the profile set's own mean.", role=FIELD,
        formula=r"\Delta N = 100 \times \frac{N(z) - \bar{N}(z)}{\bar{N}(z)}",
        reference="Rocken, C., et al. (1997), Geophys. Res. Lett., 24(22), 2885-2888",
        doi="10.1029/97GL03000",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Percentage deviation of individual refractivity from regional or temporal composite mean."
    ),
    "buoyancy_freq_sq": dict(
        label="Squared buoyancy frequency N^2", units="s^-2",
        plain="Atmospheric stiffness against vertical motion; controls gravity-wave propagation.", role=FIELD,
        formula=r"N_{BV}^2 = \frac{g}{T}\left(\frac{dT}{dz} + \frac{g}{c_p}\right) = \frac{g}{\theta}\frac{d\theta}{dz}",
        reference="Vaisala, V. (1925), Commentat. Phys.-Math., 2, 1-19; Brunt, D. (1927), QJRMS, 53, 30-32",
        doi="10.1002/qj.49705322103",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Square of the Brunt-Vaisala buoyancy frequency indicating static atmospheric stability."
    ),
    "density": dict(
        label="Atmospheric Density", units="kg/m^3",
        plain="Mass of the air per cubic metre, derived from dry temperature and pressure.", role=FIELD,
        formula=r"\rho = \frac{P}{R_{dry} T}",
        reference="US Standard Atmosphere (1976), NOAA-S/T 76-1562",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Dry atmospheric air density evaluated using the ideal gas law."
    ),
    "scale_height": dict(
        label="Scale Height", units="km",
        plain="Vertical distance over which atmospheric pressure drops by a factor of e.", role=FIELD,
        formula=r"H = \frac{R_{dry} T}{g}",
        reference="Salby, M. L. (1996), Fundamentals of Atmospheric Physics, Academic Press",
        doi="10.1016/S0074-6142(96)80005-7",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Atmospheric pressure e-folding scale height."
    ),
    "buoyancy_period": dict(
        label="Brunt-Vaisala Buoyancy Period", units="min",
        plain="Natural period of vertical buoyancy oscillations in a stably stratified atmosphere.", role=FIELD,
        formula=r"\tau_B = \frac{2\pi}{N_{BV}} = \frac{2\pi}{\sqrt{N_{BV}^2}} \cdot \frac{1}{60}",
        reference="Gill, A. E. (1982), Atmosphere-Ocean Dynamics, Academic Press",
        doi="10.1016/S0074-6142(08)60029-9",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Buoyancy oscillation period in minutes evaluated where N^2 > 0."
    ),
    "dtheta_dz": dict(
        label="Potential Temperature Gradient", units="K/km",
        plain="Vertical gradient of potential temperature; indicates static stability.", role=FIELD,
        formula=r"\frac{d\theta}{dz}",
        reference="Holton, J. R., & Hakim, G. J. (2012), An Introduction to Dynamic Meteorology",
        doi="10.1016/C2009-0-63394-8",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="First derivative of potential temperature with respect to geometric altitude."
    ),
    "speed_of_sound": dict(
        label="Acoustic Speed of Sound", units="m/s",
        plain="Speed at which acoustic pressure waves propagate through dry air.", role=FIELD,
        formula=r"c_s = \sqrt{\gamma R_{dry} T}, \quad \gamma \approx 1.40",
        reference="US Standard Atmosphere (1976), NOAA-S/T 76-1562",
        doi="10.1029/97RG02808",
        archive_url="https://data.cosmic.ucar.edu/gnss-ro/cosmic2/",
        data_level="Derived Geophysical Diagnostic",
        algorithm="Adiabatic speed of sound evaluated from temperature and specific heat ratio."
    ),
}

# Preferred x-axis for a quick look at each product.
DEFAULT_FIELD = {
    "atmPrf": "Temp",
    "wetPf2": "Temp",
    "ionPrf": "ELEC_dens",
    "scnLv2": "s4_L1",
    "ivmL2m": "ion_dens",
}
DEFAULT_VERTICAL = {
    "atmPrf": "MSL_alt",
    "wetPf2": "MSL_alt",
    "ionPrf": "MSL_alt",
    "scnLv2": "occheight",
    "ivmL2m": "alt",
}


def info(name: str) -> dict:
    """Vocabulary entry for ``name``, with a safe fallback."""
    d = VAR_INFO.get(name)
    if d:
        return dict(d, name=name)
    return dict(name=name, label=name, units="", plain="", role=FIELD,
                doi="", reference="", archive_url="", formula="", data_level="", algorithm="")


# Normalise verbose or non-standard unit strings that CDAAC files sometimes
# carry, so that axis labels are always human-readable.
_UNIT_MAP: dict[str, str] = {
    "Celsius_degree": "°C",
    "celsius_degree": "°C",
    "celsius": "°C",
    "degree_Celsius": "°C",
    "degreesC": "°C",
    "degC": "°C",
    "kelvin": "K",
    "Kelvin": "K",
    "degrees_north": "°N",
    "degrees_east": "°E",
    "degrees": "°",
    "radian": "rad",
    "radians": "rad",
    "hpa": "hPa",
    "Pa": "Pa",
    "kilogram/kilogram": "kg/kg",
    "meters": "m",
    "meter": "m",
    "kilometers": "km",
    "kilometre": "km",
    "km/s": "km/s",
    "m/s": "m/s",
    "1/cm3": "el/cm³",
    "el/cm3": "el/cm³",
    "electrons/cm3": "el/cm³",
    "TECU": "TECU",
}


def normalise_units(raw: str) -> str:
    """Return a clean display string for a raw unit attribute value."""
    if not raw:
        return raw
    return _UNIT_MAP.get(raw, raw)


def axis_title(name: str, units: str | None = None) -> str:
    d = info(name)
    u = normalise_units(units if units is not None else d["units"])
    return f"{d['label']} [{u}]" if u and u != "-" else d["label"]
