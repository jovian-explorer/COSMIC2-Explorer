"""Settings across versions (config.Settings, settings_migration.py): stored values
are kept as they are, entries this version cannot use are preserved in
settings.json, and the user is shown once what is new, changed or removed."""
import dataclasses
import json
import os

import pytest
import requests

from cosmic2 import autoupdate, config, settings_migration as sm
from cosmic2.config import SETTING_RULES, Settings


# ---------------------------------------------------------------- rules and validation

def test_every_setting_has_a_rule_and_its_default_is_allowed():
    fields = {f.name for f in dataclasses.fields(Settings)} - {"user_agent", "extra"}
    assert fields == set(SETTING_RULES)
    for k, v in Settings().to_dict().items():
        if k in SETTING_RULES:
            assert Settings.validate(k, v) == v, k


def test_stream_and_product_choices_match_the_catalog():
    from cosmic2.catalog import PRODUCTS, STREAMS
    assert set(SETTING_RULES["default_stream"][1]) == set(STREAMS)
    assert set(SETTING_RULES["default_product"][1]) == set(PRODUCTS)


@pytest.mark.parametrize("key,value", [
    ("plot_dpi", 49), ("plot_dpi", "300"), ("plot_dpi", 300.5), ("plot_dpi", True),
    ("ui_theme", "blue"), ("qc_require_good", 1), ("grid_step_km", 0), ("grid_top_km", float("nan")),
    ("default_stream", "postcal"), ("no_such_option", 1),
])
def test_values_this_version_does_not_accept(key, value):
    with pytest.raises(ValueError):
        Settings.validate(key, value)


def test_values_accepted_and_normalised():
    assert Settings.validate("plot_dpi", 300.0) == 300 and isinstance(Settings.validate("plot_dpi", 300.0), int)
    assert Settings.validate("grid_step_km", 1) == 1
    assert Settings.validate("units_temperature", "K") == "K"
    assert Settings.validate("extra", {"a": 1}) == {"a": 1}


# ---------------------------------------------------------------- loading and saving

@pytest.fixture
def home(tmp_path, monkeypatch):
    """settings.json, settings_seen.json and the update state in a fresh folder,
    with config.SETTINGS loaded from there."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    monkeypatch.setattr(sm, "SETTINGS_PATH", path)
    monkeypatch.setattr(sm, "MARKER_PATH", tmp_path / "settings_seen.json")
    monkeypatch.setattr(autoupdate, "STATE_PATH", tmp_path / "updates" / "state.json")
    monkeypatch.setattr(autoupdate, "UPDATES_DIR", tmp_path / "updates")
    monkeypatch.setattr(config, "SETTINGS_CREATED", False)

    def load(stored=None):
        if stored is not None:
            path.write_text(json.dumps(stored), encoding="utf-8")
        s = Settings.load()
        monkeypatch.setattr(config, "SETTINGS", s)
        return s
    return path, load


def test_load_keeps_what_it_cannot_use_and_writes_it_back(home):
    path, load = home
    s = load({"plot_dpi": 600, "ui_font_size": 40, "old_option": "x", "ui_theme": "dark",
              "user_agent": "COSMIC2Explorer/0.0.0 (old)"})
    assert s.plot_dpi == 600 and s.ui_theme == "dark"
    assert s.ui_font_size == Settings().ui_font_size              # invalid here: the default is used
    assert s.preserved() == {"ui_font_size": 40, "old_option": "x"}
    assert s.user_agent == Settings().user_agent                  # always this version's
    s.update(plot_dpi=150)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["plot_dpi"] == 150
    assert on_disk["ui_font_size"] == 40 and on_disk["old_option"] == "x"     # not lost by saving
    s.update(ui_font_size=16)                                     # the user chose: no longer preserved
    assert json.loads(path.read_text(encoding="utf-8"))["ui_font_size"] == 16
    assert "_preserved" not in s.to_dict()


def test_update_with_an_invalid_value_changes_nothing(home):
    path, load = home
    s = load({"plot_dpi": 600})
    with pytest.raises(ValueError):
        s.update(plot_dpi=300, ui_theme="purple")
    assert s.plot_dpi == 600 and s.ui_theme == Settings().ui_theme


def test_first_start_creates_settings_and_shows_nothing(home, monkeypatch):
    path, load = home
    load()
    assert config.SETTINGS_CREATED and path.exists()
    assert sm.pending() == {"show": False}
    assert sm.MARKER_PATH.exists()
    assert sm.pending() == {"show": False}


# ---------------------------------------------------------------- comparing versions

def _old_schema(**changes):
    """The current schema as an older version would have written it."""
    schema = json.loads(json.dumps(sm.current_schema()))
    for k, v in changes.items():
        if v is None:
            schema.pop(k)
        else:
            schema[k] = v
    return schema


def test_compare_lists_new_removed_changed_and_invalid():
    new = sm.current_schema()
    old = _old_schema(auto_update=None, retired={"default": 5, "rule": {"type": "int", "min": 0, "max": 9}},
                      plot_dpi={"default": 300, "rule": {"type": "int", "min": 50, "max": 2400}},
                      ui_theme={"default": "dark", "rule": ["light", "dark"]})
    stored = {"retired": 7, "plot_dpi": 2000, "ui_theme": "light", "grid_step_km": -1,
              "user_agent": "x", "extra": {}}
    c = sm.compare(stored, old, new)
    assert c["new"] == [{"key": "auto_update", "default": True, "rule": [False, True]}]
    assert c["removed"] == [{"key": "retired", "stored": 7}]
    changed = {x["key"]: x for x in c["changed"]}
    assert set(changed) == {"plot_dpi", "ui_theme"}
    assert changed["plot_dpi"]["valid"] is False and changed["plot_dpi"]["old_rule"]["max"] == 2400
    assert changed["ui_theme"]["valid"] is True and changed["ui_theme"]["old_default"] == "dark"
    assert c["invalid"] == [{"key": "grid_step_km", "stored": -1, "rule": new["grid_step_km"]["rule"],
                             "default": Settings().grid_step_km}]
    assert c["renamed"] == []


def test_compare_without_a_marker_uses_the_stored_keys():
    """An upgrade from a version that kept no schema (0.0.1): what it stored stands for it."""
    stored = {k: v for k, v in Settings().to_dict().items() if k != "auto_update"}
    stored["gone_option"] = 1
    c = sm.compare(stored, None, sm.current_schema())
    assert [x["key"] for x in c["new"]] == ["auto_update"]
    assert c["removed"] == [{"key": "gone_option", "stored": 1}]
    assert c["changed"] == [] and c["invalid"] == []


def test_compare_renamed_option():
    new = {"plot_resolution": {"default": 300, "rule": {"type": "int", "min": 50, "max": 1200}}}
    old = {"dpi": {"default": 300, "rule": {"type": "int", "min": 50, "max": 1200}}}
    c = sm.compare({"dpi": 600}, old, new, renamed={"dpi": "plot_resolution"},
                   valid=lambda k, v: 50 <= v <= 1200)
    assert c["renamed"] == [{"old": "dpi", "key": "plot_resolution", "stored": 600, "valid": True}]
    assert not c["new"] and not c["removed"]


def test_after_an_update_the_panel_shows_once_then_the_choices_are_kept(home, monkeypatch):
    path, load = home
    # an older build wrote settings.json and the schema it showed
    sm.MARKER_PATH.write_text(json.dumps({"version": "0.0.1", "tag": "v0.0.1-build.1",
                                          "schema": _old_schema(auto_update=None)}), encoding="utf-8")
    load({"plot_dpi": 600, "ui_font_size": 99, "legacy": True})
    monkeypatch.setitem(autoupdate.BUILD, "tag", "v0.0.1-build.2")
    autoupdate.save_state({"installed": {"tag": "v0.0.1-build.2", "name": "COSMIC-2 Explorer v0.0.1-build.2",
                                         "notes": "### Changes\n- Something new", "url": "u",
                                         "previous": "v0.0.1-build.1"}})
    r = sm.pending()
    assert r["show"] and r["tag"] == "v0.0.1-build.2" and r["previous"]["tag"] == "v0.0.1-build.1"
    assert r["whats_new"]["notes"].startswith("### Changes")
    assert [x["key"] for x in r["changes"]["new"]] == ["auto_update"]
    assert r["changes"]["removed"] == [{"key": "legacy", "stored": True}]
    assert r["changes"]["invalid"][0]["key"] == "ui_font_size"
    assert r["settings"]["plot_dpi"] == 600                      # kept as stored
    with pytest.raises(ValueError):
        sm.acknowledge({"ui_font_size": 99})
    assert json.loads(path.read_text(encoding="utf-8"))["legacy"] is True     # nothing changed
    out = sm.acknowledge({"ui_font_size": 18, "auto_update": False})
    assert out["ui_font_size"] == 18 and out["auto_update"] is False and out["plot_dpi"] == 600
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["legacy"] is True and on_disk["plot_dpi"] == 600     # nothing deleted
    assert sm.pending() == {"show": False}                       # shown once
    assert json.loads(sm.MARKER_PATH.read_text(encoding="utf-8"))["tag"] == "v0.0.1-build.2"


def test_closing_the_panel_keeps_every_value(home, monkeypatch):
    path, load = home
    sm.MARKER_PATH.write_text(json.dumps({"version": "0.0.1", "tag": None,
                                          "schema": _old_schema(auto_update=None)}), encoding="utf-8")
    load({"plot_dpi": 600, "units_temperature": "K", "ui_font_size": 99, "legacy": "abc"})
    r = sm.pending()
    assert r["show"] and r["changes"]["invalid"] and r["changes"]["removed"]
    out = sm.acknowledge(None)
    assert out["plot_dpi"] == 600 and out["units_temperature"] == "K" and out["auto_update"] is True
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["ui_font_size"] == 99 and on_disk["legacy"] == "abc"      # kept as stored
    assert sm.pending() == {"show": False}           # values already shown are not reported again
    # another version (an older copy started again) writes a different invalid value
    on_disk["ui_font_size"] = 5
    path.write_text(json.dumps(on_disk), encoding="utf-8")
    r = sm.pending()
    assert r["show"] and [x["key"] for x in r["changes"]["invalid"]] == ["ui_font_size"]
    assert r["changes"]["removed"] == []


def test_api_refuses_values_out_of_range():
    base = os.environ["COSMIC2_TEST_BASE"]
    r = requests.post(f"{base}/api/settings", json={"ui_font_size": 99}, timeout=10)
    assert r.status_code == 422 and "ui_font_size" in r.text
    r = requests.get(f"{base}/api/settings/changes", timeout=10)
    assert r.status_code == 200 and r.json() == {"show": False}       # a first start
    r = requests.post(f"{base}/api/settings/changes/ack", json={"settings": {"plot_dpi": 5}}, timeout=10)
    assert r.status_code == 422
