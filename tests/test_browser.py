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
    page.wait_for_timeout(1500)
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
