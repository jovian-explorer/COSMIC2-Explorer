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
    page.click("#btn-samples")
    page.wait_for_function("document.querySelectorAll('#f-product option').length >= 5")
    assert {"atmPrf", "ionPrf", "ivmL2m", "scnLv2", "wetPf2"} <= set(
        page.eval_on_selector_all("#f-product option", "o => o.map(x => x.value)"))
    page.click("button[data-tab=explore]")
    page.select_option("#f-product", "wetPf2")
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
    page.click("button[data-tab=export]")
    page.select_option("#e-kind", "grid_csv")
    _press(page, "#btn-export-data")
    page.select_option("#e-fig", "profiles")
    _press(page, "#btn-export-fig")
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
    sw, vw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert sw <= vw
    assert page.evaluate("document.querySelector('.tabs').getBoundingClientRect().height") < 60
    page.set_viewport_size({"width": 1400, "height": 900})
