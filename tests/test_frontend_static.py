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
