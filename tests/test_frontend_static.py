"""Static checks on the frontend JS that catch common runtime errors early.

- every ``Plotly.react('<id>')`` and ``fillSelect($('#<id>'))`` target exists in index.html
- ``time_utc`` (nullable) is never sliced without a guard
- every symbol exported from ui.js is used somewhere
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "cosmic2" / "frontend"
JS_FILES = ["main.js", "tabs_data.js", "tabs_science.js", "tabs_stats.js", "ui.js", "api.js"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dom_targets_exist_and_nullable_fields_guarded():
    html = _read(FRONTEND / "index.html")
    errors = []
    for name in JS_FILES:
        for i, line in enumerate(_read(FRONTEND / "js" / name).splitlines(), 1):
            m = re.search(r"Plotly\.react\('([^']+)'", line)
            if m and f'id="{m.group(1)}"' not in html:
                errors.append(f"{name}:{i}: Plotly.react target '{m.group(1)}' not in HTML")
            m = re.search(r"fillSelect\(\s*\$\('#([^']+)'\)", line)
            if m and f'id="{m.group(1)}"' not in html:
                errors.append(f"{name}:{i}: fillSelect target '#{m.group(1)}' not in HTML")
            if (".slice(" in line and "time_utc" in line and "??" not in line and "||" not in line
                    and any(v in line for v in ("g.time_utc", "m.time_utc", "r.time_utc"))
                    and "|| ''" not in line and "? " not in line):
                errors.append(f"{name}:{i}: possible null.slice() on time_utc")
    assert not errors, "\n".join(errors)


def test_ui_exports_are_used():
    contents = {name: _read(FRONTEND / "js" / name) for name in JS_FILES}
    exports = re.findall(r"export\s+(?:function|const)\s+(\w+)", contents["ui.js"])
    assert exports, "ui.js exports nothing; did the file move?"
    all_js = "\n".join(contents.values())
    unused = [sym for sym in exports
              if sym not in all_js.replace(f"export function {sym}", "").replace(f"export const {sym}", "")]
    assert not unused, f"ui.js exports never used: {unused}"


def test_science_default_settings_are_applied_to_controls():
    """Settings saved from the drawer must reach the controls they govern."""
    js = _read(FRONTEND / "js" / "main.js")
    body = js[js.index("function applyScienceDefaults"):]
    body = body[:body.index("\n}\n")]
    for key, target in (("qc_require_good", "#f-good"), ("units_temperature", "#p-kelvin"),
                        ("grid_top_km", "#e-top"), ("grid_step_km", "#e-step")):
        assert f"settings.{key}" in body and target in body, key
    assert "applyScienceDefaults(settings)" in js


def test_ui_helpers_used_in_a_module_are_imported_there():
    """A ui.js helper called without being imported is a ReferenceError at
    run time (the profile diagnostics panel died on renderMath this way)."""
    ui = _read(FRONTEND / "js" / "ui.js")
    exports = re.findall(r"export\s+(?:function|const)\s+(\w+)", ui)
    errors = []
    for name in JS_FILES:
        if name == "ui.js":
            continue
        js = _read(FRONTEND / "js" / name)
        m = re.search(r"import\s*\{([^}]*)\}\s*from\s*'\./ui\.js'", js, re.S)
        imported = set(re.findall(r"\w+", m.group(1))) if m else set()
        defined = set(re.findall(r"function\s+(\w+)", js))
        for sym in exports:
            if re.search(rf"(?<![\w.]){sym}\(", js) and sym not in imported | defined:
                errors.append(f"{name}: calls {sym}() without importing it")
    assert not errors, "\n".join(errors)


def test_settings_number_inputs_accept_their_default_values():
    """The browser will not submit a form whose number input holds a value
    off its min/step lattice; the Settings form could not be saved at all
    while the DPI field had min 72, step 10 and default 300."""
    from decimal import Decimal
    js = _read(FRONTEND / "js" / "main.js")
    body = js[js.index("function settingsBody"):]
    bad = []
    for m in re.finditer(r"el\('input', \{type: 'number'(.*?)\}\)", body, re.S):
        attrs = m.group(1)
        step = re.search(r"step: ([^,}\s]+)", attrs)
        lo = re.search(r"min: ([\d.]+)", attrs)
        val = re.search(r"value: [^,}]*?(?:\|\||\?\?)\s*([\d.]+)", attrs)
        if not (step and lo and val) or step.group(1).strip("'\"") == "any":
            continue
        k = (Decimal(val.group(1)) - Decimal(lo.group(1))) / Decimal(step.group(1))
        if k != k.to_integral_value():
            bad.append(attrs.strip()[:60])
    assert not bad, bad


def test_export_handlers_declare_what_they_use():
    """exportData once tested an undeclared ``kind`` (copied from
    exportFigure), so every "Write file" press threw a ReferenceError."""
    src = _read(FRONTEND / "js" / "tabs_science.js")
    for fn in ("exportData", "exportFigure"):
        body = src.split(f"async function {fn}()", 1)[1].split("\n}\n", 1)[0]
        if re.search(r"\bkind\s*===", body):
            assert re.search(r"\b(const|let|var)\s+kind\b", body), fn


def test_fmt_keeps_integer_zeros():
    """fmt(100, 0) returned "1": the trailing-zero trim also ate the zeros
    of an integer.  Runs ui.js under Node when it is installed."""
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    url = (FRONTEND / "js" / "ui.js").resolve().as_uri()
    code = (f"import {{fmt}} from '{url}';"
            "console.log([fmt(100, 0), fmt(2.5, 2), fmt(12, 2), fmt(0, 0),"
            " fmt(1.25, 1), fmt(-40, 0)].join('|'))")
    out = subprocess.run([node, "--input-type=module", "-e", code],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0 and "SyntaxError" in out.stderr:
        pytest.skip("this Node cannot load ES modules from a .js file")
    assert out.stdout.strip() == "100|2.5|12|0|1.3|-40", out.stderr


def test_table_numbers_keep_trailing_zeros():
    """The tropopause table showed 11.7 for 11.70: table columns use fixed(),
    which keeps the decimals.  Runs ui.js under Node when it is installed."""
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    url = (FRONTEND / "js" / "ui.js").resolve().as_uri()
    code = (f"import {{fixed, fmt}} from '{url}';"
            "console.log([fixed(11.7, 2), fixed(194, 1), fixed(100, 0), fixed(null, 2),"
            " fixed(-0.5, 2), fmt(11.7, 2)].join('|'))")
    out = subprocess.run([node, "--input-type=module", "-e", code],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0 and "SyntaxError" in out.stderr:
        pytest.skip("this Node cannot load ES modules from a .js file")
    assert out.stdout.strip() == "11.70|194.0|100|-|-0.50|11.7", out.stderr
    # every number cell of the tropopause table goes through fixed()
    body = _read(FRONTEND / "js" / "tabs_stats.js")
    mean_ci = body[body.index("function meanCI"):body.index("async function drawTropopause")]
    assert "fixed(" in mean_ci and "fmt(" not in mean_ci


def test_no_control_characters_in_frontend_text():
    """A LaTeX \frac written through an unescaped string became a form feed
    plus "rac" in the help page; KaTeX then shows an error."""
    files = [FRONTEND / "index.html", FRONTEND / "help.html",
             *[FRONTEND / "js" / n for n in JS_FILES]]
    for f in files:
        text = _read(f)
        bad = [hex(ord(c)) for c in text if ord(c) < 32 and c not in "\n\r\t"]
        assert not bad, f"{f.name}: {bad[:5]}"


def test_plotly_handlers_are_removed_before_being_added_again():
    """drawMap ran on every search and colour change and added a new
    plotly_selected handler each time (Plotly's MaxListeners warning)."""
    for name in JS_FILES:
        src = _read(FRONTEND / "js" / name)
        for ev in set(re.findall(r"\.on\('(plotly_\w+)'", src)):
            assert f"removeAllListeners('{ev}')" in src, f"{name}: {ev}"


def test_satellite_filter_offers_cosmic2_as_a_whole():
    """With PAZ files on disk every statistic mixed PAZ into COSMIC-2 and the
    filter could not leave it out: COSMIC-2 (its C2E and scintillation LEO
    codes) is one choice once another mission is present."""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    url = (FRONTEND / "js" / "tabs_data.js").resolve().as_uri()
    code = (f"import {{satelliteChoices}} from '{url}';"
            "console.log(JSON.stringify([satelliteChoices(['C2E1', 'C2E2', 'LEO002', 'PAZ1']),"
            " satelliteChoices(['C2E1', 'C2E2'])]))")
    out = subprocess.run([node, "--input-type=module", "-e", code],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0 and "Cannot use import statement" in out.stderr:
        pytest.skip("this Node cannot load ES modules from a .js file")
    assert out.returncode == 0, out.stderr
    mixed, alone = json.loads(out.stdout)
    assert {"value": "C2E1,C2E2,LEO002", "label": "COSMIC-2, all satellites"} in mixed
    assert {"value": "PAZ1", "label": "PAZ (PAZ1)"} in mixed
    assert [o["value"] for o in alone] == ["", "C2E1", "C2E2"]
    # a multi-satellite value reaches the search as a list
    assert "sats: sat ? sat.split(',') : null" in _read(FRONTEND / "js" / "tabs_data.js")


def test_map_shows_the_poles_when_profiles_are_there():
    """The latitude-longitude map was fixed at 60 S - 60 N, which suits
    COSMIC-2 but hid every PAZ or KOMPSAT-5 cell nearer the poles (131 of
    433 PAZ atmPrf profiles of two days lie poleward of 60 degrees)."""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    url = (FRONTEND / "js" / "tabs_stats.js").resolve().as_uri()
    code = (f"import {{mapLatitudeLimit}} from '{url}';"
            "const e10 = Array.from({length: 19}, (_, i) => -90 + 10 * i);"
            "const n10 = (lats) => e10.slice(0, -1).map((lo) => lats.some((x) => x >= lo && x < lo + 10) ? 3 : 0);"
            "const e20 = [-90, -70, -50, -30, -10, 10, 30, 50, 70, 90];"
            "console.log(JSON.stringify(["
            " mapLatitudeLimit({lat_edges: e10, zonal: {n: n10([-44, 0, 45])}}),"
            " mapLatitudeLimit({lat_edges: e10, zonal: {n: n10([-44, 0, 75])}}),"
            " mapLatitudeLimit({lat_edges: e20, zonal: {n: [0, 2, 5, 5, 5, 5, 5, 0, 0]}}),"
            " mapLatitudeLimit({lat_edges: e10, zonal: {n: n10([])}})]))")
    out = subprocess.run([node, "--input-type=module", "-e", code],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0 and "Cannot use import statement" in out.stderr:
        pytest.skip("this Node cannot load ES modules from a .js file")
    assert out.returncode == 0, out.stderr
    # COSMIC-2 only; a PAZ profile at 75 N; a 20-degree band from 70 S to
    # 50 S with profiles (its cells reach past 60 S); nothing at all
    assert json.loads(out.stdout) == [60, 90, 90, 60]
    assert "range: [-ylim, ylim]" in _read(FRONTEND / "js" / "tabs_stats.js")


def test_fmt_writes_powers_of_ten_with_superscripts():
    """Very large and small numbers read "4.12×10^-4" in tables and captions
    (a peak electron density, the sampling card's agreement with CDAAC);
    they go into plain text, so the exponent is now superscript."""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    url = (FRONTEND / "js" / "ui.js").resolve().as_uri()
    code = (f"import {{fmt, fixed}} from '{url}';"
            "console.log(JSON.stringify([fmt(4.12e-4), fmt(1.234e6), fmt(-2.5e-5),"
            " fixed(1e5, 0), fmt(0.5), fmt(99999, 0)]))")
    out = subprocess.run([node, "--input-type=module", "-e", code],
                         capture_output=True, text=True, timeout=60, encoding="utf-8")
    if out.returncode != 0 and "SyntaxError" in out.stderr:
        pytest.skip("this Node cannot load ES modules from a .js file")
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["4.12×10⁻⁴", "1.23×10⁶", "-2.50×10⁻⁵",
                                      "1.00×10⁵", "0.5", "99999"]


def test_scintillation_panel_shows_where_the_peak_was():
    """The diagnostics panel of a scnLv2 file showed its peak S4 but not the
    tangent height of that peak, which tells the E region from the F region,
    and gave the file's position without saying it is the tangent point."""
    js = _read(FRONTEND / "js" / "tabs_science.js")
    assert "['scintillation.s4_max_height_km', 'Tangent height of peak S4', 'km'," in js
    assert "m.product === 'scnLv2' ? ' (tangent point of the S4 maximum)'" in js


def test_get_tab_fetches_a_range_of_days():
    """A "Through" date makes Fetch queue the product for every day of the
    range: daysThrough counts them (across a month end; 0 when the end comes
    first) and the request carries date_end."""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed")
    url = (FRONTEND / "js" / "tabs_data.js").resolve().as_uri()
    code = (f"import {{daysThrough}} from '{url}';"
            "console.log(JSON.stringify([daysThrough('2026-06-01', ''),"
            " daysThrough('2026-06-01', '2026-06-01'), daysThrough('2026-02-27', '2026-03-02'),"
            " daysThrough('2026-06-03', '2026-06-01')]))")
    out = subprocess.run([node, "--input-type=module", "-e", code],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0 and "Cannot use import statement" in out.stderr:
        pytest.skip("this Node cannot load ES modules from a .js file")
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [1, 1, 4, 0]
    js = _read(FRONTEND / "js" / "tabs_data.js")
    assert "if (days > 1) req.date_end = end;" in js
    assert 'id="get-date-end"' in _read(FRONTEND / "index.html")


def test_every_data_term_on_the_page_is_in_the_glossary():
    import re
    from pathlib import Path
    fe = Path(__file__).resolve().parents[1] / "src" / "cosmic2" / "frontend"
    ui = (fe / "js" / "ui.js").read_text(encoding="utf-8")
    block = ui[ui.index("const GLOSSARY = {"):ui.index("};", ui.index("const GLOSSARY = {"))]
    keys = set(re.findall(r"^\s*'?([\w\- ]+?)'?\s*:", block, re.M))
    used = set(re.findall(r'data-term="([^"]+)"', (fe / "index.html").read_text(encoding="utf-8")))
    assert used and not used - keys, used - keys
