"""API routes for activity log retrieval and management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import ActivityLog
from ..schemas import ActivityLogListResponse, ActivityLogResponse
from ..services.activity_logger import cleanup_old_activity_logs

logger = logging.getLogger("pybackup.api.activity")

router = APIRouter(prefix="/api/activity-logs", tags=["activity-logs"])


def _build_activity_filters(
    stmt,
    *,
    job_name: Optional[str] = None,
    event_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Apply optional filters to an ActivityLog query."""
    if job_name:
        stmt = stmt.where(ActivityLog.job_name.ilike(f"%{job_name}%"))
    if event_type:
        stmt = stmt.where(ActivityLog.event_type == event_type)
    if date_from:
        try:
            dt = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            stmt = stmt.where(ActivityLog.timestamp >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.fromisoformat(date_to).replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            stmt = stmt.where(ActivityLog.timestamp <= dt)
        except ValueError:
            pass
    return stmt


@router.get(
    "",
    response_model=ActivityLogListResponse,
    summary="List activity log entries",
)
async def list_activity_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    job_name: Optional[str] = Query(default=None, description="Filter by job name (partial match)"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    date_from: Optional[str] = Query(default=None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(default=None, description="Filter to date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> ActivityLogListResponse:
    """Return recent activity log entries, newest first, with optional filters."""
    # Base count query
    count_stmt = select(func.count()).select_from(ActivityLog)
    count_stmt = _build_activity_filters(
        count_stmt, job_name=job_name, event_type=event_type,
        date_from=date_from, date_to=date_to,
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Data query
    data_stmt = (
        select(ActivityLog)
        .order_by(ActivityLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    data_stmt = _build_activity_filters(
        data_stmt, job_name=job_name, event_type=event_type,
        date_from=date_from, date_to=date_to,
    )
    result = await db.execute(data_stmt)
    logs = result.scalars().all()

    return ActivityLogListResponse(
        logs=[ActivityLogResponse.model_validate(log) for log in logs],
        total=total,
    )


@router.get(
    "/job-names",
    summary="List distinct job names from activity logs",
)
async def list_job_names(
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """Return unique job names for the filter dropdown."""
    result = await db.execute(
        select(ActivityLog.job_name)
        .distinct()
        .order_by(ActivityLog.job_name)
    )
    return [row[0] for row in result.all()]


@router.delete(
    "/cleanup",
    summary="Remove activity logs older than 14 days",
)
async def cleanup_logs() -> dict[str, int]:
    """Manually trigger cleanup of old activity log entries."""
    deleted = await cleanup_old_activity_logs()
    return {"deleted": deleted}
