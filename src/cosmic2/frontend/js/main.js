// Bootstrap: load metadata, wire tabs, install the help drawer.

import {api, state} from './api.js';
import {$, $$, el, banner, toast, drawer, renderMath, updatePlotlyFonts} from './ui.js';
import {initGetTab, initExploreTab, refreshLocal, refreshFacets,
        runSearch, loadSamples, updateProfileCounter} from './tabs_data.js';
import {initProfileTab, initCompositeTab, initExportTab} from './tabs_science.js';

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
  $$('.tab').forEach((t) =>
      t.addEventListener('click', () => showTab(t.dataset.tab)));
  document.addEventListener('goto-profile', () => showTab('profile'));

  $('#btn-vars-catalog')?.addEventListener('click', () => drawer('Scientific Variable & Algorithm Catalog', variablesCatalogBody()));
  $('#btn-data-policy')?.addEventListener('click', () => drawer('Data Portals, Availability & Licenses', dataPolicyBody()));
  $('#btn-settings').addEventListener('click', () => drawer('Settings', settingsBody()));
  $('#btn-about').addEventListener('click', () => drawer('About', aboutBody()));
  $('#btn-help').addEventListener('click', () => drawer('Help', helpBody()));
  $('#drawer-close').addEventListener('click', () =>
      $('#drawer').classList.add('hidden'));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') $('#drawer').classList.add('hidden');
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
}

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
      units_temperature: $('#s-units-temp').value,
      qc_require_good: $('#s-qc').checked,
      default_stream: $('#s-stream').value
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
      el('input', {type: 'number', id: 's-plot-dpi', value: state.meta.settings.plot_dpi || 300, min: 72, max: 1200, step: 10})
    ),
    el('hr'),
    el('h3', {}, 'Science Defaults'),
    el('label', {}, 'Default Stream ',
      el('select', {id: 's-stream'},
        el('option', {value: 'nrt', selected: state.meta.settings.default_stream === 'nrt'}, 'Near Real-Time (nrt)'),
        el('option', {value: 'postcal', selected: state.meta.settings.default_stream === 'postcal'}, 'Post-Processed (postcal)')
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
    <p><strong>FORMOSAT-7 / COSMIC-2</strong> is a joint collaborative satellite program between Taiwan Space Agency (TASA / NSPO) and the United States (NOAA, USAF). The six-satellite constellation operates in a 24-degree inclination low Earth orbit (~550 km altitude) to continuously monitor the tropical and subtropical atmosphere and ionosphere (30°S to 30°N).</p>
    <p>Using the TriG GNSS Radio Occultation System (TGRS), the constellation retrieves more than 5,000 vertical atmospheric soundings daily from GPS, GLONASS, and Galileo signals.</p>

    <div style="margin: 8px 0; display: flex; gap: 8px; flex-wrap: wrap;">
      <a href="https://www.tasa.org.tw/en-US/mission/formosat-7" target="_blank" rel="noopener" class="link">🌐 TASA FORMOSAT-7 Mission Page ↗</a>
      <a href="https://www.nesdis.noaa.gov/current-satellite-missions/currently-flying/cosmic-2" target="_blank" rel="noopener" class="link">🛰️ NOAA NESDIS COSMIC-2 Overview ↗</a>
      <a href="https://data.cosmic.ucar.edu/" target="_blank" rel="noopener" class="link">🗄️ UCAR CDAAC Data Portal ↗</a>
      <a href="https://www.ncei.noaa.gov/products/cosmic-2" target="_blank" rel="noopener" class="link">📊 NOAA NCEI Archive ↗</a>
    </div>

    <hr/>

    <h3>2. Third-Party Data Policy and Archives</h3>
    <p>COSMIC-2 Explorer accesses open scientific data provided by the University Corporation for Atmospheric Research (UCAR) COSMIC Data Analysis and Archive Center (CDAAC) and NOAA National Centers for Environmental Information (NCEI). The software does not claim ownership of underlying satellite telemetry.</p>
    
    <h4>Mandatory Dual-Attribution for Academic Publications</h4>
    <p>Researchers publishing scientific investigations that utilize data, figures, or products generated with COSMIC-2 Explorer are required to cite both:</p>
    <ol>
      <li>The primary space agency dataset, UCAR CDAAC archive DOI, and mission instruments.</li>
      <li>The COSMIC-2 Explorer software platform.</li>
    </ol>

    <p><strong>BibTeX Citation for COSMIC-2 Explorer:</strong></p>
    <pre style="background: rgba(0,0,0,0.06); padding: 8px; border-radius: 4px; font-size: calc(11px * var(--font-scale, 1.0)); overflow-x: auto;">
@software{Aggarwal_COSMIC2_Explorer_2026,
  author    = {Keshav Aggarwal},
  title     = {{COSMIC-2 Explorer: Atmospheric and Ionospheric GNSS Radio Occultation Scientific Analysis and Visualization Platform}},
  year      = {2026},
  publisher = {Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO},
  version   = {0.0.1},
  url       = {https://jovian-explorer.github.io/},
  address   = {Thiruvananthapuram, Kerala, India}
}</pre>

    <hr/>

    <h3>3. Software License and Open-Source Attributions</h3>
    <p><strong>License:</strong> COSMIC-2 Explorer is open-source software distributed under the <strong>MIT License</strong>. Copyright (c) 2026 Keshav Aggarwal, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), ISRO.</p>
    <p><strong>Third-Party Components:</strong> This application bundles permissive open-source libraries: KaTeX (MIT), Plotly.js (MIT), TopoJSON (BSD-3-Clause), FastAPI (MIT), Starlette (BSD-3-Clause), Pydantic (MIT), Uvicorn (BSD-3-Clause), NumPy (BSD-3-Clause), SciPy (BSD-3-Clause), NetCDF4 (MIT/BSD), Matplotlib (PSF), and PyWebView (BSD-3-Clause). Full license notices are available in the repository documentation.</p>

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
    <p style="font-size: calc(12px * var(--font-scale, 1.0));">Authors using COSMIC-2 Explorer for academic research or publications are requested to include the following Data Availability Statement:</p>
    <blockquote style="background: var(--bg); border-left: 4px solid var(--accent); margin: 6px 0; padding: 8px 12px; font-size: calc(12px * var(--font-scale, 1.0));">
      "The COSMIC-2 radio occultation soundings analyzed in this study are publicly available from the University Corporation for Atmospheric Research (UCAR) COSMIC Data Analysis and Archive Center (CDAAC) at https://data.cosmic.ucar.edu/ and the NOAA National Centers for Environmental Information (NCEI) at https://www.ncei.noaa.gov/data/gps-radio-occultation/. The processing, validation, and profile analysis were conducted using COSMIC-2 Explorer (Version 0.0.1), available open-source at https://github.com/jovian-explorer/COSMIC2-Explorer."
    </blockquote>

    <hr/>

    <h3>2. Authoritative Data Repositories & Archives</h3>
    ${portalsHtml}

    <hr/>

    <h3>3. Mandatory Dual-Attribution Policy</h3>
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
  version      = {0.0.1},
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
  document.title = `${state.meta.app.title} ${state.meta.app.version}`;

  wireChrome();
  initGetTab();
  initExploreTab();
  initProfileTab();
  initCompositeTab();
  initExportTab();
  renderMath(document.body);

  await refreshFacets();
  const summary = await api.localSummary().catch(() => null);
  updateProfileCounter(summary ? summary.n_granules : 0);
  if (summary && summary.n_granules) {
    await runSearch().catch(() => {});
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

boot();
