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

export function fmt(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '-';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v !== 'number') return String(v);
  if (v !== 0 && (Math.abs(v) >= 1e5 || Math.abs(v) < 1e-3)) {
    return v.toExponential(2).replace('e+', '\u00d710^').replace('e-', '\u00d710^-');
  }
  return v.toFixed(digits).replace(/\.?0+$/, '') || '0';
}

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
    'veda-comparison-plot', 'veda-planet-map', 'veda-observation-plot',
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

export function drawer(title, bodyNode) {
  $('#drawer-title').textContent = title;
  const body = $('#drawer-body');
  clear(body);
  body.append(bodyNode);
  renderMath(body);
  $('#drawer').classList.remove('hidden');
}

export function fillSelect(select, options, value) {
  clear(select);
  for (const o of options) {
    const opt = typeof o === 'string' ? {value: o, label: o} : o;
    select.append(el('option', {value: opt.value, title: opt.title || null},
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
};

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
