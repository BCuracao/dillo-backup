"""Activity logger: records job lifecycle events to DB and rotating log files."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import DATA_DIR
from ..database import async_session_factory
from ..models import ActivityLog

logger = logging.getLogger("pybackup.activity")

# ── Configuration ─────────────────────────────────────────────────────

LOG_DIR = DATA_DIR / "logs"
MAX_LOG_FILES = 3
RETENTION_DAYS = 14  # 2 weeks


# ── Event Types ───────────────────────────────────────────────────────

class EventType:
    JOB_CREATED = "JOB_CREATED"
    JOB_DELETED = "JOB_DELETED"
    JOB_RUN = "JOB_RUN"
    JOB_DRY_RUN = "JOB_DRY_RUN"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_FAILED = "JOB_FAILED"


# ── Public API ────────────────────────────────────────────────────────

async def log_activity(
    event_type: str,
    job_name: str,
    message: str,
    job_id: Optional[uuid.UUID] = None,
    details: Optional[str] = None,
    session: Optional[AsyncSession] = None,
) -> None:
    """
    Record an activity event to both the database and a physical log file.

    If a session is provided (e.g. from a request-scoped dependency), it
    will be used but NOT committed — the caller owns the transaction.
    Otherwise, a standalone session is created and committed.
    """
    now = datetime.now(timezone.utc)

    entry = ActivityLog(
        event_type=event_type,
        job_name=job_name,
        job_id=job_id,
        message=message,
        details=details,
        timestamp=now,
    )

    if session is not None:
        session.add(entry)
        # Caller will commit via get_db dependency
    else:
        async with async_session_factory() as standalone:
            standalone.add(entry)
            await standalone.commit()

    # Write to physical log file
    _write_log_file(now, event_type, job_name, message, details)

    logger.info("Activity: [%s] %s — %s", event_type, job_name, message)


async def cleanup_old_activity_logs() -> int:
    """
    Delete activity log entries older than RETENTION_DAYS from the database.
    Returns the number of deleted rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)

    async with async_session_factory() as session:
        # Count first for the return value
        count_result = await session.execute(
            select(func.count()).select_from(ActivityLog).where(
                ActivityLog.timestamp < cutoff
            )
        )
        count = count_result.scalar() or 0

        if count > 0:
            await session.execute(
                delete(ActivityLog).where(ActivityLog.timestamp < cutoff)
            )
            await session.commit()
            logger.info("Cleaned up %d activity log entries older than %d days.", count, RETENTION_DAYS)

    return count


# ── File-based Logging ────────────────────────────────────────────────

def _write_log_file(
    timestamp: datetime,
    event_type: str,
    job_name: str,
    message: str,
    details: Optional[str],
) -> None:
    """
    Append one event to the current log file.
    Each log file is named by date (YYYY-MM-DD.log).
    A new file is created for each day.
    After writing, rotate to keep only MAX_LOG_FILES files.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    filename = timestamp.strftime("%Y-%m-%d") + ".log"
    filepath = LOG_DIR / filename

    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts_str}] [{event_type}] {job_name} — {message}"
    if details:
        line += f"\n  Details: {details}"
    line += "\n"

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(line)

    # Rotate: keep only the 3 most recent log files
    _rotate_log_files()


def _rotate_log_files() -> None:
    """Keep only the MAX_LOG_FILES most recent .log files, delete the rest."""
    if not LOG_DIR.exists():
        return

    log_files = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.name, reverse=True)

    for old_file in log_files[MAX_LOG_FILES:]:
        try:
            old_file.unlink()
            logger.info("Rotated out old log file: %s", old_file.name)
        except OSError as exc:
            logger.warning("Failed to delete old log file %s: %s", old_file.name, exc)
