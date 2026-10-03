"""pytest configuration for COSMIC-2 Explorer tests.

Tests run against the installed ``cosmic2`` package (``pip install -e .[dev]``
for development).  All app data goes to a throwaway directory, and the API
server used by the HTTP tests binds a free loopback port, so the suite never
touches the user's real data and can run alongside other local apps.
"""
import gc
import os
import shutil
import socket
import tempfile
import threading
import time
import urllib.request

# Must be set before cosmic2.config is imported anywhere.  A folder created
# here is deleted again when the session ends.
_OWN_HOME = None
if "COSMIC2_EXPLORER_HOME" not in os.environ:
    _OWN_HOME = tempfile.mkdtemp(prefix="cosmic2-test-home-")
    os.environ["COSMIC2_EXPLORER_HOME"] = _OWN_HOME

_SERVER = {}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def pytest_sessionstart(session):
    """Start the API server before collection; tests read its URL from COSMIC2_TEST_BASE."""
    import uvicorn
    from cosmic2.api import app

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    os.environ["COSMIC2_TEST_BASE"] = base

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _SERVER.update(server=server, thread=thread)

    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)


def pytest_sessionfinish(session, exitstatus):
    """Stop the server and remove the throwaway data folder."""
    server, thread = _SERVER.get("server"), _SERVER.get("thread")
    if server is not None:
        server.should_exit = True
        thread.join(timeout=10)
    if not _OWN_HOME:
        return
    # Close the SQLite connections the request threads opened so Windows lets
    # the index file go.
    try:
        import sqlite3
        for obj in gc.get_objects():
            if isinstance(obj, sqlite3.Connection):
                try:
                    obj.close()
                except Exception:
                    pass
    except Exception:
        pass
    gc.collect()
    shutil.rmtree(_OWN_HOME, ignore_errors=True)
