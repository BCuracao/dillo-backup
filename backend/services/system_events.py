"""In-memory ring buffer of runtime system events for the frontend toast feed.

Events are produced by background services (e.g. drive watcher) and consumed
by the frontend via ``GET /api/system/events?since=<id>``.  The buffer is
intentionally bounded so it never grows unbounded across long sessions.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# Capacity is small — we only need enough for the polling window.
_BUFFER_CAPACITY = 100


@dataclass
class _Event:
    id: int
    event_type: str
    message: str
    timestamp: datetime
    data: Optional[dict] = field(default=None)


class _EventBus:
    """Thread-safe monotonic event publisher."""

    def __init__(self) -> None:
        self._events: deque[_Event] = deque(maxlen=_BUFFER_CAPACITY)
        self._next_id: int = 1
        self._lock = threading.Lock()

    def publish(
        self,
        event_type: str,
        message: str,
        data: Optional[dict] = None,
    ) -> _Event:
        with self._lock:
            event = _Event(
                id=self._next_id,
                event_type=event_type,
                message=message,
                timestamp=datetime.now(timezone.utc),
                data=data,
            )
            self._events.append(event)
            self._next_id += 1
            return event

    def since(self, last_id: int) -> tuple[list[_Event], int]:
        """Return events with id > *last_id* and the latest known id."""
        with self._lock:
            latest = self._next_id - 1
            if last_id >= latest:
                return [], latest
            return [e for e in self._events if e.id > last_id], latest


_BUS = _EventBus()

# Public event-type constants — keep in sync with the frontend.
EVT_DRIVE_DETECTED = "DRIVE_DETECTED"
EVT_AUTO_WAKE_TRIGGERED = "AUTO_WAKE_TRIGGERED"
# Aggregated "N jobs queued for drive X" toast emitted once per plug-in event
# (instead of one per job) so the user is not spammed.
EVT_DRIVE_JOBS_QUEUED = "DRIVE_JOBS_QUEUED"
# Backup lifecycle — fed to the system tray so it can show OS toasts when the
# dashboard is hidden.
EVT_BACKUP_STARTED = "BACKUP_STARTED"
EVT_BACKUP_COMPLETED = "BACKUP_COMPLETED"
EVT_BACKUP_FAILED = "BACKUP_FAILED"


def publish_event(
    event_type: str,
    message: str,
    data: Optional[dict] = None,
) -> None:
    """Convenience wrapper used by background services."""
    _BUS.publish(event_type, message, data)


def fetch_events_since(last_id: int) -> tuple[list[_Event], int]:
    """Return new events for HTTP polling."""
    return _BUS.since(last_id)
