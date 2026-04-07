"""API routes for backup job CRUD and execution triggers."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import BackupJob, JobLog
from ..schemas import (
    BackupEstimate,
    JobCreate,
    JobListResponse,
    JobResponse,
    JobLogResponse,
    JobUpdate,
    RunJobRequest,
)
from ..services.activity_logger import EventType, log_activity
from ..services.backup_engine import BackupManager
from ..services.path_validator import verify_directory_access

logger = logging.getLogger("pybackup.api.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ── Helpers ───────────────────────────────────────────────────────────

def _job_to_response(job: BackupJob) -> JobResponse:
    """Convert an ORM BackupJob (with eager-loaded logs) to the response schema."""
    latest_log: JobLogResponse | None = None
    if job.logs:
        # Logs are ordered by start_time descending
        most_recent = max(job.logs, key=lambda l: l.start_time)
        latest_log = JobLogResponse.model_validate(most_recent)

    return JobResponse(
        id=job.id,
        name=job.name,
        source_path=job.source_path,
        dest_path=job.dest_path,
        schedule_cron=job.schedule_cron,
        is_active=job.is_active,
        created_at=job.created_at,
        updated_at=job.updated_at,
        latest_log=latest_log,
    )


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new backup job",
)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Create a new backup rule.  Uses multi-strategy validation so
    cloud/virtual drives (Filen.io, Dokan, WinFsp) are accepted.
    """
    src_result = verify_directory_access(payload.source_path)
    if not src_result.accessible:
        error_map = {
            "path_found_access_denied": f"Source drive found but access denied: {payload.source_path}",
            "drive_exists_path_inaccessible": f"Source drive exists but path is not accessible: {payload.source_path}",
            "unc_share_exists_path_inaccessible": f"Network share reachable but path is not accessible: {payload.source_path}",
        }
        detail = error_map.get(
            src_result.error or "",
            f"Source path does not exist or is not accessible: {payload.source_path}",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    dst_result = verify_directory_access(payload.dest_path)
    if not dst_result.accessible:
        error_map = {
            "path_found_access_denied": f"Destination drive found but access denied: {payload.dest_path}",
            "drive_exists_path_inaccessible": f"Destination drive exists but path is not accessible: {payload.dest_path}",
            "unc_share_exists_path_inaccessible": f"Network share reachable but path is not accessible: {payload.dest_path}",
        }
        detail = error_map.get(
            dst_result.error or "",
            f"Destination path does not exist or is not accessible: {payload.dest_path}",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    job = BackupJob(
        name=payload.name,
        source_path=payload.source_path,
        dest_path=payload.dest_path,
        schedule_cron=payload.schedule_cron,
        is_active=payload.is_active,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Activity log: job created
    await log_activity(
        event_type=EventType.JOB_CREATED,
        job_name=job.name,
        message=f"Backup job created: {job.source_path} → {job.dest_path}",
        job_id=job.id,
        session=db,
    )

    return _job_to_response(job)


@router.get(
    "",
    response_model=JobListResponse,
    summary="List all backup jobs",
)
async def list_jobs(
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    """Return all jobs, each decorated with the latest log entry."""
    result = await db.execute(
        select(BackupJob).order_by(BackupJob.created_at.desc())
    )
    jobs = result.scalars().all()
    total = len(jobs)

    return JobListResponse(
        jobs=[_job_to_response(j) for j in jobs],
        total=total,
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get a single backup job",
)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    job = await db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.patch(
    "/{job_id}",
    response_model=JobResponse,
    summary="Update a backup job",
)
async def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    job = await db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "source_path" in update_data:
        src_result = verify_directory_access(update_data["source_path"])
        if not src_result.accessible:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source path is not accessible: {update_data['source_path']}",
            )

    if "dest_path" in update_data:
        dst_result = verify_directory_access(update_data["dest_path"])
        if not dst_result.accessible:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destination path is not accessible: {update_data['dest_path']}",
            )

    for field_name, value in update_data.items():
        setattr(job, field_name, value)

    await db.flush()
    await db.refresh(job)
    return _job_to_response(job)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a backup job",
)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    job = await db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Activity log: job deleted (capture name before deletion)
    job_name = job.name
    await db.delete(job)

    await log_activity(
        event_type=EventType.JOB_DELETED,
        job_name=job_name,
        message=f"Backup job deleted: {job.source_path} → {job.dest_path}",
        job_id=None,  # job is being deleted, no FK reference
        session=db,
    )


@router.post(
    "/{job_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger an immediate backup run",
)
async def run_job(
    job_id: uuid.UUID,
    body: RunJobRequest | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Kick off the backup in a background task so the API returns immediately.
    """
    job = await db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    params = body or RunJobRequest()

    # Activity log: job execution triggered
    event = EventType.JOB_DRY_RUN if params.dry_run else EventType.JOB_RUN
    mode = "dry-run" if params.dry_run else "live"
    await log_activity(
        event_type=event,
        job_name=job.name,
        message=f"Backup job triggered ({mode}): {job.source_path} → {job.dest_path}",
        job_id=job_id,
        session=db,
    )

    background_tasks.add_task(
        BackupManager.run_backup,
        job_id=job_id,
        dry_run=params.dry_run,
        force_system_drive=params.force_system_drive,
        verify_after_copy=params.verify_after_copy,
    )

    return {"message": f"Backup job '{job.name}' queued ({mode})."}


@router.get(
    "/{job_id}/estimate",
    response_model=BackupEstimate,
    summary="Estimate backup size and time without copying",
)
async def estimate_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> BackupEstimate:
    """
    Run a read-only scan of the source tree and compare against the
    destination to estimate what would be copied.
    """
    job = await db.get(BackupJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        result = await BackupManager.estimate_backup(job_id)
        return BackupEstimate(**result)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Estimation failed: {exc}",
        )


@router.get(
    "/{job_id}/logs",
    response_model=list[JobLogResponse],
    summary="Get execution logs for a job",
)
async def get_job_logs(
    job_id: uuid.UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[JobLogResponse]:
    result = await db.execute(
        select(JobLog)
        .where(JobLog.job_id == job_id)
        .order_by(JobLog.start_time.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [JobLogResponse.model_validate(log) for log in logs]
