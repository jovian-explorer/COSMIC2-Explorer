// Thin wrapper over the local JSON API, plus the shared client-side state.

async function call(path, {method = 'GET', body = null} = {}) {
  const opts = {method, headers: {}};
  if (body !== null) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (err) {
    throw new Error(`Cannot reach the backend (${err.message}). ` +
                    `Is the application still running?`);
  }
  const text = await res.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = {raw: text}; }
  }
  if (!res.ok) {
    const detail = data && (data.detail || data.error);
    throw new Error(typeof detail === 'string' ? detail
                    : `${res.status} ${res.statusText}`);
  }
  return data;
}

export const api = {
  health:        ()          => call('/api/health'),
  meta:          ()          => call('/api/meta'),
  saveSettings:  (patch)     => call('/api/settings', {method: 'POST', body: patch}),
  updateStatus:  ()          => call('/api/update/status'),
  updateCheck:   ()          => call('/api/update/check', {method: 'POST'}),
  settingsChanges: ()        => call('/api/settings/changes'),
  ackSettingsChanges: (settings) => call('/api/settings/changes/ack', {method: 'POST', body: {settings}}),

  archiveDay:    (date, streams) =>
      call(`/api/archive/day?date=${date}` + (streams ? `&streams=${streams}` : '')),
  archiveLatest: (stream, level, product) =>
      call(`/api/archive/latest?stream=${stream}&level=${level}` +
           (product ? `&product=${product}` : '')),

  download:      (req)       => call('/api/download', {method: 'POST', body: req}),
  jobs:          (activeOnly = false) => call(`/api/jobs?active_only=${activeOnly}`),
  cancelJob:     (id)        => call(`/api/jobs/${id}/cancel`, {method: 'POST'}),
  reindex:       ()          => call('/api/jobs/reindex', {method: 'POST'}),
  loadSamples:   ()          => call('/api/local/load-samples', {method: 'POST'}),
  importFiles:   (paths, product) =>
      call('/api/local/import', {method: 'POST', body: {paths, product}}),
  uploadFile:    async (file) => {
    const res = await fetch(`/api/local/upload-file?filename=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      body: file,
      headers: {'Content-Type': 'application/octet-stream'}
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = {raw: text}; }
    if (!res.ok) {
      const detail = data && (data.detail || data.error);
      throw new Error(typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`);
    }
    return data;
  },

  localSummary:  ()          => call('/api/local/summary'),
  datasets:      ()          => call('/api/local/datasets'),
  deleteDataset: (key)       => call(`/api/local/datasets/${key}`, {method: 'DELETE'}),
  facets:        ()          => call('/api/local/facets'),
  coverage:      (products)  =>
      call('/api/local/coverage' + (products ? `?products=${products}` : '')),

  search:        (req)       => call('/api/profiles/search', {method: 'POST', body: req}),
  profile:       (gid)       => call(`/api/profiles/${gid}`),
  profileData:   (gid, vars, maxPoints = 1200) =>
      call(`/api/profiles/${gid}/data?max_points=${maxPoints}` +
           (vars ? `&vars=${vars}` : '')),
  plotProfiles:  (req)       => call('/api/plot/profiles', {method: 'POST', body: req}),
  composite:     (req)       => call('/api/composite', {method: 'POST', body: req}),
  diagTable:     (req)       => call('/api/diagnostics/table', {method: 'POST', body: req}),
  statsSampling: (req)       => call('/api/stats/sampling', {method: 'POST', body: req}),
  section:       (req)       => call('/api/climatology/section', {method: 'POST', body: req}),
  diagMap:       (req)       => call('/api/climatology/map', {method: 'POST', body: req}),
  coastlines:    ()          => call('/api/coastlines'),
  radiosonde:    (req)       => call('/api/validation/radiosonde', {method: 'POST', body: req}),

  exportData:    (req)       => call('/api/export/data', {method: 'POST', body: req}),
  exportFigure:  (req)       => call('/api/export/figure', {method: 'POST', body: req}),
  exports:       ()          => call('/api/exports'),
  deleteExport:  (name)      => call(`/api/exports/${name}`, {method: 'DELETE'}),
  revealFolder:  (which)     => call(`/api/reveal-folder?which=${which}`),
};

// --------------------------------------------------------------------------
// shared state
// --------------------------------------------------------------------------

export const state = {
  meta: null,             // /api/meta payload
  results: [],            // current search page
  total: 0,
  offset: 0,
  pageSize: 100,
  selected: new Map(),    // granule_id -> row
  lastSearch: null,       // the SearchRequest that produced `results`
  curious: true,
};

export function selectRow(row) { state.selected.set(row.id, row); }
export function deselectRow(id) { state.selected.delete(id); }
export function isSelected(id) { return state.selected.has(id); }
export function selectedIds() { return [...state.selected.keys()]; }

/** The selection if there is one, otherwise the active search. */
export function selectionRequest(selectedOnly) {
  const ids = selectedIds();
  if (selectedOnly) return {granule_ids: ids};
  if (ids.length) return {granule_ids: ids};
  return {search: state.lastSearch || {good_only: true, limit: 2000}};
}

export function vocabInfo(name) {
  const v = state.meta && state.meta.vocabulary[name];
  return v || {name, label: name, units: '', plain: '', role: 'field'};
}

export function axisTitle(name, units) {
  const v = vocabInfo(name);
  const u = units === undefined || units === null ? v.units : units;
  return u && u !== '-' ? `${v.label} [${u}]` : v.label;
}
