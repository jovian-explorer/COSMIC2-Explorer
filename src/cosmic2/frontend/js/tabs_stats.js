// "Statistics" tab: sampling, quality flags and penetration depth of the
// current selection, read from the local index.

import {api, state, selectedIds} from './api.js';
import {$, el, clear, fmt, withBusy, layoutBase, PLOT_CONFIG, PALETTE,
        emptyPlot, fillSelect, cleanPlotlyMath} from './ui.js';
import {FIELD_CHOICES, VERTICAL_CHOICES, PRODUCT_AXES, labelled} from './tabs_science.js';

export function initStatsTab() {
  $('#btn-stats').addEventListener('click', (e) =>
      withBusy(e.target, 'Counting...', drawStats));
  fillSelect($('#x-field'), labelled(FIELD_CHOICES), 'Temp');
  fillSelect($('#x-vertical'), labelled(VERTICAL_CHOICES), 'MSL_alt');
  // Electron density lives hundreds of km up: move the grid with it.
  $('#x-field').addEventListener('change', () => {
    const iono = ['ELEC_dens'].includes($('#x-field').value);
    $('#x-bottom').value = iono ? 100 : 0;
    $('#x-top').value = iono ? 550 : 40;
    $('#x-step').value = iono ? 5 : 0.5;
  });
  $('#btn-section').addEventListener('click', (e) =>
      withBusy(e.target, 'Averaging...', drawSection));
  initMapCard();
  $('#btn-pairs').addEventListener('click', (e) =>
      withBusy(e.target, 'Comparing...', drawPairs));
  $('#btn-radiosonde').addEventListener('click', (e) =>
      withBusy(e.target, 'Comparing...', drawRadiosonde));
}

/** The selection when asked for, otherwise the Explore tab's search. */
export function statsSelection(selectedOnly) {
  const ids = selectedIds();
  if (selectedOnly && ids.length) return {granule_ids: ids};
  const search = Object.assign({}, state.lastSearch || {});
  delete search.limit;
  delete search.offset;
  // The point of the quality table is to count what CDAAC flagged, so the
  // Explore tab's "good quality only" filter is not applied here.
  search.good_only = false;
  return {search};
}

function pct(v) { return v === null || v === undefined ? '-' : `${fmt(100 * v, 1)} %`; }

/** Plotly layout with titled axes, in the app's theme. */
export function axesLayout(xTitle, yTitle, extra = {}) {
  const base = layoutBase();
  return layoutBase(Object.assign({
    xaxis: Object.assign(base.xaxis, {title: {text: xTitle}}),
    yaxis: Object.assign(base.yaxis, {title: {text: yTitle}}),
    legend: {orientation: 'h', y: 1.12},
    margin: {l: 64, r: 24, t: 30, b: 54},
  }, extra));
}

/** The "below 1 km above the ground" cell.  Only atmPrf has it: a wetPf2
 *  profile's lowest level is not the depth the occultation reached (on the
 *  2026 sample it sits up to 1.7 km above its atmPrf's, 95th percentile). */
function groundCell(product, pen) {
  if (pen && pen.above_ground && pen.above_ground.n) {
    return el('td', {class: 'num'},
              `${pct(pen.above_ground.fraction_below['1'])} (n=${pen.above_ground.n})`);
  }
  if (product === 'atmPrf' && pen) {
    return el('td', {class: 'num', title: 'Needs the wetPf2 files of the same occultations on disk (they carry the terrain height).'},
              'needs wetPf2');
  }
  if (product === 'wetPf2') {
    return el('td', {class: 'num', title: "A wetPf2 profile's lowest level is not the depth the occultation reached; see the atmPrf row."},
              'atmPrf only');
  }
  return el('td', {class: 'num'}, '-');
}

async function drawStats() {
  const res = await api.statsSampling(statsSelection($('#st-selected-only').checked));
  const products = Object.keys(res.products);
  const tb = $('#st-table').tBodies[0];
  clear(tb);
  for (const name of products) {
    const p = res.products[name];
    const pen = p.penetration;
    const codes = Object.entries(p.bad_codes).map(([k, v]) => `${k}: ${v}`).join(', ');
    tb.append(el('tr', {},
      el('td', {}, name),
      el('td', {class: 'num'}, String(p.n)),
      el('td', {class: 'num'}, `${p.n_bad} (${pct(p.bad_fraction)})`),
      el('td', {}, codes || '-'),
      el('td', {class: 'num'}, fmt(p.levels_median, 0)),
      el('td', {}, p.lat_range ? `${fmt(p.lat_range[0], 1)} to ${fmt(p.lat_range[1], 1)}` : '-'),
      el('td', {class: 'num'}, pen ? `${fmt(pen.median_km, 2)} km` : '-'),
      el('td', {class: 'num'}, pen ? pct(pen.fraction_below['1']) : '-'),
      groundCell(name, pen)));
  }
  const atm = res.products.atmPrf && res.products.atmPrf.penetration;
  const notes = [`${res.n} profiles.`];
  if (atm && atm.archive_check && atm.archive_check.n) {
    notes.push(`atmPrf lowest levels agree with CDAAC's profile_bottom_km to ` +
               `${fmt(atm.archive_check.max_abs_diff_km * 1000, 3)} m (n=${atm.archive_check.n}).`);
  }
  notes.push('Flagged profiles are counted here even when the Explore search ' +
             'shows good ones only; penetration uses good profiles.');
  notes.push('"Ground" uses the terrain height in the matching wetPf2 file, so it ' +
             'needs both products of the same day on disk.');
  $('#st-caption').textContent = notes.join(' ');

  const centres = (edges) => edges.slice(0, -1).map((v, i) => (v + edges[i + 1]) / 2);
  const latC = centres(res.lat_edges);
  Plotly.react('st-lat-plot', products.map((name, i) => ({
    type: 'bar', name, x: latC, y: res.products[name].lat_counts,
    marker: {color: PALETTE[i % PALETTE.length]},
  })), axesLayout('Latitude [°N]', 'Profiles', {barmode: 'group'}), PLOT_CONFIG);

  const hourC = centres(res.hour_edges);
  Plotly.react('st-lt-plot', products.map((name, i) => ({
    type: 'scatter', mode: 'lines+markers', name, x: hourC,
    y: res.products[name].local_time_counts, line: {shape: 'hvh'},
    marker: {color: PALETTE[i % PALETTE.length]},
  })), axesLayout('Local solar time [h]', 'Profiles',
                  {xaxis: Object.assign(layoutBase().xaxis,
                    {title: {text: 'Local solar time [h]'}, range: [0, 24], dtick: 3})}),
  PLOT_CONFIG);

  const neutral = products.filter((n) => res.products[n].penetration);
  if (!neutral.length) {
    emptyPlot('st-pen-plot', 'No neutral-atmosphere profiles (atmPrf, wetPf2) in the selection.');
    emptyPlot('st-penlat-plot', 'No neutral-atmosphere profiles in the selection.');
    return;
  }
  const penC = centres(res.penetration_edges_km);
  const traces = [];
  neutral.forEach((name, i) => {
    const pen = res.products[name].penetration;
    const colour = PALETTE[products.indexOf(name) % PALETTE.length];
    traces.push({type: 'bar', name: `${name} profiles`, x: penC, y: pen.counts,
                 marker: {color: colour}, opacity: 0.6});
    // Cumulative fraction reaching below each bin's top edge.
    let run = 0;
    const cum = pen.counts.map((c) => (run += c) / Math.max(pen.n, 1));
    traces.push({type: 'scatter', mode: 'lines', name: `${name} fraction below`,
                 x: res.penetration_edges_km.slice(1), y: cum, yaxis: 'y2',
                 line: {color: colour, width: 2.5}});
  });
  Plotly.react('st-pen-plot', traces, axesLayout(
      'Lowest retrieved level [km above sea level]', 'Profiles', {
        barmode: 'overlay',
        yaxis2: {overlaying: 'y', side: 'right', range: [0, 1], dtick: 0.2,
                 tickformat: '.0%', title: {text: 'Fraction below'},
                 showgrid: false, automargin: true},
        margin: {l: 64, r: 64, t: 30, b: 54},
      }), PLOT_CONFIG);
  Plotly.react('st-penlat-plot', neutral.map((name) => {
    const pen = res.products[name].penetration;
    return {type: 'scatter', mode: 'lines+markers', name, x: latC, y: pen.lat_median_km,
            text: pen.lat_n.map((n) => `n=${n}`),
            hovertemplate: '%{x}°: %{y:.2f} km (%{text})<extra></extra>',
            marker: {color: PALETTE[products.indexOf(name) % PALETTE.length]}};
  }), axesLayout('Latitude [°N]', 'Median lowest level [km]'), PLOT_CONFIG);
}

// ------------------------------------------------------------ cross section

async function drawSection() {
  const field = $('#x-field').value;
  const req = Object.assign({
    field,
    vertical: $('#x-vertical').value,
    lat_step: Number($('#x-lat').value) || 5,
    min_count: Number($('#x-min').value) || 3,
    bottom_km: Number($('#x-bottom').value) || 0,
    top_km: Number($('#x-top').value) || 40,
    step_km: Number($('#x-step').value) || 0.5,
    convert_kelvin: field === 'Temp' || field === 'temp_dry',
    good_only: true,
    screen_k: $('#x-screen').checked ? (Number($('#x-screen-k').value) || 5) : null,
  }, statsSelection($('#x-selected-only').checked));
  let product = null;
  if (req.search) {
    req.search.good_only = true;
    req.search.limit = req.max_profiles = 5000;
    // The quantity decides the product: one that carries it, preferring the
    // Explore tab's product, and wetPf2 (real temperature) over atmPrf (dry
    // temperature) otherwise. Two products holding Temp as different
    // quantities are never averaged together.
    const carriers = ['wetPf2', 'atmPrf', 'ionPrf', 'scnLv2', 'ivmL2m']
        .filter((p) => PRODUCT_AXES[p][0].includes(field));
    const wanted = (req.search.products || []).filter((p) => carriers.includes(p));
    product = wanted[0] || carriers[0] || null;
    if (product) req.search.products = [product];
  }
  const res = await api.section(req);
  if (!res.n_profiles) {
    emptyPlot('section-plot', `None of the ${res.selected} selected profiles carry ` +
              `${field} on ${req.vertical} in ${req.bottom_km}-${req.top_km} km.`);
    $('#section-caption').textContent = '';
    return;
  }
  const show = $('#x-show').value;
  const z = res[show];
  // Plotly heatmaps take z[y][x]: heights down the rows, latitude across.
  const zT = res.grid.map((_, j) => res.lat_centres.map((__, i) => z[i][j]));
  const diverging = show === 'departure_pct';
  let lim = 0;
  if (diverging) {
    for (const row of zT) for (const v of row) if (v !== null) lim = Math.max(lim, Math.abs(v));
  }
  const zTitle = show === 'mean' ? res.field_label
               : show === 'std' ? `Std. dev. of ${res.field_label}`
               : show === 'sem' ? `Std. error of ${res.field_label}`
               : show === 'count' ? 'Profiles' : 'Departure [%]';
  Plotly.react('section-plot', [{
    type: 'heatmap', x: res.lat_centres, y: res.grid, z: zT,
    colorscale: diverging ? 'RdBu' : 'Viridis', reversescale: false,  // RdBu: positive red
    zmid: diverging ? 0 : undefined,
    zmin: diverging ? -lim : undefined, zmax: diverging ? lim : undefined,
    colorbar: {title: {text: cleanPlotlyMath(zTitle), side: 'right'}, thickness: 12},
    hovertemplate: '%{x}°, %{y} km: %{z:.4g}<extra></extra>',
  }], axesLayout('Latitude [°N] (band centre)', cleanPlotlyMath(res.vertical_label)),
  PLOT_CONFIG);
  const kind = {mean: 'Mean', departure_pct: 'Departure from the all-profile mean of',
                std: 'Spread of', sem: 'Standard error of the mean of',
                count: 'Profiles behind'}[show];
  $('#section-title').textContent = `${kind} ${res.field_label.replace(/\s*\[[^\]]*\]$/, '')}`;
  $('#section-caption').textContent =
    (res.screen_k ? `Outlier screen (k = ${res.screen_k}): ${res.screened_out} profile(s) left out. ` : '') +
    `${res.n_profiles} ${product ? product + ' ' : ''}profiles in ${res.lat_centres.length} bands of ${req.lat_step}° ` +
    `(${res.profiles_per_band.join(', ')} profiles from south to north), on a ` +
    `${req.step_km} km grid; cells with fewer than ${res.min_count} profiles are blank.` +
    (diverging ? ' Departure = 100 (band mean - mean of all profiles) / mean of all ' +
                 'profiles, at each height.' : '') +
    (show === 'sem' ? ' Standard error = standard deviation / sqrt(profiles in the cell); it ' +
                      'treats the profiles as independent and leaves out sampling error.' : '');
}

// ------------------------------------------------------------ diagnostic map

const EP = 'gravity_waves.ep_J_per_kg';
let coast = null;   // bundled coastlines, fetched once

function initMapCard() {
  const cols = Object.keys(state.meta.diag_columns || {})
      .filter((c) => c.includes('.') || c.startsWith('column_'));
  fillSelect($('#m-col'), cols.map((c) => ({value: c, label: state.meta.diag_columns[c]})),
             cols.includes(EP) ? EP : cols[0]);
  const sync = () => { $('#m-gw').disabled = $('#m-col').value !== EP; };
  $('#m-col').addEventListener('change', sync);
  sync();
  $('#btn-map').addEventListener('click', (e) =>
      withBusy(e.target, 'Computing...', drawMap));
}

async function drawMap() {
  const column = $('#m-col').value;
  const req = Object.assign({
    column,
    lat_step: Number($('#m-lat').value) || 10,
    lon_step: Number($('#m-lon').value) || 20,
    min_count: Number($('#m-min').value) || 1,
    gw_z_lo: Number($('#m-zlo').value) || 20,
    gw_z_hi: Number($('#m-zhi').value) || 40,
    gw_method: $('#m-method').value,
    gw_cutoff_km: Number($('#m-cut').value) || 10,
  }, statsSelection($('#m-selected-only').checked));
  if (req.search) {
    req.search.good_only = true;
    req.search.limit = req.max_profiles = 5000;
    // Each diagnostic belongs to one family of products.
    const family = column.startsWith('ionosphere.') ? ['ionPrf']
                 : column.startsWith('scintillation.') ? ['scnLv2']
                 : column.startsWith('insitu.') ? ['ivmL2m'] : ['atmPrf', 'wetPf2'];
    const wanted = (req.search.products || []).filter((p) => family.includes(p));
    req.search.products = wanted.length ? wanted : [family[0]];
  }
  const [res, cl] = await Promise.all([api.diagMap(req), coast || api.coastlines()]);
  coast = cl;
  if (!res.n) {
    emptyPlot('mapgrid-plot', `No selected profile has ${res.title}.`);
    emptyPlot('zonal-plot', 'Nothing to average.');
    $('#mapgrid-caption').textContent = '';
    return;
  }
  const base = layoutBase();
  Plotly.react('mapgrid-plot', [
    {type: 'heatmap', x: res.lon_centres, y: res.lat_centres, z: res.mean,
     colorscale: 'Viridis', hoverongaps: false, customdata: res.count,
     hovertemplate: '%{y}°N %{x}°E: %{z:.3g} (n=%{customdata})<extra></extra>',
     colorbar: {title: {text: cleanPlotlyMath(res.title), side: 'right'}, thickness: 12}},
    {type: 'scatter', mode: 'lines', x: coast.lon, y: coast.lat, hoverinfo: 'skip',
     line: {color: 'rgba(100,116,139,0.9)', width: 0.8}, showlegend: false},
  ], axesLayout('Longitude [°E]', 'Latitude [°N]', {
    xaxis: Object.assign(base.xaxis, {title: {text: 'Longitude [°E]'},
                                      range: [-180, 180], dtick: 60}),
    yaxis: Object.assign(base.yaxis, {title: {text: 'Latitude [°N]'},
                                      range: [-60, 60], dtick: 15}),
  }), PLOT_CONFIG);
  const z = res.zonal;
  Plotly.react('zonal-plot', [
    {type: 'scatter', mode: 'lines+markers', name: 'mean ± 1 std', x: res.lat_centres,
     y: z.mean, error_y: {type: 'data', array: z.std.map((v) => (v === null ? 0 : v)),
                          visible: true},
     text: z.n.map((n) => `n=${n}`), marker: {color: PALETTE[0]},
     hovertemplate: '%{x}°: %{y:.3g} (%{text})<extra></extra>'},
    {type: 'scatter', mode: 'lines+markers', name: 'median', x: res.lat_centres,
     y: z.median, marker: {color: PALETTE[1]}, line: {dash: 'dot'}},
    // the uncertainty of the zonal mean itself, as thick bars over the spread
    {type: 'scatter', mode: 'markers', name: '95% CI of the mean', x: res.lat_centres,
     y: z.mean, marker: {color: PALETTE[2], size: 1},
     error_y: {type: 'data', symmetric: false, thickness: 5, width: 0, color: PALETTE[2],
               array: z.mean.map((m, i) => (m === null || z.ci95_hi[i] === null ? 0 : z.ci95_hi[i] - m)),
               arrayminus: z.mean.map((m, i) => (m === null || z.ci95_lo[i] === null ? 0 : m - z.ci95_lo[i]))},
     hoverinfo: 'skip'},
  ], axesLayout('Latitude [°N] (band centre)', cleanPlotlyMath(res.title)), PLOT_CONFIG);
  const gw = res.gw;
  $('#mapgrid-title').textContent = `${res.title}: mean in each cell`;
  $('#mapgrid-caption').textContent =
    `${res.n} of ${res.selected} profiles have a value; overall mean ` +
    `${fmt(res.overall.mean, 3)}, median ${fmt(res.overall.median, 3)}. ` +
    `Cells of ${req.lat_step}° × ${req.lon_step}° with fewer than ` +
    `${res.min_count} profiles are blank. Zonal mean: thin bars ± 1 standard deviation, ` +
    `thick bars the 95% confidence interval of the mean (Student's t, profiles taken as independent).` +
    (gw ? ` Gravity-wave energy over ${gw.z_lo}-${gw.z_hi} km, background: ` +
          (gw.method === 'highpass' ? `high-pass, ${gw.cutoff_km} km cut-off.`
                                    : `degree-${gw.poly_order} polynomial.`) : '');
}

// ------------------------------------------------------- radiosonde comparison

const PAIR_NOTES = {
  refractivity: 'The 1D-Var analysis departs from the observed refractivity where the ' +
    'background and the observation disagree, mostly in the moist lower troposphere.',
  moisture_effect: 'How much colder the dry temperature is than the real one: the ' +
    'water vapour the dry retrieval leaves out. It follows T - 77.6 P_dry / N.',
  dry_temperature: 'Both files carry the dry retrieval of the same occultation, so this ' +
    'should be near zero; it shows the differences in their processing and grids.',
  dry_pressure: 'Both files carry the dry retrieval of the same occultation, so this ' +
    'should be near zero.',
};

async function drawPairs() {
  const req = Object.assign({
    quantity: $('#pp-quantity').value,
    top_km: Number($('#pp-top').value) || 30,
    step_km: Number($('#pp-step').value) || 0.5,
  }, statsSelection($('#pp-selected-only').checked));
  if (req.search) {
    req.search.good_only = true;
    req.search.limit = req.max_profiles = 5000;
  }
  const res = await api.productPairs(req);
  $('#pp-count').textContent = `${res.n_pairs} pairs`;
  if (!res.n_pairs) {
    emptyPlot('pp-plot', 'No occultation of the selection has both its atmPrf and its ' +
              'wetPf2 on this computer. Download both products for the same day.');
    $('#pp-caption').textContent = '';
    return;
  }
  const band = (a, b, fill, name) => [
    {type: 'scatter', mode: 'lines', x: a, y: res.grid, line: {width: 0},
     hoverinfo: 'skip', showlegend: false},
    {type: 'scatter', mode: 'lines', x: b, y: res.grid, line: {width: 0},
     fill: 'tonextx', fillcolor: fill, hoverinfo: 'skip', name},
  ];
  const lo = res.mean.map((m, i) => (m === null || res.std[i] === null ? null : m - res.std[i]));
  const hi = res.mean.map((m, i) => (m === null || res.std[i] === null ? null : m + res.std[i]));
  Plotly.react('pp-plot', [
    ...band(lo, hi, 'rgba(2,132,199,0.14)', '± 1 std'),
    ...band(res.ci95_lo, res.ci95_hi, 'rgba(2,132,199,0.40)', '95% CI of the mean'),
    {type: 'scatter', mode: 'lines', x: res.mean, y: res.grid, name: 'mean',
     line: {color: PALETTE[0], width: 2}, text: res.n.map((n) => `n=${n}`),
     hovertemplate: '%{y} km: %{x:.3g} (%{text})<extra></extra>'},
    {type: 'scatter', mode: 'lines', x: res.median, y: res.grid, name: 'median',
     line: {color: PALETTE[1], width: 1.5, dash: 'dot'}},
  ], axesLayout(`${res.label} [${res.units}]`, 'Altitude above mean sea level [km]', {
    shapes: [{type: 'line', x0: 0, x1: 0, yref: 'paper', y0: 0, y1: 1,
              line: {color: '#94a3b8', width: 1, dash: 'dot'}}],
  }), PLOT_CONFIG);
  $('#pp-caption').textContent =
    `${res.n_pairs} occultations with both files (of ${res.selected} selected profiles); ` +
    `levels with fewer than ${res.min_count} pairs are blank. ` +
    (res.relative ? 'Differences in percent of the wetPf2 value. ' : '') +
    `${PAIR_NOTES[res.quantity] || ''} Shading: ± 1 standard deviation and the 95% ` +
    'confidence interval of the mean (Student\'s t, occultations taken as independent).';
}

async function drawRadiosonde() {
  const product = $('#rs-product').value;
  const req = Object.assign({
    max_km: Number($('#rs-km').value) || 300,
    max_hours: Number($('#rs-h').value) || 3,
    bin_km: Number($('#rs-bin').value) || 1,
    export_csv: $('#rs-csv').checked,
  }, statsSelection($('#rs-selected-only').checked));
  if (req.search) {
    req.search.good_only = true;
    req.search.products = [product];
    req.search.limit = req.max_profiles = 5000;
  }
  const res = await api.radiosonde(req);
  $('#rs-count').textContent = `${res.n_pairs} pairs`;
  const plots = [['temp_K', 'rs-temp-plot', 'Temperature difference [K]'],
                 ['ref_N', 'rs-ref-plot', 'Refractivity difference [%]'],
                 ['sph_gkg', 'rs-sph-plot', 'Specific humidity difference [g/kg]']];
  for (const [key, id, title] of plots) {
    const st = res.stats && res.stats[key];
    if (!st) {
      emptyPlot(id, res.n_pairs ? `${key === 'sph_gkg' ? 'Humidity needs wetPf2.' : 'No data.'}`
                                : 'No colocated radiosonde.');
      continue;
    }
    const lo = st.mean.map((m, i) => (m === null || st.std[i] === null ? null : m - st.std[i]));
    const hi = st.mean.map((m, i) => (m === null || st.std[i] === null ? null : m + st.std[i]));
    Plotly.react(id, [
      {type: 'scatter', mode: 'lines', x: lo, y: res.bin_centres_km, line: {width: 0},
       hoverinfo: 'skip', showlegend: false},
      {type: 'scatter', mode: 'lines', x: hi, y: res.bin_centres_km, line: {width: 0},
       fill: 'tonextx', fillcolor: 'rgba(2,132,199,0.18)', hoverinfo: 'skip',
       name: '± 1 std'},
      {type: 'scatter', mode: 'lines+markers', x: st.mean, y: res.bin_centres_km,
       name: 'mean', marker: {color: PALETTE[0], size: 5}, text: st.n.map((n) => `n=${n}`),
       hovertemplate: '%{y} km: %{x:.3g} (%{text})<extra></extra>'},
    ], axesLayout(title, 'Geopotential height [km]', {
      shapes: [{type: 'line', x0: 0, x1: 0, yref: 'paper', y0: 0, y1: 1,
                line: {color: '#94a3b8', width: 1, dash: 'dot'}}],
      showlegend: false,
    }), PLOT_CONFIG);
  }
  const tb = $('#rs-table').tBodies[0];
  clear(tb);
  for (const p of res.pairs.slice(0, 300)) {
    tb.append(el('tr', {},
      el('td', {}, (p.time_utc || '').slice(0, 19).replace('T', ' ')),
      el('td', {}, p.product),
      el('td', {class: 'num'}, fmt(p.lat, 2)), el('td', {class: 'num'}, fmt(p.lon, 2)),
      el('td', {}, `${p.station} ${p.station_name}`),
      el('td', {}, (p.launch_utc || '').slice(0, 16).replace('T', ' ')),
      el('td', {class: 'num'}, fmt(p.distance_km, 0)),
      el('td', {class: 'num'}, fmt(p.dt_hours, 2)),
      el('td', {class: 'num'}, fmt(p.sonde_top_km, 1))));
  }
  const notes = [`${res.n_pairs} of ${res.n_occultations} occultations (${res.products.join(', ')}) ` +
                 `have a radiosonde within ${res.max_km} km and ${res.max_hours} h ` +
                 `(${res.stations_with_data} of ${res.stations_considered} nearby stations had ` +
                 `soundings then).`,
                 'Shading: ± 1 standard deviation of the differences; each pair counts ' +
                 'once per height bin.'];
  if (res.products.includes('atmPrf')) {
    notes.push('atmPrf temperature is dry temperature: below about 8-10 km its ' +
               'difference from the sonde is the water vapour, not an error.');
  }
  if (res.export) notes.push(`Wrote ${res.export.filename}.`);
  $('#rs-caption').textContent = notes.join(' ');
}
