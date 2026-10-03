"""Static checks on the frontend JS that catch common runtime errors early.

- every ``Plotly.react('<id>')`` and ``fillSelect($('#<id>'))`` target exists in index.html
- ``time_utc`` (nullable) is never sliced without a guard
- every symbol exported from ui.js is used somewhere
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "cosmic2" / "frontend"
JS_FILES = ["main.js", "tabs_data.js", "tabs_science.js", "ui.js", "api.js"]


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
