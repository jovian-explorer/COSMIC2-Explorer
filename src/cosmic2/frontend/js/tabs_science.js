// "Profiles", "Compare" and "Export" tabs.

import {api, state, selectedIds, deselectRow, axisTitle, vocabInfo} from './api.js';
import {$, el, clear, fmt, bytes, dayOf, latlon, toast, withBusy, fillSelect,
        layoutBase, PLOT_CONFIG, PALETTE, emptyPlot, drawer, cleanPlotlyMath,
        renderMath} from './ui.js';

let lastPlot = null;      // the payload behind the current profile plot
let diagCache = null;     // diagnostics table for the scatter panel

// ==========================================================================
// Profiles
// ==========================================================================

const FIELD_CHOICES = [
  'Temp', 'temp_dry', 'Pres', 'sph', 'rh', 'Vp', 'ref', 'Ref', 'Bend_ang',
  'ELEC_dens', 'TEC_cal', 's4_L1', 'sigma_phi_L1', 'ion_dens', 'ion_temp',
  'iv_zon', 'iv_mer', 'theta', 'dtheta_dz', 'lapse_rate', 'dNdz', 'buoyancy_freq_sq',
  'buoyancy_period', 'speed_of_sound', 'density', 'scale_height',
];
const VERTICAL_CHOICES = ['MSL_alt', 'gph', 'Impact_height', 'occheight', 'alt'];

// What each product can draw ([quantities], [heights]); the first of each is
// the default when a selection of that product cannot show the current pick.
const THERMO_DERIVED = ['theta', 'dtheta_dz', 'lapse_rate', 'dNdz', 'buoyancy_freq_sq',
                        'buoyancy_period', 'speed_of_sound', 'density', 'scale_height'];
const PRODUCT_AXES = {
  atmPrf: [['Temp', 'Pres', 'Ref', 'Bend_ang', ...THERMO_DERIVED],
           ['MSL_alt', 'Impact_height']],
  wetPf2: [['Temp', 'temp_dry', 'Pres', 'sph', 'rh', 'Vp', 'ref', ...THERMO_DERIVED],
           ['MSL_alt', 'gph']],
  ionPrf: [['ELEC_dens', 'TEC_cal'], ['MSL_alt']],
  scnLv2: [['s4_L1', 'sigma_phi_L1'], ['occheight']],
  ivmL2m: [['ion_dens', 'ion_temp', 'iv_zon', 'iv_mer'], ['alt']],
};

/** When every selected profile is one product that cannot draw the chosen
 *  quantity or height (Temp for an ionPrf selection, say), switch to that
 *  product's default instead of drawing an empty plot. */
function fitAxesToSelection() {
  const products = new Set(selectedIds().map((id) => state.selected.get(id).product));
  if (products.size !== 1) return;
  const axes = PRODUCT_AXES[[...products][0]];
  if (!axes) return;
  const [fields, verticals] = axes;
  if (!fields.includes($('#p-field').value)) {
    $('#p-field').value = fields[0];
    $('#p-logx').checked = false;
  }
  if (!verticals.includes($('#p-vertical').value)) $('#p-vertical').value = verticals[0];
}

function labelled(names) {
  return names.map((n) => ({value: n, label: `${vocabInfo(n).label} (${n})`,
                            title: vocabInfo(n).plain}));
}

export function initProfileTab() {
  fillSelect($('#p-field'), labelled(FIELD_CHOICES), 'Temp');
  fillSelect($('#p-vertical'), labelled(VERTICAL_CHOICES), 'MSL_alt');
  $('#btn-plot').addEventListener('click', (e) =>
      withBusy(e.target, 'Drawing...', drawProfiles));
  $('#btn-view-thermo').addEventListener('click', () => quickView('thermo'));
  $('#btn-view-bending').addEventListener('click', () => quickView('bending'));
  $('#btn-view-iono').addEventListener('click', () => quickView('iono'));
  document.addEventListener('selection-changed', () => { renderChips(); fitAxesToSelection(); });
  renderChips();
}

function renderChips() {
  const box = $('#p-selected');
  if (!box) return;
  clear(box);
  const ids = selectedIds();
  if (!ids.length) {
    box.append(el('p', {class: 'hint'}, 'Nothing selected.'));
    return;
  }
  for (const id of ids.slice(0, 60)) {
    const row = state.selected.get(id);
    const x = el('button', {title: 'remove'}, '\u00d7');
    x.addEventListener('click', () => {
      deselectRow(id);
      renderChips();
      document.dispatchEvent(new CustomEvent('selection-changed'));
    });
    box.append(el('span', {class: 'chip'},
      `${row.sat || '?'} ${(row.time_utc || '').slice(11, 16)}`, x));
  }
  if (ids.length > 60) box.append(el('span', {class: 'hint'},
                                     `+${ids.length - 60} more`));
}

function quickView(which) {
  if (which === 'thermo') { $('#p-field').value = 'Temp'; $('#p-logx').checked = false; }
  if (which === 'bending') {
    $('#p-field').value = 'Bend_ang';
    $('#p-vertical').value = 'Impact_height';
    $('#p-logx').checked = true;
  }
  if (which === 'iono') {
    $('#p-field').value = 'ELEC_dens';
    $('#p-vertical').value = 'MSL_alt';
    $('#p-logx').checked = false;
  }
  drawProfiles();
}

async function drawProfiles() {
  const ids = selectedIds();
  if (!ids.length) {
    emptyPlot('profile-plot', 'Select profiles on the Explore tab, then press Draw.');
    return;
  }
  const req = {
    granule_ids: ids.slice(0, 200),
    field: $('#p-field').value,
    vertical: $('#p-vertical').value,
    convert_kelvin: $('#p-kelvin').checked,
    outlier_method: $('#p-outlier-method') ? $('#p-outlier-method').value : 'none',
    smooth_method: $('#p-smooth-method') ? $('#p-smooth-method').value : 'none',
    uncert_method: $('#p-uncert-method') ? $('#p-uncert-method').value : 'none',
    max_points: 900,
  };
  const res = await api.plotProfiles(req);
  lastPlot = res;
  if (!res.series.length) {
    const why = res.skipped.length ? res.skipped[0].why : 'no matching variable';
    emptyPlot('profile-plot',
      `None of the selected profiles carry ${req.field} on ${req.vertical} ` +
      `(${why}).`);
    $('#profile-caption').textContent = '';
    // Keep the diagnostics panel in step with the selection; it otherwise
    // went on showing the previous selection's profile.
    await showDiagnostics(ids[0]);
    return;
  }
  const many = res.series.length > 8;
  const traces = [];
  res.series.forEach((s, i) => {
    const isProcessed = s.provenance && s.provenance.some(p => p.operation === 'outlier_removal' || p.operation === 'smoothing' && p.parameters.method !== 'none');
    
    if (!many && isProcessed && s.original_x) {
        traces.push({
          type: 'scattergl', mode: 'lines',
          x: s.original_x, y: s.y,
          name: `${s.label} (raw)`,
          showlegend: true,
          hoverinfo: 'skip',
          line: {width: 1, color: PALETTE[i % PALETTE.length], dash: 'dot'},
          opacity: 0.4,
        });
    }
  
    const trace = {
      type: 'scattergl', mode: 'lines',
      x: s.x, y: s.y,
      name: s.label + (isProcessed && !many ? ' (processed)' : ''),
      showlegend: !many,
      hovertemplate: `${s.label}<br>%{x:.3f} \u00b7 %{y:.2f} km<extra></extra>`,
      line: {width: many ? 1.2 : 2.2,
             color: many ? colourByLat(s.lat) : PALETTE[i % PALETTE.length]},
      opacity: many ? 0.78 : 1,
    };
    if (s.uncertainty) {
      trace.error_x = {
        type: 'data',
        array: s.uncertainty,
        visible: true,
        color: trace.line.color,
        thickness: 1,
        width: 0,
        opacity: 0.5
      };
    }
    traces.push(trace);
  });
  const fontScale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1.0');
  const base = layoutBase();
  const layout = layoutBase({
    title: {
      text: cleanPlotlyMath(`${vocabInfo(req.field).label} vs ${vocabInfo(req.vertical).label}`),
      font: { size: Math.round(14 * fontScale), color: document.documentElement.dataset.theme === 'dark' ? '#f8fafc' : '#0f172a' },
    },
    xaxis: Object.assign(base.xaxis, {
      title: {text: cleanPlotlyMath(res.field_label), font: {size: Math.round(12 * fontScale)}},
      type: $('#p-logx').checked ? 'log' : 'linear',
      tickfont: {size: Math.round(10.5 * fontScale)},
    }),
    yaxis: Object.assign(base.yaxis, {
      title: {text: cleanPlotlyMath(res.vertical_label), font: {size: Math.round(12 * fontScale)}},
      tickfont: {size: Math.round(10.5 * fontScale)},
    }),
    showlegend: !many,
    legend: {x: 1, xanchor: 'right', y: 1, font: {size: Math.round(10.5 * fontScale)}},
  });
  Plotly.react('profile-plot', traces, layout, PLOT_CONFIG);
  $('#profile-count').textContent = `${res.series.length} profiles`;
  const parts = [`${res.series.length} profile(s).`];
  if (many) parts.push('Line colour runs from blue at the south to red at the north.');
  if (res.skipped.length) {
    parts.push(`${res.skipped.length} skipped: ${res.skipped[0].why}.`);
  }
  if (res.series[0] && res.series[0].x.length >= 900) {
    parts.push('Displayed at reduced vertical resolution; exports use every level.');
  }
  if (res.series[0] && res.series[0].provenance && res.series[0].provenance.length > 0) {
    const prov = res.series[0].provenance;
    let provStr = "Pipeline applied: ";
    const steps = prov.map(p => {
       if (p.operation === 'outlier_removal') {
           const prm = p.parameters;
           if (prm.method === 'none') return '';
           let s = `Outlier removal (${prm.method}`;
           if (prm.removed_count !== undefined) {
               s += `, removed ${prm.removed_count} points [${(prm.percent || 0).toFixed(1)}%]`;
           }
           s += ')';
           return s;
       } else if (p.operation === 'smoothing') {
           if (p.parameters.method === 'none') return '';
           return `Smoothing (${p.parameters.method}, window=${p.parameters.window})`;
       } else if (p.operation === 'uncertainty_estimation') {
           if (p.parameters.method === 'none') return '';
           return `Uncertainty (${p.parameters.method})`;
       }
       return p.operation;
    }).filter(s => s !== '');
    
    if (steps.length > 0) {
        parts.push(provStr + steps.join(" \u2192 ") + ".");
    }
  }
  $('#profile-caption').textContent = parts.join(' ');
  if (res.series.length === 1) await showDiagnostics(res.series[0].granule_id);
  else await showDiagnostics(ids[0]);
}

function colourByLat(lat) {
  if (lat === null || lat === undefined) return '#8a929b';
  const t = Math.max(0, Math.min(1, (lat + 45) / 90));
  const c0 = [31, 78, 121], c1 = [193, 68, 14];
  return `rgb(${c0.map((v, i) => Math.round(v + t * (c1[i] - v))).join(',')})`;
}

// ------------------------------------------------------------- diagnostics

const DIAG_SPECS = [
  ['tropopause.height_km', 'Tropopause height', 'km',
   'Where the temperature stops falling with height - the lid on our weather.'],
  ['tropopause.temp_C', 'Tropopause temperature', '\u00b0C', ''],
  ['cold_point.height_km', 'Cold point height', 'km',
   'The very coldest level, which sets how much water vapour can reach the ' +
   'stratosphere.'],
  ['cold_point.temp_C', 'Cold point temperature', '\u00b0C', ''],
  ['boundary_layer.height_km', 'Boundary-layer top', 'km',
   'Top of the turbulent layer stirred by the surface.'],
  ['column_water_vapour_mm', 'Column water vapour', 'mm',
   'All the water vapour above that spot, as a depth of liquid.'],
  ['gravity_waves.ep_J_per_kg', 'Gravity-wave energy', 'J/kg',
   'Energy carried by buoyancy waves rippling through the stratosphere.'],
  ['ducting.min_gradient', 'Steepest refractivity gradient', 'N/km',
   'Below -157 the atmosphere traps radio waves entirely.'],
  ['ionosphere.NmF2_el_cm3', 'Peak electron density', 'el/cm\u00b3',
   'The densest plasma layer, which reflects shortwave radio.'],
  ['ionosphere.hmF2_km', 'Height of the peak', 'km', ''],
  ['ionosphere.foF2_MHz', 'Critical frequency', 'MHz',
   'Radio below this bounces off the ionosphere; above it escapes to space.'],
  ['ionosphere.topside_scale_height_km', 'Topside scale height', 'km', ''],
  ['ionosphere.vtec_below_peak_TECU', 'Vertical TEC below the peak', 'TECU',
   'All the free electrons in a 1 m\u00b2 column up to the F2 peak.'],
  ['ionosphere.vtec_profile_TECU', 'Vertical TEC of the profile', 'TECU',
   'The same column from the bottom of the profile to its top.'],
  ['scintillation.s4_max', 'Peak S4', '',
   'How hard the signal flickered. Above 0.4 means strong turbulence.'],
  ['scintillation.severity', 'Scintillation class', '', ''],
  ['insitu.ion_dens_median_Ncc', 'Ion density at the spacecraft', 'N/cc', ''],
];

function dig(obj, path) {
  return path.split('.').reduce((o, k) => (o && o[k] !== undefined ? o[k] : null), obj);
}

async function showDiagnostics(gid) {
  const body = $('#diag-body');
  clear(body);
  let detail;
  try {
    detail = await api.profile(gid);
  } catch (err) {
    body.append(el('p', {class: 'hint'}, err.message));
    return;
  }
  const d = detail.diagnostics || {};
  const m = detail.meta;
  body.append(el('p', {class: 'hint'},
    `${m.file_name} \u00b7 ${dayOf(m.time_utc)} ${(m.time_utc || '').slice(11, 19)}Z ` +
    `\u00b7 ${latlon(m.lat, 'lat')} ${latlon(m.lon, 'lon')} ` +
    `\u00b7 local solar time ${fmt(m.local_time, 1)} h ` +
    `\u00b7 ${m.setting || ''} occultation`));
  if (m.error_text) {
    body.append(el('p', {class: 'pill bad'},
      `The archive marked this granule as failed: ${m.error_text}`));
  }
  const grid = el('div', {class: 'diag-grid'});
  let shown = 0;
  for (const [path, label, unit, plain] of DIAG_SPECS) {
    const v = dig(d, path);
    if (v === null || v === undefined) continue;
    shown++;
    grid.append(el('div', {class: 'diag'},
      el('div', {class: 'dk'}, label),
      el('div', {class: 'dv'}, typeof v === 'number'
          ? `${fmt(v, 2)}${unit ? ' ' + unit : ''}` : String(v)),
      plain ? el('div', {class: 'dn', 'data-curious': true}, plain) : null));
  }
  if (!shown) grid.append(el('p', {class: 'hint'},
    'No scalar diagnostics apply to this product.'));
  body.append(grid);
  // A density maximum on the first or last level is where the profile was
  // cut, not an F2 peak: say so beside the numbers rather than in a flag
  // nobody sees.
  if (d.ionosphere && d.ionosphere.peak_at_profile_edge) {
    const hm = d.ionosphere.hmF2_km;
    const edge = Math.abs(hm - m.alt_max) < Math.abs(hm - m.alt_min) ? 'top' : 'bottom';
    body.append(el('p', {class: 'pill warn'},
      `No F2 peak: the largest density is on the ${edge} ` +
      `level of the profile (${fmt(hm, 1)} km), so the peak values ` +
      `above are the profile's maximum, not NmF2/hmF2.`));
  }

  // Where our numbers can be checked against the archive's own, show both.
  const av = d.archive_values || {};
  const pairs = [
    ['tropopause.height_km', 'tropopause_height_wmo_km', 'Tropopause height', 'km'],
    ['cold_point.height_km', 'cold_point_height_km', 'Cold point height', 'km'],
    ['ionosphere.NmF2_el_cm3', 'NmF2_el_cm3', 'Peak electron density', 'el/cm\u00b3'],
    ['ionosphere.hmF2_km', 'hmF2_km', 'Height of the peak', 'km'],
    ['ionosphere.vtec_profile_TECU', 'tec_profile_TECU', 'Vertical TEC of the profile', 'TECU'],
    ['scintillation.s4_max', 's4max_L1', 'Peak S4', ''],
  ].filter(([ours, theirs]) => dig(d, ours) !== null && av[theirs] !== null &&
                               av[theirs] !== undefined);
  if (pairs.length) {
    const rows = pairs.map(([ours, theirs, label, unit]) => el('tr', {},
      el('td', {}, label),
      el('td', {class: 'num'}, `${fmt(dig(d, ours), 3)} ${unit}`),
      el('td', {class: 'num'}, `${fmt(av[theirs], 3)} ${unit}`)));
    body.append(el('h3', {}, 'Cross-check against CDAAC'),
      el('table', {class: 'table'},
        el('thead', {}, el('tr', {}, el('th', {}, 'Quantity'),
                           el('th', {}, 'Computed here'),
                           el('th', {}, 'From the archive'))),
        el('tbody', {}, ...rows)),
      el('p', {class: 'hint'},
        'Recomputed independently from the profile arrays. Differences of a ' +
        'grid step are expected; large ones are worth a look.'));
  }
  const more = el('button', {class: 'link'}, 'Show every archive attribute');
  more.addEventListener('click', () => showAttributes(detail));
  body.append(el('p', {}, more));
  renderMath(body);
}

function showAttributes(detail) {
  const rows = Object.entries(detail.meta.extras || {}).map(([k, v]) =>
      el('tr', {}, el('td', {}, k), el('td', {}, fmt(v, 4))));
  const notes = Object.entries(detail.attribute_notes || {}).slice(0, 200)
      .map(([k, v]) => el('tr', {}, el('td', {}, k), el('td', {}, v)));
  drawer(detail.meta.file_name, el('div', {},
    el('h3', {}, detail.product_info.label),
    el('p', {}, detail.product_info.blurb),
    el('h3', {}, 'Derived scalars from the archive'),
    el('table', {}, el('tbody', {}, ...rows)),
    notes.length ? el('h3', {}, 'Attribute descriptions') : null,
    notes.length ? el('table', {}, el('tbody', {}, ...notes)) : null));
}

// ==========================================================================
// Compare
// ==========================================================================

export function initCompositeTab() {
  fillSelect($('#c-field'), labelled(FIELD_CHOICES), 'Temp');
  fillSelect($('#c-vertical'), labelled(VERTICAL_CHOICES), 'MSL_alt');
  // Scintillation records have no MSL_alt; their height is the ray tangent
  // height, so follow the quantity unless the user picked a height.
  $('#c-field').addEventListener('change', () => {
    const scint = ['s4_L1', 'sigma_phi_L1'].includes($('#c-field').value);
    const v = $('#c-vertical');
    if (scint && v.value === 'MSL_alt') v.value = 'occheight';
    if (!scint && v.value === 'occheight') v.value = 'MSL_alt';
  });
  fillSelect($('#c-groupby'), state.meta.group_by_options.map((g) =>
      ({value: g, label: g.replace(/_/g, ' ')})), 'lat_band');
  $('#btn-composite').addEventListener('click', (e) =>
      withBusy(e.target, 'Averaging...', drawComposite));
  $('#btn-scatter').addEventListener('click', (e) =>
      withBusy(e.target, 'Plotting...', drawScatter));
}

function selection(selectedOnly) {
  const ids = selectedIds();
  if (selectedOnly && ids.length) return {granule_ids: ids};
  return {search: Object.assign({}, state.lastSearch || {good_only: true},
                                {limit: 2000, offset: 0})};
}

async function drawComposite() {
  const req = Object.assign({
    field: $('#c-field').value,
    vertical: $('#c-vertical').value,
    group_by: $('#c-groupby').value,
    top_km: Number($('#c-top').value) || 40,
    step_km: Number($('#c-step').value) || 0.5,
    good_only: true,
    convert_kelvin: $('#c-field').value === 'Temp',
  }, selection($('#c-selected-only').checked));
  const res = await api.composite(req);
  const names = Object.keys(res.groups);
  if (!res.n_profiles) {
    emptyPlot('composite-plot',
      `None of the ${res.selected} selected profiles carry ${req.field} on ` +
      `${req.vertical} below ${req.top_km} km.`);
    $('#composite-caption').textContent = '';
    return;
  }
  if (!names.length) {
    emptyPlot('composite-plot', 'No group had enough profiles to average.');
    return;
  }
  const spread = $('#c-spread').value;
  const traces = [];
  names.forEach((name, i) => {
    const g = res.groups[name];
    const colour = PALETTE[i % PALETTE.length];
    const lo = spread === 'p10p90' ? g.p10
             : g.mean.map((m, k) => (m === null || g.std[k] === null
                                     ? null : m - g.std[k]));
    const hi = spread === 'p10p90' ? g.p90
             : g.mean.map((m, k) => (m === null || g.std[k] === null
                                     ? null : m + g.std[k]));
    traces.push({
      type: 'scatter', mode: 'lines', x: lo, y: res.grid,
      line: {width: 0}, hoverinfo: 'skip', showlegend: false,
      legendgroup: name,
    });
    traces.push({
      type: 'scatter', mode: 'lines', x: hi, y: res.grid,
      fill: 'tonextx', fillcolor: hexToRgba(colour, .22),
      line: {width: 0}, hoverinfo: 'skip', showlegend: false,
      legendgroup: name,
    });
    traces.push({
      type: 'scatter', mode: 'lines', x: g.mean, y: res.grid,
      name: `${name} (n=${g.n})`, legendgroup: name,
      line: {color: colour, width: 2.5},
      hovertemplate: `${name}<br>%{x:.2f} \u00b7 %{y:.1f} km<extra></extra>`,
    });
  });
  const fontScale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1.0');
  const isDark = document.documentElement.dataset.theme === 'dark';
  const base = layoutBase();
  Plotly.react('composite-plot', traces, layoutBase({
    title: {
      text: cleanPlotlyMath(`Average ${vocabInfo(res.field).label} by ${$('#c-groupby').value.replace(/_/g, ' ')}`),
      font: { size: Math.round(14 * fontScale), color: isDark ? '#f8fafc' : '#0f172a' }
    },
    xaxis: Object.assign(base.xaxis, {
      title: {text: cleanPlotlyMath(res.field_label), font: {size: Math.round(12 * fontScale)}},
      tickfont: {size: Math.round(10.5 * fontScale)}
    }),
    yaxis: Object.assign(base.yaxis, {
      title: {text: cleanPlotlyMath(res.vertical_label), font: {size: Math.round(12 * fontScale)}},
      tickfont: {size: Math.round(10.5 * fontScale)}
    }),
    legend: {x: .02, y: .02, xanchor: 'left', yanchor: 'bottom', font: {size: Math.round(10.5 * fontScale)}},
  }), PLOT_CONFIG);

  const band = spread === 'std' ? 'mean \u00b1 1 standard deviation'
                                : '10th-90th percentile';
  let cap = `Shading: ${band}. ${res.n_profiles} profiles interpolated to a ` +
            `common ${fmt(res.grid[1] - res.grid[0], 2)} km grid before ` +
            `averaging; levels with fewer than ${res.min_count} profiles are blank.`;
  const dropped = Object.entries(res.dropped_groups || {});
  if (dropped.length) {
    cap += ` Omitted for having fewer than ${res.min_count} profiles: ` +
           dropped.map(([k, v]) => `${k} (n=${v})`).join(', ') + '.';
  }
  $('#composite-caption').textContent = cap;
  $('#composite-title').textContent =
    `Average ${vocabInfo(res.field).label} by ` +
    `${$('#c-groupby').value.replace(/_/g, ' ')}`;
}

function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

async function drawScatter() {
  const req = Object.assign({max_profiles: 2000},
                            selection($('#c-selected-only').checked));
  diagCache = await api.diagTable(req);
  populateScatterAxes(diagCache.columns);
  const xf = $('#s-x').value, yf = $('#s-y').value, cf = $('#s-c').value;
  const rows = diagCache.rows.filter((r) => r[xf] !== null && r[yf] !== null &&
                                            r[xf] !== undefined && r[yf] !== undefined);
  if (!rows.length) {
    emptyPlot('scatter-plot', `No profile has both ${xf} and ${yf}.`);
    return;
  }
  const trace = {
    type: 'scattergl', mode: 'markers',
    x: rows.map((r) => r[xf]), y: rows.map((r) => r[yf]),
    text: rows.map((r) => `${r.file_name}<br>${(r.time_utc || '').slice(0, 19)}Z`),
    hovertemplate: '%{text}<br>%{x:.3f}, %{y:.3f}<extra></extra>',
    marker: {
      size: 8, line: {width: 0.8, color: 'rgba(255, 255, 255, 0.85)'},
      opacity: 0.88,
      color: cf ? rows.map((r) => r[cf]) : '#0284c7',
      colorscale: 'Viridis',
      colorbar: cf ? {title: {text: cleanPlotlyMath(prettyCol(cf)), side: 'right'},
                      thickness: 12, len: .8} : undefined,
    },
  };
  const sFontScale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1.0');
  const sIsDark = document.documentElement.dataset.theme === 'dark';
  const base = layoutBase();
  Plotly.react('scatter-plot', [trace], layoutBase({
    title: {
      text: cleanPlotlyMath(`${prettyCol(yf)} vs ${prettyCol(xf)}`),
      font: { size: Math.round(14 * sFontScale), color: sIsDark ? '#f8fafc' : '#0f172a' }
    },
    xaxis: Object.assign(base.xaxis, {
      title: {text: cleanPlotlyMath(prettyCol(xf)), font: {size: Math.round(12 * sFontScale)}},
      tickfont: {size: Math.round(10.5 * sFontScale)}
    }),
    yaxis: Object.assign(base.yaxis, {
      title: {text: cleanPlotlyMath(prettyCol(yf)), font: {size: Math.round(12 * sFontScale)}},
      tickfont: {size: Math.round(10.5 * sFontScale)}
    }),
  }), PLOT_CONFIG);
  $('#scatter-caption').textContent =
    `${rows.length} of ${diagCache.n} profiles have both quantities` +
    (diagCache.unreadable ? `; ${diagCache.unreadable} were unreadable.` : '.');
}

function prettyCol(col) {
  if (!col) return '';
  if (!col.includes('.')) return axisTitle(col);
  const [group, leaf] = col.split('.');
  const unit = leaf.match(/_(km|K|C|MHz|mm)$/);
  const name = leaf.replace(/_(km|K|C|MHz|mm|el_cm3|J_per_kg|Ncc)$/, '')
                   .replace(/_/g, ' ');
  return `${group.replace(/_/g, ' ')}: ${name}${unit ? ` [${unit[1]}]` : ''}`;
}

function populateScatterAxes(columns) {
  const numeric = columns.filter((c) =>
      !['granule_id', 'file_name', 'product', 'time_utc', 'sat', 'good'].includes(c) &&
      !c.endsWith('.found') && !c.endsWith('.method') && !c.endsWith('.ducting') &&
      !c.endsWith('.critical_gradient'));
  const opts = numeric.map((c) => ({value: c, label: prettyCol(c)}));
  for (const [sel, preferred] of [['#s-x', 'lat'],
                                  ['#s-y', 'tropopause.height_km'],
                                  ['#s-c', 'local_time']]) {
    const node = $(sel);
    const keep = node.value;
    const list = sel === '#s-c' ? [{value: '', label: 'none'}, ...opts] : opts;
    fillSelect(node, list,
               numeric.includes(keep) ? keep
               : (numeric.includes(preferred) ? preferred : list[0].value));
  }
}

// ==========================================================================
// Export
// ==========================================================================

export function initExportTab() {
  fillSelect($('#e-field'), labelled(FIELD_CHOICES), 'Temp');
  $('#citation-box').textContent = state.meta.citation;
  $('#citation-src').textContent = state.meta.citation_source;
  $('#e-dpi').value = state.meta.settings.plot_dpi;
  $('#btn-export-data').addEventListener('click', (e) =>
      withBusy(e.target, 'Writing...', exportData));
  $('#btn-export-fig').addEventListener('click', (e) =>
      withBusy(e.target, 'Rendering...', exportFigure));
  $('#btn-open-exports').addEventListener('click', () =>
      api.revealFolder('exports').catch((err) => toast(err.message, 'bad')));
  refreshExports();
}

async function exportData() {
  const req = Object.assign({
    kind: $('#e-kind').value,
    field: $('#e-field').value,
    vertical: 'MSL_alt',
    top_km: Number($('#e-top').value) || 60,
    step_km: Number($('#e-step').value) || 0.2,
    basename: $('#e-name').value || 'cosmic2',
  }, selection($('#e-selected-only').checked));
  if (kind === 'composite') {
    // The figure reproduces the Compare tab's average as drawn there: its
    // quantity, height, grid and Kelvin choice (the grid used to fall back to
    // 0-60 km, which left an ionospheric composite empty).
    Object.assign(req, {
      field: $('#c-field').value,
      vertical: $('#c-vertical').value || 'MSL_alt',
      top_km: Number($('#c-top').value) || 40,
      step_km: Number($('#c-step').value) || 0.5,
      convert_kelvin: $('#c-field').value === 'Temp',
    });
  }
  
  // Attach current processing parameters for provenance
  req.outlier_method = $('#p-outlier-method') ? $('#p-outlier-method').value : 'none';
  req.smooth_method = $('#p-smooth-method') ? $('#p-smooth-method').value : 'none';
  req.uncert_method = $('#p-uncert-method') ? $('#p-uncert-method').value : 'none';
  
  const res = await api.exportData(req);
  toast(`Wrote ${res.filename} (${bytes(res.bytes)}).`, 'good');
  await refreshExports();
}

async function exportFigure() {
  const kind = $('#e-fig').value;
  const req = Object.assign({
    kind,
    field: $('#e-field').value,
    vertical: $('#p-vertical').value || 'MSL_alt',
    group_by: $('#c-groupby').value || 'lat_band',
    spread: $('#c-spread').value || 'std',
    fmt: $('#e-fmt').value,
    dpi: Number($('#e-dpi').value) || 300,
    title: $('#e-title').value,
    caption: $('#e-caption').value,
    logx: $('#p-logx').checked,
    convert_kelvin: $('#p-kelvin').checked,
    color_field: kind === 'map' ? 'local_time' : null,
    panels: kind === 'panels' ? panelsFor() : null,
    x_field: $('#s-x').value || 'lat',
    y_field: $('#s-y').value || 'tropopause.height_km',
  }, selection($('#e-selected-only').checked));
  if (kind === 'composite') {
    // The figure reproduces the Compare tab's average as drawn there: its
    // quantity, height, grid and Kelvin choice (the grid used to fall back to
    // 0-60 km, which left an ionospheric composite empty).
    Object.assign(req, {
      field: $('#c-field').value,
      vertical: $('#c-vertical').value || 'MSL_alt',
      top_km: Number($('#c-top').value) || 40,
      step_km: Number($('#c-step').value) || 0.5,
      convert_kelvin: $('#c-field').value === 'Temp',
    });
  }
  
  // Attach current processing parameters for provenance
  req.outlier_method = $('#p-outlier-method') ? $('#p-outlier-method').value : 'none';
  req.smooth_method = $('#p-smooth-method') ? $('#p-smooth-method').value : 'none';
  req.uncert_method = $('#p-uncert-method') ? $('#p-uncert-method').value : 'none';
  
  const res = await api.exportFigure(req);
  toast(`Rendered ${res.filename} (${bytes(res.bytes)}).`, 'good');
  await refreshExports();
}

/** Sensible multi-panel set for whichever product is selected. */
function panelsFor() {
  const ids = selectedIds();
  const product = ids.length ? (state.selected.get(ids[0]).product) : 'wetPf2';
  return {
    wetPf2: ['Temp', 'sph', 'ref'],
    atmPrf: ['Temp', 'Ref', 'Bend_ang'],
    ionPrf: ['ELEC_dens', 'TEC_cal'],
    scnLv2: ['s4_L1', 'sigma_phi_L1', 'L1_SNR'],
    ivmL2m: ['ion_dens', 'ion_temp', 'iv_zon'],
  }[product] || ['Temp'];
}

async function refreshExports() {
  const {exports} = await api.exports();
  const tb = $('#exports-table').tBodies[0];
  clear(tb);
  if (!exports.length) {
    tb.append(el('tr', {}, el('td', {colspan: 4, class: 'hint'},
                              'Nothing exported yet.')));
    return;
  }
  for (const f of exports) {
    const dl = el('a', {href: `/api/exports/${encodeURIComponent(f.filename)}`,
                        download: f.filename, class: 'link'}, 'Download');
    const del = el('button', {class: 'ghost danger'}, 'Delete');
    del.addEventListener('click', async () => {
      await api.deleteExport(f.filename).catch((e) => toast(e.message, 'bad'));
      await refreshExports();
    });
    tb.append(el('tr', {},
      el('td', {}, f.filename),
      el('td', {class: 'num'}, bytes(f.bytes)),
      el('td', {}, f.modified.slice(0, 19).replace('T', ' ')),
      el('td', {}, dl, ' ', del)));
  }
}
