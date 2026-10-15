"""The interface in a real browser: every tab and main action, no script
errors.  Skipped unless Playwright and its Chromium are installed
(``pip install playwright && playwright install chromium``)."""
import os

import pytest

BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")


@pytest.fixture(scope="module")
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    try:
        browser = pw.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        pw.stop()
        pytest.skip(f"Chromium for Playwright is not installed ({exc})")
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    pg.errors = []
    pg.on("console", lambda m: m.type == "error" and pg.errors.append(m.text))
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    browser.close()
    pw.stop()


def _press(page, sel, timeout=120000):
    page.click(sel)
    page.wait_for_function(f"document.querySelector('{sel}').disabled === false",
                           timeout=timeout)


def test_every_tab_and_main_action_without_script_errors(page):
    page.goto(BASE + "/")
    page.wait_for_selector("#version-tag:not(:empty)")
    # a first start loads the examples, then opens Explore: wait for that
    page.wait_for_load_state("networkidle")
    page.click("button[data-tab=get]")
    page.click("#btn-samples")
    page.wait_for_function("document.querySelectorAll('#f-product option').length >= 5")
    assert {"atmPrf", "ionPrf", "ivmL2m", "scnLv2", "wetPf2"} <= set(
        page.eval_on_selector_all("#f-product option", "o => o.map(x => x.value)"))
    page.click("button[data-tab=explore]")
    page.select_option("#f-product", "wetPf2")
    streams = page.eval_on_selector_all("#f-stream option", "o => o.map(x => x.value)")
    assert streams[0] == "" and len(streams) >= 2
    page.select_option("#f-stream", streams[1])
    _press(page, "#btn-search")
    assert "profiles match" in page.inner_text("#search-note")
    page.select_option("#f-stream", "")
    _press(page, "#btn-search")
    page.click("#btn-select-page")
    page.click("button[data-tab=profile]")
    _press(page, "#btn-plot")
    assert "profile" in page.inner_text("#profile-caption")
    page.click("button[data-tab=composite]")
    page.fill("#c-top", "30")
    _press(page, "#btn-composite")
    _press(page, "#btn-scatter")
    page.click("button[data-tab=stats]")
    _press(page, "#btn-stats")
    assert page.query_selector_all("#st-table tbody tr")
    page.select_option("#x-field", "Temp")
    page.fill("#x-min", "1")
    _press(page, "#btn-section")
    _press(page, "#btn-map")
    _press(page, "#btn-pairs")
    assert page.inner_text("#pp-count") == "2 pairs"
    _press(page, "#btn-missions")
    assert "No good wetPf2 profiles of PAZ" in page.inner_text("#ms-plot")
    _press(page, "#btn-tropopause")
    assert page.inner_text("#tp-count") == "2 profiles"
    assert page.query_selector_all("#tp-table tbody tr")
    # with every band filled, no column is shown that holds only dashes
    # (CDAAC's values need atmPrf files in the selection)
    page.fill("#tp-min", "1")
    _press(page, "#btn-tropopause")
    dash_only = page.evaluate("""() => {
      const rows = [...document.querySelectorAll('#tp-table tbody tr')];
      const n = rows[0].cells.length, out = [];
      for (let k = 2; k < n; k++) {
        const cells = rows.map((r) => r.cells[k]).filter((c) => c && c.offsetParent);
        if (cells.length && cells.every((c) => c.innerText.trim() === '-')) out.push(k);
      }
      return out;
    }""")
    assert dash_only == [], dash_only
    _press(page, "#btn-nwp")
    assert page.inner_text("#nwp-count") == "2 occultations"
    # the numbers behind the plot, from its toolbar
    page.hover("#nwp-plot")
    page.click("#nwp-plot .modebar-btn[data-title^='Save the plotted numbers']")
    page.wait_for_selector("#toasts .toast:has-text('values) to the exports folder')")
    page.select_option("#nwp-kind", "differences:bending_angle")
    _press(page, "#btn-nwp")
    assert page.inner_text("#nwp-count") == "2 occultations"
    page.select_option("#nwp-kind", "tch:refractivity")
    _press(page, "#btn-nwp")
    assert "at least 30 occultations" in page.inner_text("#nwp-plot")
    page.click("button[data-tab=export]")
    page.select_option("#e-kind", "grid_csv")
    _press(page, "#btn-export-data")
    page.select_option("#e-fig", "profiles")
    _press(page, "#btn-export-fig")
    from cosmic2.config import EXPORT_DIR
    recipe = max(EXPORT_DIR.glob("*.recipe.json"), key=lambda q: q.stat().st_mtime)
    page.set_input_files("#e-recipe", str(recipe))
    page.wait_for_selector("#toasts .toast:has-text('again from')")
    for b in ("#btn-vars-catalog", "#btn-data-policy", "#btn-settings", "#btn-about", "#btn-help"):
        page.click(b)
        page.wait_for_timeout(400)
        page.click("#drawer-close")
    page.click("button[data-tab=guide]")
    page.wait_for_timeout(500)
    bad = [t.inner_text() for t in page.query_selector_all("#toasts .toast.bad")]
    assert not bad, bad
    assert not page.errors, page.errors


def test_settings_updates_row(page):
    page.goto(BASE + "/")
    page.wait_for_selector("#version-tag:not(:empty)")
    page.click("#btn-settings")
    page.wait_for_function("document.querySelector('#s-update-status')?.textContent.length > 0")
    assert "not a published build" in page.inner_text("#s-update-status")
    assert page.is_disabled("#s-update-now")
    assert page.is_checked("#s-auto-update")
    page.click("#drawer-close")
    assert not page.errors, page.errors


def test_settings_changed_panel_once(page):
    """A data folder last used by an older version: the panel lists the new option
    once; closing it keeps settings.json as it was."""
    import json
    from cosmic2 import settings_migration as sm
    from cosmic2.config import SETTINGS_PATH
    schema = sm.current_schema()
    schema.pop("auto_update")
    sm.MARKER_PATH.write_text(json.dumps({"version": "0.0.0", "tag": None, "schema": schema}), encoding="utf-8")
    before = SETTINGS_PATH.read_text(encoding="utf-8")
    page.goto(BASE + "/")
    page.wait_for_selector("#settings-changes")
    text = page.text_content("#settings-changes")
    assert "New settings" in text and "Update automatically" in text and "before: 0.0.0" in text
    page.click("#drawer-close")
    page.wait_for_timeout(500)
    assert SETTINGS_PATH.read_text(encoding="utf-8") == before
    assert json.loads(sm.MARKER_PATH.read_text(encoding="utf-8"))["schema"] == sm.current_schema()
    page.reload()
    page.wait_for_selector("#version-tag:not(:empty)")
    page.wait_for_timeout(800)
    assert not page.is_visible("#settings-changes")
    assert not page.errors, page.errors


@pytest.mark.parametrize("width", [1024, 1280, 1366, 1920])
def test_no_horizontal_scroll(page, width):
    """The header used to be one row 1455 px wide (scrolling sideways at 1366 px)
    and squeezed the tab bar into a column below 1100 px."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(BASE + "/")
    page.wait_for_selector("#version-tag:not(:empty)")
    for tab in ("guide", "get", "explore", "profile", "composite", "stats", "export"):
        page.click(f"button[data-tab={tab}]")
        page.wait_for_timeout(150)
        sw, vw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert sw <= vw, tab
    assert page.evaluate("document.querySelector('.tabs').getBoundingClientRect().height") < 60
    page.set_viewport_size({"width": 1400, "height": 900})


_LONGEST_OPTION_FITS = """() => { const c = document.createElement('canvas').getContext('2d'); const bad = [];
  for (const s of document.querySelectorAll('select')) {
    if (!s.offsetParent) continue;
    const cs = getComputedStyle(s);
    c.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const avail = s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    for (const o of s.options) if (c.measureText(o.text).width > avail + 1) { bad.push(`#${s.id}: ${o.text}`); break; }
  } return bad; }"""


def test_dropdown_labels_fit_at_1366(page):
    """The 290 px controls column cut quantity and height names short
    ("Altitude above mean sea level (MSL")."""
    page.set_viewport_size({"width": 1366, "height": 900})
    page.goto(BASE + "/")
    page.wait_for_selector("#version-tag:not(:empty)")
    for tab in ("profile", "composite", "stats"):
        page.click(f"button[data-tab={tab}]")
        page.wait_for_timeout(150)
        assert page.evaluate(_LONGEST_OPTION_FITS) == [], tab
    page.set_viewport_size({"width": 1400, "height": 900})


def test_map_and_stats_follow_an_ionprf_search(page):
    page.goto(BASE + "/")
    page.wait_for_selector("#version-tag:not(:empty)")
    page.click("button[data-tab=explore]")
    page.select_option("#f-product", "ionPrf")
    _press(page, "#btn-search")
    page.click("button[data-tab=stats]")
    page.select_option("#m-col", "gravity_waves.ep_J_per_kg")
    _press(page, "#btn-map")
    # an ionPrf search maps an ionospheric diagnostic, not atmPrf profiles
    assert page.eval_on_selector("#m-col", "e => e.value") == "ionosphere.foF2_MHz"
    _press(page, "#btn-stats")
    assert "terrain" not in page.inner_text("#st-caption")


def test_drop_mixed_files_says_what_was_added_and_what_was_not(page):
    import base64

    from cosmic2.config import sampledata_dir
    good = next(sampledata_dir().glob("echPrf_*_nc"))
    data = base64.b64encode(good.read_bytes()).decode()
    page.goto(BASE + "/")
    page.wait_for_selector("#version-tag:not(:empty)")
    page.evaluate("""([name, b64]) => {
        const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
        const dt = new DataTransfer();
        dt.items.add(new File([bytes], name));
        dt.items.add(new File([bytes.slice(0, 2000)], 'cut_' + name));
        dt.items.add(new File(['orbit'], 'leoOrb_C2E1.2026.200.sp3'));
        window.dispatchEvent(new DragEvent('drop', {dataTransfer: dt}));
    }""", [good.name, data])
    page.wait_for_selector("#toasts .toast:has-text('Added')")
    msg = page.inner_text("#toasts .toast:has-text('Added')")
    assert "Added 1 file" in msg and "1 could not be read" in msg
    assert "1 not netCDF" in msg
    assert not page.errors
