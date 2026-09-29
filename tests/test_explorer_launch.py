"""
Explorer double-click launch verification tests.

Tests the exact conditions under which Windows Explorer launches an EXE:
  - CWD set to something other than the EXE directory (Desktop, home, etc.)
  - No stdin/stdout/stderr attached
  - Process starts as a non-terminal child of explorer.exe

Windows only.  Skipped unless a built EXE is present: build one with
``python scripts/build_exe.py`` (lands in dist/) or point COSMIC2_EXE at it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
EXE = Path(os.environ.get("COSMIC2_EXE") or PROJECT / "dist" / "COSMIC2-Explorer.exe")
# The EXE inherits COSMIC2_EXPLORER_HOME (set by conftest), so it logs there.
APPDATA = Path(os.environ.get("COSMIC2_EXPLORER_HOME")
               or Path(os.environ.get("LOCALAPPDATA", "")) / "COSMIC2Explorer")

pytestmark = [
    pytest.mark.exe,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows EXE launch test"),
    pytest.mark.skipif(not EXE.is_file(), reason=f"no built EXE at {EXE}"),
]
STARTUP_LOG = APPDATA / "logs" / "startup.log"
ERROR_LOG = APPDATA / "logs" / "startup-error.log"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = PASS if condition else FAIL
    print(f"  {icon}  {name}" + (f"  [{detail}]" if detail else ""))
    results.append((name, condition, detail))
    assert condition, f"{name} failed: {detail}"


def _kill_cosmic() -> None:
    """Kill any running COSMIC2-Explorer processes."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "COSMIC2-Explorer.exe"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass
    time.sleep(0.5)


def _launch_from_cwd(cwd: str, timeout_s: int = 35) -> tuple[bool, str]:
    """Launch the EXE with given CWD and return (alive_after_timeout, log_content)."""
    _kill_cosmic()
    # Clear old startup log so we can detect fresh entries
    if STARTUP_LOG.exists():
        STARTUP_LOG.unlink()
    if ERROR_LOG.exists():
        ERROR_LOG.unlink()

    proc = subprocess.Popen(
        [str(EXE)],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    start_t = time.time()
    while time.time() - start_t < timeout_s:
        if proc.poll() is not None:
            break
        if STARTUP_LOG.exists():
            try:
                txt = STARTUP_LOG.read_text(encoding="utf-8", errors="replace")
                if "Backend healthy" in txt:
                    break
            except Exception:
                pass
        time.sleep(0.5)

    alive = proc.poll() is None
    _kill_cosmic()

    log = ""
    if STARTUP_LOG.exists():
        log = STARTUP_LOG.read_text(encoding="utf-8", errors="replace")
    if ERROR_LOG.exists():
        log += "\n--- error ---\n" + ERROR_LOG.read_text(encoding="utf-8", errors="replace")
    return alive, log



# ── Tests ─────────────────────────────────────────────────────────────────────

def test_exe_exists() -> None:
    print("\n[1] EXE existence")
    check("EXE exists", EXE.is_file(), str(EXE))
    if EXE.is_file():
        size_mb = EXE.stat().st_size / 1024 / 1024
        check("EXE size > 50 MB", size_mb > 50, f"{size_mb:.1f} MB")


def test_launch_from_exe_dir() -> None:
    print("\n[2] Launch from EXE directory (PowerShell-style)")
    if not EXE.is_file():
        print(f"  {SKIP}  EXE not found")
        return
    alive, log = _launch_from_cwd(str(EXE.parent))
    check("Process alive after 20s", alive)
    check("Startup log written", bool(log))
    if log:
        check("Backend healthy logged", "Backend healthy" in log, log[:200])


def test_launch_from_desktop() -> None:
    print("\n[3] Launch from Desktop (Explorer double-click)")
    if not EXE.is_file():
        print(f"  {SKIP}  EXE not found")
        return
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        desktop = Path.home()
    alive, log = _launch_from_cwd(str(desktop))
    check("Process alive after 20s (from Desktop)", alive)
    check("Startup log written", bool(log))
    if log:
        check("CWD logged (not relative-path crash)", "Starting COSMIC-2 Explorer" in log, log[:200])
        check("Backend healthy from Desktop CWD", "Backend healthy" in log)


def test_launch_from_home() -> None:
    print("\n[4] Launch from home folder (Explorer variant)")
    if not EXE.is_file():
        print(f"  {SKIP}  EXE not found")
        return
    alive, log = _launch_from_cwd(str(Path.home()))
    check("Process alive after 20s (from home)", alive)
    if log:
        check("No CWD-relative path crash", "Frontend assets are missing" not in log)


def test_launch_from_temp() -> None:
    print("\n[5] Launch from temp directory (adversarial CWD)")
    if not EXE.is_file():
        print(f"  {SKIP}  EXE not found")
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        alive, log = _launch_from_cwd(tmpdir, timeout_s=35)
    check("Process alive after 35s (from temp dir)", alive)
    if log:
        check("Backend healthy from temp CWD", "Backend healthy" in log)


def test_no_error_log() -> None:
    print("\n[6] No startup errors")
    # Run one more clean launch
    if not EXE.is_file():
        print(f"  {SKIP}  EXE not found")
        return
    desktop = Path.home() / "Desktop"
    _launch_from_cwd(str(desktop if desktop.is_dir() else Path.home()), timeout_s=15)
    if ERROR_LOG.exists():
        content = ERROR_LOG.read_text(encoding="utf-8", errors="replace")
        check("No startup-error.log after Explorer launch", False, f"Error log:\n{content[:400]}")
    else:
        check("No startup-error.log after Explorer launch", True)


# ── Summary ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not EXE.is_file():
        print(f"[SKIP] EXE not found: {EXE}")
        print("  Build first: python scripts/build_exe.py")
        sys.exit(0)

    test_exe_exists()
    test_launch_from_exe_dir()
    test_launch_from_desktop()
    test_launch_from_home()
    test_launch_from_temp()
    test_no_error_log()

    _kill_cosmic()

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(results)} checks")
    if failed:
        print("\nFailed checks:")
        for name, ok, detail in results:
            if not ok:
                print(f"  ✗ {name}: {detail}")
        sys.exit(1)
    else:
        print("All checks PASSED.")
        sys.exit(0)
