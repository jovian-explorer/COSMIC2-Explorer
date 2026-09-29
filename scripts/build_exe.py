"""Build the standalone COSMIC-2 Explorer app for the current OS.

    pip install -e .[build]
    python scripts/build_exe.py            # build into dist/
    python scripts/build_exe.py --archive  # also write a release archive

Output (see packaging/cosmic2-explorer.spec):
    Windows  dist/COSMIC2-Explorer.exe
    Linux    dist/COSMIC2-Explorer
    macOS    dist/COSMIC2-Explorer.app

With --archive, dist/COSMIC2-Explorer-<version>-<os>-<arch>.zip (.tar.gz on
Linux, so the executable bit survives) is written next to it.
"""
from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAME = "COSMIC2-Explorer"


def _version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def _os_tag() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def _arch() -> str:
    m = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(m, m)


def build() -> Path:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
         "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
         str(ROOT / "packaging" / "cosmic2-explorer.spec")],
        check=True, cwd=ROOT,
    )
    out = {"win32": DIST / f"{NAME}.exe", "darwin": DIST / f"{NAME}.app"}.get(sys.platform, DIST / NAME)
    if not out.exists():
        raise SystemExit(f"build finished but {out} is missing")
    return out


def archive(artifact: Path) -> Path:
    stem = DIST / f"{NAME}-{_version()}-{_os_tag()}-{_arch()}"
    if sys.platform == "darwin":
        # ditto keeps the framework symlinks inside the .app intact.
        dest = Path(f"{stem}.zip")
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(artifact), str(dest)], check=True)
    elif sys.platform == "win32":
        dest = Path(f"{stem}.zip")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(artifact, artifact.name)
    else:
        dest = Path(f"{stem}.tar.gz")
        with tarfile.open(dest, "w:gz") as t:
            t.add(artifact, artifact.name)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", action="store_true", help="also write a release archive")
    args = ap.parse_args()
    if not _has_pyinstaller():
        raise SystemExit("PyInstaller is not installed: pip install -e .[build]")
    artifact = build()
    print(f"[build] {artifact}")
    if args.archive:
        print(f"[build] {archive(artifact)}")
    return 0


def _has_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
