"""pytest configuration for COSMIC-2 Explorer tests."""
import sys
import threading
import time
import urllib.request
from pathlib import Path
import pytest

# Make the backend importable
backend_dir = Path(__file__).resolve().parents[1] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

def pytest_sessionstart(session):
    """Ensure backend server is running on 127.0.0.1:8992 before test collection."""
    import uvicorn
    from cosmic2.api import app

    base = "http://127.0.0.1:8992"
    try:
        urllib.request.urlopen(base + "/api/health", timeout=1)
        return
    except Exception:
        pass

    config = uvicorn.Config(app, host="127.0.0.1", port=8992, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Wait for server to become responsive
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)


