# Changelog

## Unreleased

### Science fixes (results change)

- **Vertical TEC below hmF2** now integrates the whole profile from its lowest level up to the F2 peak. It previously started at 150 km, dropping the E and lower F region (bundled ionPrf sample: 14.3 to 16.4 TECU).
- **TEC ignores negative electron densities**: ionPrf profiles often carry a negative bottomside (an Abel-inversion artefact, typically -4e4 el/cm3 below 100 km), which was integrated as it stood and removed TEC: on one real 2026-09-30 profile the column came out 0.4 TECU instead of 11.5. Negative densities now count as zero, as in CDAAC's own integral. A new whole-profile `vtec_profile_TECU` sits beside `vtec_below_peak_TECU` and is cross-checked against the archive in the Profiles diagnostics (median agreement 0.2 % over 119 profiles); both TEC values are shown in the diagnostics panel.
- The archive's ionPrf `tec0` was labelled "TEC below edmax". CDAAC defines it as the TEC integrated between the bottom and top of the profile, and `tec1` as the extrapolated TEC above the top; they are now `tec_profile_TECU` and `tec_above_top_TECU`.
- **E layer**: an electron-density maximum on the edge of the 90-150 km window is no longer reported as an E layer (the bundled sample showed a spurious "hmE" of 149.4 km, which is the F-region bottomside). An F2 maximum on the first or last level of a profile is flagged `peak_at_profile_edge` and not reported as found. hmF2/NmF2 refinement uses the exact parabola vertex for uneven level spacing.
- **Integrated water vapour**: when specific humidity had missing levels, the remaining humidities were paired with the first N pressures instead of the pressures at the same heights. Fixed; the lowest integrated level is reported as `column_water_vapour_bottom_km`.
- **Density** counts water vapour (wetPf2 `Vp`) with its own gas constant: rho = (p - e)/(R_d T) + e/(R_v T).
- **atmPrf `Temp` and `Pres` are dry quantities** (dry temperature and dry pressure, as the files' own `long_name` says). They are now labelled so everywhere, and a composite over a selection containing both atmPrf and wetPf2 no longer averages dry and moist temperature together: each group is split by quantity. netCDF exports record each profile's product and say which rows hold which quantity.
- **WMO tropopause on atmPrf dry temperature**: in moist tropical air the dry temperature's lapse rate falls below 2 K/km near 6 km (450-500 hPa), so 220 of 570 real COSMIC-2 profiles (2026-06-20 and 2026-09-30) were given a tropopause there, up to 12 km below CDAAC's own `trhwmo`. On dry temperature the search now skips levels warmer than 235 K; 568 of 570 then agree with `trhwmo` within 0.3 km (CDAAC's tropopause temperatures never exceeded 233.7 K). wetPf2's moist temperature is searched without the guard, and the `method` field says when it applied.
- **WMO tropopause** accepts lapse rates of exactly 2 K/km ("2 K/km or less") and requires the full 2 km test layer below the search ceiling.
- **Interpolation in log space** for pressure, density, vapour pressure, specific humidity and electron density when profiles are put on a common grid (composites, grid CSV, netCDF). Linear interpolation overestimates these between levels (about 1 % across a 2 km gap in pressure).
- **Profile error bars** ("Rolling Std Dev", "Standard Error") now measure the scatter of the values about their running mean. They were the raw rolling standard deviation, which on a smooth profile measures the vertical gradient: a noise-free straight line got error bars equal to its slope.
- **Composites** grouped by date work (every profile used to land in "unknown"); a group with one profile has undefined (NaN) spread instead of zero.
- **Local times**: ivmL2m `local_time` is local solar time of the first sample (it was the median *magnetic* local time); a per-sample solar local time `slt` is available as a derived field. scnLv2 records without an S4 maximum fall back to the ray start position and its local time.
- **Fill values**: each variable's own `_FillValue`/`missing_value` is masked and `scale_factor`/`add_offset` applied for both netCDF backends; the float32 netCDF default fill (9.96921e36) is now caught. Character variables no longer stop a granule from loading.
- Granule longitudes are normalised to [-180, 180) so the longitude-box search finds products that use 0-360.

### Interface

- On the Profiles tab, selecting profiles of one product that cannot show the chosen quantity or height (Temp for ionPrf, MSL_alt for scnLv2) switches to that product's natural pair (ELEC_dens on MSL_alt, S4 on tangent height, ion density on altitude) instead of drawing an empty plot.
- The Compare tab has a **Height** choice. Scintillation (scnLv2 S4, sigma-phi) can now be averaged against tangent-point height (`occheight`), for example S4 by day and night; choosing an S4 quantity switches the height to `occheight` automatically. When no selected profile carries the quantity on that height, the plot says so instead of "No group had enough profiles".

### Exports and figures

- CSV cells and composite JSON are written at full double precision (they were rounded to 6 decimal places, leaving small fields such as N^2 with one or two significant digits).
- netCDF exports use UDUNITS unit strings (`degree_Celsius`, `kg m-3`, `s-2`, ...). `C` is the coulomb to UDUNITS, so tools that decode units read temperature as a charge.
- The `Software License` line in CSV headers is plain text (name, copyright, URL); it was a Python dictionary dump.
- Export provenance now states that the Profiles-tab outlier/smoothing/uncertainty settings were not applied to the exported values.
- The exported "Group averages" figure reproduces the Compare tab's average: its quantity, height, top and step. It used the Export tab's quantity, the Profiles tab's height and a fixed 0-60 km grid, so an ionospheric composite came out empty.
- Exported figures keep their captions (they were cut off), embed TrueType fonts in PDF/EPS instead of Type 3, follow the Plot Theme setting, draw profiles from every level rather than the 900-point screen subsample, and keep a linear axis when the log switch meets data with no positive values. Concurrent figure exports no longer mix their DPI or styling.

### Performance

- New **CPU workers** setting (Settings > Performance) and `--workers N` option for `cosmic2-explorer` and `cosmic2-explorer-server`: composites, profile plots, the diagnostics table, regridded CSV/netCDF exports, importing files and "Rebuild index" read granules on up to N processes when a job has 24 or more granules. 0 = automatic (CPUs - 1), 1 = serial. Results are identical to a serial run. A 400-profile atmPrf composite on 8 CPUs: 21 s serial, 2.6 s with a cold pool, 1.2 s warm.
- Composites and profile plots of a quantity stored in the file (Temp, Pres, ELEC_dens, ...) no longer compute every derived field for each granule: about 25 % less work per profile.
- **Draw** on the Profiles tab reads and filters the selected granules on the CPU workers when 24 or more are selected: 200 atmPrf profiles take about 0.8 s instead of 2.1 s (8 CPUs, pool already running; this includes faster conversion of the arrays to JSON, which also speeds up every other response carrying profile data).
- netCDF-3 granules (all CDAAC products) are read with scipy first: a day-long ivmL2m file loads in about 0.2 s instead of 1.3 s; atmPrf/wetPf2 loads are several times faster.
- The day manifest lists collections and fetches file sizes concurrently.

### Downloads, index and settings

- Granules received before a cancelled or failed download are indexed (the dataset is marked incomplete); they used to stay on disk, unindexed.
- A missing archive directory (for example today's, before CDAAC publishes) is re-checked after 5 minutes instead of being cached for 6 hours.
- The Explore tab's default date range now includes granules observed in the last seconds of the previous UTC day. Every CDAAC day file starts with a few of these (5 of 460 atmPrf on 2026-06-20), and every ivmL2m day file starts at about 23:59:50, so with a single day downloaded its ivmL2m files never appeared in a search.
- "Rebuild index" keeps each granule's archive day (from its cache folder). It used the observation date instead, which moved the granules observed just before midnight to the previous day: deleting that day's dataset then left them on disk and in the index, and grouping by date split them off.
- Re-indexing refreshes the quality code, satellite, PRN and stamp of existing entries.
- "Spread over 24 h" sampling no longer drops ivmL2m files: the `01` in their names is a file sequence, not an hour, so every satellite's whole-day file counted against the same hour (with 24 profiles requested, only one satellite of five was kept). Whole-day products are exempt from the hourly quota.
- A change to "concurrent downloads" takes effect for the next download instead of after a restart.
- The Settings drawer's Save button works again (the DPI field's min/step made the browser refuse to submit the form). The default stream, "require good QC", temperature units and export grid settings are now saved and applied.
- The Profiles tab's diagnostics panel warns when an ionPrf profile has no F2 peak (its largest density is on the top or bottom level, as on profiles cut off below the peak) instead of presenting that maximum as NmF2/hmF2.
- The diagnostics panel follows the selection when the chosen quantity is missing from it (it went on showing a profile from the previous selection, for example an ionPrf profile after selecting scnLv2 records).
- The Profiles tab's diagnostics panel no longer ends in a script error.

### Robustness and security

- The local API accepts cross-origin requests only from loopback origins; previously any web page open in the browser could call it (including the delete endpoints).
- Grid, DPI and settings values are validated (a zero grid step returned a server error, and could be saved as a setting).
- The coverage summary (the Explore overview and the "Sampling summary" figure) no longer needs SQLite's optional `FLOOR` function, which is absent from SQLite builds without math functions (for example the system SQLite 3.34 of RHEL/Rocky 9).
- The test suite removes its temporary data folder when it finishes.
