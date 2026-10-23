"""The two start-up commands, cosmic2-explorer (app.py) and
cosmic2-explorer-server (server.py), with the server and window replaced by
stand-ins so nothing is opened or bound for long."""
from __future__ import annotations

import socket
import time
import types

from cosmic2 import app, server
from cosmic2.config import SETTINGS


def test_free_port_skips_a_port_in_use():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        assert server.free_port(busy, tries=3) != busy


def test_server_warns_when_bound_beyond_this_computer(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(server.uvicorn, "run", lambda app_, **kw: calls.update(kw))
    monkeypatch.setattr(SETTINGS, "analysis_workers", SETTINGS.analysis_workers)
    assert server.main(["--host", "0.0.0.0", "--port", "9123", "--workers", "2"]) == 0
    out = capsys.readouterr()
    assert "WARNING" in out.err and "http://0.0.0.0:9123/" in out.out
    assert calls["host"] == "0.0.0.0" and calls["port"] == 9123
    assert SETTINGS.analysis_workers == 2


def _no_backend(monkeypatch, healthy: bool):
    monkeypatch.setattr(app, "_serve", lambda host, port: None)
    monkeypatch.setattr(app, "_wait_until_up", lambda url: healthy)
    monkeypatch.setattr(app, "_show_error_dialog", lambda *a: None)


def test_app_reports_missing_frontend(monkeypatch, tmp_path):
    _no_backend(monkeypatch, True)
    monkeypatch.setattr(app, "frontend_dir", lambda: tmp_path / "none")
    assert app.main(["--browser"]) == 2


def test_app_reports_a_backend_that_never_answers(monkeypatch):
    _no_backend(monkeypatch, False)
    assert app.main(["--browser", "--port", "9124"]) == 3


def test_app_browser_mode_opens_the_url_and_stops_on_ctrl_c(monkeypatch):
    _no_backend(monkeypatch, True)
    opened = []
    monkeypatch.setattr(app.webbrowser, "open", opened.append)

    def interrupt(_):
        raise KeyboardInterrupt
    monkeypatch.setattr(app, "time", types.SimpleNamespace(
        sleep=interrupt, time=time.time, strftime=time.strftime))
    assert app.main(["--browser", "--port", "9125"]) == 0
    assert opened == ["http://127.0.0.1:9125/"]
