"""The weekly automatic update (cosmic2/autoupdate.py) against a local stand-in for
the GitHub releases API: release ordering, picking this platform's archive, the
SHA-256 check, unpacking beside the installation, and what start-up does after."""
import hashlib
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cosmic2 import autoupdate as au
from cosmic2.config import DATA_ROOT, SETTINGS

PLAT = "windows-x64"


# ---------------------------------------------------------------- tags and releases

def test_tags_are_ordered_by_version_then_build():
    assert au.parse_tag("v0.0.2-build.7") == ((0, 0, 2), 7)
    assert au.parse_tag("v0.0.2") == ((0, 0, 2), 0)
    assert au.parse_tag("nightly") == ((), 0)
    assert au.is_newer("v0.0.1-build.2", "v0.0.1-build.1")
    assert au.is_newer("v0.0.2", "v0.0.1-build.9")
    assert au.is_newer("v0.0.1-build.1", "v0.0.1")
    assert not au.is_newer("v0.0.1-build.1", "v0.0.1-build.1")
    assert not au.is_newer("v0.0.1", "v0.0.1-build.3")
    assert not au.is_newer("v0.0.9", None)          # an unstamped copy compares with nothing
    assert not au.is_newer("junk", "v0.0.1")


def test_newest_release_skips_drafts_and_keeps_prereleases():
    rels = [{"tag_name": "v0.0.1", "prerelease": True},
            {"tag_name": "v0.0.1-build.3", "prerelease": True},
            {"tag_name": "v0.0.2", "draft": True},
            {"tag_name": "nightly"}]
    assert au.newest_release(rels)["tag_name"] == "v0.0.1-build.3"
    assert au.newest_release([{"tag_name": "x"}]) is None


def test_pick_asset_for_each_platform():
    rel = {"assets": [{"name": "SHA256SUMS.txt"},
                      {"name": "COSMIC2-Explorer-0.0.1-windows-x64.zip"},
                      {"name": "COSMIC2-Explorer-0.0.1-macos-arm64.zip"},
                      {"name": "COSMIC2-Explorer-0.0.1-linux-x64.tar.gz"}]}
    assert au.pick_asset(rel, "windows-x64")["name"].endswith("windows-x64.zip")
    assert au.pick_asset(rel, "macos-arm64")["name"].endswith("macos-arm64.zip")
    assert au.pick_asset(rel, "linux-x64")["name"].endswith("linux-x64.tar.gz")
    assert au.pick_asset(rel, "linux-arm64") is None


def test_platform_tag_names_match_the_build_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_exe", Path(__file__).resolve().parents[1] / "scripts" / "build_exe.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    assert au.platform_tag() == f"{b._os_tag()}-{b._arch()}"


def test_no_token_is_sent_to_another_server(monkeypatch):
    monkeypatch.setenv("COSMIC2_UPDATE_API_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    au._token_cache.clear()
    try:
        assert au._token() is None
        assert "Authorization" not in au._api_headers()
    finally:
        au._token_cache.clear()


# ---------------------------------------------------------------- a fake installation and API

def _zip_bytes(launcher_name: str, marker=True, extra=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"COSMIC2-Explorer/{launcher_name}", b"new build")
        if marker:
            z.writestr("COSMIC2-Explorer/INSTALL_FOLDER.json", json.dumps({"build": {"tag": "v0.0.1-build.2"}}))
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


class _Api:
    """A local server answering /repos/<repo>/releases and serving the assets."""

    def __init__(self):
        self.files = {}
        self.releases = []
        self.requests = []
        api = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                api.requests.append((self.path, self.headers.get("Authorization")))
                path = self.path.split("?")[0]
                if path == f"/repos/{au.REPO}/releases":
                    body, ctype = json.dumps(api.releases).encode(), "application/json"
                elif path in api.files:
                    body, ctype = api.files[path], "application/octet-stream"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def release(self, tag, data: bytes, digest="good", sums=False, name=None):
        name = name or f"COSMIC2-Explorer-0.0.1-{PLAT}.zip"
        sha = hashlib.sha256(data).hexdigest()
        self.files[f"/dl/{tag}/{name}"] = data
        asset = {"name": name, "size": len(data), "browser_download_url": f"{self.base}/dl/{tag}/{name}",
                 "url": f"{self.base}/api-asset/{name}"}
        if digest == "good":
            asset["digest"] = f"sha256:{sha}"
        elif digest:
            asset["digest"] = digest
        assets = [asset]
        if sums:
            text = f"{sha}  {name}\n".encode()
            self.files[f"/dl/{tag}/SHA256SUMS.txt"] = text
            assets.append({"name": "SHA256SUMS.txt", "size": len(text),
                           "browser_download_url": f"{self.base}/dl/{tag}/SHA256SUMS.txt"})
        self.releases.append({"tag_name": tag, "name": f"COSMIC-2 Explorer {tag}", "prerelease": True,
                              "body": "### Changes\n- A new thing", "html_url": f"{self.base}/rel/{tag}",
                              "assets": assets})

    def close(self):
        self.server.shutdown()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """An installed build v0.0.1-build.1 in tmp/apps/COSMIC2-Explorer and a fake API."""
    root = tmp_path / "apps" / "COSMIC2-Explorer"
    root.mkdir(parents=True)
    au.launcher(root).write_bytes(b"old build")
    (root / au.MARKER).write_text("{}")
    upd = tmp_path / "data-updates"
    monkeypatch.setattr(au, "UPDATES_DIR", upd)
    monkeypatch.setattr(au, "STATE_PATH", upd / "state.json")
    monkeypatch.setattr(au, "install_root", lambda: root)
    monkeypatch.setattr(au, "platform_tag", lambda: PLAT)
    monkeypatch.setitem(au.BUILD, "tag", "v0.0.1-build.1")
    api = _Api()
    monkeypatch.setenv("COSMIC2_UPDATE_API_URL", api.base)
    au._token_cache.clear()
    yield root, api
    api.close()


def test_install_problems(fake, monkeypatch, tmp_path):
    root, _ = fake
    assert au.install_problem() is None
    monkeypatch.setitem(au.BUILD, "tag", None)
    assert "not a published build" in au.install_problem()
    monkeypatch.setitem(au.BUILD, "tag", "v0.0.1-build.1")
    (root / au.MARKER).unlink()
    assert au.MARKER in au.install_problem()        # an exe copied out of its folder
    (root / au.MARKER).write_text("{}")
    monkeypatch.setattr(au, "DATA_ROOT", root / "data")
    assert "data folder" in au.install_problem()


def test_check_downloads_verifies_and_stages_beside_the_install(fake):
    root, api = fake
    data = _zip_bytes(au.launcher(root).name)
    api.release("v0.0.1-build.1", _zip_bytes(au.launcher(root).name))
    api.release("v0.0.1-build.2", data)
    before = sorted(p.name for p in DATA_ROOT.iterdir())
    res = au.check_and_stage(force=True)
    assert res == {"result": "staged", "tag": "v0.0.1-build.2"}
    staged = au.staged_dir(root)
    assert au.launcher(staged).read_bytes() == b"new build"
    assert au.launcher(root).read_bytes() == b"old build"        # installed at the next start
    st = au.load_state()
    assert st["staged"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert st["staged"]["notes"].startswith("### Changes") and st["last_check"]
    assert not list(au.UPDATES_DIR.glob("*.part"))
    assert sorted(p.name for p in DATA_ROOT.iterdir()) == before     # the data folder is not touched
    assert au.check_and_stage(force=True)["result"] == "already staged"
    # anonymous, as for a public repository
    assert all(auth is None for _, auth in api.requests)


def test_latest_build_stages_nothing(fake):
    root, api = fake
    api.release("v0.0.1-build.1", _zip_bytes(au.launcher(root).name))
    assert au.check_and_stage(force=True)["result"] == "latest"
    assert not au.staged_dir(root).exists()
    assert not au.due()                                   # counted as this week's check


def test_wrong_digest_is_refused(fake):
    root, api = fake
    api.release("v0.0.1-build.2", _zip_bytes(au.launcher(root).name), digest="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        au.check_and_stage(force=True)
    assert not au.staged_dir(root).exists()
    assert not list(au.UPDATES_DIR.glob("*.part"))
    assert "staged" not in au.load_state()


def test_sha256sums_file_is_used_without_a_github_digest(fake):
    root, api = fake
    api.release("v0.0.1-build.2", _zip_bytes(au.launcher(root).name), digest=None, sums=True)
    assert au.check_and_stage(force=True)["result"] == "staged"


def test_a_release_without_any_digest_is_not_installed(fake):
    root, api = fake
    api.release("v0.0.1-build.2", _zip_bytes(au.launcher(root).name), digest=None)
    res = au.check_and_stage(force=True)
    assert res["result"] == "error" and "SHA-256" in res["reason"]
    assert not au.staged_dir(root).exists()


def test_a_release_still_uploading_is_looked_at_again(fake):
    root, api = fake
    api.release("v0.0.1-build.2", _zip_bytes(au.launcher(root).name), name="COSMIC2-Explorer-0.0.1-macos-arm64.zip")
    res = au.check_and_stage(force=True)
    assert res["result"] == "error" and PLAT in res["reason"]
    assert au.due()                                       # not counted as a check


def test_archive_escaping_its_folder_or_without_marker_is_refused(fake):
    root, api = fake
    api.release("v0.0.1-build.2", _zip_bytes(au.launcher(root).name, extra={"../evil.txt": "x"}))
    with pytest.raises(ValueError, match="outside"):
        au.check_and_stage(force=True)
    api.releases.clear()
    api.release("v0.0.1-build.3", _zip_bytes(au.launcher(root).name, marker=False))
    with pytest.raises(ValueError, match="INSTALL_FOLDER"):
        au.check_and_stage(force=True)
    assert not au.staged_dir(root).exists()


def test_weekly_schedule_and_the_setting(fake, monkeypatch):
    root, api = fake
    assert au.due()
    au.save_state({"last_check": 1000.0})
    assert au.due(now=1000.0 + au.CHECK_EVERY_S)
    assert not au.due(now=1000.0 + au.CHECK_EVERY_S - 60)
    monkeypatch.setattr(SETTINGS, "auto_update", False)
    assert not au.due(now=1e12)
    assert au.check_and_stage(force=False)["result"] == "disabled"


def test_start_up_hands_over_then_the_new_build_finishes(fake, monkeypatch):
    root, api = fake
    api.release("v0.0.1-build.2", _zip_bytes(au.launcher(root).name))
    au.check_and_stage(force=True)
    started = []
    monkeypatch.setattr(au.subprocess, "Popen", lambda cmd, **kw: started.append((cmd, kw)))
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Temp\_MEI123")
    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "1")
    assert au.install_staged_on_start(["--port", "8123", "it's"]) is True
    env = started[0][1]["env"]
    # the new one-file build must not take itself for a child of the old one
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert not [k for k in env if k.startswith("_PYI_")]
    assert env.get("COSMIC2_EXPLORER_HOME") == au.os.environ.get("COSMIC2_EXPLORER_HOME")
    script = au.UPDATES_DIR / ("install_update.ps1" if au.sys.platform == "win32" else "install_update.sh")
    text = script.read_text(encoding="utf-8-sig")
    assert str(au.staged_dir(root)) in text and str(au.previous_dir(root)) in text
    assert "8123" in text and ("'it''s'" in text or "'it'\\''s'" in text)
    assert str(DATA_ROOT) not in text.replace(str(au.UPDATES_DIR), "")   # nothing else in the data folder
    # the swap (done by the script) and the new build's first start
    root.rename(au.previous_dir(root))
    au.staged_dir(root).rename(root)
    monkeypatch.setitem(au.BUILD, "tag", "v0.0.1-build.2")
    assert au.install_staged_on_start([]) is False
    au.finish_install()
    st = au.load_state()
    assert "staged" not in st and st["installed"]["tag"] == "v0.0.1-build.2"
    assert st["installed"]["previous"] == "v0.0.1-build.1"
    assert not au.previous_dir(root).exists()
    assert au.installed_notes()["notes"].startswith("### Changes")


def test_update_endpoints_from_source_copy():
    import requests, os
    base = os.environ["COSMIC2_TEST_BASE"]
    st = requests.get(f"{base}/api/update/status", timeout=10).json()
    assert st["tag"] is None and "not a published build" in st["problem"]
    assert st["enabled"] is True
    r = requests.post(f"{base}/api/update/check", timeout=10)
    assert r.status_code == 409 and "not a published build" in r.json()["detail"]


def test_linux_tar_archive_unpacks_with_permissions(tmp_path):
    import tarfile
    src = tmp_path / "src" / "COSMIC2-Explorer"
    src.mkdir(parents=True)
    au.launcher(src).write_bytes(b"app")
    (src / au.MARKER).write_text("{}")
    arc = tmp_path / "COSMIC2-Explorer-0.0.1-linux-x64.tar.gz.part"
    with tarfile.open(arc, "w:gz") as t:
        info = t.gettarinfo(str(au.launcher(src)), f"COSMIC2-Explorer/{au.launcher(src).name}")
        info.mode = 0o755
        with open(au.launcher(src), "rb") as fh:
            t.addfile(info, fh)
        t.add(src / au.MARKER, f"COSMIC2-Explorer/{au.MARKER}")
    top = au.extract(arc, tmp_path / "out")
    assert top.name == "COSMIC2-Explorer" and au.launcher(top).read_bytes() == b"app"
    if au.os.name != "nt":
        assert au.os.stat(au.launcher(top)).st_mode & 0o111
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as t:
        link = tarfile.TarInfo("COSMIC2-Explorer/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        t.addfile(link)
    with pytest.raises(ValueError, match="plain file"):
        au.extract(bad, tmp_path / "out2")
