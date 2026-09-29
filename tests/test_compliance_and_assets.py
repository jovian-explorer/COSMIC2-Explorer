"""Compliance, documentation, typography, and offline assets integrity tests."""
from __future__ import annotations

import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_zero_em_en_dashes():
    """Verify strictly zero em-dashes and en-dashes across all source files."""
    bad_chars = ["\u2014", "\u2013", "&mdash;", "&ndash;"]
    violating_lines = []

    ignored_dirs = {
        ".git", "__pycache__", ".pytest_cache", "dist",
        "vendor", ".orchestrator", "_devhome", ".idea", ".vscode"
    }

    scanned_exts = {".py", ".html", ".js", ".css", ".md", ".json", ".spec", ".ini", ".ps1"}

    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs]
        for fname in filenames:
            if fname == "test_compliance_and_assets.py":
                continue
            ext = Path(fname).suffix.lower()
            if ext in scanned_exts:
                file_path = Path(dirpath) / fname
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
                        for line_idx, line in enumerate(fh, 1):
                            for bad in bad_chars:
                                if bad in line:
                                    violating_lines.append(
                                        f"{file_path.relative_to(ROOT)}:{line_idx} - {line.strip()}"
                                    )
                except Exception as err:
                    pytest.fail(f"Could not read {file_path}: {err}")

    assert not violating_lines, (
        f"Found {len(violating_lines)} occurrences of em/en dashes:\n"
        + "\n".join(violating_lines[:20])
    )


def test_license_and_documentation_present():
    """Verify all mandatory licensing and data availability documents exist and are populated."""
    mandatory_files = [
        "LICENSE",
        "DATA_POLICY.md",
        "THIRD_PARTY_LICENSES.md",
        "README.md",
        "STATUS.md",
    ]
    for rel_path in mandatory_files:
        p = ROOT / rel_path
        assert p.is_file(), f"Mandatory file missing: {rel_path}"
        assert p.stat().st_size > 100, f"File {rel_path} is unexpectedly small or empty"


def test_author_affiliation():
    """Verify lead researcher name and ISRO/VSSC/SPL affiliation are consistently documented."""
    docs_to_check = [
        ROOT / "LICENSE",
        ROOT / "DATA_POLICY.md",
        ROOT / "README.md",
        ROOT / "STATUS.md",
        ROOT / "frontend" / "js" / "main.js",
    ]
    for p in docs_to_check:
        assert p.is_file(), f"Document missing: {p}"
        content = p.read_text(encoding="utf-8")
        assert "Keshav Aggarwal" in content, f"Lead researcher name missing in {p.name}"
        assert ("Space Physics Laboratory" in content or "SPL" in content), f"SPL affiliation missing in {p.name}"
        assert ("Vikram Sarabhai Space Centre" in content or "VSSC" in content), f"VSSC affiliation missing in {p.name}"
        assert "ISRO" in content, f"ISRO affiliation missing in {p.name}"


def test_katex_offline_assets_integrity():
    """Verify that KaTeX scripts, styles, and font binaries are available locally without CDNs."""
    katex_dir = ROOT / "frontend" / "vendor" / "katex"
    assert katex_dir.is_dir(), "frontend/vendor/katex directory missing"
    assert (katex_dir / "katex.min.js").is_file(), "katex.min.js missing"
    assert (katex_dir / "katex.min.css").is_file(), "katex.min.css missing"
    assert (katex_dir / "contrib" / "auto-render.min.js").is_file(), "auto-render.min.js missing"
    
    fonts_dir = katex_dir / "fonts"
    assert fonts_dir.is_dir(), "katex fonts directory missing"
    fonts = list(fonts_dir.glob("*.woff2"))
    assert len(fonts) >= 15, f"Expected at least 15 woff2 font files, found {len(fonts)}"


def test_logo_and_icons_integrity():
    """Verify all mission logos and icon formats exist and are non-empty."""
    icon_assets = [
        ROOT / "frontend" / "assets" / "cosmic2_logo.png",
        ROOT / "frontend" / "assets" / "cosmic2_icon.png",
        ROOT / "frontend" / "assets" / "cosmic2.ico",
        ROOT / "build" / "cosmic2.ico",
        ROOT / "dist" / "cosmic2.ico",
    ]
    for asset in icon_assets:
        assert asset.is_file(), f"Visual asset missing: {asset}"
        assert asset.stat().st_size > 1000, f"Visual asset appears corrupt or empty: {asset}"


def test_veda_package_structure():
    """Verify all VEDA packages and subpackages have __init__.py files for PyInstaller."""
    subpkgs = ["analysis", "api", "core", "missions", "readers"]
    assert (ROOT / "backend" / "veda" / "__init__.py").is_file(), "backend/veda/__init__.py missing"
    for sub in subpkgs:
        init_file = ROOT / "backend" / "veda" / sub / "__init__.py"
        assert init_file.is_file(), f"Missing __init__.py in backend/veda/{sub}"


def test_tutorial_guide_and_ui_features():
    """Verify presence and structure of Tutorial Guide, presets, counter badge, and dropzone."""
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    # 1. Tutorial Guide tab button and panel
    assert 'data-tab="guide"' in index_html, "Missing Tutorial Guide tab button"
    assert 'Tutorial Guide' in index_html, "Missing Tutorial Guide button text"
    assert 'id="tab-guide"' in index_html, "Missing tab-guide panel section"

    # Verify 6 steps in Tutorial Guide
    for step_num in range(1, 7):
        assert f"Step {step_num}" in index_html, f"Missing Step {step_num} in Tutorial Guide"

    # Verify interactive action buttons
    guide_buttons = [
        "guide-btn-load-samples",
        "guide-btn-goto-explore",
        "guide-btn-goto-profile",
        "guide-btn-goto-composite",
        "guide-btn-goto-export",
    ]
    for btn_id in guide_buttons:
        assert f'id="{btn_id}"' in index_html, f"Missing guide button: {btn_id}"

    # 2. Quick Latitude Filter Presets
    assert 'id="lat-presets"' in index_html, "Missing lat-presets container"
    assert "All Tropics (30&deg;S - 30&deg;N)" in index_html, "Missing All Tropics preset"
    assert "Equatorial (10&deg;S - 10&deg;N)" in index_html, "Missing Equatorial preset"
    assert "Northern Tropics (0&deg; - 30&deg;N)" in index_html, "Missing Northern Tropics preset"
    assert "Southern Tropics (30&deg;S - 0&deg;)" in index_html, "Missing Southern Tropics preset"
    assert "Global/All" in index_html, "Missing Global/All preset"

    # 3. Topbar Profile Counter Badge
    assert 'id="granule-count-badge"' in index_html, "Missing granule-count-badge in topbar"

    # 4. Drag-and-drop NetCDF ingestion overlay
    assert 'id="drop-overlay"' in index_html, "Missing drop-overlay in index.html"


def test_universal_font_scaling_controls():
    """Verify Universal UI Font Size Zoom Controller in index.html and app.css."""
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    app_css = (ROOT / "frontend" / "css" / "app.css").read_text(encoding="utf-8")
    main_js = (ROOT / "frontend" / "js" / "main.js").read_text(encoding="utf-8")

    # 1. HTML Controls exist
    assert 'class="font-zoom-ctrl"' in index_html, "Missing font-zoom-ctrl in index.html"
    assert 'id="btn-font-dec"' in index_html, "Missing btn-font-dec button in index.html"
    assert 'id="font-scale-display"' in index_html, "Missing font-scale-display in index.html"
    assert 'id="btn-font-inc"' in index_html, "Missing btn-font-inc button in index.html"

    # 2. CSS font scale variable and rules
    assert "--font-scale" in app_css, "Missing --font-scale in app.css"
    assert ".font-zoom-ctrl" in app_css, "Missing .font-zoom-ctrl in app.css"
    assert "calc(" in app_css, "CSS does not use calc() for scalable font sizing"

    # 3. JS handler implementation
    assert "applyFontScale" in main_js, "Missing applyFontScale in main.js"
    assert "wireFontScaling" in main_js, "Missing wireFontScaling in main.js"


def test_clean_plotly_math_and_katex_integration():
    """Verify cleanPlotlyMath helper and KaTeX equation formatting."""
    ui_js = (ROOT / "frontend" / "js" / "ui.js").read_text(encoding="utf-8")
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    science_js = (ROOT / "frontend" / "js" / "tabs_science.js").read_text(encoding="utf-8")

    # 1. cleanPlotlyMath export and usage
    assert "export function cleanPlotlyMath" in ui_js, "Missing cleanPlotlyMath in ui.js"
    assert "cleanPlotlyMath" in science_js, "tabs_science.js should use cleanPlotlyMath"

    # 2. KaTeX rendering integration
    assert "export function renderMath" in ui_js, "Missing renderMath in ui.js"
    assert "renderMathInElement" in ui_js, "renderMath should delegate to renderMathInElement"

    # 3. No double-escaped backslashes in HTML formulas
    assert "\\\\left" not in index_html, "Double backslash \\left detected in index.html"
    assert "\\\\frac" not in index_html, "Double backslash \\frac detected in index.html"

