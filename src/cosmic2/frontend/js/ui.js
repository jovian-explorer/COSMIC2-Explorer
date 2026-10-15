// Small DOM and formatting helpers, plus the Plotly defaults.

export const $  = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

// ---------------------------------------------------------------- formatting

const SUPERSCRIPT = {'-': '\u207b', 0: '\u2070', 1: '\u00b9', 2: '\u00b2', 3: '\u00b3',
                     4: '\u2074', 5: '\u2075', 6: '\u2076', 7: '\u2077', 8: '\u2078', 9: '\u2079'};

export function fmt(v, digits = 2, trim = true) {
  if (v === null || v === undefined || Number.isNaN(v)) return '-';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v !== 'number') return String(v);
  if (v !== 0 && (Math.abs(v) >= 1e5 || Math.abs(v) < 1e-3)) {
    // 4.12x10 with a superscript -4, not "10^-4": the result goes into plain text
    const [mant, exp] = v.toExponential(2).split('e');
    return `${mant}\u00d710${[...String(Number(exp))].map((c) => SUPERSCRIPT[c]).join('')}`;
  }
  // Trim trailing zeros of the decimals only: with digits = 0 the old
  // pattern also ate the zeros of the integer (fmt(100, 0) gave "1").
  const s = v.toFixed(digits);
  return trim && s.includes('.') ? s.replace(/\.?0+$/, '') : s;
}

/** fmt for table columns: keeps the trailing zeros, so the decimals of a
 *  column line up (11.70, not 11.7). */
export function fixed(v, digits = 2) { return fmt(v, digits, false); }

export function bytes(n) {
  if (!n && n !== 0) return '-';
  const u = ['B', 'kB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n < 10 && i > 0 ? n.toFixed(1) : Math.round(n)} ${u[i]}`;
}

export function clock(seconds) {
  if (!seconds || seconds < 0) return '-';
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export function isoDay(d) { return d.toISOString().slice(0, 10); }

export function timeOf(iso) { return iso ? iso.slice(11, 19) : '-'; }
export function dayOf(iso)  { return iso ? iso.slice(0, 10) : '-'; }

/** Signed degrees to a hemisphere-tagged string. */
export function latlon(v, kind) {
  if (v === null || v === undefined) return '-';
  const h = kind === 'lat' ? (v >= 0 ? 'N' : 'S') : (v >= 0 ? 'E' : 'W');
  return `${Math.abs(v).toFixed(2)}\u00b0${h}`;
}

// ---------------------------------------------------------------- feedback

export function toast(message, kind = '') {
  const node = el('div', {class: `toast ${kind}`, text: message});
  $('#toasts').append(node);
  setTimeout(() => {
    node.style.transition = 'opacity .4s';
    node.style.opacity = '0';
    setTimeout(() => node.remove(), 400);
  }, kind === 'bad' ? 9000 : 4200);
}

export function banner(message, kind = '') {
  const b = $('#banner');
  if (!message) { b.classList.add('hidden'); return; }
  b.className = `banner ${kind}`;
  b.textContent = message;
}

/** Run an async action with a busy button and uniform error reporting. */
export async function withBusy(button, label, fn) {
  const old = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try {
    return await fn();
  } catch (err) {
    toast(err.message || String(err), 'bad');
    return null;
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

/**
 * Render KaTeX math in the target element (or document.body by default).
 * Safely handles synchronous execution and deferred asset loading.
 */
export function renderMath(element) {
  const target = element || document.body;
  if (!target) return;
  const doRender = () => {
    if (typeof window.renderMathInElement === 'function') {
      try {
        window.renderMathInElement(target, {
          delimiters: [
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false},
            {left: '\\[', right: '\\]', display: true},
            {left: '\\(', right: '\\)', display: false}
          ],
          ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option'],
          throwOnError: false
        });
      } catch (err) {
        console.warn('Math rendering warning:', err);
      }
    }
  };
  if (typeof window.renderMathInElement === 'function') {
    doRender();
  } else if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', doRender, { once: true });
    window.addEventListener('load', doRender, { once: true });
  } else {
    setTimeout(doRender, 200);
    setTimeout(doRender, 800);
  }
}

/**
 * Convert LaTeX math expressions and HTML entities to native SVG HTML/Unicode for Plotly.
 * Enables clean subscripts, superscripts, Greek letters, and formulas on figure titles
 * and axis labels without requiring external MathJax.
 */
export function cleanPlotlyMath(str) {
  if (!str || typeof str !== 'string') return str || '';
  let s = str;

  // 1. Decode HTML entities
  const entityMap = {
    '&bull;': ' \u2022 ',
    '&rarr;': ' \u2192 ',
    '&larr;': ' \u2190 ',
    '&harr;': ' \u2194 ',
    '&deg;': '\u00b0',
    '&plusmn;': '\u00b1',
    '&times;': '\u00d7',
    '&middot;': '\u00b7',
    '&le;': '\u2264',
    '&ge;': '\u2265',
    '&ne;': '\u2260',
    '&infin;': '\u221e',
    '&alpha;': '\u03b1', '&beta;': '\u03b2', '&gamma;': '\u03b3',
    '&delta;': '\u03b4', '&epsilon;': '\u03b5', '&theta;': '\u03b8',
    '&lambda;': '\u03bb', '&mu;': '\u03bc', '&pi;': '\u03c0',
    '&rho;': '\u03c1', '&sigma;': '\u03c3', '&tau;': '\u03c4',
    '&phi;': '\u03c6', '&omega;': '\u03c9'
  };
  for (const [ent, rep] of Object.entries(entityMap)) {
    s = s.split(ent).join(rep);
  }

  // 2. LaTeX Greek symbols
  const greekMap = {
    '\\alpha': '\u03b1', '\\beta': '\u03b2', '\\gamma': '\u03b3', '\\Gamma': '\u0393',
    '\\delta': '\u03b4', '\\Delta': '\u0394', '\\epsilon': '\u03b5', '\\varepsilon': '\u03b5',
    '\\zeta': '\u03b6', '\\eta': '\u03b7', '\\theta': '\u03b8', '\\vartheta': '\u03b8', '\\Theta': '\u0398',
    '\\iota': '\u03b9', '\\kappa': '\u03ba', '\\lambda': '\u03bb', '\\Lambda': '\u039b',
    '\\mu': '\u03bc', '\\nu': '\u03bd', '\\xi': '\u03be', '\\Xi': '\u039e',
    '\\pi': '\u03c0', '\\Pi': '\u03a0', '\\varpi': '\u03d6',
    '\\rho': '\u03c1', '\\varrho': '\u03f1', '\\sigma': '\u03c3', '\\Sigma': '\u03a3', '\\varsigma': '\u03c2',
    '\\tau': '\u03c4', '\\upsilon': '\u03c5', '\\Upsilon': '\u03a5',
    '\\phi': '\u03c6', '\\varphi': '\u03c6', '\\Phi': '\u03a6',
    '\\chi': '\u03c7', '\\psi': '\u03c8', '\\Psi': '\u03a8',
    '\\omega': '\u03c9', '\\Omega': '\u03a9'
  };
  for (const [tex, uni] of Object.entries(greekMap)) {
    s = s.replace(new RegExp(tex.replace(/\\/g, '\\\\'), 'g'), uni);
  }

  // 3. LaTeX Math symbols, sizing, and delimiters
  const symMap = {
    '\\partial': '\u2202', '\\nabla': '\u2207', '\\pm': '\u00b1', '\\mp': '\u2213',
    '\\times': '\u00d7', '\\cdot': '\u00b7', '\\approx': '\u2248', '\\sim': '~',
    '\\equiv': '\u2261', '\\neq': '\u2260', '\\leq': '\u2264', '\\le': '\u2264',
    '\\geq': '\u2265', '\\ge': '\u2265', '\\ll': '\u226a', '\\gg': '\u226b',
    '\\int': '\u222b', '\\infty': '\u221e', '\\odot': '\u2299', '\\oplus': '\u2295',
    '\\hbar': '\u0127', '\\circ': '\u00b0', '\\deg': '\u00b0', '\\prime': '\u2032',
    '\\quad': '  ', '\\qquad': '    ', '\\,': ' ', '\\;': ' ', '\\:': ' ', '\\!': '',
    '\\left': '', '\\right': ''
  };
  for (const [tex, uni] of Object.entries(symMap)) {
    s = s.replace(new RegExp(tex.replace(/\\/g, '\\\\'), 'g'), uni);
  }

  // 4. Fractions & Square Roots
  s = s.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, '($1 / $2)');
  s = s.replace(/\\sqrt\{([^}]+)\}/g, '\u221a($1)');
  s = s.replace(/\\sqrt([a-zA-Z0-9])/g, '\u221a$1');

  // 5. Degrees and Primes
  s = s.replace(/\^\{\\circ\}|\^\\circ/g, '\u00b0');
  s = s.replace(/\^\{\\prime\}|\^\\prime|\^\'/g, '\u2032');
  s = s.replace(/\b([a-zA-Z])\'(?!\w)/g, '$1\u2032');

  // 6. Explicit LaTeX text/math wrappers
  s = s.replace(/\\(?:text|mathrm|mathbf|mathit|mathsf|operatorname)\{([^}]+)\}/g, '$1');

  // 7. Explicit braced sub/super: _{...} and ^{...}
  s = s.replace(/_\{([^}]+)\}/g, '<sub>$1</sub>');
  s = s.replace(/\^\{([^}]+)\}/g, '<sup>$1</sup>');

  // 8. Single letter / Greek symbol subscripts: c_s, E_p, N_e, \tau_B (-> \u03c4_B), P_0, T_0, g_0, R_p, C_p, H_p, z_0
  s = s.replace(/(?<![a-zA-Z0-9_\u0370-\u03ff])([a-zA-Z\u0370-\u03ff])_([a-zA-Z0-9]{1,4})(?![a-zA-Z0-9_])/g, '$1<sub>$2</sub>');

  // 9. Caret superscripts: N^2, a^2, r^2, 10^5, m^3, cm^-3, s^-2, rad^2, K^2
  s = s.replace(/(?<![a-zA-Z0-9])([a-zA-Z0-9\u0370-\u03ff]+|\)|\])\^([0-9+-]+)\b/g, '$1<sup>$2</sup>');

  // 10. Slash unit notation: e.g. /s^2 -> /s<sup>2</sup>, /m^3 -> /m<sup>3</sup>
  s = s.replace(/\/([a-zA-Z]+)\^([0-9+-]+)\b/g, '/$1<sup>$2</sup>');

  // 11. Inside math mode $...$: clean remaining sub/superscripts
  s = s.replace(/\$([^$]+)\$/g, (_, inner) => {
    let cleanInner = inner;
    cleanInner = cleanInner.replace(/([a-zA-Z\u0370-\u03ff])_([0-9a-zA-Z])/g, '$1<sub>$2</sub>');
    cleanInner = cleanInner.replace(/([a-zA-Z0-9\u0370-\u03ff])\^([0-9+-]+)/g, '$1<sup>$2</sup>');
    return cleanInner;
  });

  // 12. Strip lingering $ delimiters and backslashes before plain words
  s = s.replace(/\$+/g, '');
  s = s.replace(/\\([a-zA-Z]+)/g, '$1');

  // 13. Normalize whitespace
  s = s.replace(/\s+/g, ' ').trim();
  return s;
}

/**
 * Dynamically relayout all active Plotly plots when universal font scale changes.
 */
export function updatePlotlyFonts() {
  const root = document.documentElement;
  const fontScale = parseFloat(getComputedStyle(root).getPropertyValue('--font-scale') || '1.0');
  const plotIds = [
    'explore-map', 'profile-plot', 'composite-plot', 'scatter-plot',
    'transect-plot', 'histogram-plot'
  ];
  for (const id of plotIds) {
    const el = document.getElementById(id);
    if (el && el.data && window.Plotly && typeof window.Plotly.relayout === 'function') {
      try {
        window.Plotly.relayout(el, {
          'font.size': Math.round(12 * fontScale),
          'title.font.size': Math.round(14 * fontScale),
          'xaxis.title.font.size': Math.round(12 * fontScale),
          'yaxis.title.font.size': Math.round(12 * fontScale),
          'xaxis.tickfont.size': Math.round(10.5 * fontScale),
          'yaxis.tickfont.size': Math.round(10.5 * fontScale),
          'legend.font.size': Math.round(10.5 * fontScale),
        });
      } catch (_) {}
    }
  }
}

let drawerOnClose = null;

/** Open the side drawer; ``onClose`` runs once when it is next closed or replaced. */
export function drawer(title, bodyNode, {onClose = null} = {}) {
  const previous = drawerOnClose;
  drawerOnClose = onClose;
  if (previous) { try { previous(); } catch (err) { console.error(err); } }
  $('#drawer-title').textContent = title;
  const body = $('#drawer-body');
  clear(body);
  body.append(bodyNode);
  renderMath(body);
  $('#drawer').classList.remove('hidden');
}

export function closeDrawer() {
  const cb = drawerOnClose;
  drawerOnClose = null;
  if (cb) { try { cb(); } catch (err) { console.error(err); } }
  $('#drawer').classList.add('hidden');
}

export function fillSelect(select, options, value) {
  clear(select);
  for (const o of options) {
    const opt = typeof o === 'string' ? {value: o, label: o} : o;
    select.append(el('option', {value: opt.value, title: opt.title || GLOSSARY[opt.value] || null},
                     opt.label));
  }
  if (value !== undefined && value !== null) select.value = value;
}

// ---------------------------------------------------------------- plotly

export const PALETTE = [
  '#0284c7', // Luminous Celestial Blue
  '#f97316', // Vibrant Solar Amber
  '#10b981', // Neon Emerald
  '#8b5cf6', // Electric Violet
  '#f43f5e', // Radiant Rose
  '#06b6d4', // Bright Cyan
  '#eab308', // Sun Gold
  '#ec4899', // Nebula Pink
];

export const PLOT_CONFIG = {
  displaylogo: false,
  responsive: true,
  // The bundled basemaps make geo plots work with no network access.
  topojsonURL: 'vendor/topojson/',
  toImageButtonOptions: {format: 'png', scale: 2, filename: 'cosmic2'},
  modeBarButtonsToRemove: ['sendDataToCloud', 'select2d'],
  // the numbers behind every plot, with its caption, for use elsewhere
  modeBarButtonsToAdd: [{
    name: 'Save the plotted numbers as CSV (in the exports folder)',
    icon: globalThis.Plotly ? globalThis.Plotly.Icons.disk : undefined,
    click: (gd) => savePlotCsv(gd),
  }],
};

async function savePlotCsv(gd) {
  const card = gd.closest('.card');
  const head = card && card.querySelector('h2');
  const cap = card && card.querySelector('p.hint[id$="caption"]');
  const title = (gd.layout && gd.layout.title && gd.layout.title.text) || (head ? head.textContent : gd.id);
  const traces = (gd.data || []).filter((t) => t.visible !== false).map((t) => ({
    name: t.name || t.legendgroup || '', x: t.x ? Array.from(t.x) : null,
    y: t.y ? Array.from(t.y) : null, z: t.z ? Array.from(t.z, (r) => Array.from(r)) : null}));
  try {
    const res = await fetch('/api/export/plot-csv', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({title, caption: cap ? cap.textContent : '', traces,
                            basename: gd.id || 'cosmic2_plot'})});
    const out = await res.json();
    if (!res.ok) throw new Error(out.detail || res.statusText);
    toast(`Wrote ${out.filename} (${out.rows} values) to the exports folder.`, 'good');
  } catch (err) {
    toast(`Could not save the plot's numbers: ${err.message}`, 'bad');
  }
}

export function layoutBase(extra = {}) {
  const isDark = document.documentElement.dataset.theme === 'dark';
  const fontScale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale') || '1.0');

  return Object.assign({
    font: {
      family: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      size: Math.round(12 * fontScale),
      color: isDark ? '#e2e8f0' : '#1e293b'
    },
    paper_bgcolor: isDark ? '#0f172a' : '#ffffff',
    plot_bgcolor: isDark ? 'rgba(15, 23, 42, 0.75)' : 'rgba(248, 250, 252, 0.75)',
    margin: {l: 64, r: 24, t: 40, b: 54},
    hovermode: 'closest',
    hoverlabel: {
      bgcolor: isDark ? '#1e293b' : '#ffffff',
      bordercolor: isDark ? '#475569' : '#cbd5e1',
      font: {
        family: 'system-ui, -apple-system, sans-serif',
        size: Math.round(11.5 * fontScale),
        color: isDark ? '#f8fafc' : '#0f172a'
      }
    },
    xaxis: {
      gridcolor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
      zerolinecolor: isDark ? 'rgba(255, 255, 255, 0.2)' : '#94a3b8',
      zeroline: true,
      zerolinewidth: 1.2,
      ticks: 'outside',
      ticklen: 4,
      tickcolor: isDark ? '#475569' : '#94a3b8',
      automargin: true,
      linecolor: isDark ? '#334155' : '#cbd5e1',
      linewidth: 1
    },
    yaxis: {
      gridcolor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
      zerolinecolor: isDark ? 'rgba(255, 255, 255, 0.2)' : '#94a3b8',
      zeroline: true,
      zerolinewidth: 1.2,
      ticks: 'outside',
      ticklen: 4,
      tickcolor: isDark ? '#475569' : '#94a3b8',
      automargin: true,
      linecolor: isDark ? '#334155' : '#cbd5e1',
      linewidth: 1
    },
    legend: {
      bgcolor: isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255, 255, 255, 0.85)',
      bordercolor: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.08)',
      borderwidth: 1,
      font: {size: Math.round(11 * fontScale), color: isDark ? '#e2e8f0' : '#334155'}
    },
  }, extra);
}

export function emptyPlot(nodeId, message) {
  Plotly.purge(nodeId);
  const node = document.getElementById(nodeId);
  clear(node);
  node.append(el('p', {class: 'hint', style: 'padding:34px 6px;text-align:center'},
                 message));
}

// ------------------------------------------------------------- glossary
// One plain-language line per term the screens use without explaining it.
// Elements marked data-term="key" get the line as a tooltip (dotted
// underline), product codes in drop-downs get it too, and the Help drawer
// lists them all.
const GLOSSARY = {
  'radio occultation': 'A satellite watches a navigation (GPS) signal bend as it passes through the air at the horizon; the bending gives the air\'s density, hence temperature and humidity, at each height.',
  occultation: 'One set of measurements as a GPS satellite sets or rises behind the Earth seen from COSMIC-2: one vertical profile.',
  atmPrf: 'Atmospheric profile: bending angle, refractivity and the "dry" temperature and pressure (computed as if the air held no water vapour), up to 80 km.',
  wetPf2: 'Moist profile: temperature, pressure and humidity from CDAAC\'s retrieval that also uses a weather model; the friendliest product to start with.',
  ionPrf: 'Ionospheric profile: the density of free electrons from about 100 km up to the satellite (about 575 km).',
  scnLv2: 'Scintillation: how much the signal flickered (S4) as it crossed irregular patches of the ionosphere; files exist only for flickering signals.',
  ivmL2m: 'In-situ measurements at the satellite itself (about 575 km): ion density, temperature and composition, one day per file.',
  echPrf: 'The European weather model (ECMWF) profile at the same place and time as an occultation, for comparison.',
  avnPrf: 'The US weather model (NCEP) profile at the same place and time as an occultation, for comparison.',
  stream: 'How the archive produced the files: nrt within hours (most days), rapid within days, provisional for the space-weather products.',
  LST: 'Local solar time: the clock time set by the Sun at the profile\'s longitude (noon when the Sun is highest).',
  sat: 'Which of the six COSMIC-2 satellites (C2E1 to C2E6), or another mission such as PAZ.',
  PRN: 'The navigation satellite whose signal was measured: G for GPS, R for GLONASS, E for Galileo, and its number.',
  levels: 'How many heights the profile holds.',
  QC: 'Quality control: whether the archive (CDAAC) marked the retrieval as good or failed.',
  'flagged bad': 'Profiles the archive marked as failed retrievals; the statistics leave them out.',
  'lowest level': 'How far down the profile reaches: low means the signal was tracked close to the ground.',
  tropopause: 'The boundary between the weather layer (troposphere) and the stratosphere above, where temperature stops falling with height: about 16-17 km in the tropics, 8-12 km at higher latitudes.',
  'cold point': 'The coldest level between 10 and 30 km; in the tropics it marks the tropopause.',
  refractivity: 'How much the air slows (and so bends) radio waves, in N-units; it grows with pressure and humidity and falls with temperature.',
  'bending angle': 'How much the atmosphere bent the radio ray; the basic measurement from which everything else is derived.',
  'impact height': 'The height at which a straight ray would have passed: the natural height scale for bending angles.',
  'boundary layer': 'The lowest kilometre or two of the air, stirred by the ground; its top is often marked by a sharp drop in humidity.',
  S4: 'Amplitude scintillation index: how much the signal strength flickered (0 steady, above about 0.4 strong).',
  TEC: 'Total electron content: the number of free electrons in a column of the ionosphere, in TEC units (10^16 per square metre).',
  'F2 peak': 'The height and density of the ionosphere\'s densest layer (hmF2, NmF2); foF2 is the highest radio frequency it reflects.',
  '1D-Var': 'A retrieval that blends the measurement with a weather model\'s first guess, weighting each by how much it is trusted (used for wetPf2).',
  'confidence interval': 'The range that would contain the true mean in 95 of 100 repeats; narrow means the mean is well determined.',
  section: 'Averages of many profiles, latitude band by latitude band and height by height, drawn as a picture of the atmosphere from south to north.',
  'zonal mean': 'The average around the whole Earth at each latitude (all longitudes together).',
  'weather model': 'A computer forecast of the atmosphere (ECMWF in Europe, NCEP in the US); comparing with it shows where the measurement and the model disagree.',
  'three-cornered hat': 'A way to estimate the error of each of three data sets measuring the same thing from how much each pair differs.',
  duct: 'A thin layer, usually the top of a moist boundary layer, that traps radio waves; a radio occultation profile cannot see inside it.',
  radiosonde: 'A weather balloon carrying instruments, launched twice a day at hundreds of stations; the classic reference for upper-air temperature and humidity.',
};

/** Tooltips from GLOSSARY on [data-term] elements (fillSelect gives them to
 *  product codes in drop-downs); also fills #glossary (Help) when present. */
export function explainTerms(root = document) {
  root.querySelectorAll('[data-term]').forEach((n) => {
    const text = GLOSSARY[n.dataset.term];
    if (text) { n.title = text; n.classList.add('term'); }
  });
  const list = root.querySelector('#glossary');
  if (list && !list.childElementCount) {
    for (const [term, text] of Object.entries(GLOSSARY)) {
      list.append(el('dt', {}, term), el('dd', {}, text));
    }
  }
}
