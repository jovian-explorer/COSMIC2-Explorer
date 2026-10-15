# Model audit: what the app computes rather than reads

Every place where COSMIC-2 Explorer computes a time, position, height or
physical quantity instead of taking it from a CDAAC file, ranked by how much
a wrong result could mislead. Each item gives where it is, what it does, its
basis, what is wrong (if anything), how it was or can be checked against real
files, and the smallest fix. Line numbers refer to the commit that adds this
file. Citations were checked against the registries with Argus.

Real data used for the checks: COSMIC-2 `nrt` of 2021-10-27 and 2026-05-31,
`provisional` ionPrf of 2026-09-18 (690 profiles), Metop-A (2021), Metop-C and
TanDEM-X (2026-05-31) and COSMIC-1 (2019-12-10) from CDAAC.

## Medium

### M1. ivmL2m records get an invented position and local time
* **Where**: `src/cosmic2/readers.py:678-691` (`_read_ivml2m`).
* **What**: a record's `lat`/`lon` is the median of the file's samples and its
  local time that of the first sample.
* **Problem**: an ivmL2m file holds a whole day of the orbit (23.99 h,
  latitudes -24 to +24, longitudes -180 to +180 in the bundled file). The
  median (-0.8, -3.6) is a place the satellite crossed briefly, not where
  the data were taken. The Explore map draws the day there, a latitude or
  longitude filter keeps or drops the whole day on that point, and the
  local-time filter uses one sample's time.
* **Check**: the bundled `ivmL2m_C2E1.2026.200.01` spans 24 h and every
  longitude.
* **Fix**: no point position and no local time for a day-long ivmL2m record.
  The latitude range stays in `extras`, and the per-sample `lat`, `lon` and
  local time (`slt`) are still plotted from the file.
* **Status**: fixed in 35d23d5. The diagnostic map now draws ivmL2m from its
  samples, one a minute, where they were taken (1418 samples in 108 cells
  for the bundled day, instead of one point).

### M2. ionPrf placed at CDAAC's `edmax` even when that is a spike near the orbit
* **Where**: `src/cosmic2/readers.py:547-565` (`_read_ionprf`).
* **What**: the record is placed at `edmaxlat/edmaxlon`. It is moved to the
  F2 peak only when `edmaxalt` is below 150 km.
* **Problem**: CDAAC's maximum can also be an inversion spike near the top. In
  COSMIC-1 `ionPrf_C006.2019.344.08.04.G20` it sits at 778 km, while the F2
  peak found by `analysis.ionosphere_peak` (with spike rejection, commit
  35a577c) is at 222 km. Since the tangent point moves with height, the
  record is put far from where its F2 layer was measured.
* **Check**: on 713 ionPrf (690 COSMIC-2, 23 COSMIC-1), CDAAC's `edmaxalt` and
  the app's hmF2 agree within 10 km for 706. The 5 COSMIC-2 exceptions are
  the E-region case already handled; the COSMIC-1 one is the spike.
* **Fix**: place the record at the app's F2 peak whenever it is more than
  50 km from `edmaxalt`, in either direction.
* **Status**: fixed. Of the 713 real profiles, 6 move: the 5 E-region cases
  as before (424-1598 km) and the COSMIC-1 spike (413 km).

### M3. One position per neutral profile, though the tangent point drifts
* **Where**: `src/cosmic2/readers.py:461, 511, 734` (CDAAC's `lat`/`lon`
  attributes); used by `missions.collocate` (`missions.py:67`), the radiosonde
  pairing, latitude bands, maps and sections.
* **What**: each atmPrf, wetPf2 or echPrf is one point: CDAAC's reference
  tangent point.
* **Basis**: standard RO practice (Kursinski et al. 1997,
  doi:10.1029/97JD01569; Anthes et al. 2008, doi:10.1175/BAMS-89-3-313).
* **Problem**: not wrong, but undocumented. On 300 good atmPrf of the audit
  data, the tangent point moves a median 113 km (90th percentile 244 km)
  between the lowest level and 30 km. CDAAC's point is the level at a median
  3.4 km (10-90 %: 2.7-5.3 km; 12.5 km for some COSMIC-2 files). A 300 km
  collocation window therefore pairs profiles whose upper levels can be
  further apart than the window says.
* **Fix**: say so in Help, next to the collocation windows. The per-level
  `Lat`/`Lon` stay available.
* **Status**: documented in Help (section N) and the README notes. The
  collocated mission comparison now also leaves out each level where the
  two profiles' own tangent points (per-level `Lat`/`Lon`) are further apart
  than the limit: of 19 COSMIC-2 / Metop pairs of October 2021 within 300 km
  at the reference point, 5 % were further apart at 5 km and 26 % at 20 and
  30 km.

## Low

### L1. GPS-UTC leap seconds
* **Where**: `readers.py:235-258`.
* **What**: CDAAC's date and time attributes are GPS time; the app subtracts
  14-18 s by date, and 13 s before 2006.
* **Check**: the calendar attributes equal the GPS-seconds `start_time` to
  the second for every atmPrf of COSMIC-2 (400), COSMIC-1 (66), Metop-A
  (1100), Metop-C (200) and TanDEM-X (168) in the audit data. 13 s is
  correct from 1999 to 2005 (IERS Bulletin C). No mission the app downloads
  is older.
* **Fix**: none needed.

### L2. Local time is mean solar time
* **Where**: `readers.py:262` (`_local_time`).
* **What**: UTC + longitude/15.
* **Problem**: this is mean, not apparent, solar time; the equation of time
  is up to about 16 min. The Help and vocabulary already say "mean local
  solar time".
* **Fix**: none; the label is correct.

### L3. Derived fields use dry air and constant gravity
* **Where**: `analysis.py:173` (N^2), `604` (speed of sound, gamma = 1.4 and
  R_dry), `606` (scale height R_dry T / g0).
* **Problem**: on wetPf2 the moist temperature is used with dry-air
  constants. Virtual-temperature effects are at most a few tenths of a
  percent near the tropical surface, and gravity falls by 0.3 % per 10 km.
  The vocabulary already states g0 for the scale height.
* **Fix**: none; documented approximations.

### L4. Radiosonde comparison falls back to latitude 0
* **Where**: `radiosonde.py:376` (`_ro_profile`, `lat or 0.0`).
* **What**: atmPrf heights are turned into geopotential with normal gravity
  at the profile's latitude (Mahoney 2001), and at the equator when the
  latitude is missing.
* **Problem**: an invented default. The effect is at most 0.5 % of the
  height (equator against pole), but there is no reason to guess.
* **Fix**: skip a profile without a latitude.
* **Status**: fixed.

### L5. scnLv2 tangent point on a straight ray
* **Where**: `readers.py:331` (`scn_tangent_point`).
* **What**: the closest approach of the straight line from satellite to
  transmitter, turned Earth-fixed with the file's `gast1` and the Earth's
  rotation rate.
* **Check**: its height matches the file's `occheight` within 1 m, and the
  rotated satellite positions match the file's own `lat`/`lon` within
  0.0002 and 0.006 degrees on 602 files. Ionospheric bending at 100-400 km
  is far too small to move the point.
* **Fix**: none.

### L6. Constants and formulas checked against their sources
* `sat_vapour_pressure_hpa` (`radiosonde.py:304`): Bolton 1980,
  doi:10.1175/1520-0493(1980)108<1046:TCOEPT>2.0.CO;2. Correct.
* Sonde refractivity 77.6 p/T + 3.73e5 e/T^2 (`radiosonde.py:332`): Smith
  and Weintraub 1953, doi:10.1109/JRPROC.1953.274297, as CDAAC uses it.
  Correct.
* Geopotential (`radiosonde.py:340`): Mahoney (2001) with WGS-84 normal
  gravity; within 2 m of wetPf2's own `gph` on the real sample.
* `model_impact_height` (`nwp.py:50`): matches atmPrf's own `Impact_height`
  (median difference 0.0000 km on 300 profiles).
* `PLASMA_FREQ_COEFF` (`analysis.py:29`): from CODATA 2018 constants, with a
  test.
* `TEC_BOTTOM_KM` = 80 (`analysis.py:545`): chosen so the integral matches
  CDAAC's `tec0` (within 0.5 % on 689 of 690 profiles).
* `DRY_TROPOPAUSE_T_MAX_K` = 235 (`analysis.py:254`): empirical guard for
  atmPrf dry temperature. Its basis, the false lapse-rate tropopause near
  6 km in the tropics, is in the README science notes.
* Collocation weights (`missions.py:67`): Rieckh et al. 2021,
  doi:10.1175/JTECH-D-20-0209.1.
* `EARTH_RADIUS_KM` = 6371 for great-circle distances
  (`radiosonde.py:59`): spherical distances are within 0.5 % of ellipsoidal
  ones, far inside the 300 km windows.
* Composite and band uncertainties (`analysis.py:1072`) treat profiles as
  independent; every caption says so.
