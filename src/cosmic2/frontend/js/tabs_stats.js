// "Statistics" tab: sampling, quality flags and penetration depth of the
// current selection, read from the local index.

import {api, state, selectedIds} from './api.js';
import {$, el, clear, fmt, withBusy, layoutBase, PLOT_CONFIG, PALETTE,
        emptyPlot} from './ui.js';

export function initStatsTab() {
  $('#btn-stats').addEventListener('click', (e) =>
      withBusy(e.target, 'Counting...', drawStats));
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
      el('td', {class: 'num'}, pen && pen.above_ground && pen.above_ground.n
          ? `${pct(pen.above_ground.fraction_below['1'])} (n=${pen.above_ground.n})` : '-')));
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
