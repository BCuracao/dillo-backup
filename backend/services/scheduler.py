"""Cron-based backup scheduler.

Runs an asyncio loop that checks active jobs every 60 seconds.
When a job's cron expression indicates it should have fired since the last
check, BackupManager.run_backup is dispatched.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select

from ..database import async_session_factory
from ..models import BackupJob, JobLog
from ..services.activity_logger import EventType, log_activity

logger = logging.getLogger("pybackup.scheduler")

CHECK_INTERVAL_SECONDS = 60
_scheduler_task: asyncio.Task | None = None


async def _should_run_now(job: BackupJob, last_check: datetime) -> bool:
    """Return True if the job's cron expression triggered between *last_check* and now."""
    if not job.schedule_cron or not job.schedule_cron.strip():
        return False
    if not job.is_active:
        return False

    try:
        cron = croniter(job.schedule_cron, last_check)
        next_fire: datetime = cron.get_next(datetime)
        return next_fire <= datetime.now(timezone.utc)
    except (ValueError, KeyError):
        logger.warning("Invalid cron expression for job %s: %r", job.name, job.schedule_cron)
        return False


async def _is_already_running(job_id, session) -> bool:
    """Check if the job already has a RUNNING log entry (prevent overlap)."""
    result = await session.execute(
        select(JobLog)
        .where(JobLog.job_id == job_id, JobLog.status == "RUNNING")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _scheduler_loop() -> None:
    """Main loop: check all active scheduled jobs every CHECK_INTERVAL_SECONDS."""
    from ..services.backup_engine import BackupManager

    logger.info("Cron scheduler started (interval=%ds).", CHECK_INTERVAL_SECONDS)
    last_check = datetime.now(timezone.utc)

    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        now = datetime.now(timezone.utc)

        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(BackupJob).where(
                        BackupJob.is_active.is_(True),
                        BackupJob.schedule_cron.isnot(None),
                        BackupJob.schedule_cron != "",
                    )
                )
                jobs = result.scalars().all()

                for job in jobs:
                    if not await _should_run_now(job, last_check):
                        continue

                    if await _is_already_running(job.id, session):
                        logger.debug("Skipping scheduled run for '%s' — already running.", job.name)
                        continue

                    logger.info("Scheduler triggering backup for job '%s' (cron: %s).", job.name, job.schedule_cron)

                    await log_activity(
                        event_type=EventType.JOB_RUN,
                        job_name=job.name,
                        message=f"Scheduled backup triggered: {job.source_path} → {job.dest_path}",
                        job_id=job.id,
                    )

                    asyncio.create_task(
                        BackupManager.run_backup(job_id=job.id),
                        name=f"scheduled-backup-{job.id}",
                    )

        except Exception:
            logger.exception("Scheduler tick failed.")

        last_check = now


def start_scheduler() -> asyncio.Task:
    """Launch the scheduler as a background asyncio task. Idempotent."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(
            _scheduler_loop(), name="cron-scheduler"
        )
    return _scheduler_task


def stop_scheduler() -> None:
    """Cancel the running scheduler task."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
        logger.info("Cron scheduler stopped.")
