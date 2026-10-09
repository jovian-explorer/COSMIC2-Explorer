"""Build the standalone COSMIC-2 Explorer app for the current OS.

    pip install -e .[build]
    python scripts/build_exe.py            # build into dist/
    python scripts/build_exe.py --archive  # also write a release archive
    python scripts/build_exe.py --archive --tag v0.0.2   # a release build

Output (see packaging/cosmic2-explorer.spec):
    Windows  dist/COSMIC2-Explorer/COSMIC2-Explorer.exe  (+ _internal/)
    Linux    dist/COSMIC2-Explorer/COSMIC2-Explorer      (+ _internal/)
    macOS    dist/COSMIC2-Explorer.app

With --archive, dist/COSMIC2-Explorer-<version>-<os>-<arch>.zip (.tar.gz on
Linux, so the executable bit survives) is written next to it.  The archive
holds one folder, COSMIC2-Explorer/, with the app (on Windows and Linux the
whole one-folder build) and INSTALL_FOLDER.json; the
automatic update (cosmic2/autoupdate.py) replaces only a folder that holds
that file, so an app copied elsewhere (the Desktop, Downloads) never has its
surroundings moved.

--tag stamps the build with its release tag (``v<version>`` or
``v<version>-build.<n>``, <version> as in pyproject.toml) in
src/cosmic2/_build.py, which is removed again after the build.  Only a
stamped build updates itself; the release workflow passes the pushed tag.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import shutil
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAME = "COSMIC2-Explorer"
BUILD_FILE = ROOT / "src" / "cosmic2" / "_build.py"
MARKER = "INSTALL_FOLDER.json"
TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)(?:-build\.(\d+))?$")


def _version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def _os_tag() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def _arch() -> str:
    m = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(m, m)


def check_tag(tag: str) -> None:
    """A release tag must be v<version> or v<version>-build.<n> for the version
    in pyproject.toml, so that the updater can order the releases."""
    m = TAG_RE.match(tag)
    if not m:
        raise SystemExit(f"tag {tag!r} is not v<version> or v<version>-build.<n>")
    if m.group(1) != _version():
        raise SystemExit(f"tag {tag!r} does not match version {_version()} in pyproject.toml")


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def stamp(tag: str) -> dict:
    info = {"tag": tag, "commit": _git_commit(),
            "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")}
    BUILD_FILE.write_text('"""Written by scripts/build_exe.py --tag for a release build."""\n'
                          f"BUILD = {info!r}\n", encoding="utf-8")
    return info


def build() -> Path:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
         "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
         str(ROOT / "packaging" / "cosmic2-explorer.spec")],
        check=True, cwd=ROOT,
    )
    out = {"win32": DIST / NAME / f"{NAME}.exe", "darwin": DIST / f"{NAME}.app"}.get(sys.platform, DIST / NAME / NAME)
    if not out.exists():
        raise SystemExit(f"build finished but {out} is missing")
    return out


def archive(artifact: Path, build_info: dict | None = None) -> Path:
    """The release archive: COSMIC2-Explorer/<app> and COSMIC2-Explorer/INSTALL_FOLDER.json."""
    stem = DIST / f"{NAME}-{_version()}-{_os_tag()}-{_arch()}"
    marker = DIST / MARKER
    marker.write_text(json.dumps({
        "app": NAME, "version": _version(), "build": build_info or {},
        "note": "This folder is the COSMIC-2 Explorer installation. The automatic update "
                "replaces the whole folder with the new build, so keep nothing else in it. "
                "Your data and settings are kept elsewhere and are never touched.",
    }, indent=2), encoding="utf-8")
    try:
        if sys.platform == "darwin":
            # ditto keeps the framework symlinks inside the .app intact.
            staging = DIST / "archive-staging" / NAME
            shutil.rmtree(staging.parent, ignore_errors=True)
            staging.mkdir(parents=True)
            subprocess.run(["ditto", str(artifact), str(staging / artifact.name)], check=True)
            shutil.copy2(marker, staging / MARKER)
            dest = Path(f"{stem}.zip")
            dest.unlink(missing_ok=True)
            subprocess.run(["ditto", "-c", "-k", "--keepParent", str(staging), str(dest)], check=True)
            shutil.rmtree(staging.parent, ignore_errors=True)
        else:
            # the one-folder build: the executable and everything beside it
            files = sorted(p for p in artifact.parent.rglob("*") if p.is_file())
            arcs = [(p, f"{NAME}/{p.relative_to(artifact.parent).as_posix()}") for p in files]
            arcs.append((marker, f"{NAME}/{MARKER}"))
            if sys.platform == "win32":
                dest = Path(f"{stem}.zip")
                with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                    for p, arc in arcs:
                        z.write(p, arc)
            else:
                dest = Path(f"{stem}.tar.gz")
                with tarfile.open(dest, "w:gz") as t:
                    for p, arc in arcs:
                        t.add(p, arc)
    finally:
        marker.unlink(missing_ok=True)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", action="store_true", help="also write a release archive")
    ap.add_argument("--tag", default="", help="release tag to stamp into the build "
                    "(v<version> or v<version>-build.<n>); only stamped builds update themselves")
    args = ap.parse_args()
    if not _has_pyinstaller():
        raise SystemExit("PyInstaller is not installed: pip install -e .[build]")
    info = None
    if args.tag:
        check_tag(args.tag)
        info = stamp(args.tag)
        print(f"[build] stamped {info}")
    try:
        artifact = build()
    finally:
        if info is not None:
            BUILD_FILE.unlink(missing_ok=True)
    print(f"[build] {artifact}")
    if args.archive:
        print(f"[build] {archive(artifact, info)}")
    return 0


def _has_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
