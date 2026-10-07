"""What changed in the settings between the version that wrote settings.json and this one.

Another version (an update, or an older copy started again) may have options this
one lacks, lack options this one has, or allow other values.  Nothing stored is
changed when that happens: every stored value this version can use is used as it
is, and the others stay in settings.json (``Settings.preserved``) while the
default stands in for them.  Once per version and build the user is shown what
changed (with what is new in the release, after an automatic update) and can
change the values; nothing is deleted from settings.json either way, and closing
the panel does not write it at all.  The schema they saw, and the stored values
this version cannot use that they were shown, are then kept in
``settings_seen.json`` beside settings.json: the next comparison starts from that
schema, and such a value is not reported again while it stays the same.

A first start (no settings.json yet) has nothing to compare and shows nothing.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from . import config
from .config import APP_VERSION, DATA_ROOT, RENAMED_SETTINGS, SETTING_RULES, SETTINGS_PATH, Settings

MARKER_PATH = DATA_ROOT / "settings_seen.json"


def rule_json(rule: tuple) -> Any:
    """A setting's allowed values in JSON: a list of choices ([false, true] for an
    on/off option) or {"min", "max", "type"} for a range."""
    if rule[0] == "bool":
        return [False, True]
    if rule[0] == "choice":
        return list(rule[1])
    return {"type": rule[0], "min": rule[1], "max": rule[2]}


def current_schema() -> Dict[str, Dict[str, Any]]:
    defaults = Settings().to_dict()
    return {k: {"default": defaults.get(k), "rule": rule_json(rule)} for k, rule in SETTING_RULES.items()}


def _valid(key: str, value: Any) -> bool:
    try:
        Settings.validate(key, value)
        return True
    except ValueError:
        return False


# internal entries of settings.json that are not options the user sets
_INTERNAL = {"user_agent", "extra"}


def compare(stored: Dict[str, Any], old_schema: Optional[Dict[str, Dict[str, Any]]],
            new_schema: Dict[str, Dict[str, Any]], renamed: Optional[Dict[str, str]] = None,
            valid=_valid) -> Dict[str, List]:
    """The differences that concern the user.

    ``stored``: settings.json as written; ``old_schema``: the schema the user last
    saw (None: unknown, then the stored keys stand for it).  Returns
      new      options this version has and the old one had not: {key, default, rule}
      renamed  {old, key, stored, valid}
      removed  options of the old version this one has not: {key, stored}
      changed  options whose allowed values or default changed:
               {key, rule, old_rule, default, old_default, stored, valid}
      invalid  other stored values this version does not accept: {key, stored, rule, default}
    """
    renamed = renamed or {}
    stored = {k: v for k, v in stored.items() if k not in _INTERNAL}
    old_keys = (set(old_schema) if old_schema is not None else set(stored)) - _INTERNAL
    out: Dict[str, List] = {"new": [], "renamed": [], "removed": [], "changed": [], "invalid": []}
    renamed_to = {new: old for old, new in renamed.items() if old in old_keys or old in stored}
    for key, spec in new_schema.items():
        if key in renamed_to:
            old = renamed_to[key]
            if old in stored:
                out["renamed"].append({"old": old, "key": key, "stored": stored[old],
                                       "valid": valid(key, stored[old])})
            continue
        if key not in old_keys:
            out["new"].append({"key": key, "default": spec["default"], "rule": spec["rule"]})
            continue
        has = key in stored
        if old_schema is not None and key in old_schema and (
                old_schema[key].get("rule") != spec["rule"] or old_schema[key].get("default") != spec["default"]):
            out["changed"].append({"key": key, "rule": spec["rule"], "old_rule": old_schema[key].get("rule"),
                                   "default": spec["default"], "old_default": old_schema[key].get("default"),
                                   "stored": stored.get(key), "valid": has and valid(key, stored[key])})
        elif has and not valid(key, stored[key]):
            out["invalid"].append({"key": key, "stored": stored[key], "rule": spec["rule"], "default": spec["default"]})
    for key in sorted(old_keys | set(stored)):
        if key not in new_schema and key not in renamed:
            out["removed"].append({"key": key, "stored": stored.get(key)})
    return out


def _read_json(path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _identity() -> Dict[str, Any]:
    from .autoupdate import this_tag
    return {"version": APP_VERSION, "tag": this_tag()}


def _write_marker() -> None:
    # the stored entries this version cannot use (unknown here, or not allowed):
    # the user has been shown them, so they are not reported again unchanged.
    # Values this version can use are not listed: once another version drops or
    # restricts the option, they are news.
    stored = _read_json(SETTINGS_PATH) or {}
    unusable = {k: v for k, v in stored.items() if k not in _INTERNAL and not _valid(k, v)}
    tmp = MARKER_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({**_identity(), "schema": current_schema(), "unusable_seen": unusable}, fh, indent=2)
    os.replace(tmp, MARKER_PATH)


def _not_seen(entries: List[Dict[str, Any]], stored: Dict[str, Any], seen: Optional[Dict[str, Any]]) -> List:
    """The entries whose stored value the user has not been shown as unusable yet."""
    if not isinstance(seen, dict):
        return entries
    return [e for e in entries if e["key"] not in seen or seen[e["key"]] != stored.get(e["key"])]


def pending() -> Dict[str, Any]:
    """What to show the user once at this start: the settings changes since the
    schema they last saw and, after an automatic update, the release notes of the
    new build.  When there is nothing to show, the marker is brought up to date."""
    from . import autoupdate
    marker = _read_json(MARKER_PATH)
    ident = _identity()
    if marker is None and config.SETTINGS_CREATED:
        try:
            _write_marker()
        except OSError:
            pass
        return {"show": False}
    stored = _read_json(SETTINGS_PATH) or {}
    changes = compare(stored, (marker or {}).get("schema"), current_schema(), RENAMED_SETTINGS)
    seen = (marker or {}).get("unusable_seen")
    changes["invalid"] = _not_seen(changes["invalid"], stored, seen)
    changes["removed"] = _not_seen(changes["removed"], stored, seen)
    seen_here = marker is not None and marker.get("version") == ident["version"] and marker.get("tag") == ident["tag"]
    notes = None if seen_here else autoupdate.installed_notes()
    if not any(changes.values()) and not notes:
        try:
            _write_marker()
        except OSError:
            pass
        return {"show": False}
    return {"show": True, **ident,
            "previous": None if marker is None else {"version": marker.get("version"), "tag": marker.get("tag")},
            "whats_new": notes, "changes": changes, "settings": config.SETTINGS.to_dict()}


def acknowledge(patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The user has seen the changes: apply their choices (all validated first;
    ValueError for an invalid one, and nothing is changed then) and remember the
    schema and the stored values they saw.  Entries this version cannot use and
    the user did not replace stay in settings.json, which is not written at all
    when there are no choices (the panel was closed)."""
    settings = config.SETTINGS
    patch = {k: v for k, v in dict(patch or {}).items() if k in SETTING_RULES}
    for k, v in patch.items():
        Settings.validate(k, v)
    if patch:
        settings.update(**patch)
    _write_marker()
    return settings.to_dict()
