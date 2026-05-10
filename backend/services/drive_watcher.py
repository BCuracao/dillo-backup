"""Cross-platform background drive watcher for the Auto-Wake feature.

A lightweight polling thread snapshots the set of mounted drive roots every
``POLL_INTERVAL_SECONDS`` seconds.  When a *new* drive appears, it walks the
active backup jobs and triggers any whose destination path lives inside that
drive — provided Auto-Wake is enabled (per-job override or global default).

Polling is used in preference to ``WMI`` / ``win32gui`` / Cocoa
notifications because it has zero native dependencies, works identically on
Windows / macOS / Linux, and is fully decoupled from the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import string
import sys
import threading
import time
from pathlib import Path
from typing import Iterable

from sqlalchemy import select

from ..database import async_session_factory
from ..models import BackupJob
from ..services.activity_logger import EventType, log_activity
from ..services.backup_queue import derive_volume_key, get_backup_queue
from ..services.settings_service import get_global_settings, resolve_auto_wake
from ..services.system_events import (
    EVT_AUTO_WAKE_TRIGGERED,
    EVT_DRIVE_DETECTED,
    EVT_DRIVE_JOBS_QUEUED,
    publish_event,
)

logger = logging.getLogger("pybackup.drive_watcher")

# How often to scan for newly mounted drives.
POLL_INTERVAL_SECONDS = 4.0
# Suppress repeated triggers for the same job within this many seconds (drive flap).
DEBOUNCE_SECONDS = 60.0


# ── Drive enumeration ────────────────────────────────────────────────


def _list_current_drive_roots() -> set[str]:
    """Snapshot the set of currently mounted drive roots."""
    roots: set[str] = set()
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            try:
                if os.path.exists(root):
                    roots.add(root)
            except OSError:
                continue
    elif sys.platform == "darwin":
        volumes = Path("/Volumes")
        try:
            if volumes.is_dir():
                for entry in volumes.iterdir():
                    if entry.is_dir() and not entry.is_symlink():
                        roots.add(str(entry))
        except OSError:
            pass
    else:
        for parent in ("/media", "/mnt", "/run/media"):
            base = Path(parent)
            try:
                if base.is_dir():
                    for entry in base.iterdir():
                        if entry.is_dir() and not entry.is_symlink():
                            roots.add(str(entry))
                            # /media/<user>/<drive> on most Linux desktops
                            try:
                                for sub in entry.iterdir():
                                    if sub.is_dir() and not sub.is_symlink():
                                        roots.add(str(sub))
                            except OSError:
                                pass
            except OSError:
                continue
    return roots


def _path_belongs_to_drive(target_path: str, drive_root: str) -> bool:
    """Return True if *target_path* lives on the same drive as *drive_root*."""
    if not target_path:
        return False
    try:
        target_norm = os.path.normcase(os.path.abspath(target_path))
        root_norm = os.path.normcase(os.path.abspath(drive_root))
    except Exception:
        return False

    if sys.platform == "win32":
        target_drive = os.path.splitdrive(target_norm)[0]
        root_drive = os.path.splitdrive(root_norm)[0]
        if not target_drive or not root_drive:
            return False
        return target_drive == root_drive

    # Unix: prefix match on the mount point with a separator boundary.
    if target_norm == root_norm:
        return True
    return target_norm.startswith(root_norm.rstrip("/") + "/")


# ── Trigger logic ────────────────────────────────────────────────────


async def _handle_new_drive(
    drive_root: str,
    last_trigger: dict[str, float],
) -> None:
    """When a drive appears, queue any matching auto-wake jobs sequentially."""
    # Local import to avoid a circular dependency at module load time.
    from ..services.backup_engine import BackupManager

    publish_event(
        EVT_DRIVE_DETECTED,
        f"Drive detected: {drive_root}",
        data={"drive": drive_root},
    )

    snapshot = await get_global_settings()

    async with async_session_factory() as session:
        result = await session.execute(
            select(BackupJob).where(BackupJob.is_active.is_(True))
        )
        jobs = result.scalars().all()

    queue = get_backup_queue()
    triggered: list[str] = []
    now = time.monotonic()

    for job in jobs:
        if not _path_belongs_to_drive(job.dest_path, drive_root):
            continue
        if not resolve_auto_wake(job.job_auto_wake, snapshot):
            continue

        debounce_key = f"{drive_root}:{job.id}"
        last = last_trigger.get(debounce_key, 0.0)
        if now - last < DEBOUNCE_SECONDS:
            logger.debug(
                "Auto-Wake debounced for job '%s' on %s.", job.name, drive_root
            )
            continue
        last_trigger[debounce_key] = now

        # Enqueue against the destination volume so jobs on the same drive run
        # one after another (sequential queue per volume).
        volume_key = derive_volume_key(job.dest_path)
        # Bind job id to a local so the lambda captures the correct value.
        bound_job_id = job.id
        position = await queue.enqueue(
            volume_key=volume_key,
            job_id=bound_job_id,
            job_name=job.name,
            factory=lambda jid=bound_job_id: BackupManager.run_backup(job_id=jid),
        )
        if position < 0:
            # Duplicate suppressed by the queue manager.
            continue

        triggered.append(job.name)

        await log_activity(
            event_type=EventType.JOB_RUN,
            job_name=job.name,
            message=(
                f"Auto-Wake queued (position {position + 1}) by drive {drive_root}"
                if position > 0
                else f"Auto-Wake triggered by drive {drive_root}"
            ),
            job_id=job.id,
            details=f"destination={job.dest_path} | queue_position={position}",
        )

    if triggered:
        # Single, aggregated toast for the whole drive — one notification per
        # plug-in event rather than one per job (per the spec).
        publish_event(
            EVT_DRIVE_JOBS_QUEUED,
            f"{len(triggered)} backup job(s) found for drive {drive_root}. "
            f"Starting now...",
            data={
                "drive": drive_root,
                "count": len(triggered),
                "jobs": triggered,
            },
        )
        # Keep the per-job event too so the dashboard can still highlight the
        # first job that begins.  The ``triggered`` list is already in queue
        # order, so the first entry is the one that starts immediately.
        publish_event(
            EVT_AUTO_WAKE_TRIGGERED,
            f"Drive Detected: Starting Dillo Backup for {triggered[0]}...",
            data={
                "drive": drive_root,
                "job_name": triggered[0],
                "queued_total": len(triggered),
            },
        )
        logger.info(
            "Auto-Wake queued for drive %s — jobs: %s",
            drive_root, ", ".join(triggered),
        )


# ── Background loops ─────────────────────────────────────────────────


_watcher_task: asyncio.Task | None = None
_known_roots: set[str] = set()
_last_trigger_per_job: dict[str, float] = {}


def _scan_in_thread() -> set[str]:
    """Run drive enumeration off the event loop (sync syscalls)."""
    return _list_current_drive_roots()


async def _watcher_loop() -> None:
    """Async loop that polls for newly mounted drives and dispatches triggers."""
    global _known_roots
    loop = asyncio.get_running_loop()

    # Prime the baseline so already-mounted drives don't fire on startup.
    try:
        _known_roots = await loop.run_in_executor(None, _scan_in_thread)
    except Exception:
        logger.exception("Failed to enumerate initial drive roots; starting empty.")
        _known_roots = set()

    logger.info(
        "Drive watcher started (interval=%.1fs, %d baseline drives).",
        POLL_INTERVAL_SECONDS, len(_known_roots),
    )

    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        try:
            current = await loop.run_in_executor(None, _scan_in_thread)
        except Exception:
            logger.exception("Drive enumeration failed; will retry next tick.")
            continue

        new_drives: Iterable[str] = current - _known_roots
        removed = _known_roots - current

        if removed:
            logger.debug("Drives unmounted: %s", ", ".join(sorted(removed)))

        for drive in sorted(new_drives):
            logger.info("New drive detected: %s", drive)
            try:
                await _handle_new_drive(drive, _last_trigger_per_job)
            except Exception:
                logger.exception("Auto-Wake handler failed for %s", drive)

        _known_roots = current


def start_drive_watcher() -> asyncio.Task | None:
    """Launch the watcher as a background asyncio task. Idempotent."""
    global _watcher_task
    if _watcher_task is not None and not _watcher_task.done():
        return _watcher_task
    try:
        _watcher_task = asyncio.create_task(_watcher_loop(), name="drive-watcher")
    except RuntimeError:
        # No running loop (e.g. during certain test setups).
        logger.warning("No running loop; drive watcher not started.")
        return None
    return _watcher_task


def stop_drive_watcher() -> None:
    """Cancel the watcher task on shutdown."""
    global _watcher_task
    if _watcher_task and not _watcher_task.done():
        _watcher_task.cancel()
        _watcher_task = None
        logger.info("Drive watcher stopped.")


# ── Threaded variant (kept for completeness) ─────────────────────────

# The polling loop is implemented as an asyncio task so it shares the FastAPI
# event loop (lightweight, no GIL contention with worker threads).  If you
# ever need a fully isolated thread variant — e.g. for very chatty platforms
# where `os.path.exists()` blocks — see ``threading.Thread`` with a daemon
# flag wrapping ``_scan_in_thread`` plus ``asyncio.run_coroutine_threadsafe``
# to dispatch back into the event loop.
_thread_lock = threading.Lock()  # placeholder, kept for future use
