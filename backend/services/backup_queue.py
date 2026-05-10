"""Per-volume backup queue.

Backups that target the same physical volume are executed **sequentially** to
protect the drive's lifespan and to avoid IO contention.  Backups that target
*different* volumes still run in parallel.

The queue is keyed by *volume key* — derived from the destination path:

* **Windows** — drive letter (e.g. ``D:``).
* **Unix**     — first path segment (e.g. ``/Volumes/Backups``).

Each volume key gets its own worker coroutine that drains an
``asyncio.Queue`` one task at a time.  Tasks are simple zero-arg coroutine
factories so the caller can pass any pre-bound ``BackupManager.run_backup``
invocation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger("pybackup.queue")


# ── Volume-key derivation ─────────────────────────────────────────────


def derive_volume_key(path: str) -> str:
    """Return a stable, OS-appropriate identifier for the volume *path* lives on.

    The result is upper-cased on Windows so ``d:\\foo`` and ``D:\\foo`` collide.
    Returns an empty string when the path is falsy — caller should treat that
    as "no queueing needed" and run the backup immediately.
    """
    if not path:
        return ""
    try:
        norm = os.path.abspath(path)
    except Exception:
        return ""

    if sys.platform == "win32":
        drive, _ = os.path.splitdrive(norm)
        return drive.upper() if drive else norm.upper()

    # Unix: prefer the mount-point. Best-effort by walking up until the parent
    # changes filesystems (st_dev). Falls back to the second-level segment.
    try:
        target_dev = os.stat(norm).st_dev
        candidate = norm
        parent = os.path.dirname(candidate)
        while parent and parent != candidate:
            try:
                if os.stat(parent).st_dev != target_dev:
                    return candidate
            except OSError:
                return candidate
            candidate = parent
            parent = os.path.dirname(candidate)
        return candidate or "/"
    except OSError:
        # Fall back: first two segments e.g. "/Volumes/MyDrive".
        parts = [p for p in norm.split(os.sep) if p]
        if not parts:
            return "/"
        if len(parts) == 1:
            return os.sep + parts[0]
        return os.sep + os.sep.join(parts[:2])


# ── Queue primitives ──────────────────────────────────────────────────


@dataclass
class _QueuedJob:
    """A single queued backup invocation."""

    job_id: uuid.UUID
    job_name: str
    factory: Callable[[], Awaitable[object]]
    enqueued_at: float = field(default_factory=lambda: 0.0)


class BackupQueueManager:
    """Tracks active and pending backups per volume key."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[_QueuedJob]] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._active: dict[str, _QueuedJob | None] = {}
        self._pending: dict[str, list[uuid.UUID]] = {}
        self._lock = asyncio.Lock()

    async def enqueue(
        self,
        *,
        volume_key: str,
        job_id: uuid.UUID,
        job_name: str,
        factory: Callable[[], Awaitable[object]],
    ) -> int:
        """Add a backup to the queue for *volume_key*.

        Returns the **0-based position** of the new entry (0 == will start
        immediately, 1 == one job ahead, …).  Falsy ``volume_key`` bypasses
        the queue entirely and dispatches the task immediately.
        """
        if not volume_key:
            asyncio.create_task(
                _run_safely(factory, job_id, job_name),
                name=f"backup-immediate-{job_id}",
            )
            return 0

        async with self._lock:
            queue = self._queues.get(volume_key)
            if queue is None:
                queue = asyncio.Queue()
                self._queues[volume_key] = queue
                self._pending[volume_key] = []
                self._active[volume_key] = None

            # Reject duplicates so a flapping drive does not stack the same
            # job multiple times in a row.
            already_active = (
                self._active.get(volume_key) is not None
                and self._active[volume_key].job_id == job_id  # type: ignore[union-attr]
            )
            already_pending = job_id in self._pending[volume_key]
            if already_active or already_pending:
                logger.info(
                    "Backup '%s' (%s) already queued for volume %s — skipping duplicate.",
                    job_name, job_id, volume_key,
                )
                return -1

            self._pending[volume_key].append(job_id)
            entry = _QueuedJob(job_id=job_id, job_name=job_name, factory=factory)
            await queue.put(entry)
            position = len(self._pending[volume_key]) - 1
            if self._active.get(volume_key) is not None:
                position += 1  # account for the active one

            # Lazily spawn the per-volume worker.
            worker = self._workers.get(volume_key)
            if worker is None or worker.done():
                self._workers[volume_key] = asyncio.create_task(
                    self._worker_loop(volume_key),
                    name=f"backup-queue-{volume_key}",
                )

        logger.info(
            "Queued backup '%s' (%s) on volume %s — position %d.",
            job_name, job_id, volume_key, position,
        )
        return position

    async def _worker_loop(self, volume_key: str) -> None:
        """Drain the queue for one volume sequentially."""
        queue = self._queues[volume_key]
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=300.0)
            except asyncio.TimeoutError:
                # No work for 5 min — let the worker exit; it will be respawned.
                async with self._lock:
                    if queue.empty():
                        self._workers.pop(volume_key, None)
                        return
                continue

            async with self._lock:
                self._active[volume_key] = entry
                if entry.job_id in self._pending[volume_key]:
                    self._pending[volume_key].remove(entry.job_id)

            logger.info(
                "Volume %s starting backup '%s' (%s).",
                volume_key, entry.job_name, entry.job_id,
            )
            try:
                await _run_safely(entry.factory, entry.job_id, entry.job_name)
            finally:
                async with self._lock:
                    self._active[volume_key] = None
                queue.task_done()

    def status_for(self, volume_key: str) -> tuple[Optional[uuid.UUID], list[uuid.UUID]]:
        """Diagnostic helper: ``(active_job_id, pending_ids)``."""
        active = self._active.get(volume_key)
        pending = list(self._pending.get(volume_key, []))
        return (active.job_id if active else None, pending)


async def _run_safely(
    factory: Callable[[], Awaitable[object]],
    job_id: uuid.UUID,
    job_name: str,
) -> None:
    """Wrap the user-supplied coroutine factory with logging-only error handling."""
    try:
        await factory()
    except Exception:
        logger.exception(
            "Queued backup '%s' (%s) raised an unhandled exception.",
            job_name, job_id,
        )


# ── Module-level singleton ────────────────────────────────────────────


_QUEUE: BackupQueueManager | None = None


def get_backup_queue() -> BackupQueueManager:
    """Return the process-wide ``BackupQueueManager`` instance."""
    global _QUEUE
    if _QUEUE is None:
        _QUEUE = BackupQueueManager()
    return _QUEUE
