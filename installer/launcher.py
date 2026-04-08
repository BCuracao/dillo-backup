"""Dillo Launcher — starts both backend and frontend, opens the browser.

This script is the main entry point for the installed application.
It is bundled into dillo.exe via PyInstaller (--onefile --windowed).
"""

from __future__ import annotations

import atexit
import errno
import logging
import os
import signal
import socket
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
_DEFAULT_FRONTEND_PORT = 3000
HEALTH_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/system/health"

_children: list[subprocess.Popen] = []


def _resolve_install_dir() -> Path:
    """Return the directory containing the launcher executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolve_bundle_root() -> Path:
    """Directory that contains backend/, frontend/, and node/.

    On a macOS .app bundle these live in Contents/Resources; the executable
    stays in Contents/MacOS so Gatekeeper/code signing only seals real Mach-O
    binaries under MacOS. Falls back to the executable directory (legacy layout
    with payloads next to the launcher) or to walking up to ``*.app``.
    """
    base = _resolve_install_dir()
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        if base.name == "MacOS" and base.parent.name == "Contents":
            resources = base.parent / "Resources"
            if (resources / "backend").is_dir():
                return resources
        exe = Path(sys.executable).resolve()
        for ancestor in [exe, *exe.parents]:
            if ancestor.suffix == ".app" and ancestor.is_dir():
                resources = ancestor / "Contents" / "Resources"
                if (resources / "backend").is_dir():
                    return resources
                break
    if (base / "backend").is_dir():
        return base
    return base


def _pause_before_exit() -> None:
    """Avoid ``input()`` when stdin is not a TTY (double-clicked ``.app``).

    PyInstaller would otherwise raise EOFError and macOS reports a broken app.
    """
    if sys.stdin.isatty():
        input("Press Enter to exit...")
    else:
        time.sleep(12)


def _port_available(port: int) -> bool:
    """True if loopback can bind on the port (IPv4; IPv6 on macOS/Linux when available)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    if sys.platform == "win32":
        return True
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("::1", port))
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, errno.EACCES):
            return False
    return True


def _pick_local_port(preferred: int, attempts: int = 20) -> int:
    """Return a TCP port free on loopback (check both ``127.0.0.1`` and ``::1``)."""
    for port in range(preferred, preferred + attempts):
        if _port_available(port):
            return port
    log.error("No free TCP port in range %d–%d", preferred, preferred + attempts - 1)
    return preferred


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
    bundle_root = _resolve_bundle_root()
    log.info("Bundle root: %s", bundle_root)

    # ── Resolve paths (cross-platform) ───────────────────────────────
    if sys.platform == "win32":
        backend_exe = bundle_root / "backend" / "dillo-backend" / "dillo-backend.exe"
        node_exe = bundle_root / "node" / "node.exe"
    else:
        backend_exe = bundle_root / "backend" / "dillo-backend" / "dillo-backend"
        node_exe = bundle_root / "node" / "bin" / "node"
    frontend_server = bundle_root / "frontend" / "server.js"

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
        cwd=str(bundle_root),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _children.append(backend_proc)

    if not _wait_for_health(HEALTH_URL, timeout=30):
        log.error("Backend failed to start within 30 seconds.")
        _pause_before_exit()
        sys.exit(1)
    log.info("Backend is healthy.")

    frontend_port = _pick_local_port(_DEFAULT_FRONTEND_PORT)
    frontend_url = f"http://localhost:{frontend_port}"
    if frontend_port != _DEFAULT_FRONTEND_PORT:
        log.warning(
            "Port %d is in use; using %d for the web UI.",
            _DEFAULT_FRONTEND_PORT,
            frontend_port,
        )

    # ── Start frontend ────────────────────────────────────────────────
    log.info("Starting frontend on port %d ...", frontend_port)
    frontend_env = {
        **os.environ,
        "PORT": str(frontend_port),
        "HOSTNAME": "localhost",
    }
    frontend_proc = subprocess.Popen(
        [str(node_exe), str(frontend_server)],
        cwd=str(bundle_root / "frontend"),
        env=frontend_env,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _children.append(frontend_proc)

    # Give the frontend a moment to start
    time.sleep(2)
    if frontend_proc.poll() is not None:
        log.error("Frontend process exited immediately (code %d).", frontend_proc.returncode)
        _pause_before_exit()
        sys.exit(1)
    log.info("Frontend started.")

    # ── Open browser ──────────────────────────────────────────────────
    _open_browser(frontend_url)
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
