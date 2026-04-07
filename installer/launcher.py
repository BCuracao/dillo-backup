"""Dillo Launcher — starts both backend and frontend, opens the browser.

This script is the main entry point for the installed application.
It is bundled into dillo.exe via PyInstaller (--onefile --windowed).
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dillo.launcher")

BACKEND_PORT = 8000
FRONTEND_PORT = 3000
HEALTH_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/system/health"
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"

_children: list[subprocess.Popen] = []


def _resolve_install_dir() -> Path:
    """Return the installation root (parent of the launcher executable)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _kill_children() -> None:
    """Terminate all managed child processes."""
    for proc in _children:
        if proc.poll() is None:
            log.info("Stopping PID %d ...", proc.pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


atexit.register(_kill_children)


def _signal_handler(_sig: int, _frame: object) -> None:
    _kill_children()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
if sys.platform == "win32":
    signal.signal(signal.SIGBREAK, _signal_handler)


def _wait_for_health(url: str, timeout: int = 30) -> bool:
    """Poll a health endpoint until it returns 200 or timeout is reached."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _open_browser(url: str) -> None:
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        log.warning("Could not open browser automatically.")


def main() -> None:
    install_dir = _resolve_install_dir()
    log.info("Install directory: %s", install_dir)

    # ── Resolve paths (cross-platform) ───────────────────────────────
    if sys.platform == "win32":
        backend_exe = install_dir / "backend" / "dillo-backend" / "dillo-backend.exe"
        node_exe = install_dir / "node" / "node.exe"
    else:
        backend_exe = install_dir / "backend" / "dillo-backend" / "dillo-backend"
        node_exe = install_dir / "node" / "bin" / "node"
    frontend_server = install_dir / "frontend" / "server.js"

    for label, path in [
        ("Backend", backend_exe),
        ("Node.js", node_exe),
        ("Frontend server.js", frontend_server),
    ]:
        if not path.exists():
            log.error("%s not found at %s", label, path)
            if sys.platform == "win32":
                input("Press Enter to exit...")
            sys.exit(1)

    # ── Ensure data directory exists ──────────────────────────────────
    if sys.platform == "darwin":
        data_dir = Path.home() / "Library" / "Application Support" / "Dillo"
    elif sys.platform == "win32":
        data_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Dillo"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        data_dir = Path(xdg) / "dillo"
    data_dir.mkdir(parents=True, exist_ok=True)
    log.info("Data directory: %s", data_dir)

    # ── Start backend ─────────────────────────────────────────────────
    log.info("Starting backend on port %d ...", BACKEND_PORT)
    backend_proc = subprocess.Popen(
        [str(backend_exe)],
        cwd=str(install_dir),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _children.append(backend_proc)

    if not _wait_for_health(HEALTH_URL, timeout=30):
        log.error("Backend failed to start within 30 seconds.")
        input("Press Enter to exit...")
        sys.exit(1)
    log.info("Backend is healthy.")

    # ── Start frontend ────────────────────────────────────────────────
    log.info("Starting frontend on port %d ...", FRONTEND_PORT)
    frontend_env = {
        **os.environ,
        "PORT": str(FRONTEND_PORT),
        "HOSTNAME": "localhost",
    }
    frontend_proc = subprocess.Popen(
        [str(node_exe), str(frontend_server)],
        cwd=str(install_dir / "frontend"),
        env=frontend_env,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _children.append(frontend_proc)

    # Give the frontend a moment to start
    time.sleep(2)
    if frontend_proc.poll() is not None:
        log.error("Frontend process exited immediately (code %d).", frontend_proc.returncode)
        input("Press Enter to exit...")
        sys.exit(1)
    log.info("Frontend started.")

    # ── Open browser ──────────────────────────────────────────────────
    _open_browser(FRONTEND_URL)
    log.info("Dillo is running. Close this window to stop.")

    # ── Wait for either process to exit ───────────────────────────────
    try:
        while True:
            if backend_proc.poll() is not None:
                log.warning("Backend exited with code %d.", backend_proc.returncode)
                break
            if frontend_proc.poll() is not None:
                log.warning("Frontend exited with code %d.", frontend_proc.returncode)
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _kill_children()


if __name__ == "__main__":
    main()
