"""Desktop entry point - this is what the packaged .exe runs.

Starts the FastAPI backend on a free loopback port in a daemon thread, waits
for it to answer, then opens a native window pointed at it via pywebview
(WebView2 on Windows, WebKit on macOS, GTK or Qt on Linux).  If no webview
runtime is available the app falls back to the system browser rather than
failing, so the tool still works.

Explorer double-click fix (2026-09-19):
  When Windows Explorer launches an EXE it sets CWD to Desktop or the user's
  home folder, not to the directory containing the EXE.  For a PyInstaller
  onefile build, sys._MEIPASS is the real resource root, so no path should
  ever be relative to CWD.  Additionally, pywebview's start() can silently
  return without raising (no window, no exception) when the WebView2
  WinForms message loop initialises under the GUI-less Explorer context.
  We detect this by waiting for the window.events.shown event, and fall
  back to the system browser if the window never appears.
"""
from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if getattr(sys, "stdin", None) is None:
    sys.stdin = open(os.devnull, "r")
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# In a PyInstaller build, run from the unpack dir so native DLLs (for example
# WebView2Loader) are found; every resource path is package-relative, so a
# source or pip-installed run never needs to touch the working directory.
if getattr(sys, "frozen", False):
    _CWD_DIR = getattr(sys, "_MEIPASS", str(Path(sys.executable).resolve().parent))
    os.chdir(_CWD_DIR)
    os.environ["PATH"] = _CWD_DIR + os.pathsep + os.environ.get("PATH", "")

from .config import (APP_NAME, APP_TITLE, APP_VERSION, LOG_DIR,
                     DATA_ROOT, ensure_dirs, frontend_dir)
from .server import free_port

STARTUP_TIMEOUT_S = 120   # cold-start of a 198 MB onefile EXE can take 60-90s
# How long to wait for the pywebview window to appear after start() returns.
_WEBVIEW_SHOWN_TIMEOUT_S = 60


# ── Logging helpers ───────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    """Append a timestamped line to the startup log (always succeeds)."""
    try:
        ensure_dirs()
        log_file = LOG_DIR / "startup.log"
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def _log_crash(exc: BaseException) -> Path:
    ensure_dirs()
    path = LOG_DIR / "startup-error.log"
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=fh)
    except Exception:  # noqa: BLE001
        pass
    return path


def _show_error_dialog(title: str, message: str) -> None:
    """Show a Windows message-box so errors are visible when there's no console."""
    try:
        if sys.platform == "win32":
            import ctypes
            # MB_OK | MB_ICONERROR | MB_SETFOREGROUND
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x40000)
    except Exception:  # noqa: BLE001
        pass  # absolute last resort


# ── Backend server ────────────────────────────────────────────────────────────

def _serve(host: str, port: int) -> None:
    import uvicorn
    from .api import app
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _wait_until_up(url: str, timeout: float = STARTUP_TIMEOUT_S) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    return False


# ── pywebview window launch ───────────────────────────────────────────────────

def _launch_webview(url: str) -> bool:
    """Open the application in a native WebView2 window.

    Returns True if the window was shown successfully, False on any failure.
    """
    import webview  # pywebview

    # WebView2 user-data dir must be writable; never rely on CWD.
    wv2_cache = str(DATA_ROOT / "webview2-cache")
    os.makedirs(wv2_cache, exist_ok=True)

    shown_event = threading.Event()

    window = webview.create_window(
        f"{APP_TITLE} {APP_VERSION}", url,
        width=1380, height=900, min_size=(1024, 680),
        confirm_close=False, text_select=True,
    )

    def _on_shown():
        shown_event.set()

    window.events.shown += _on_shown

    # pywebview *must* run on the main thread. If it hangs or fails silently,
    # we use a background watchdog thread to destroy the window and abort.
    def _watchdog():
        if not shown_event.wait(timeout=_WEBVIEW_SHOWN_TIMEOUT_S):
            try:
                window.destroy()
            except Exception:
                pass

    watchdog = threading.Thread(target=_watchdog, daemon=True, name="webview-watchdog")
    watchdog.start()

    try:
        webview.start(storage_path=wv2_cache)
    except Exception as e:  # noqa: BLE001
        path = _log_crash(e)
        _log(f"pywebview raised {e!r}; log: {path}")
        return False

    if not shown_event.is_set():
        _log(
            f"pywebview start() returned / timed-out after "
            f"{_WEBVIEW_SHOWN_TIMEOUT_S}s without showing a window. "
            "Falling back to system browser."
        )
        return False

    _log("pywebview window closed normally.")
    return True


# ── Main entry point ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"{APP_TITLE} {APP_VERSION}")
    ap.add_argument("--browser", action="store_true",
                    help="open in the default browser instead of a native window")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-window", action="store_true",
                    help="run the server only (no GUI)")
    ap.add_argument("--workers", type=int, default=None, metavar="N",
                    help="worker processes for per-granule analysis for this "
                         "session (0 = automatic, 1 = serial); overrides Settings")
    args = ap.parse_args(argv)
    if args.workers is not None:
        from .config import SETTINGS
        SETTINGS.analysis_workers = max(0, args.workers)  # not saved

    _log(f"Starting {APP_TITLE} {APP_VERSION} | exe={sys.executable} "
         f"| cwd={os.getcwd()} | frozen={getattr(sys, 'frozen', False)} "
         f"| _MEIPASS={getattr(sys, '_MEIPASS', 'n/a')}")

    ensure_dirs()

    if getattr(sys, "frozen", False):
        # a newer build downloaded by the weekly update: install it now (autoupdate.py)
        try:
            from . import autoupdate
            autoupdate.finish_install()
            if autoupdate.install_staged_on_start(sys.argv[1:] if argv is None else list(argv)):
                _log("A newer build is staged: handing over to the update script.")
                return 0
        except Exception as exc:  # noqa: BLE001 - never keep the app from starting
            _log(f"Automatic update skipped: {exc!r}")

    fe = frontend_dir()
    if not fe.is_dir():
        msg = f"Frontend assets are missing.\nExpected: {fe}"
        _log(f"ERROR: {msg}")
        _show_error_dialog(f"{APP_TITLE} - Startup Error", msg)
        return 2

    host, port = "127.0.0.1", args.port or free_port()
    url = f"http://{host}:{port}/"
    _log(f"Backend URL: {url}")
    threading.Thread(target=_serve, args=(host, port), daemon=True).start()

    if not _wait_until_up(url + "api/health"):
        msg = f"The backend server did not start within {STARTUP_TIMEOUT_S}s.\nCheck: {LOG_DIR / 'startup.log'}"
        _log(f"ERROR: {msg}")
        _show_error_dialog(f"{APP_TITLE} - Startup Error", msg)
        return 3

    _log("Backend healthy.")
    if getattr(sys, "frozen", False):
        try:
            from . import autoupdate
            autoupdate.scheduler()
        except Exception as exc:  # noqa: BLE001
            _log(f"Update scheduler not started: {exc!r}")

    if args.no_window:
        _log("--no-window flag set; running server-only mode.")
        if sys.stdout:
            print(f"{APP_TITLE} serving at {url} - press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0

    if not args.browser:
        try:
            if _launch_webview(url):
                return 0
        except Exception as exc:  # noqa: BLE001
            path = _log_crash(exc)
            _log(f"Unexpected error from _launch_webview: {exc!r}; log: {path}")

        # Fall back to browser with an informational dialog (no console visible).
        _log("Falling back to system browser.")
        try:
            import ctypes
            if sys.platform == "win32":
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"The native application window could not be opened.\n\n"
                    f"{APP_TITLE} will open in your default web browser instead.\n\n"
                    f"URL: {url}\n\n"
                    f"Leave this process running while you use the application.\n"
                    f"A startup log is available at:\n{LOG_DIR / 'startup.log'}",
                    f"{APP_TITLE} - Opening in Browser",
                    0x40 | 0x40000,  # MB_ICONINFORMATION | MB_SETFOREGROUND
                )
        except Exception:  # noqa: BLE001
            pass

    webbrowser.open(url)
    _log(f"Browser opened at {url}.")
    if sys.stdout:
        print(f"{APP_TITLE} serving at {url} - close this window to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


def run() -> None:
    """Console-script entry point (``cosmic2-explorer``)."""
    multiprocessing.freeze_support()  # required for a PyInstaller onefile build
    raise SystemExit(main())


if __name__ == "__main__":
    run()
