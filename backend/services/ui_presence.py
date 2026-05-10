"""Tracks whether a frontend dashboard is currently watching the API.

The web UI sends a heartbeat to ``POST /api/system/heartbeat`` every few
seconds while it is mounted in a foreground tab.  The system tray (running
inside the launcher) consults ``is_dashboard_visible()`` before deciding
whether to surface OS toast notifications — when the dashboard is open,
toasts are already shown in-browser and an additional OS toast would be
double-notification.
"""

from __future__ import annotations

import threading
import time

# How long after the last heartbeat the dashboard is still considered "open".
# The frontend pings every 5 s (see ``hooks/useDashboardHeartbeat.ts``), so a
# 30 s window tolerates short network blips and tab switches.
_PRESENCE_TTL_SECONDS = 30.0

_lock = threading.Lock()
_last_seen: float = 0.0


def mark_dashboard_visible() -> None:
    """Record that the dashboard just sent a heartbeat."""
    global _last_seen
    with _lock:
        _last_seen = time.monotonic()


def is_dashboard_visible() -> bool:
    """Return True if the dashboard pinged within the last TTL window."""
    with _lock:
        if _last_seen == 0.0:
            return False
        return (time.monotonic() - _last_seen) < _PRESENCE_TTL_SECONDS


def seconds_since_last_heartbeat() -> float | None:
    """Return seconds since the last heartbeat (None if never seen)."""
    with _lock:
        if _last_seen == 0.0:
            return None
        return time.monotonic() - _last_seen
