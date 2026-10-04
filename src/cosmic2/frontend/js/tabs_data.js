// "Get data" and "Explore" tabs: archive browsing, downloads, map and results.

import {api, state, selectRow, deselectRow, isSelected, selectedIds} from './api.js';
import {$, $$, el, clear, fmt, bytes, clock, isoDay, timeOf, latlon,
        toast, withBusy, fillSelect, layoutBase, PLOT_CONFIG,
        emptyPlot} from './ui.js';

let pollTimer = null;
let manifest = [];

// ==========================================================================
// Get data
// ==========================================================================

export function initGetTab() {
  const streams = Object.entries(state.meta.streams).map(([k, v]) =>
      ({value: k, label: v.label, title: v.blurb}));
  fillSelect($('#get-stream'), streams, state.meta.settings.default_stream);
  updateStreamBlurb();
  updateSamplingHint();

  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 3);
  $('#get-date').value = isoDay(d);

  $('#get-stream').addEventListener('change', updateStreamBlurb);
  $('#get-sampling').addEventListener('change', updateSamplingHint);
  $('#get-count').addEventListener('change', updateSamplingHint);
  $('#btn-scan').addEventListener('click', (e) => scanDay(e.target));
  $('#btn-latest').addEventListener('click', (e) => useLatest(e.target));
  $('#btn-samples').addEventListener('click', (e) => loadSamples(e.target));
  $('#btn-reindex').addEventListener('click', (e) => withBusy(e.target, 'Working...',
      async () => { await api.reindex(); pollJobs(); toast('Rebuilding the index.'); }));
  $('#btn-open-cache').addEventListener('click', () =>
      api.revealFolder('cache').catch((err) => toast(err.message, 'bad')));

  refreshLocal();
  pollJobs();
}

function currentStream() {
  const key = $('#get-stream').value;
  return {key, level: state.meta.streams[key].levels[0]};
}

function updateStreamBlurb() {
  const {key} = currentStream();
  $('#stream-blurb').textContent = state.meta.streams[key].blurb;
}

function updateSamplingHint() {
  const spread = $('#get-sampling').value === 'spread';
  const all = $('#get-count').value === '0';
  $('#sampling-hint').textContent = all
    ? 'The whole day will be transferred. For atmPrf that is over 2 GB.'
    : spread
      ? 'Fills an even quota for each UTC hour, so the sample spans the whole ' +
        'day. The archive is read through to the end, so more is transferred ' +
        'than is kept.'
      : 'Takes profiles in archive order and stops as soon as the quota is met. ' +
        'Cheapest option, but covers only the start of the UTC day.';
}

async function useLatest(button) {
  const {key, level} = currentStream();
  await withBusy(button, 'Checking...', async () => {
    const res = await api.archiveLatest(key, level);
    $('#get-date').value = res.date;
    toast(`Most recent ${key} day with data: ${res.date}`);
    await scanDay($('#btn-scan'));
  });
}

async function scanDay(button) {
  const date = $('#get-date').value;
  if (!date) { toast('Pick a date first.', 'bad'); return; }
  const card = $('#manifest-card');
  card.classList.remove('hidden');
  $('#manifest-note').textContent = 'Asking the archive...';
  await withBusy(button, 'Scanning...', async () => {
    const res = await api.archiveDay(date);
    manifest = res.files;
    renderManifest(date, res);
  });
}

function renderManifest(date, res) {
  const list = $('#manifest-list');
  clear(list);
  if (!manifest.length) {
    $('#manifest-note').textContent =
      `Nothing published for ${date}. Near-real-time data appears within hours; ` +
      `post-processed streams lag by months.`;
    return;
  }
  $('#manifest-note').textContent =
    `${manifest.length} files for ${date}, ${bytes(res.total_bytes)} in total on ` +
    `the archive. You only transfer what you ask for.`;
  for (const f of manifest) list.append(productCard(f));
}

function productCard(f) {
  const count = $('#get-count');
  const big = (f.size_bytes || 0) > state.meta.settings.warn_download_mb * 1024 * 1024;
  const btn = el('button', {class: f.readable ? 'primary' : 'ghost',
                            disabled: !f.readable},
                 f.readable ? 'Fetch' : 'No reader yet');
  btn.addEventListener('click', () => startDownload(f, btn));
  return el('div', {class: `product ${f.readable ? '' : 'unreadable'}`},
    el('div', {class: 'ptitle'},
      el('span', {class: 'pname'}, f.label),
      el('span', {class: 'pcode'}, f.product)),
    el('div', {class: 'pdesc', 'data-curious': true}, f.plain),
    el('div', {class: 'pdesc'}, f.blurb),
    el('div', {class: 'pfoot'},
      el('span', {class: `pill ${big ? 'warn' : ''}`},
         f.size_bytes ? bytes(f.size_bytes) : 'size unknown'),
      el('span', {class: 'pill'}, f.stream),
      btn));
}

async function startDownload(f, button) {
  const raw = parseInt($('#get-count').value, 10);
  const req = {
    stream: f.stream, level: f.level, product: f.product,
    date: f.date, max_profiles: raw === 0 ? 0 : raw,
    sampling: $('#get-sampling').value,
    good_only: $('#get-goodonly').checked,
  };
  if (raw === 0 && (f.size_bytes || 0) > 400 * 1024 ** 2 &&
      !confirm(`A whole day of ${f.label} is ${bytes(f.size_bytes)}. ` +
               `Download all of it?`)) return;
  await withBusy(button, 'Queued', async () => {
    await api.download(req);
    toast(`Fetching ${f.label} for ${f.date}.`);
    pollJobs();
  });
}

export async function loadSamples(button) {
  const run = async () => {
    const res = await api.loadSamples();
    toast(`Indexed ${res.indexed} bundled granules.`, 'good');
    await refreshLocal();
    await runSearch();
  };
  if (button) {
    await withBusy(button, 'Loading...', run);
  } else {
    await run();
  }
}

// -------------------------------------------------------------- job polling

export function pollJobs() {
  if (pollTimer) clearTimeout(pollTimer);
  api.jobs().then(({jobs}) => {
    renderJobs(jobs);
    const active = jobs.some((j) => j.state === 'running' || j.state === 'queued');
    if (active) pollTimer = setTimeout(pollJobs, 900);
    else { refreshLocal(); refreshFacets(); }
  }).catch(() => { /* backend restarting; the next user action will retry */ });
}

function renderJobs(jobs) {
  const box = $('#jobs-list');
  clear(box);
  if (!jobs.length) {
    box.append(el('p', {class: 'hint'}, 'Nothing queued.'));
    return;
  }
  for (const j of jobs.slice(0, 8)) box.append(jobCard(j));
}

function jobCard(j) {
  const cls = j.state === 'completed' ? 'done'
            : (j.state === 'failed' ? 'failed' : '');
  const pill = {running: '', queued: '', completed: 'ok', failed: 'bad',
                cancelled: 'warn'}[j.state] || '';
  const bits = [];
  if (j.extracted) bits.push(`${j.extracted} granules kept`);
  if (j.members_seen) bits.push(`${j.members_seen} scanned`);
  if (j.bytes_done) {
    bits.push(`${bytes(j.bytes_done)}` +
              (j.bytes_total ? ` of ${bytes(j.bytes_total)} transferred` : ''));
  }
  if (j.speed_bps) bits.push(`${bytes(j.speed_bps)}/s`);
  if (j.eta_s && j.state === 'running') bits.push(`~${clock(j.eta_s)} left`);
  if (j.hours_covered) bits.push(`${j.hours_covered}/24 UTC hours covered`);
  if (j.elapsed_s) bits.push(`${clock(j.elapsed_s)} elapsed`);

  const head = el('div', {class: 'job-head'},
    el('span', {class: 'job-title'}, j.title),
    el('span', {class: `pill ${pill}`}, j.state));
  if (j.state === 'running' || j.state === 'queued') {
    const cancel = el('button', {class: 'ghost'}, 'Cancel');
    cancel.addEventListener('click', () => api.cancelJob(j.id)
        .then(() => pollJobs()).catch((e) => toast(e.message, 'bad')));
    head.append(cancel);
  }
  return el('div', {class: `job ${cls}`}, head,
    el('div', {class: 'bar'}, el('span', {style: `width:${j.percent || 0}%`})),
    el('div', {class: 'job-meta'}, j.error || j.message || j.phase),
    bits.length ? el('div', {class: 'job-meta'}, bits.join(' \u00b7 ')) : null);
}

// -------------------------------------------------------------- local state

export function updateProfileCounter(count) {
  const badge = $('#granule-count-badge');
  if (!badge) return;
  const n = count ?? 0;
  badge.textContent = `${n} ${n === 1 ? 'profile' : 'profiles'}`;
  badge.classList.toggle('has-data', n > 0);
}

export async function refreshLocal() {
  try {
    const s = await api.localSummary();
    updateProfileCounter(s.n_granules);
    const box = $('#local-summary');
    clear(box);
    const stats = [
      ['profiles indexed', String(s.n_granules)],
      ['products', String(s.by_product.length)],
      ['on disk', bytes(s.cache_bytes_on_disk)],
      ['quota', bytes(s.cache_quota_bytes)],
      ['earliest', s.time_min ? s.time_min.slice(0, 10) : '-'],
      ['latest', s.time_max ? s.time_max.slice(0, 10) : '-'],
    ];
    for (const [k, v] of stats) {
      box.append(el('div', {class: 'stat'}, el('div', {class: 'v'}, v),
                    el('div', {class: 'k'}, k)));
    }
    const {datasets} = await api.datasets();
    const tb = $('#datasets-table').tBodies[0];
    clear(tb);
    if (!datasets.length) {
      tb.append(el('tr', {}, el('td', {colspan: 7, class: 'hint'},
                                'Nothing downloaded yet.')));
    }
    for (const d of datasets) {
      const del = el('button', {class: 'ghost danger'}, 'Delete');
      del.addEventListener('click', async () => {
        if (!confirm(`Delete ${d.n_granules} granules of ${d.product} ` +
                     `for ${d.date}? The files are removed from disk.`)) return;
        await withBusy(del, '...', async () => {
          const r = await api.deleteDataset(d.key);
          toast(`Removed ${r.deleted} files, freed ${bytes(r.freed_bytes)}.`);
          await refreshLocal();
          await refreshFacets();
        });
      });
      tb.append(el('tr', {},
        el('td', {}, d.product), el('td', {}, d.date), el('td', {}, d.stream),
        el('td', {class: 'num'}, String(d.n_granules)),
        el('td', {class: 'num'}, bytes(d.bytes)),
        el('td', {}, el('span', {class: `pill ${d.complete ? 'ok' : 'warn'}`},
                        d.complete ? 'whole day' : 'sample')),
        el('td', {}, del)));
    }
  } catch (err) {
    toast(err.message, 'bad');
  }
}

export async function refreshFacets() {
  try {
    const f = await api.facets();
    const products = f.products.length ? f.products : ['wetPf2'];
    fillSelect($('#f-product'), products, products[0]);
    fillSelect($('#f-sat'), [{value: '', label: 'any'},
                             ...f.sats.map((s) => ({value: s, label: s}))], '');
    if (f.date_min) $('#f-start').value = f.date_min;
    if (f.date_max) $('#f-end').value = f.date_max;
  } catch { /* empty index is fine */ }
}

// ==========================================================================
// Explore
// ==========================================================================

export function initExploreTab() {
  $('#btn-search').addEventListener('click', (e) =>
      withBusy(e.target, 'Searching...', runSearch));
  $('#btn-reset').addEventListener('click', () => {
    for (const id of ['f-latmin', 'f-latmax', 'f-lonmin', 'f-lonmax',
                      'f-ltmin', 'f-ltmax']) $(`#${id}`).value = '';
    $('#f-good').checked = state.meta.settings.qc_require_good !== false;
    $('#f-sat').value = '';
    $$('.preset-btn').forEach((b) => b.classList.remove('active'));
    runSearch();
  });
  $('#map-colour').addEventListener('change', drawMap);
  $('#btn-select-page').addEventListener('click', () => {
    state.results.forEach(selectRow);
    renderResults();
  });
  $('#btn-clear-sel').addEventListener('click', () => {
    state.selected.clear();
    renderResults();
  });

  // Quick latitude presets
  $$('.preset-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      $$('.preset-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      $('#f-latmin').value = btn.dataset.latmin !== undefined ? btn.dataset.latmin : '';
      $('#f-latmax').value = btn.dataset.latmax !== undefined ? btn.dataset.latmax : '';
      runSearch();
    });
  });
  ['f-latmin', 'f-latmax'].forEach((id) => {
    const elInput = $(`#${id}`);
    if (elInput) {
      elInput.addEventListener('input', () => {
        $$('.preset-btn').forEach((b) => b.classList.remove('active'));
      });
    }
  });

  refreshFacets();
}

function num(id) {
  const v = $(`#${id}`).value;
  return v === '' ? null : Number(v);
}

function buildSearch(offset = 0) {
  const product = $('#f-product').value;
  const sat = $('#f-sat').value;
  return {
    products: product ? [product] : null,
    start: $('#f-start').value || null,
    end: $('#f-end').value ? `${$('#f-end').value}T23:59:59Z` : null,
    lat_min: num('f-latmin'), lat_max: num('f-latmax'),
    lon_min: num('f-lonmin'), lon_max: num('f-lonmax'),
    local_time_min: num('f-ltmin'), local_time_max: num('f-ltmax'),
    sats: sat ? [sat] : null,
    good_only: $('#f-good').checked,
    sort: 'time', desc: false,
    limit: state.pageSize, offset,
  };
}

export async function runSearch(offset = 0) {
  const req = buildSearch(offset);
  const res = await api.search(req);
  state.lastSearch = req;
  state.results = res.granules;
  state.total = res.total;
  state.offset = res.offset;
  $('#search-note').textContent =
    `${res.total} profiles match. Showing ${res.granules.length}.`;
  renderResults();
  drawMap();
  return res;
}

function renderResults() {
  const tb = $('#results-table').tBodies[0];
  clear(tb);
  if (!state.results.length) {
    tb.append(el('tr', {}, el('td', {colspan: 10, class: 'hint'},
      'No profiles. Download a day on the "Get data" tab, or load the ' +
      'bundled examples.')));
  }
  for (const g of state.results) {
    const box = el('input', {type: 'checkbox'});
    box.checked = isSelected(g.id);
    box.addEventListener('change', () => {
      box.checked ? selectRow(g) : deselectRow(g.id);
      row.classList.toggle('selected', box.checked);
      updateSelCount();
    });
    const row = el('tr', {class: isSelected(g.id) ? 'selected' : ''},
      el('td', {}, box),
      el('td', {}, `${(g.time_utc || '').slice(0, 10)} ${timeOf(g.time_utc)}`),
      el('td', {class: 'num'}, latlon(g.lat, 'lat')),
      el('td', {class: 'num'}, latlon(g.lon, 'lon')),
      el('td', {class: 'num'}, fmt(g.local_time, 1)),
      el('td', {}, g.sat || '-'),
      el('td', {}, g.occ_prn || '-'),
      el('td', {class: 'num'}, String(g.n_levels ?? '-')),
      el('td', {class: 'num'}, fmt(g.alt_max, 1)),
      el('td', {}, el('span', {class: `pill ${g.good ? 'ok' : 'bad'}`},
                      g.good ? 'good' : 'failed')));
    row.addEventListener('dblclick', () => {
      selectRow(g);
      updateSelCount();
      document.dispatchEvent(new CustomEvent('goto-profile'));
    });
    tb.append(row);
  }
  updateSelCount();
  renderPager();
}

function updateSelCount() {
  const n = selectedIds().length;
  $('#sel-count').textContent = `${n} selected`;
  document.dispatchEvent(new CustomEvent('selection-changed'));
}

function renderPager() {
  const box = $('#pager');
  clear(box);
  if (state.total <= state.pageSize) return;
  const pages = Math.ceil(state.total / state.pageSize);
  const current = Math.floor(state.offset / state.pageSize);
  const mk = (label, target, disabled) => {
    const b = el('button', {class: 'ghost', disabled}, label);
    b.addEventListener('click', () => runSearch(target * state.pageSize));
    return b;
  };
  box.append(mk('\u2190 Previous', current - 1, current === 0));
  box.append(el('span', {class: 'hint'}, `page ${current + 1} of ${pages}`));
  box.append(mk('Next \u2192', current + 1, current >= pages - 1));
}

// -------------------------------------------------------------------- map

function drawMap() {
  const rows = state.results.filter((g) => g.lat !== null && g.lon !== null);
  if (!rows.length) {
    emptyPlot('map-plot', 'No located profiles to show.');
    return;
  }
  const key = $('#map-colour').value;
  const colour = rows.map((g) => g[key]);
  const text = rows.map((g) =>
    `${g.file_name}<br>${(g.time_utc || '').slice(0, 19)}Z<br>` +
    `${latlon(g.lat, 'lat')} ${latlon(g.lon, 'lon')}<br>` +
    `local time ${fmt(g.local_time, 1)} h \u00b7 ${g.n_levels} levels`);
  const cyclic = key === 'local_time';
  const isDark = document.documentElement.dataset.theme === 'dark';
  const trace = {
    type: 'scattergeo', mode: 'markers',
    lat: rows.map((g) => g.lat), lon: rows.map((g) => g.lon),
    text, hoverinfo: 'text',
    customdata: rows.map((g) => g.id),
    marker: {
      size: 8, color: colour,
      // Local solar time wraps at midnight, so it needs a cyclic scale;
      // latitude and level count do not.
      colorscale: cyclic ? 'IceFire' : 'Viridis',
      cmin: cyclic ? 0 : undefined, cmax: cyclic ? 24 : undefined,
      colorbar: {
        title: {text: cyclic ? 'local time (h)' : key, side: 'right', font: {size: 11, color: isDark ? '#e2e8f0' : '#1e293b'}},
        tickfont: {size: 10, color: isDark ? '#94a3b8' : '#475569'},
        thickness: 12, len: .75,
      },
      line: {width: 0.8, color: isDark ? 'rgba(255, 255, 255, 0.7)' : '#ffffff'},
      opacity: 0.92,
    },
  };
  const layout = layoutBase({
    margin: {l: 4, r: 4, t: 8, b: 4},
    paper_bgcolor: isDark ? '#0b0f17' : '#ffffff',
    geo: {
      projection: {type: 'equirectangular'},
      showland: true,
      landcolor: isDark ? '#1e293b' : '#f1f5f9',
      showocean: true,
      oceancolor: isDark ? '#0b1329' : '#e0f2fe',
      coastlinecolor: isDark ? '#475569' : '#94a3b8',
      coastlinewidth: 0.8,
      showcountries: true,
      countrycolor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#cbd5e1',
      lataxis: {showgrid: true, gridcolor: isDark ? 'rgba(255, 255, 255, 0.06)' : '#e2e8f0', dtick: 30},
      lonaxis: {showgrid: true, gridcolor: isDark ? 'rgba(255, 255, 255, 0.06)' : '#e2e8f0', dtick: 60},
      bgcolor: isDark ? '#0b0f17' : '#ffffff',
    },
  });
  Plotly.react('map-plot', [trace], layout, PLOT_CONFIG);
  const node = document.getElementById('map-plot');
  // Every redraw re-registers the handlers, so the old ones go first (only
  // the click handler was removed before: each search or colour change
  // added another plotly_selected handler, until Plotly warned of a leak).
  if (node.removeAllListeners) {
    node.removeAllListeners('plotly_click');
    node.removeAllListeners('plotly_selected');
  }
  node.on('plotly_click', (ev) => {
    const id = ev.points[0] && ev.points[0].customdata;
    const row = state.results.find((g) => g.id === id);
    if (!row) return;
    selectRow(row);
    renderResults();
    toast(`Added ${row.file_name} to the selection.`);
  });
  node.on('plotly_selected', (ev) => {
    if (!ev || !ev.points) return;
    for (const p of ev.points) {
      const row = state.results.find((g) => g.id === p.customdata);
      if (row) selectRow(row);
    }
    renderResults();
  });
}
