// Bootstrap: load metadata, wire tabs, install the help drawer.

import {api, state} from './api.js';
import {$, $$, el, banner, toast, drawer, closeDrawer, renderMath, updatePlotlyFonts,
        explainTerms} from './ui.js';
import {initGetTab, initExploreTab, refreshLocal, refreshFacets,
        runSearch, loadSamples, updateProfileCounter} from './tabs_data.js';
import {initProfileTab, initCompositeTab, initExportTab} from './tabs_science.js';
import {initStatsTab} from './tabs_stats.js';

const FONT_SCALES = [0.85, 0.92, 1.0, 1.10, 1.20, 1.32, 1.45];
let currentScaleIdx = 2; // Default 1.0 (100%)

export function applyFontScale(scale) {
  const s = Math.min(Math.max(scale, 0.8), 1.6);
  document.documentElement.style.setProperty('--font-scale', s.toFixed(2));
  const basePx = (state && state.meta && state.meta.settings && state.meta.settings.ui_font_size) || 14;
  document.documentElement.style.fontSize = `${(basePx * s).toFixed(1)}px`;
  document.body.style.fontSize = `${(basePx * s).toFixed(1)}px`;
  const disp = $('#font-scale-display');
  if (disp) disp.textContent = `${Math.round(s * 100)}%`;
  try {
    localStorage.setItem('cosmic2_font_scale', s.toString());
  } catch (_) {}
  updatePlotlyFonts();
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
    updatePlotlyFonts();
  }, 80);
}

function wireFontScaling() {
  const saved = localStorage.getItem('cosmic2_font_scale');
  if (saved) {
    const val = parseFloat(saved);
    if (!Number.isNaN(val) && val >= 0.8 && val <= 1.6) {
      const closest = FONT_SCALES.reduce((prev, curr) =>
        Math.abs(curr - val) < Math.abs(prev - val) ? curr : prev
      );
      currentScaleIdx = FONT_SCALES.indexOf(closest);
      applyFontScale(closest);
    }
  }

  $('#btn-font-dec')?.addEventListener('click', () => {
    if (currentScaleIdx > 0) {
      currentScaleIdx--;
      applyFontScale(FONT_SCALES[currentScaleIdx]);
    }
  });

  $('#btn-font-inc')?.addEventListener('click', () => {
    if (currentScaleIdx < FONT_SCALES.length - 1) {
      currentScaleIdx++;
      applyFontScale(FONT_SCALES[currentScaleIdx]);
    }
  });

  $('#font-scale-display')?.addEventListener('click', () => {
    currentScaleIdx = 2; // 100%
    applyFontScale(FONT_SCALES[currentScaleIdx]);
  });
}

function showTab(name) {
  $$('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  $$('.panel').forEach((p) => p.classList.toggle('active', p.id === `tab-${name}`));
  // Plotly needs a resize once its container becomes visible.
  window.dispatchEvent(new Event('resize'));
  const activePanel = $(`#tab-${name}`);
  if (activePanel) renderMath(activePanel);
}

function wireChrome() {
  wireFontScaling();
  // The header wraps onto two rows on narrower windows; sticky panels below it
  // (the Explore filters) are placed under its real height.
  const topbar = $('.topbar');
  if (topbar && window.ResizeObserver) {
    new ResizeObserver(() => document.documentElement.style.setProperty(
      '--topbar-h', `${topbar.offsetHeight}px`)).observe(topbar);
  }
  $$('.tab').forEach((t) =>
      t.addEventListener('click', () => showTab(t.dataset.tab)));
  document.addEventListener('goto-profile', () => showTab('profile'));

  $('#btn-vars-catalog')?.addEventListener('click', () => drawer('Scientific Variable & Algorithm Catalog', variablesCatalogBody()));
  $('#btn-data-policy')?.addEventListener('click', () => drawer('Data Portals, Availability & Licenses', dataPolicyBody()));
  $('#btn-settings').addEventListener('click', () => drawer('Settings', settingsBody()));
  $('#btn-about').addEventListener('click', () => drawer('About', aboutBody()));
  $('#btn-help').addEventListener('click', () => drawer('Help', helpBody()));
  $('#drawer-close').addEventListener('click', () => closeDrawer());
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('#drawer').classList.contains('hidden')) closeDrawer();
  });

  wireGuideTab();
  wireDragAndDrop();
  applySettings(state.meta.settings);
}

function applySettings(settings) {
  if (settings.ui_theme) {
    document.documentElement.dataset.theme = settings.ui_theme;
  }
  if (settings.ui_font_size) {
    document.documentElement.style.setProperty('--ui-font-size', `${settings.ui_font_size}px`);
  }
  if (settings.ui_mode) {
    document.body.classList.toggle('no-curious', settings.ui_mode === 'research');
  } else if (settings.explain_mode !== undefined) {
    document.body.classList.toggle('no-curious', !settings.explain_mode);
  }
  applyScienceDefaults(settings);
}

/** Science defaults from Settings into the working controls.  These settings
 *  were saved before but nothing read them, so changing them had no effect. */
function applyScienceDefaults(settings) {
  const set = (sel, fn) => { const node = $(sel); if (node) fn(node); };
  if (settings.qc_require_good !== undefined) {
    set('#f-good', (n) => { n.checked = !!settings.qc_require_good; });
  }
  if (settings.units_temperature) {
    set('#p-kelvin', (n) => { n.checked = settings.units_temperature === 'K'; });
  }
  if (settings.grid_top_km) set('#e-top', (n) => { n.value = settings.grid_top_km; });
  if (settings.grid_step_km) set('#e-step', (n) => { n.value = settings.grid_step_km; });
}

const SETTING_LABELS = {
  max_profiles_per_download: 'Most profiles per download', concurrent_downloads: 'Parallel downloads',
  request_timeout_s: 'Download timeout (s)', listing_cache_hours: 'Keep archive listings for (hours)',
  cache_quota_gb: 'Cache quota (GB)', warn_download_mb: 'Warn before downloads larger than (MB)',
  default_stream: 'Default stream', default_product: 'Default product',
  qc_require_good: 'Require Good QC by default', grid_top_km: 'Export grid top (km)',
  grid_step_km: 'Export grid step (km)', analysis_workers: 'CPU workers (0 = automatic)',
  plot_dpi: 'Plot DPI (export)', plot_theme: 'Plot theme', ui_theme: 'Interface theme',
  ui_font_size: 'Base font size (px)', ui_mode: 'Interface mode', units_temperature: 'Temperature units',
  explain_mode: 'Plain-language captions', auto_update: 'Update automatically (weekly)',
};

function ruleText(rule) {
  if (rule == null) return '';
  if (Array.isArray(rule)) return rule.map(String).join(', ');
  if (typeof rule === 'object') return `${rule.min} to ${rule.max}`;
  return String(rule);
}

/** An input for one setting in the after-update panel, from its allowed values. */
function settingControl(key, rule, value) {
  const id = `su-${key}`;
  if (Array.isArray(rule) && rule.length === 2 && rule.every((v) => typeof v === 'boolean')) {
    return el('input', {type: 'checkbox', id, 'data-key': key, 'data-kind': 'bool', checked: value === true});
  }
  if (Array.isArray(rule)) {
    return el('select', {id, 'data-key': key, 'data-kind': 'text'},
      ...rule.map((v) => el('option', {value: String(v), selected: String(v) === String(value)}, String(v))));
  }
  if (rule && typeof rule === 'object') {
    return el('input', {type: 'number', id, 'data-key': key, 'data-kind': 'number', value,
                        min: rule.min, max: rule.max, step: rule.type === 'int' ? 1 : 'any'});
  }
  return el('input', {type: 'text', id, 'data-key': key, 'data-kind': 'text', value: value == null ? '' : String(value)});
}

/** Release notes (Markdown from GitHub) as plain elements: headings, list items, links. */
function notesNode(md) {
  const box = el('div', {class: 'whats-new'});
  let list = null;
  const inline = (text) => {
    const out = [];
    const re = /\[([^\]]+)\]\((https?:[^)\s]+)\)|\*\*([^*]+)\*\*|`([^`]+)`|(https?:\/\/\S+)/g;
    let last = 0;
    let m;
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      if (m[1]) out.push(el('a', {href: m[2], target: '_blank', rel: 'noopener'}, m[1]));
      else if (m[3]) out.push(el('strong', {}, m[3]));
      else if (m[4]) out.push(el('code', {}, m[4]));
      else out.push(el('a', {href: m[5], target: '_blank', rel: 'noopener'}, m[5]));
      last = re.lastIndex;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  };
  for (const raw of String(md || '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) { list = null; continue; }
    const h = line.match(/^#{1,6}\s+(.*)$/);
    if (h) { list = null; box.append(el('h4', {}, ...inline(h[1]))); continue; }
    const li = line.match(/^[-*]\s+(.*)$/);
    if (li) {
      if (!list) { list = el('ul'); box.append(list); }
      list.append(el('li', {}, ...inline(li[1])));
      continue;
    }
    list = null;
    box.append(el('p', {}, ...inline(line)));
  }
  return box;
}

/**
 * Once after an update (or after another version wrote settings.json): what is new
 * in this build and which settings were added, removed or changed, with the stored
 * values kept and editable.  Closing the panel keeps everything as it is.
 */
async function showSettingsChanges() {
  let r;
  try { r = await api.settingsChanges(); } catch (_) { return; }
  if (!r || !r.show) return;
  const c = r.changes || {};
  const label = (k) => SETTING_LABELS[k] || k;
  const fmtVal = (v) => (v === undefined || v === null ? 'none' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const name = (x) => (x && (x.tag || x.version)) || '';
  const body = el('div', {class: 'stack settings-changes', id: 'settings-changes'});
  const prev = name(r.previous);
  body.append(el('p', {}, `This is COSMIC-2 Explorer ${name(r)}${prev && prev !== name(r) ? ` (before: ${prev})` : ''}. ` +
    'Your settings are kept as they were; check the ones listed below.'));
  if (r.whats_new) {
    body.append(el('h3', {}, `What's new in ${r.whats_new.name || r.whats_new.tag}`));
    const b = r.whats_new.behind;
    if (b && b.behind > 1) {
      // The notes below list only the newest release's changes.
      body.append(el('p', {class: 'behind', id: 'whats-new-behind'},
        `You were ${b.behind} releases behind (${b.from} to ${b.to}). `,
        b.compare_url
          ? el('a', {href: b.compare_url, target: '_blank', rel: 'noopener'}, 'Every change since your version, on GitHub')
          : el('a', {href: b.changelog_url, target: '_blank', rel: 'noopener'}, 'All changes, in CHANGELOG.md'),
        '. The notes below are those of the newest release.'));
    }
    body.append(notesNode(r.whats_new.notes));
    if (r.whats_new.url) body.append(el('p', {}, el('a', {href: r.whats_new.url, target: '_blank', rel: 'noopener'}, 'Release page')));
  }
  const rows = [];
  const row = (key, rule, value, note) => {
    const ctl = settingControl(key, rule, value);
    rows.push(ctl);
    if (ctl.dataset.kind === 'bool') {
      return el('label', {class: 'check settings-change'}, ctl, ` ${label(key)}`, el('br'), el('span', {class: 'hint'}, note));
    }
    return el('label', {class: 'settings-change'}, `${label(key)} `, ctl, el('br'), el('span', {class: 'hint'}, note));
  };
  if ((c.new || []).length) {
    body.append(el('h3', {}, 'New settings'),
      ...c.new.map((n) => row(n.key, n.rule, n.default, `New in this version. Default: ${fmtVal(n.default)}` +
        `${n.rule && !Array.isArray(n.rule) ? ` (allowed: ${ruleText(n.rule)})` : ''}.`)));
  }
  const changed = [...(c.changed || []), ...(c.invalid || []).map((x) => ({...x, valid: false}))];
  if (changed.length) {
    body.append(el('h3', {}, 'Changed settings'),
      ...changed.map((x) => row(x.key, x.rule, x.valid ? x.stored : x.default,
        (x.old_rule !== undefined && !same(x.old_rule, x.rule) ? `Allowed values were ${ruleText(x.old_rule)}, now ${ruleText(x.rule)}. ` : '') +
        (x.old_default !== undefined && !same(x.old_default, x.default) ? `Default was ${fmtVal(x.old_default)}, now ${fmtVal(x.default)}. ` : '') +
        (x.valid ? `Your value ${fmtVal(x.stored)} is kept.`
          : x.stored === undefined || x.stored === null ? `The default ${fmtVal(x.default)} is used.`
          : `Your stored value ${fmtVal(x.stored)} is not allowed now (${ruleText(x.rule)}); the default ${fmtVal(x.default)} is used until you choose.`))));
  }
  if ((c.renamed || []).length) {
    body.append(el('h3', {}, 'Renamed settings'),
      el('ul', {}, ...c.renamed.map((x) => el('li', {},
        `${x.old} is now ${label(x.key)}; your value ${fmtVal(x.stored)} ${x.valid ? 'is kept' : 'is not allowed there, the default is used'}.`))));
  }
  if ((c.removed || []).length) {
    body.append(el('h3', {}, 'Settings no longer used'),
      el('ul', {}, ...c.removed.map((x) => el('li', {}, `${x.key} (your value: ${fmtVal(x.stored)})`))));
  }
  let sent = false;
  const send = async (withChoices) => {
    if (sent) return;
    sent = true;
    const patch = {};
    if (withChoices) {
      for (const ctl of rows) {
        const key = ctl.dataset.key;
        if (ctl.dataset.kind === 'bool') patch[key] = ctl.checked;
        else if (ctl.dataset.kind === 'number') patch[key] = Number(ctl.value);
        else patch[key] = ctl.value;
      }
    }
    try {
      const updated = await api.ackSettingsChanges(patch);
      state.meta.settings = updated;
      applySettings(updated);
      if (withChoices) toast('Settings saved');
    } catch (err) {
      sent = false;
      toast(`Could not save the settings: ${err.message}`, 'bad');
      throw err;
    }
  };
  body.append(el('div', {class: 'settings-actions'},
    el('button', {
      class: 'primary', type: 'button', id: 'su-accept',
      onclick: async () => { try { await send(true); closeDrawer(); } catch (_) { /* message shown */ } },
    }, 'Use these settings')),
    el('p', {class: 'hint'}, 'Closing this panel changes nothing: every stored value stays in settings.json, ' +
      'and one this version cannot use is replaced by its default only while the app runs.'));
  drawer(r.whats_new ? 'COSMIC-2 Explorer was updated' : 'Settings changed', body,
         {onClose: () => { send(false).catch(() => {}); }});
}

/** "Check now" for the weekly automatic update, with what it last did. */
function autoUpdateRow() {
  const status = el('span', {class: 'hint', id: 's-update-status'}, '');
  const button = el('button', {type: 'button', class: 'ghost', id: 's-update-now'}, 'Check now');
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : 'never');
  let timer = null;
  const show = (st) => {
    const job = st.job || {};
    const build = st.tag ? `This is build ${st.tag}` + (st.build_date ? ` (${st.build_date})` : '') + '. ' : '';
    let text;
    if (st.problem) text = `Automatic updates are not available: ${st.problem}.`;
    else if (job.running) text = job.total ? `${job.message}: ${Math.round(100 * job.done / job.total)} %` : (job.message || 'Checking...');
    else if (job.error) text = `The last check failed: ${job.error}`;
    else if (st.staged) text = `${st.staged.name || st.staged.tag} is downloaded and will be installed when the app next starts.`;
    else text = (job.message ? `${job.message}. ` : '') + `Last checked: ${when(st.last_check)}.`;
    status.textContent = build + text;
    button.disabled = !!st.problem || !!job.running;
    clearTimeout(timer);
    if (job.running) timer = setTimeout(refresh, 1000);
  };
  const refresh = async () => {
    if (timer && !document.body.contains(status)) return;   // the drawer was closed
    try { show(await api.updateStatus()); } catch (err) { status.textContent = err.message; }
  };
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { show(await api.updateCheck()); } catch (err) { status.textContent = err.message; button.disabled = false; }
  });
  refresh();
  return el('div', {class: 'settings-update-row'}, button, status);
}

// Every number input in this form must accept its own default: the browser
// refuses to submit a form when value is not min + k * step, and the old DPI
// field (min 72, step 10, value 300) silently blocked every Settings save.
function settingsBody() {
  const container = el('div', {class: 'stack'});
  
  const form = el('form', {onsubmit: async (e) => {
    e.preventDefault();
    const patch = {
      ui_theme: $('#s-theme').value,
      ui_font_size: parseInt($('#s-font').value, 10),
      ui_mode: $('#s-mode').value,
      plot_theme: $('#s-plot-theme').value,
      plot_dpi: parseInt($('#s-plot-dpi').value, 10),
      analysis_workers: Math.max(0, parseInt($('#s-workers').value, 10) || 0),
      units_temperature: $('#s-units-temp').value,
      qc_require_good: $('#s-qc').checked,
      grid_top_km: Number($('#s-grid-top').value) || 60,
      grid_step_km: Number($('#s-grid-step').value) || 0.2,
      default_stream: $('#s-stream').value,
      auto_update: $('#s-auto-update').checked,
    };
    try {
      const updated = await api.saveSettings(patch);
      state.meta.settings = updated;
      applySettings(updated);
      toast('Settings saved');
    } catch (err) {
      toast('Error saving settings: ' + err, 'bad');
    }
  }});

  form.append(
    el('label', {}, 'Interface Theme ',
      el('select', {id: 's-theme'},
        el('option', {value: 'light', selected: state.meta.settings.ui_theme === 'light'}, 'Light / Day'),
        el('option', {value: 'dark', selected: state.meta.settings.ui_theme === 'dark'}, 'Dark / Night')
      )
    ),
    el('label', {}, 'Base Font Size (px) ',
      el('input', {type: 'number', id: 's-font', value: state.meta.settings.ui_font_size || 14, min: 10, max: 24})
    ),
    el('label', {}, 'Universal UI Zoom / Scale ',
      el('select', {id: 's-font-scale', onchange: (e) => applyFontScale(parseFloat(e.target.value))},
        el('option', {value: '0.85', selected: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1') * 100) === 85}, 'Compact (85%)'),
        el('option', {value: '0.92', selected: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1') * 100) === 92}, 'Small (92%)'),
        el('option', {value: '1.0', selected: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1') * 100) === 100}, 'Standard (100%)'),
        el('option', {value: '1.10', selected: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1') * 100) === 110}, 'Medium Large (110%)'),
        el('option', {value: '1.20', selected: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1') * 100) === 120}, 'Large (120%)'),
        el('option', {value: '1.32', selected: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1') * 100) === 132}, 'Extra Large (132%)'),
        el('option', {value: '1.45', selected: Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1') * 100) === 145}, 'Maximum Accessibility (145%)')
      )
    ),
    el('label', {}, 'Interface Mode ',
      el('select', {id: 's-mode'},
        el('option', {value: 'educational', selected: state.meta.settings.ui_mode !== 'research'}, 'Educational (More explanations)'),
        el('option', {value: 'research', selected: state.meta.settings.ui_mode === 'research'}, 'Research (Compact interface)')
      )
    ),
    el('hr'),
    el('h3', {}, 'Plot Appearance'),
    el('label', {}, 'Plot Theme ',
      el('select', {id: 's-plot-theme'},
        el('option', {value: 'light', selected: state.meta.settings.plot_theme === 'light'}, 'Light'),
        el('option', {value: 'dark', selected: state.meta.settings.plot_theme === 'dark'}, 'Dark')
      )
    ),
    el('label', {}, 'Plot DPI (Export) ',
      el('input', {type: 'number', id: 's-plot-dpi', value: state.meta.settings.plot_dpi || 300, min: 50, max: 1200, step: 10})
    ),
    el('hr'),
    el('h3', {}, 'Science Defaults'),
    el('label', {}, 'Default Stream ',
      // Built from the archive's own stream list ('postcal' was offered
      // here before, which is not a CDAAC stream).
      el('select', {id: 's-stream'},
        ...Object.entries(state.meta.streams).map(([code, s]) =>
          el('option', {value: code, selected: state.meta.settings.default_stream === code},
             `${s.label} (${code})`))
      )
    ),
    el('label', {}, 'Temperature Units ',
      el('select', {id: 's-units-temp'},
        el('option', {value: 'C', selected: state.meta.settings.units_temperature === 'C'}, 'Celsius (°C)'),
        el('option', {value: 'K', selected: state.meta.settings.units_temperature === 'K'}, 'Kelvin (K)')
      )
    ),
    el('label', {class: 'check'},
      el('input', {type: 'checkbox', id: 's-qc', checked: state.meta.settings.qc_require_good}),
      ' Require Good QC by default'
    ),
    el('label', {}, 'Export grid top (km) ',
      el('input', {type: 'number', id: 's-grid-top', min: 5, step: 5,
                   value: state.meta.settings.grid_top_km || 60})
    ),
    el('label', {}, 'Export grid step (km) ',
      el('input', {type: 'number', id: 's-grid-step', min: 0.01, step: 'any',
                   value: state.meta.settings.grid_step_km || 0.2})
    ),
    el('hr'),
    el('h3', {}, 'Performance'),
    el('label', {}, `CPU workers (0 = automatic; this computer has ${state.meta.cpu_count || '?'} CPUs) `,
      el('input', {type: 'number', id: 's-workers', min: 0,
                   max: state.meta.cpu_count || 64, step: 1,
                   value: state.meta.settings.analysis_workers ?? 0})
    ),
    el('p', {class: 'hint'},
      'Composites, the diagnostics table, regridded exports and indexing read ' +
      'granules on this many processes when the selection is large (24 or more ' +
      'profiles). 1 runs everything in the main process.'),
    el('hr'),
    el('h3', {}, 'Updates'),
    el('label', {class: 'check'},
      el('input', {type: 'checkbox', id: 's-auto-update', checked: state.meta.settings.auto_update !== false}),
      ' Update automatically: look for a new release once a week, download it in the ' +
      'background and install it when the app next starts'
    ),
    autoUpdateRow(),
    el('p', {class: 'hint'},
      'Only the app folder is replaced. Your downloads, exports, index and settings are ' +
      'kept in the data folder, which an update never touches.'),
    el('hr'),
    el('button', {class: 'primary', type: 'submit'}, 'Save Settings')
  );

  container.append(form);
  return container;
}

function helpBody() {
  const container = el('div', {class: 'stack'});
  container.innerHTML = '<p>Loading guidebook...</p>';
  fetch('/help.html')
    .then(r => r.text())
    .then(html => {
      container.innerHTML = html;
      renderMath(container);
      explainTerms(container);
    })
    .catch(err => {
      container.innerHTML = `<p class="error">Failed to load help: ${err}</p>`;
    });
  return container;
}

function aboutBody() {
  const container = el('div', {class: 'stack'});
  container.innerHTML = `
    <h2>About COSMIC-2 Explorer</h2>
    <p>COSMIC-2 Explorer is an open-source, interactive desktop scientific analysis and visualization platform dedicated to processing, exploring, and analyzing Global Navigation Satellite System (GNSS) Radio Occultation (RO) soundings from the FORMOSAT-7 / COSMIC-2 constellation.</p>

    <h3>1. Mission Overview</h3>
    <p><strong>FORMOSAT-7 / COSMIC-2</strong> is a joint collaborative satellite program between Taiwan Space Agency (TASA / NSPO) and the United States (NOAA, USAF). The six satellites fly in low Earth orbits inclined at 24 degrees (~550 km altitude) and sample the atmosphere and ionosphere between about 45°S and 45°N, most densely in the tropics.</p>
    <p>Using the TriG GNSS Radio Occultation System (TGRS), which tracks GPS and GLONASS signals, the constellation yields several thousand neutral-atmosphere profiles a day. UCAR CDAAC turns the measurements into the profiles this app reads; COSMIC-2 Explorer computes its diagnostics from those profiles.</p>

    <div style="margin: 8px 0; display: flex; gap: 8px; flex-wrap: wrap;">
      <a href="https://www.tasa.org.tw/en-US/mission/formosat-7" target="_blank" rel="noopener" class="link">🌐 TASA FORMOSAT-7 Mission Page ↗</a>
      <a href="https://www.nesdis.noaa.gov/current-satellite-missions/currently-flying/cosmic-2" target="_blank" rel="noopener" class="link">🛰️ NOAA NESDIS COSMIC-2 Overview ↗</a>
      <a href="https://data.cosmic.ucar.edu/" target="_blank" rel="noopener" class="link">🗄️ UCAR CDAAC Data Portal ↗</a>
      <a href="https://www.ncei.noaa.gov/products/cosmic-2" target="_blank" rel="noopener" class="link">📊 NOAA NCEI Archive ↗</a>
    </div>

    <hr/>

    <h3>2. Third-Party Data Policy and Archives</h3>
    <p>COSMIC-2 Explorer accesses open scientific data provided by the University Corporation for Atmospheric Research (UCAR) COSMIC Data Analysis and Archive Center (CDAAC) and NOAA National Centers for Environmental Information (NCEI). The software does not claim ownership of underlying satellite telemetry.</p>
    
    <h4>Suggested Citations for Publications</h4>
    <p>Researchers publishing work that uses data, figures, or products generated with COSMIC-2 Explorer are asked to cite both:</p>
    <ol>
      <li>The UCAR CDAAC data set, as UCAR asks (doi:10.5065/T353-C093).</li>
      <li>The COSMIC-2 Explorer software platform.</li>
    </ol>

    <p><strong>BibTeX Citation for COSMIC-2 Explorer:</strong></p>
    <pre style="background: rgba(0,0,0,0.06); padding: 8px; border-radius: 4px; font-size: calc(11px * var(--font-scale, 1.0)); overflow-x: auto;">
@software{Aggarwal_COSMIC2_Explorer_2026,
  author    = {Keshav Aggarwal},
  title     = {{COSMIC-2 Explorer: Atmospheric and Ionospheric GNSS Radio Occultation Scientific Analysis and Visualization Platform}},
  year      = {2026},
  publisher = {Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO},
  version   = {${state.meta.app.version}},
  url       = {https://jovian-explorer.github.io/},
  address   = {Thiruvananthapuram, Kerala, India}
}</pre>

    <hr/>

    <h3>3. Software License and Open-Source Attributions</h3>
    <p><strong>License:</strong> COSMIC-2 Explorer is open-source software distributed under the <strong>MIT License</strong>. Copyright (c) 2026 Keshav Aggarwal, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO.</p>
    <p><strong>Third-Party Components:</strong> This application bundles permissive open-source libraries: KaTeX (MIT), Plotly.js (MIT), TopoJSON (BSD-3-Clause), FastAPI (MIT), Starlette (BSD-3-Clause), Pydantic (MIT), Uvicorn (BSD-3-Clause), NumPy (BSD-3-Clause), SciPy (BSD-3-Clause), pandas (BSD-3-Clause), NetCDF4 (MIT), Matplotlib (PSF-based Matplotlib License), Requests (Apache-2.0), and PyWebView (BSD-3-Clause). Full license notices are available in the repository documentation.</p>

    <hr/>

    <h3>4. Lead Researcher and Developer</h3>
    <p><strong>Keshav Aggarwal</strong></p>
    <p>Research Associate, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India.</p>
    <p>Former Prime Minister's Research Fellow (PMRF Scholar), Department of Astronomy, Astrophysics and Space Engineering (DAASE), Indian Institute of Technology (IIT) Indore.</p>
    <p>Research Specialization: Radio Occultation, Space Physics, Solar Wind Velocity and Turbulence, Coronal Electron Density, and Planetary Atmospheric and Ionospheric Structure.</p>
    <p><a href="https://jovian-explorer.github.io/" target="_blank" rel="noopener">🌐 Visit Researcher Website ↗</a></p>
  `;
  renderMath(container);
  return container;
}

function variablesCatalogBody() {
  const container = el('div', {class: 'stack'});
  const vocab = state.meta?.vocabulary || {};
  const keys = Object.keys(vocab);
  
  let cardsHtml = '';
  keys.forEach(k => {
    const v = vocab[k];
    const formulaHtml = v.formula ? `<div class="guide-formula-box" style="margin: 6px 0; padding: 6px 10px; background: var(--bg); border: 1px solid var(--line); border-radius: 4px;">$$${v.formula}$$</div>` : '';
    const doiLink = v.doi ? `<a href="https://doi.org/${v.doi}" target="_blank" rel="noopener" class="link">DOI: ${v.doi} ↗</a>` : '';
    const archiveLink = v.archive_url ? `<a href="${v.archive_url}" target="_blank" rel="noopener" class="link">CDAAC Archive ↗</a>` : '';
    const refHtml = v.reference ? `<p style="font-size: calc(11px * var(--font-scale, 1.0)); color: var(--text-muted); margin: 4px 0;"><strong>Reference:</strong> ${v.reference} ${doiLink}</p>` : '';
    const algoHtml = v.algorithm ? `<p style="font-size: calc(11px * var(--font-scale, 1.0)); margin: 4px 0;"><strong>Algorithm:</strong> ${v.algorithm}</p>` : '';
    const levelBadge = v.data_level ? `<span class="badge-pill" style="font-size: calc(10px * var(--font-scale, 1.0)); padding: 2px 6px;">${v.data_level}</span>` : '';

    cardsHtml += `
      <div class="card" style="margin-bottom: 10px; padding: 12px; background: var(--bg); border: 1px solid var(--line);">
        <div style="display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 6px;">
          <div>
            <strong style="font-size: calc(14px * var(--font-scale, 1.0)); color: var(--accent);">${v.label || k}</strong>
            <code style="margin-left: 6px; font-size: calc(11px * var(--font-scale, 1.0));">${k}</code>
            ${v.units && v.units !== '-' ? `<span style="margin-left: 6px; font-size: calc(11px * var(--font-scale, 1.0)); color: var(--text-muted);">[${v.units}]</span>` : ''}
          </div>
          <div>${levelBadge}</div>
        </div>
        <p style="font-size: calc(12px * var(--font-scale, 1.0)); margin: 6px 0;">${v.plain || ''}</p>
        ${formulaHtml}
        ${algoHtml}
        ${refHtml}
        <div style="margin-top: 6px; display: flex; gap: 10px; font-size: calc(11px * var(--font-scale, 1.0));">
          ${archiveLink}
        </div>
      </div>
    `;
  });

  container.innerHTML = `
    <h2>Scientific Variable & Algorithm Catalog</h2>
    <p>Comprehensive physical formulas, definitions, academic citations, DOIs, and processing methods for all measurements and derived quantities:</p>
    <div style="margin-top: 12px;">
      ${cardsHtml}
    </div>
  `;
  renderMath(container);
  return container;
}

function dataPolicyBody() {
  const container = el('div', {class: 'stack'});
  const portals = state.meta?.data_portals || [];
  let portalsHtml = '';
  portals.forEach(p => {
    portalsHtml += `
      <div class="card" style="margin-bottom: 8px; padding: 10px; background: var(--bg); border: 1px solid var(--line);">
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
          <strong style="font-size: calc(13px * var(--font-scale, 1.0));">${p.name}</strong>
          <span class="badge-pill" style="font-size: calc(10px * var(--font-scale, 1.0));">${p.agency}</span>
        </div>
        <p style="font-size: calc(11px * var(--font-scale, 1.0)); margin: 4px 0;">${p.description}</p>
        <div style="margin-top: 4px; display: flex; gap: 8px;">
          <a href="${p.url}" target="_blank" rel="noopener" class="link" style="font-size: calc(11px * var(--font-scale, 1.0));">Data Endpoint ↗</a>
          <a href="${p.portal_url}" target="_blank" rel="noopener" class="link" style="font-size: calc(11px * var(--font-scale, 1.0));">Official Portal ↗</a>
        </div>
      </div>
    `;
  });

  container.innerHTML = `
    <h2>Authoritative Data Portals, Availability & Licenses</h2>

    <h3>1. Data Availability Statement</h3>
    <p style="font-size: calc(12px * var(--font-scale, 1.0));">Authors using COSMIC-2 Explorer for academic research or publications may adapt the following Data Availability Statement:</p>
    <blockquote style="background: var(--bg); border-left: 4px solid var(--accent); margin: 6px 0; padding: 8px 12px; font-size: calc(12px * var(--font-scale, 1.0));">
      "The COSMIC-2 radio occultation soundings analyzed in this study are publicly available from the University Corporation for Atmospheric Research (UCAR) COSMIC Data Analysis and Archive Center (CDAAC) at https://data.cosmic.ucar.edu/ and the NOAA National Centers for Environmental Information (NCEI) at https://www.ncei.noaa.gov/data/gps-radio-occultation/. The profile analysis was conducted using COSMIC-2 Explorer (Version ${state.meta.app.version}), https://github.com/jovian-explorer/COSMIC2-Explorer."
    </blockquote>

    <hr/>

    <h3>2. Authoritative Data Repositories & Archives</h3>
    ${portalsHtml}

    <hr/>

    <h3>3. Suggested Citations</h3>
    <p style="font-size: calc(12px * var(--font-scale, 1.0));">Please cite both the primary UCAR CDAAC dataset and the COSMIC-2 Explorer software environment in publications:</p>
    
    <div style="margin-bottom: 8px;">
      <strong>UCAR CDAAC Dataset:</strong>
      <pre style="background: var(--bg); padding: 6px; border-radius: 4px; font-size: calc(10px * var(--font-scale, 1.0)); overflow-x: auto; border: 1px solid var(--line);">
@misc{UCAR_COSMIC2_2019,
  author    = {{UCAR COSMIC Program}},
  title     = {{COSMIC-2 Data Products [Data set]}},
  year      = {2019},
  publisher = {UCAR/NCAR - COSMIC Data Analysis and Archive Center},
  doi       = {10.5065/T353-C093},
  url       = {https://doi.org/10.5065/T353-C093}
}</pre>
    </div>

    <div>
      <strong>COSMIC-2 Explorer Platform:</strong>
      <pre style="background: var(--bg); padding: 6px; border-radius: 4px; font-size: calc(10px * var(--font-scale, 1.0)); overflow-x: auto; border: 1px solid var(--line);">
@software{Aggarwal_COSMIC2_Explorer_2026,
  author       = {Keshav Aggarwal},
  title        = {{COSMIC-2 Explorer: High-Resolution Radio Occultation Processing, Visualisation, and Atmospheric Profiling System}},
  year         = {2026},
  version      = {${state.meta.app.version}},
  institution  = {Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO},
  address      = {Thiruvananthapuram, Kerala, India},
  url          = {https://github.com/jovian-explorer/COSMIC2-Explorer}
}</pre>
    </div>

    <hr/>

    <h3>4. Software Licensing (MIT)</h3>
    <p style="font-size: calc(12px * var(--font-scale, 1.0));">
      COSMIC-2 Explorer is free and open-source software distributed under the <strong>MIT License</strong>. Copyright &copy; 2026 <strong>Keshav Aggarwal</strong>, Research Associate at Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram, Kerala, India (Former PMRF Scholar at DAASE, IIT Indore).
    </p>
  `;
  renderMath(container);
  return container;
}

function wireGuideTab() {
  const triggerLoadSamples = async (btn) => {
    try {
      await loadSamples(btn);
      showTab('explore');
    } catch (err) {
      toast('Error loading sample granules: ' + err.message, 'bad');
    }
  };

  $('#guide-hero-btn-samples')?.addEventListener('click', (e) => triggerLoadSamples(e.target));
  $('#guide-btn-load-samples')?.addEventListener('click', (e) => triggerLoadSamples(e.target));
  $('#guide-btn-goto-get')?.addEventListener('click', () => showTab('get'));
  $('#guide-btn-goto-explore')?.addEventListener('click', () => showTab('explore'));
  $('#guide-btn-goto-profile')?.addEventListener('click', () => showTab('profile'));
  $('#guide-btn-goto-pipeline')?.addEventListener('click', () => showTab('profile'));
  $('#guide-btn-goto-composite')?.addEventListener('click', () => showTab('composite'));
  $('#guide-btn-goto-stats')?.addEventListener('click', () => showTab('stats'));
  $('#guide-btn-goto-export')?.addEventListener('click', () => showTab('export'));
}

function wireDragAndDrop() {
  const overlay = $('#drop-overlay');
  let dragCounter = 0;

  window.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    if (overlay) overlay.classList.remove('hidden');
  });

  window.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy';
    }
  });

  window.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter <= 0) {
      dragCounter = 0;
      if (overlay) overlay.classList.add('hidden');
    }
  });

  window.addEventListener('drop', async (e) => {
    e.preventDefault();
    dragCounter = 0;
    if (overlay) overlay.classList.add('hidden');

    const dt = e.dataTransfer;
    if (!dt || !dt.files || !dt.files.length) return;

    const allFiles = Array.from(dt.files);
    const ncFiles = allFiles.filter((f) => f.name.endsWith('.nc') || f.name.endsWith('_nc'));

    if (!ncFiles.length) {
      toast('Please drop valid NetCDF files (*.nc or *_nc).', 'bad');
      return;
    }

    toast(`Ingesting ${ncFiles.length} NetCDF ${ncFiles.length === 1 ? 'file' : 'files'}...`);

    try {
      const paths = ncFiles.map((f) => f.path).filter(Boolean);
      let indexedTotal = 0;
      if (paths.length === ncFiles.length) {
        const res = await api.importFiles(paths);
        indexedTotal = res.indexed || 0;
      } else {
        for (const file of ncFiles) {
          const res = await api.uploadFile(file);
          if (res && res.indexed) {
            indexedTotal += res.indexed;
          }
        }
      }

      toast(`Successfully ingested and indexed ${indexedTotal} ${indexedTotal === 1 ? 'granule' : 'granules'}.`, 'good');
      await refreshLocal();
      await refreshFacets();
      await runSearch();
      showTab('explore');
    } catch (err) {
      toast(`Ingestion error: ${err.message}`, 'bad');
    }
  });
}

async function boot() {
  try {
    state.meta = await api.meta();
  } catch (err) {
    banner(`Could not reach the backend: ${err.message}`, 'bad');
    return;
  }
  $('#version-tag').textContent = `v${state.meta.app.version}`;
  // Citations in the tutorial quote the running version, not a hard-coded one.
  $$('.app-version').forEach((n) => { n.textContent = state.meta.app.version; });
  document.title = `${state.meta.app.title} ${state.meta.app.version}`;

  wireChrome();
  initGetTab();
  initExploreTab();
  initProfileTab();
  initCompositeTab();
  initStatsTab();
  initExportTab();
  renderMath(document.body);
  showSettingsChanges();

  await refreshFacets();
  explainTerms();
  const summary = await api.localSummary().catch(() => null);
  updateProfileCounter(summary ? summary.n_granules : 0);
  if (summary && summary.n_granules) {
    await runSearch().catch(() => {});
  } else if (firstStart()) {
    // Something real to look at straight away: the bundled example day
    await loadSamples().catch(() => {});
    banner('Showing the example files that come with the app (real COSMIC-2 ' +
           'profiles of 19 July 2026). Pick a profile on the map or in the table, or ' +
           'download any other day on the "Get data" tab.');
  } else {
    banner('No profiles on this computer yet. Pick a date and fetch some on the ' +
           '"Get data" tab, or load the bundled examples to try things out.');
  }
  if (summary && summary.cache_quota_bytes &&
      summary.cache_bytes_on_disk > 0.9 * summary.cache_quota_bytes) {
    banner('The local cache is nearly at its quota. Delete a dataset or raise ' +
           'the quota before downloading more.', 'bad');
  }
}

/** True only the first time the app opens on this computer (the examples
 *  are loaded once, not again after the user has cleared the data). */
function firstStart() {
  try {
    if (localStorage.getItem('cosmic2-started')) return false;
    localStorage.setItem('cosmic2-started', '1');
  } catch (err) { /* no storage: treat as a first start */ }
  return true;
}

boot();
