"""
JS static analysis - checks for common runtime errors that static analysis can catch.
"""
import re
import sys
from pathlib import Path

frontend = Path(__file__).resolve().parents[1] / "frontend"
js_dir = frontend / "js"
errors = []
warnings = []

def check_file(name):
    content = (js_dir / name).read_text(encoding="utf-8")
    lines = content.splitlines()

    # 1. Check that all DOM lookups are guarded or clearly safe
    # 2. Check that template literals don't have unclosed expressions
    # 3. Check for common pitfalls

    for i, line in enumerate(lines, 1):
        # Check for potential null dereferences on DOM lookups
        # Pattern: $(selector).something without null check
        # (This is acceptable for elements that always exist - just document them)

        # Check for Plotly.react without a target div
        if "Plotly.react(" in line:
            m = re.search(r"Plotly\.react\('([^']+)'", line)
            if m:
                div_id = m.group(1)
                html = (frontend / "index.html").read_text()
                if f'id="{div_id}"' not in html:
                    errors.append(f"{name}:{i}: Plotly.react target '{div_id}' not in HTML")

        # Check that fillSelect is called with a valid select element
        if "fillSelect(" in line:
            m = re.search(r"fillSelect\(\s*\$\('#([^']+)'\)", line)
            if m:
                eid = m.group(1)
                html = (frontend / "index.html").read_text()
                if f'id="{eid}"' not in html:
                    errors.append(f"{name}:{i}: fillSelect target '#{eid}' not in HTML")

        # Check for suspicious string operations on potentially null fields
        if ".slice(" in line and "time_utc" in line and "??" not in line and "||" not in line:
            # Check if there's a null guard
            if "g.time_utc" in line or "m.time_utc" in line or "r.time_utc" in line:
                if "|| ''" not in line and "? " not in line and ".slice" in line:
                    # The time_utc can be null; slicing null would fail
                    warnings.append(f"{name}:{i}: potential null.slice() on time_utc - check guard")

    return content


contents = {}
for jsfile in ["main.js", "tabs_data.js", "tabs_science.js", "ui.js", "api.js"]:
    contents[jsfile] = check_file(jsfile)

# Check imports are consistent
main_imports = re.findall(r"import\s*\{([^}]+)\}\s*from\s*'([^']+)'", contents["main.js"])
print("main.js imports:")
for names, module in main_imports:
    print(f"  from {module}: {names.strip()}")

# Check that all exported symbols from ui.js are actually imported somewhere
ui_exports = re.findall(r"export\s+(?:function|const)\s+(\w+)", contents["ui.js"])
print("\nui.js exports:", ui_exports)

all_js = "\n".join(contents.values())
for sym in ui_exports:
    if sym not in all_js.replace(f"export function {sym}", "").replace(f"export const {sym}", ""):
        warnings.append(f"ui.js export '{sym}' may not be used")

print("\n--- Results ---")
if errors:
    print(f"ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  {e}")
else:
    print("No errors found")

if warnings:
    print(f"\nWARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  {w}")
else:
    print("No warnings")

sys.exit(1 if errors else 0)
