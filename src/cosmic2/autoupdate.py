"""Weekly automatic update of a published build.

Once a week (Settings > Updates, on by default; *Check now* any time) a published
build of COSMIC-2 Explorer asks GitHub for the releases of
jovian-explorer/COSMIC2-Explorer, anonymously like any visitor (a ``GITHUB_TOKEN``
or ``GH_TOKEN`` in the environment, or a logged-in ``gh``, is used when present,
and only towards api.github.com).  When the newest release is newer than this
build, the archive for this platform (``COSMIC2-Explorer-<version>-<os>-<arch>.zip``,
``.tar.gz`` on Linux; scripts/build_exe.py) is downloaded into the data folder
(``updates/``), checked against its size and the SHA-256 digest GitHub lists for it
(or the release's SHA256SUMS.txt; an archive with neither is refused), and unpacked
beside the installation (``<folder>.update``).  The next time the app starts it
hands over to a small script that waits for it to exit, renames the installation to
``<folder>.previous``, moves the new one into its place and starts it again with
the same arguments; the new build then deletes the previous one.

Only the installation folder is replaced, and only one that holds the
``INSTALL_FOLDER.json`` the release archive puts there (an app copied to the
Desktop or Downloads is never updated, so nothing around it moves).  The data
folder (downloads, exports, index, settings.json, logs) is a different folder and
is never touched; an installation that holds the data folder
(COSMIC2_EXPLORER_HOME inside it) or cannot be renamed is not updated.  Copies run
from source or built without a release tag are never updated.

Releases are ordered by their tags, ``v<version>`` and ``v<version>-build.<n>``
(pre-releases included: every 0.x release is one).  ``COSMIC2_UPDATE_API_URL``
replaces https://api.github.com (a local test server).

State (last check, the staged build, the notes of the installed one) is kept in
``updates/state.json`` in the data folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import APP_VERSION, DATA_ROOT, SETTINGS

try:
    from ._build import BUILD  # type: ignore[import-not-found]  # release builds only
except ImportError:
    BUILD: Dict[str, Any] = {}

REPO = "jovian-explorer/COSMIC2-Explorer"
GITHUB_API = "https://api.github.com"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
NAME = "COSMIC2-Explorer"
MARKER = "INSTALL_FOLDER.json"
UPDATES_DIR = DATA_ROOT / "updates"
STATE_PATH = UPDATES_DIR / "state.json"
CHECK_EVERY_S = 7 * 24 * 3600

_lock = threading.Lock()
_job: Dict[str, Any] = {"running": False, "message": "", "done": 0, "total": 0, "error": None,
                        "result": None}


def api_base() -> str:
    return (os.environ.get("COSMIC2_UPDATE_API_URL") or GITHUB_API).rstrip("/")


def this_tag() -> Optional[str]:
    """The release tag this build was stamped with, or None (source, unstamped build)."""
    tag = BUILD.get("tag")
    return tag if tag and parse_tag(tag)[0] else None


# ---------------------------------------------------------------- tags

_TAG_RE = re.compile(r"^v?(\d+(?:\.\d+)*)(?:-build\.(\d+))?$")


def parse_tag(tag: str) -> Tuple[Tuple[int, ...], int]:
    """"v0.0.2-build.7" -> ((0, 0, 2), 7); a plain version tag has build 0; a tag of
    another form -> ((), 0)."""
    m = _TAG_RE.match((tag or "").strip())
    if not m:
        return (), 0
    return tuple(int(x) for x in m.group(1).split(".")), int(m.group(2) or 0)


def is_newer(tag: str, than: Optional[str]) -> bool:
    new, old = parse_tag(tag), parse_tag(than or "")
    return bool(new[0]) and bool(old[0]) and new > old


def newest_release(releases: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The published (not draft) release with the highest tag."""
    ok = [r for r in releases or [] if isinstance(r, dict) and not r.get("draft")
          and parse_tag(r.get("tag_name", ""))[0]]
    if not ok:
        return None
    return max(ok, key=lambda r: (parse_tag(r["tag_name"]), r.get("published_at") or ""))


# ---------------------------------------------------------------- state

def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: Dict[str, Any]) -> None:
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, STATE_PATH)


def installed_notes(tag: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Release notes of this build, when the updater installed it."""
    tag = tag if tag is not None else this_tag()
    inst = load_state().get("installed") or {}
    if tag and inst.get("tag") == tag:
        return {"tag": inst.get("tag"), "name": inst.get("name"), "notes": inst.get("notes") or "",
                "url": inst.get("url"), "previous": inst.get("previous")}
    return None


# ---------------------------------------------------------------- this installation

def platform_tag() -> str:
    """The "<os>-<arch>" part of this platform's archive name (scripts/build_exe.py)."""
    os_tag = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    m = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(m, m)
    return f"{os_tag}-{arch}"


def install_root() -> Optional[Path]:
    """The folder unpacked from the release archive (holding COSMIC2-Explorer.exe,
    COSMIC2-Explorer or COSMIC2-Explorer.app).  None when not a frozen build."""
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent.parent
        return None
    return exe.parent


def launcher(root: Path) -> Path:
    if sys.platform == "darwin":
        return root / f"{NAME}.app"
    return root / (f"{NAME}.exe" if sys.platform == "win32" else NAME)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def install_problem(root: Optional[Path] = None) -> Optional[str]:
    """Why this copy cannot update itself, or None."""
    if this_tag() is None:
        return "this copy is not a published build (it runs from source or was built without a release tag)"
    root = root or install_root()
    if root is None:
        return "the installation folder could not be found"
    if not (root / MARKER).is_file():
        return (f"{root} is not the folder unpacked from the release archive ({MARKER} is missing); "
                "update by hand from the releases page")
    if _inside(DATA_ROOT, root):
        return "the data folder is inside the installation folder"
    if not launcher(root).exists():
        return f"{launcher(root).name} is not in {root}"
    if not os.access(root.parent, os.W_OK):
        return f"{root.parent} is not writable"
    return None


def staged_dir(root: Path) -> Path:
    return root.parent / f"{root.name}.update"


def previous_dir(root: Path) -> Path:
    return root.parent / f"{root.name}.previous"


# ---------------------------------------------------------------- talking to GitHub

_token_cache: Dict[str, Optional[str]] = {}


def _token() -> Optional[str]:
    """A GitHub token for api.github.com when one is at hand (not needed for a public
    repository; raises the anonymous rate limit of 60 requests an hour)."""
    if api_base() != GITHUB_API:
        return None                      # never send a token to another server
    if "t" not in _token_cache:
        tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not tok and shutil.which("gh"):
            try:
                kw: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": 5}
                if sys.platform == "win32":
                    kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
                r = subprocess.run(["gh", "auth", "token"], **kw)
                tok = r.stdout.strip() if r.returncode == 0 else None
            except (OSError, subprocess.SubprocessError):
                tok = None
        _token_cache["t"] = tok or None
    return _token_cache["t"]


def _session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = SETTINGS.user_agent
    return s


def _api_headers() -> Dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    tok = _token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def fetch_releases() -> List[Dict[str, Any]]:
    r = _session().get(f"{api_base()}/repos/{REPO}/releases", params={"per_page": 30},
                       headers=_api_headers(), timeout=min(SETTINGS.request_timeout_s, 30))
    if r.status_code == 404:
        raise RuntimeError(f"no releases found at {api_base()} for {REPO}")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError("unexpected answer from the releases API")
    return data


def pick_asset(release: Dict[str, Any], tag: Optional[str] = None) -> Optional[Dict[str, Any]]:
    tag = tag or platform_tag()
    for a in release.get("assets") or []:
        name = a.get("name", "")
        if name.startswith(NAME + "-") and (name.endswith(f"-{tag}.zip") or name.endswith(f"-{tag}.tar.gz")):
            return a
    return None


def _download(asset: Dict[str, Any], dest, progress=None) -> None:
    """Download an asset to ``dest`` (a path, or an open binary file)."""
    # With a token (a private repository) the browser URL does not work: the API URL
    # with Accept: octet-stream answers with a redirect to the file.
    if _token() and asset.get("url"):
        url, headers = asset["url"], {**_api_headers(), "Accept": "application/octet-stream"}
    else:
        url, headers = asset["browser_download_url"], {}
    total = int(asset.get("size") or 0)
    with _session().get(url, headers=headers, stream=True, timeout=SETTINGS.request_timeout_s) as r:
        r.raise_for_status()
        done = 0
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total, f"Downloading {asset['name']}")


def expected_sha256(release: Dict[str, Any], asset: Dict[str, Any]) -> Optional[str]:
    """The SHA-256 the release lists for ``asset``: GitHub's own ``digest``, else the
    line for it in the release's SHA256SUMS.txt."""
    digest = asset.get("digest") or ""
    algo, _, value = digest.partition(":")
    if algo.lower() == "sha256" and re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return value.lower()
    sums = next((a for a in release.get("assets") or [] if a.get("name") == "SHA256SUMS.txt"), None)
    if sums is None:
        return None
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = UPDATES_DIR / "SHA256SUMS.txt.part"
    try:
        _download(sums, tmp)
        for line in tmp.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == asset["name"] and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
                return parts[0].lower()
    finally:
        tmp.unlink(missing_ok=True)
    return None


# ---------------------------------------------------------------- checking an archive

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, size: Optional[int], sha256: Optional[str]) -> None:
    """Raise ValueError unless the file has the listed size and SHA-256 digest and is
    a readable archive."""
    if not sha256:
        raise ValueError("the release lists no SHA-256 digest for the download, so it cannot be checked")
    if size is not None and path.stat().st_size != int(size):
        raise ValueError(f"the download has {path.stat().st_size} bytes, the release lists {size}")
    got = sha256_of(path)
    if got.lower() != sha256.lower():
        raise ValueError(f"SHA-256 {got} does not match the release's {sha256}")
    if path.name.removesuffix(".part").endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"{bad} in the download is damaged")
    else:
        with tarfile.open(path) as tf:
            tf.getmembers()


def extract(archive: Path, dest: Path) -> Path:
    """Unpack the release archive into ``dest`` and return its top folder (the one
    holding the app and INSTALL_FOLDER.json).  macOS uses ditto (keeps the app
    bundle's links and permissions); elsewhere the files' Unix permissions are
    restored from the zip.  Nothing is written outside ``dest``."""
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    root = dest.resolve()
    name = archive.name.removesuffix(".part")
    if name.endswith(".zip") and sys.platform == "darwin":
        subprocess.run(["ditto", "-x", "-k", str(archive), str(dest)], check=True)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                target = (dest / info.filename).resolve()
                if not _inside(target, root):
                    raise ValueError(f"{info.filename} would be written outside the update folder")
                zf.extract(info, dest)
                mode = (info.external_attr >> 16) & 0o777
                if mode and os.name != "nt":
                    os.chmod(target, mode)
    else:
        with tarfile.open(archive) as tf:
            members = tf.getmembers()
            for m in members:
                if not _inside((dest / m.name).resolve(), root) or m.issym() or m.islnk() or m.isdev():
                    raise ValueError(f"{m.name} is not a plain file or folder inside the update folder")
            if hasattr(tarfile, "data_filter"):           # Python 3.10.12+, 3.11.4+
                tf.extractall(dest, members=members, filter="data")
            else:
                tf.extractall(dest, members=members)
    tops = [p for p in dest.iterdir() if p.is_dir()]
    top = tops[0] if len(tops) == 1 else dest
    if not launcher(top).exists():
        raise ValueError(f"the release has no {launcher(top).name}")
    if not (top / MARKER).is_file():
        raise ValueError(f"the release has no {MARKER}")
    return top


# ---------------------------------------------------------------- checking and downloading

def status() -> Dict[str, Any]:
    st = load_state()
    last = st.get("last_check")
    staged = st.get("staged") or None
    return {"enabled": bool(SETTINGS.auto_update), "problem": install_problem(),
            "last_check": last, "next_check": (last + CHECK_EVERY_S) if last else None,
            "staged": None if not staged else {k: staged.get(k) for k in ("tag", "name", "staged_at")},
            "latest_seen": st.get("latest_seen"),
            "job": dict(_job), "version": APP_VERSION, "tag": this_tag(),
            "commit": BUILD.get("commit"), "build_date": BUILD.get("date"),
            "releases_page": RELEASES_PAGE}


def due(now: Optional[float] = None) -> bool:
    if not SETTINGS.auto_update or install_problem() is not None:
        return False
    last = load_state().get("last_check")
    return not last or (now or time.time()) - float(last) >= CHECK_EVERY_S


def _progress(done: int, total: int, message: str) -> None:
    _job.update(done=done, total=total, message=message)


def check_and_stage(force: bool = False, releases: Optional[List[Dict[str, Any]]] = None,
                    progress: Callable[[int, int, str], None] = _progress) -> Dict[str, Any]:
    """Look for a newer published build and, when there is one, download, verify and
    unpack it beside the installation.  Returns {"result": "latest" | "staged" |
    "already staged" | "disabled" | "error", ...}."""
    problem = install_problem()
    if problem:
        return {"result": "disabled", "reason": problem}
    if not force and not due():
        return {"result": "disabled", "reason": "checked less than a week ago"}
    root = install_root()
    assert root is not None
    rel = newest_release(releases if releases is not None else fetch_releases())
    st = load_state()
    if rel is None:
        st["last_check"] = time.time()
        save_state(st)
        return {"result": "latest", "tag": None}
    tag = rel["tag_name"]
    st["latest_seen"] = tag
    if not is_newer(tag, this_tag()):
        st["last_check"] = time.time()
        save_state(st)
        return {"result": "latest", "tag": tag}
    staged = st.get("staged") or {}
    if staged.get("tag") == tag and Path(staged.get("path", "")).exists():
        st["last_check"] = time.time()
        save_state(st)
        return {"result": "already staged", "tag": tag}
    asset = pick_asset(rel)
    if asset is None:
        # not counted as a check: a release is listed before all its files are uploaded,
        # so the hourly scheduler looks again
        save_state(st)
        return {"result": "error", "reason": f"release {tag} has no download for {platform_tag()} yet"}
    sha = expected_sha256(rel, asset)
    if not sha:
        save_state(st)
        return {"result": "error", "reason": f"release {tag} lists no SHA-256 digest for {asset['name']} yet"}
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    part = UPDATES_DIR / (asset["name"] + ".part")
    total = int(asset.get("size") or 0)
    progress(0, total, f"Downloading {asset['name']}")
    try:
        _download(asset, part, progress)
        progress(total, total, "Checking the download")
        verify(part, asset.get("size"), sha)
        progress(total, total, "Unpacking")
        work = UPDATES_DIR / "unpacked"
        top = extract(part, work)
        target = staged_dir(root)
        shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(top), str(target))
        shutil.rmtree(work, ignore_errors=True)
    finally:
        part.unlink(missing_ok=True)
    st["last_check"] = time.time()
    st["staged"] = {"tag": tag, "name": rel.get("name") or tag, "notes": rel.get("body") or "",
                    "url": rel.get("html_url"), "path": str(target), "sha256": sha,
                    "size": asset.get("size"), "asset": asset["name"], "staged_at": time.time(),
                    "from": this_tag()}
    save_state(st)
    return {"result": "staged", "tag": tag}


_MESSAGES = {"latest": "This is the latest build",
             "staged": "The new build will be installed when COSMIC-2 Explorer next starts",
             "already staged": "The new build will be installed when COSMIC-2 Explorer next starts"}


def start_check(force: bool = False) -> Dict[str, Any]:
    """Run check_and_stage in the background (one at a time)."""
    with _lock:
        if _job["running"]:
            return status()
        _job.update(running=True, error=None, message="Looking for a newer build", done=0, total=0, result=None)

    def run():
        try:
            res = check_and_stage(force=force)
            _job.update(result=res, message=_MESSAGES.get(res["result"], res.get("reason", "")))
            if res["result"] == "error":
                _job["error"] = res.get("reason")
        except Exception as exc:  # noqa: BLE001 - offline, rate limited, bad download
            _job.update(error=str(exc)[:300], message="")
        finally:
            _job["running"] = False
    threading.Thread(target=run, daemon=True, name="cosmic2-update").start()
    return status()


def scheduler(first_delay_s: float = 60) -> None:
    """Background loop of a running app: the weekly check (first after a minute, so it
    does not compete with start-up), then every hour whether a week has passed."""
    def loop():
        time.sleep(first_delay_s)
        while True:
            try:
                if due():
                    start_check(force=False)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(3600)
    if install_problem() is None:
        threading.Thread(target=loop, daemon=True, name="cosmic2-update-scheduler").start()


# ---------------------------------------------------------------- installing on start-up

def finish_install() -> None:
    """At start-up: when this build is the one that was staged, it has been installed:
    keep its notes for "What's new" and remove the previous installation."""
    st = load_state()
    staged = st.get("staged")
    tag = this_tag()
    if not staged or tag is None or staged.get("tag") != tag:
        return
    st["installed"] = {k: staged.get(k) for k in ("tag", "name", "notes", "url")}
    st["installed"].update(installed_at=time.time(), previous=staged.get("from"))
    st.pop("staged", None)
    save_state(st)
    root = install_root()
    if root is not None:
        shutil.rmtree(previous_dir(root), ignore_errors=True)
        shutil.rmtree(staged_dir(root), ignore_errors=True)


def _pids_to_wait_for() -> List[int]:
    """This process and, in a one-file build, the bootloader process that started it
    and holds the executable open until this one has exited."""
    pids = [os.getpid()]
    meipass = getattr(sys, "_MEIPASS", None)
    root = install_root()
    if meipass and root is not None and not _inside(Path(meipass), root):
        ppid = os.getppid()
        if ppid and ppid != os.getpid():
            pids.append(ppid)
    return pids


def helper_script(root: Path, staged: Path, previous: Path, args: List[str],
                  pids: Optional[List[int]] = None) -> Tuple[Path, List[str]]:
    """(script path, command) for the platform's swap-and-restart script."""
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    log = UPDATES_DIR / "install.log"
    pids = pids or _pids_to_wait_for()
    if sys.platform == "win32":
        def q(p):
            return "'" + str(p).replace("'", "''") + "'"
        arglist = ", ".join(q(a) for a in args)
        exe = launcher(root)
        waits = "\n".join(
            f"try {{ Wait-Process -Id {p} -Timeout 120 -ErrorAction SilentlyContinue }} catch {{ }}" for p in pids)
        body = f"""$ErrorActionPreference = 'Stop'
function Log($m) {{ Add-Content -LiteralPath {q(log)} -Value ("[" + (Get-Date -Format s) + "] " + $m) }}
function Start-App {{ if ({len(args)} -gt 0) {{ Start-Process -FilePath {q(exe)} -WorkingDirectory {q(root)} -ArgumentList @({arglist}) }} else {{ Start-Process -FilePath {q(exe)} -WorkingDirectory {q(root)} }} }}
Log 'waiting for COSMIC-2 Explorer (process {", ".join(map(str, pids))}) to exit'
{waits}
if (Test-Path -LiteralPath {q(previous)}) {{ Remove-Item -LiteralPath {q(previous)} -Recurse -Force }}
$moved = $false
for ($i = 0; $i -lt 60 -and -not $moved; $i++) {{
  try {{ Move-Item -LiteralPath {q(root)} -Destination {q(previous)}; $moved = $true }} catch {{ Start-Sleep -Milliseconds 500 }}
}}
if (-not $moved) {{ Log 'could not move the installation aside; starting the old build'; Start-App; exit 1 }}
try {{ Move-Item -LiteralPath {q(staged)} -Destination {q(root)} }}
catch {{ Log ('could not move the new build in: ' + $_); Move-Item -LiteralPath {q(previous)} -Destination {q(root)}; Start-App; exit 1 }}
Log 'installed; starting the new build'
Start-App
"""
        script = UPDATES_DIR / "install_update.ps1"
        script.write_text(body, encoding="utf-8-sig")
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
               "-WindowStyle", "Hidden", "-File", str(script)]
        return script, cmd

    def q(p):
        return "'" + str(p).replace("'", "'\\''") + "'"
    if sys.platform == "darwin":
        start = f"open -n {q(launcher(root))}" + (" --args " + " ".join(q(a) for a in args) if args else "")
    else:
        start = f"nohup {q(launcher(root))} {' '.join(q(a) for a in args)} >/dev/null 2>&1 &"
    waits = "\n".join(
        f"n=0; while kill -0 {p} 2>/dev/null && [ $n -lt 240 ]; do sleep 0.5; n=$((n+1)); done" for p in pids)
    body = f"""#!/bin/sh
log() {{ echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $1" >> {q(log)}; }}
start_app() {{
  {start}
}}
log 'waiting for COSMIC-2 Explorer (process {" ".join(map(str, pids))}) to exit'
{waits}
rm -rf {q(previous)}
if ! mv {q(root)} {q(previous)}; then log 'could not move the installation aside'; start_app; exit 1; fi
if ! mv {q(staged)} {q(root)}; then log 'could not move the new build in'; mv {q(previous)} {q(root)}; start_app; exit 1; fi
log 'installed; starting the new build'
start_app
"""
    script = UPDATES_DIR / "install_update.sh"
    script.write_text(body, encoding="utf-8")
    os.chmod(script, 0o755)
    return script, ["/bin/sh", str(script)]


def install_staged_on_start(args: List[str]) -> bool:
    """At start-up of a published build, before anything else: when a newer build is
    staged and complete, start the swap script and return True (the caller exits at
    once; the script starts the new build with the same ``args``)."""
    if install_problem() is not None:
        return False
    st = load_state()
    staged = st.get("staged")
    root = install_root()
    if not staged or root is None:
        return False
    path = Path(staged.get("path", ""))
    if not is_newer(staged.get("tag", ""), this_tag()) or path != staged_dir(root) \
            or not launcher(path).exists() or not (path / MARKER).is_file():
        return False
    _, cmd = helper_script(root, path, previous_dir(root), list(args))
    kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                          "close_fds": True, "cwd": str(UPDATES_DIR)}
    if sys.platform == "win32":
        # a new process group without a window (DETACHED_PROCESS would leave PowerShell
        # without the console it needs), out of the app's job object if allowed
        flags = 0x00000200 | 0x08000000                     # CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW
        try:
            subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kw)   # CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            subprocess.Popen(cmd, creationflags=flags, **kw)
        return True
    subprocess.Popen(cmd, start_new_session=True, **kw)
    return True
