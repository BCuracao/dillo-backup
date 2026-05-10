"""Dillo Backup Launcher — starts both backend and frontend, owns the tray icon.

This script is the main entry point for the installed application.
It is bundled into DilloBackup.exe via PyInstaller (--onefile --windowed).
"""

from __future__ import annotations

import atexit
import errno
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
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
_CONTROL_PORT = 32145
HEALTH_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/system/health"
EVENTS_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/system/events"
PRESENCE_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/system/presence"

# Backend events that should surface as OS-native toasts when the dashboard
# is not visible.  Other events (DRIVE_DETECTED, AUTO_WAKE_TRIGGERED) are
# already covered by the aggregated DRIVE_JOBS_QUEUED toast.
_NOTIFY_EVENT_TYPES = {
    "DRIVE_JOBS_QUEUED",
    "BACKUP_STARTED",
    "BACKUP_COMPLETED",
    "BACKUP_FAILED",
}
_NOTIFY_POLL_INTERVAL = 5.0
_NOTIFY_TITLE = "Dillo Backup"

_children: list[subprocess.Popen] = []
_control_socket: socket.socket | None = None
_frontend_url: str | None = None
_stop_requested = threading.Event()


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
    _stop_requested.set()
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


def _open_dashboard() -> None:
    if _frontend_url:
        _open_browser(_frontend_url)
    else:
        _open_browser(f"http://localhost:{_DEFAULT_FRONTEND_PORT}")


def _notify_existing_instance(open_dashboard: bool) -> bool:
    """Ask an already running launcher to open the dashboard and then exit."""
    command = b"OPEN\n" if open_dashboard else b"PING\n"
    try:
        with socket.create_connection(("127.0.0.1", _CONTROL_PORT), timeout=1.5) as client:
            client.sendall(command)
            try:
                client.recv(16)
            except OSError:
                pass
        return True
    except OSError:
        return False


def _start_control_server() -> bool:
    """Bind the single-instance control socket."""
    global _control_socket

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", _CONTROL_PORT))
        server.listen(5)
    except OSError:
        server.close()
        return False

    _control_socket = server

    def serve() -> None:
        while not _stop_requested.is_set():
            try:
                client, _addr = server.accept()
            except OSError:
                break
            with client:
                try:
                    command = client.recv(32).strip().upper()
                    if command == b"OPEN":
                        _open_dashboard()
                    client.sendall(b"OK\n")
                except OSError:
                    pass

    threading.Thread(target=serve, name="dillo-control", daemon=True).start()
    return True


def _close_control_server() -> None:
    if _control_socket is not None:
        try:
            _control_socket.close()
        except OSError:
            pass


def _is_dashboard_visible() -> bool:
    """Ask the backend whether the dashboard pinged recently."""
    try:
        with urllib.request.urlopen(PRESENCE_URL, timeout=1.0) as resp:
            if resp.status != 200:
                return False
            payload = json.loads(resp.read().decode("utf-8"))
            return bool(payload.get("visible", False))
    except Exception:
        # If the backend is briefly unreachable, fall back to "not visible"
        # so the user still receives notifications about lifecycle events.
        return False


def _show_native_toast(icon, title: str, message: str) -> None:
    """Show an OS-native notification.

    Tries pystray's built-in ``notify()`` first (works on Windows and most
    Linux desktops).  Falls back to ``osascript`` on macOS where pystray
    notifications are limited.
    """
    try:
        if icon is not None and hasattr(icon, "notify"):
            icon.notify(message, title)
            return
    except Exception:
        log.debug("pystray notify failed", exc_info=True)

    if sys.platform == "darwin":
        try:
            safe_msg = message.replace('"', '\\"')
            safe_title = title.replace('"', '\\"')
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{safe_msg}" with title "{safe_title}"',
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except Exception:
            log.debug("osascript notify failed", exc_info=True)


def _notification_poll_loop(icon_holder: dict) -> None:
    """Background poller that surfaces backend events as OS toasts.

    Notifications are suppressed while the dashboard is visible (the in-browser
    toast feed already covers it) — this is the "tray-only mode" rule from
    the spec.  We keep the cursor moving forward in either case so we never
    flood the user with stale events when they later minimise the window.
    """
    last_id = 0
    # Prime the cursor: ignore events that occurred before the launcher
    # finished starting so we don't toast a backlog on boot.
    try:
        with urllib.request.urlopen(f"{EVENTS_URL}?since=0", timeout=2.0) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                last_id = int(payload.get("last_id", 0))
    except Exception:
        last_id = 0

    while not _stop_requested.is_set():
        time.sleep(_NOTIFY_POLL_INTERVAL)
        if _stop_requested.is_set():
            break
        try:
            url = f"{EVENTS_URL}?since={last_id}"
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if resp.status != 200:
                    continue
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue

        events = payload.get("events", []) or []
        new_last = int(payload.get("last_id", last_id))

        if events:
            dashboard_visible = _is_dashboard_visible()
            if not dashboard_visible:
                icon = icon_holder.get("icon")
                for event in events:
                    event_type = event.get("event_type")
                    if event_type not in _NOTIFY_EVENT_TYPES:
                        continue
                    message = event.get("message") or ""
                    if message:
                        _show_native_toast(icon, _NOTIFY_TITLE, message)

        if new_last > last_id:
            last_id = new_last


def _load_tray_image(bundle_root: Path):
    """Load the packaged Dillo icon for pystray."""
    from PIL import Image

    candidates = [
        bundle_root / "frontend" / "public" / "dillo-logo-color.png",
        bundle_root / "frontend" / "public" / "dillo-logo.png",
        bundle_root / "dillo.ico",
    ]
    for candidate in candidates:
        if candidate.exists():
            return Image.open(candidate)

    image = Image.new("RGBA", (64, 64), (59, 130, 246, 255))
    return image


def _run_tray(bundle_root: Path) -> bool:
    """Start the tray icon. Returns False when tray support is unavailable."""
    try:
        import pystray
    except Exception:
        log.warning("System tray is unavailable; running without tray icon.")
        # Even without a tray icon we can still surface OS toasts where
        # supported (e.g. macOS osascript), so kick off the polling thread.
        threading.Thread(
            target=_notification_poll_loop,
            args=({"icon": None},),
            name="dillo-notify-poll",
            daemon=True,
        ).start()
        return False

    def open_dashboard(_icon, _item) -> None:
        _open_dashboard()

    def quit_app(icon, _item) -> None:
        _stop_requested.set()
        icon.stop()
        _kill_children()

    try:
        icon = pystray.Icon(
            "Dillo Backup",
            _load_tray_image(bundle_root),
            "Dillo Backup",
            menu=pystray.Menu(
                pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
                pystray.MenuItem("Quit Dillo Backup", quit_app),
            ),
        )

        def stop_when_requested() -> None:
            _stop_requested.wait()
            try:
                icon.stop()
            except Exception:
                pass

        threading.Thread(
            target=stop_when_requested,
            name="dillo-tray-stop",
            daemon=True,
        ).start()

        # Background poller for OS-native backup notifications.  Uses a dict
        # holder so the icon reference can be set after pystray.Icon() so the
        # poller has a stable handle to ``icon.notify``.
        icon_holder = {"icon": icon}
        threading.Thread(
            target=_notification_poll_loop,
            args=(icon_holder,),
            name="dillo-notify-poll",
            daemon=True,
        ).start()

        log.info("System tray icon started.")
        icon.run()
        return True
    except Exception:
        log.exception("System tray failed to start.")
        return False


def _monitor_children(backend_proc: subprocess.Popen, frontend_proc: subprocess.Popen) -> None:
    """Keep the launcher alive until a child exits or the user quits from tray."""
    while not _stop_requested.is_set():
        if backend_proc.poll() is not None:
            log.warning("Backend exited with code %d.", backend_proc.returncode)
            _stop_requested.set()
            break
        if frontend_proc.poll() is not None:
            log.warning("Frontend exited with code %d.", frontend_proc.returncode)
            _stop_requested.set()
            break
        time.sleep(1)


def main() -> None:
    hidden = "--hidden" in sys.argv[1:]

    if not _start_control_server():
        if _notify_existing_instance(open_dashboard=not hidden):
            log.info("Dillo Backup is already running.")
            return
        log.error("Another process is using Dillo Backup's control port.")
        sys.exit(1)

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
        data_dir = Path.home() / "Library" / "Application Support" / "Dillo Backup"
    elif sys.platform == "win32":
        data_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Dillo Backup"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        data_dir = Path(xdg) / "dillo-backup"
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
    global _frontend_url
    _frontend_url = f"http://localhost:{frontend_port}"
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
    if hidden:
        log.info("Started hidden from autostart; dashboard remains closed.")
    else:
        _open_dashboard()
    log.info("Dillo Backup is running. Use the tray icon to open or quit.")

    # ── Tray + process supervision ────────────────────────────────────
    monitor = threading.Thread(
        target=_monitor_children,
        args=(backend_proc, frontend_proc),
        name="dillo-process-monitor",
        daemon=True,
    )
    monitor.start()
    try:
        if not _run_tray(bundle_root):
            _monitor_children(backend_proc, frontend_proc)
    except KeyboardInterrupt:
        pass
    finally:
        _close_control_server()
        _kill_children()


if __name__ == "__main__":
    main()
