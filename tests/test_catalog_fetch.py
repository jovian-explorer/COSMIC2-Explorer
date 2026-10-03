"""Archive listing cache and download bookkeeping, with the network faked."""
import types

import pytest

from cosmic2 import catalog


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text
        self.ok = status < 400
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _archive():
    settings = types.SimpleNamespace(listing_cache_hours=6, request_timeout_s=5,
                                     user_agent="test")
    return catalog.Archive(settings)


def test_missing_directory_is_retried_after_a_few_minutes(monkeypatch):
    arc = _archive()
    answers = [FakeResponse(404),
               FakeResponse(200, '<a href="wetPf2_nrt_2026_200.tar.gz">x</a>')]
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return answers[min(len(calls) - 1, 1)]

    monkeypatch.setattr(arc._session, "get", fake_get)
    clock = [1000.0]
    monkeypatch.setattr(catalog.time, "time", lambda: clock[0])
    assert arc.list_dir("https://x/2026/200") == []
    clock[0] += 60
    assert arc.list_dir("https://x/2026/200") == []          # still cached
    clock[0] += 600                                            # 11 min later
    assert arc.list_dir("https://x/2026/200") == ["wetPf2_nrt_2026_200.tar.gz"]
    clock[0] += 3600                                           # found: long TTL
    arc.list_dir("https://x/2026/200")
    assert len(calls) == 2
