"""scripts/build_exe.py: release tags and the layout of the release archive,
which the automatic update relies on (one COSMIC2-Explorer/ folder holding the
app and INSTALL_FOLDER.json; the archive named by platform)."""
import importlib.util
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("build_exe", ROOT / "scripts" / "build_exe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tags_must_name_the_project_version():
    b = _load()
    v = b._version()
    b.check_tag(f"v{v}")
    b.check_tag(f"v{v}-build.12")
    for bad in (v, f"v{v}-rc1", "v9.9.9", f"v{v}-build.", "latest"):
        with pytest.raises(SystemExit):
            b.check_tag(bad)


def test_stamp_writes_an_importable_build_file(tmp_path, monkeypatch):
    b = _load()
    target = tmp_path / "_build.py"
    monkeypatch.setattr(b, "BUILD_FILE", target)
    info = b.stamp(f"v{b._version()}-build.3")
    ns = {}
    exec(target.read_text(encoding="utf-8"), ns)
    assert ns["BUILD"] == info and ns["BUILD"]["tag"].endswith("-build.3")


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS archives with ditto")
def test_archive_holds_one_install_folder(tmp_path, monkeypatch):
    b = _load()
    monkeypatch.setattr(b, "DIST", tmp_path)
    app = tmp_path / ("COSMIC2-Explorer.exe" if sys.platform == "win32" else "COSMIC2-Explorer")
    app.write_bytes(b"not really an app")
    dest = b.archive(app, {"tag": "v0.0.1"})
    assert dest.name.startswith(f"COSMIC2-Explorer-{b._version()}-{b._os_tag()}-{b._arch()}.")
    if dest.suffix == ".zip":
        with zipfile.ZipFile(dest) as z:
            names = sorted(z.namelist())
            marker = json.loads(z.read("COSMIC2-Explorer/INSTALL_FOLDER.json"))
    else:
        with tarfile.open(dest) as t:
            names = sorted(t.getnames())
            marker = json.loads(t.extractfile("COSMIC2-Explorer/INSTALL_FOLDER.json").read())
    assert names == sorted([f"COSMIC2-Explorer/{app.name}", "COSMIC2-Explorer/INSTALL_FOLDER.json"])
    assert marker["build"] == {"tag": "v0.0.1"}
    assert not (tmp_path / "INSTALL_FOLDER.json").exists()      # the loose copy is removed
