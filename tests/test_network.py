"""End-to-end download from the live UCAR CDAAC archive.

Opt-in because it depends on a remote server: set COSMIC2_NETWORK_TESTS=1.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

import pytest

BASE = os.environ.get("COSMIC2_TEST_BASE", "http://127.0.0.1:8992")

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(os.environ.get("COSMIC2_NETWORK_TESTS") != "1",
                       reason="set COSMIC2_NETWORK_TESTS=1 to run live-archive tests"),
]


def _get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=60).read())


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def test_archive_listing_and_download():
    days = _get("/api/archive/days?year=2023")
    assert days["dates"], "no archive days listed for 2023"

    job = _post("/api/download", {
        "stream": "nrt", "level": "level2", "product": "wetPf2",
        "date": "2023-01-01", "max_profiles": 3, "sampling": "first",
    })
    deadline = time.time() + 600
    while time.time() < deadline:
        st = _get(f"/api/jobs/{job['id']}")
        if st["state"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(2)
    assert st["state"] == "completed", st.get("error") or st

    found = _post("/api/profiles/search", {"limit": 10, "good_only": False})
    assert found["total"] >= 1


def test_readme_download_snippet_runs(tmp_path):
    """The README's download example, in a fresh data folder."""
    import re
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    code = re.findall(r"```python\n(.*?)```", readme, re.S)[1]
    code += "\nassert job.state == 'completed', job.error\nassert rows\n"
    env = dict(os.environ, COSMIC2_EXPLORER_HOME=str(tmp_path), PYTHONPATH=str(root / "src"))
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                         text=True, timeout=900)
    assert out.returncode == 0, out.stderr
